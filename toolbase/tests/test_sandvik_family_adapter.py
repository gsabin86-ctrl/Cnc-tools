from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sandvik_family_adapter.py"
SPEC = importlib.util.spec_from_file_location("sandvik_family_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


class SandvikFamilyAdapterTests(unittest.TestCase):
    def candidate(self, material_id: str = "5730446", title: str = "DCGT 11 T3 01-UM    1105"):
        return {
            "Title": title,
            "Description": "CoroTurn® 107, insert for turning.",
            "Type": "ordcode",
            "ID": material_id,
            "LCS": "30",
            "ItemType": "iso",
        }

    def response(self, material_id: int = 5730446, order_code: str = "DCGT 11 T3 01-UM    1105"):
        return {
            "product": {
                "MaterialID": material_id,
                "ORDCODE": order_code,
                "PRODFAM": "CoroTurn 107",
                "InsertDesignation": "DCGT",
                "GTCId": "INSI",
                "LCS": "30",
                "TIBPAvailability": "Available",
                "CBMD": "UM",
                "GRADE": "1105",
                "InsertSizeCode": "11T301",
                "TMC1ISO": ["M", "S"],
                "ReplacementProductId": "8432106",
                "CuttingOperations": [{"materials": [{"material": "S"}]}],
            }
        }

    def test_collapse_order_code_preserves_segments_and_removes_display_padding(self):
        self.assertEqual(
            adapter.collapse_order_code("DCGT 11 T3 01-UM    1105"),
            "DCGT 11 T3 01-UM 1105",
        )
        self.assertEqual(
            adapter.normalized_order_code("DCGT 11 T3 01-UM    1105"),
            "DCGT11T301UM1105",
        )

    def test_family_membership_requires_exact_identity_and_taxonomy(self):
        self.assertEqual(adapter.family_membership_errors(self.candidate(), self.response()), [])
        wrong = self.response()
        wrong["product"]["PRODFAM"] = "Another family"
        wrong["product"]["MaterialID"] = 999
        errors = adapter.family_membership_errors(self.candidate(), wrong)
        self.assertTrue(any("material ID mismatch" in item for item in errors))
        self.assertTrue(any("product family mismatch" in item for item in errors))

    def test_discovery_requires_two_identical_below_limit_results(self):
        payload = [self.candidate()]
        encoded = json.dumps(payload).encode("utf-8")
        with mock.patch.object(adapter, "fetch_json_bytes", side_effect=[(encoded, payload), (encoded, payload)]):
            result = adapter.discover("DCGT", limits=(10, 20))
        self.assertEqual(result["verification"]["suggestion_count"], 1)
        self.assertEqual(result["verification"]["candidate_material_id_count"], 1)
        self.assertTrue(result["verification"]["same_candidate_identities"])

    def test_discovery_allows_iso_and_ansi_aliases_for_one_material_id(self):
        payload = [
            self.candidate(),
            {**self.candidate(), "Title": "DCGT 3(2.5)03-UM 1105", "ItemType": "ansi"},
        ]
        encoded = json.dumps(payload).encode("utf-8")
        with mock.patch.object(adapter, "fetch_json_bytes", side_effect=[(encoded, payload), (encoded, payload)]):
            result = adapter.discover("DCGT", limits=(10, 20))
        self.assertEqual(result["verification"]["suggestion_count"], 2)
        self.assertEqual(result["verification"]["candidate_material_id_count"], 1)

    def test_discovery_rejects_a_result_that_reaches_the_limit(self):
        payload = [self.candidate(str(index), f"DCGT 11 T3 0{index}-UM 1105") for index in range(2)]
        encoded = json.dumps(payload).encode("utf-8")
        with mock.patch.object(adapter, "fetch_json_bytes", side_effect=[(encoded, payload), (encoded, payload)]):
            with self.assertRaisesRegex(ValueError, "reached an autocomplete limit"):
                adapter.discover("DCGT", limits=(2, 4))

    def test_summary_counts_lifecycle_replacement_and_cutting_rows(self):
        snapshot = {
            "discovery": {"verification": {"suggestion_count": 2, "candidate_material_id_count": 1}},
            "included_material_ids": ["5730446"],
            "excluded_candidates": {},
            "products": {
                "5730446": {
                    "response": self.response(),
                }
            },
        }
        summary = adapter.summarize(snapshot)
        self.assertEqual(summary["included_count"], 1)
        self.assertEqual(summary["products_with_replacements"], 1)
        self.assertEqual(summary["cutting_profile_rows"], 1)
        self.assertEqual(summary["material_groups"], ["M", "S"])
        self.assertEqual(summary["lifecycle_codes"], {"30": 1})


if __name__ == "__main__":
    unittest.main()
