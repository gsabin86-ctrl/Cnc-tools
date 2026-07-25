from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "iscar_scirl22_family_import.py"
SNAPSHOT = ROOT / "data" / "source_snapshots" / "iscar-scir-l-22-br-bl-bra-bla-family-2026-07-24.json"
TOOLS = ROOT / "data" / "tools.jsonl"
CANONICAL_IMPORT = ROOT / "data" / "manufacturer_imports" / "iscar-scirl22-family-2026-07.json"


def load_importer():
    spec = importlib.util.spec_from_file_location("iscar_scirl22_family_import", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class IscarScirl22FamilyImportTests(unittest.TestCase):
    def test_snapshot_has_exact_unique_family_identities_and_seed_product(self) -> None:
        importer = load_importer()
        documents = importer.family_documents(SNAPSHOT)
        self.assertEqual(len(documents), 16)
        self.assertEqual(len({doc["ProductName_s"] for doc in documents}), 16)
        self.assertEqual(len({doc["ManufacturerNo_s"] for doc in documents}), 16)
        self.assertEqual(len({doc["product_id_i"] for doc in documents}), 16)
        self.assertIn(1953152, {doc["product_id_i"] for doc in documents})

    def test_seed_row_preserves_exact_identity_zero_radius_and_materials(self) -> None:
        importer = load_importer()
        documents = importer.family_documents(SNAPSHOT)
        zero = next(doc for doc in documents if doc["F_SIG_2_s"] == "0″")
        row = importer.seed_row(zero, importer.slug_id(zero["ProductName_s"]))
        self.assertEqual(row["part_number"], zero["ProductName_s"])
        self.assertEqual(row["grade"], zero["F_SIG_15_s"])
        self.assertEqual(row["specs"]["manufacturer_material_number"], zero["ManufacturerNo_s"])
        self.assertEqual(row["specs"]["webshop_product_id"], zero["product_id_i"])
        self.assertEqual(row["specs"]["corner_radius_in"], 0.0)
        self.assertEqual(row["specs"]["corner_radius_mm"], 0.0)
        self.assertTrue(row["specs"]["workpiece_material_groups"])
        self.assertNotIn("material_groups", row["specs"])

    def test_generate_upserts_direct_seed_rows_idempotently(self) -> None:
        importer = load_importer()
        unrelated = {
            "json_id": "unrelated-tool",
            "manufacturer": "Other",
            "component_type": "insert",
            "description": "preserve me",
            "specs": {},
        }
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            data = repo / "toolbase" / "data"
            snapshots = data / "source_snapshots"
            snapshots.mkdir(parents=True)
            snapshot_copy = snapshots / SNAPSHOT.name
            shutil.copyfile(SNAPSHOT, snapshot_copy)
            (data / "tools.jsonl").write_text(
                json.dumps(unrelated, separators=(",", ":")) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            (data / "manifest.json").write_text(
                json.dumps({"counts": {"tools": 1}}, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            first = importer.generate(repo, snapshot_copy)
            first_bytes = (data / "tools.jsonl").read_bytes()
            first_import = (repo / importer.IMPORT_REL).read_bytes()
            second = importer.generate(repo, snapshot_copy)
            second_bytes = (data / "tools.jsonl").read_bytes()
            second_import = (repo / importer.IMPORT_REL).read_bytes()

            self.assertEqual(first["new_seed_rows_added"], 16)
            self.assertEqual(first["seed_rows_updated"], 0)
            self.assertEqual(first["material_recommendations"], 72)
            self.assertEqual(second["new_seed_rows_added"], 0)
            self.assertEqual(second["seed_rows_updated"], 16)
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(first_import, second_import)
            rows = load_jsonl(data / "tools.jsonl")
            self.assertEqual(len(rows), 17)
            self.assertEqual(rows[0], unrelated)
            self.assertFalse((repo / "toolbase" / "proposals").exists())
            self.assertFalse((repo / "toolbase" / "reviews").exists())
            manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["tools"], 17)

    def test_committed_canonical_import_has_exact_material_scope(self) -> None:
        payload = json.loads(CANONICAL_IMPORT.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["manufacturer"], "Iscar")
        self.assertEqual(len(payload["rows"]), 16)
        recommendations = [
            item
            for row in payload["rows"]
            for item in row["material_recommendations"]
        ]
        self.assertEqual(len(recommendations), 72)
        self.assertFalse(any(row["cutting_profiles"] for row in payload["rows"]))
        self.assertTrue(
            all(
                item["suitability"] == "recommended"
                and item["verification_status"] == "manufacturer_verified"
                and item["grade_code"] in {"IC07", "IC1007", "IC1008"}
                for item in recommendations
            )
        )

    def test_committed_seed_contains_all_16_exact_products(self) -> None:
        importer = load_importer()
        documents = importer.family_documents(SNAPSHOT)
        expected = {
            (str(doc["ProductName_s"]), str(doc["ManufacturerNo_s"]), int(doc["product_id_i"]))
            for doc in documents
        }
        actual = {
            (
                str(row["specs"]["manufacturer_order_code"]),
                str(row["specs"]["manufacturer_material_number"]),
                int(row["specs"]["webshop_product_id"]),
            )
            for row in load_jsonl(TOOLS)
            if row.get("manufacturer") == "Iscar"
            and (row.get("specs") or {}).get("product_family") == importer.FAMILY_NAME
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
