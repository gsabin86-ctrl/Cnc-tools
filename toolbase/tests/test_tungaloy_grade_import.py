from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tungaloy_grade_import.py"
SNAPSHOT = ROOT / "data" / "source_snapshots" / "tungaloy-sh7025-grade-2026-07-24.json"
HTML = ROOT / "data" / "source_snapshots" / "tungaloy-sh7025-grade-page-2026-07-24.html"
CANONICAL_IMPORT = (
    ROOT / "data" / "manufacturer_imports" / "tungaloy-sh7025-grade-baselines-2026-07.json"
)


def load_importer():
    spec = importlib.util.spec_from_file_location("tungaloy_grade_import", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TungaloyGradeImportTests(unittest.TestCase):
    def test_saved_page_hash_and_parser_match_normalized_snapshot(self) -> None:
        importer = load_importer()
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(HTML.read_bytes()).hexdigest(), snapshot["raw_page_sha256"])
        parsed = importer.validate_snapshot_against_html(
            snapshot, HTML.read_text(encoding="utf-8")
        )
        self.assertEqual(
            parsed["standard_cutting_conditions"],
            snapshot["standard_cutting_conditions"],
        )
        self.assertEqual(
            parsed["standard_cutting_conditions"]["P"]["vc_m_min"],
            {"min": 10.0, "max": 200.0},
        )

    def test_strict_feed_selection_uses_exact_breaker_and_radius_band(self) -> None:
        importer = load_importer()
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        conditions = snapshot["standard_cutting_conditions"]["P"]
        self.assertEqual(importer.feed_range("02", "JS", conditions)[:2], (0.05, 0.2))
        self.assertEqual(importer.feed_range("02", "JP", conditions)[:2], (None, None))
        self.assertEqual(importer.feed_range("04", "JS", conditions)[:2], (None, None))
        self.assertEqual(importer.feed_range("02", "01", conditions)[:2], (None, None))

    def test_canonical_import_has_exact_scope_and_values(self) -> None:
        payload = json.loads(CANONICAL_IMPORT.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["manufacturer"], "Tungaloy")
        self.assertEqual(len(payload["rows"]), 34)
        self.assertEqual(
            sum(len(row["material_recommendations"]) for row in payload["rows"]),
            68,
        )
        profiles = [
            profile
            for row in payload["rows"]
            for profile in row["cutting_profiles"]
        ]
        self.assertEqual(len(profiles), 8)
        self.assertEqual(
            {row["tool_id"] for row in payload["rows"] if row["cutting_profiles"]},
            {
                "DCGT11T302FN-JS",
                "DCGT11T302M-JS",
                "DCGT11T302MF-JS",
                "DCGT11T302N-JS",
            },
        )
        for profile in profiles:
            self.assertEqual(profile["source_grade"], "SH7025")
            self.assertEqual(profile["coolant_condition"], "unknown")
            self.assertEqual(
                (
                    profile["surface_speed_min"],
                    profile["surface_speed_max"],
                    profile["feed_min"],
                    profile["feed_max"],
                    profile["depth_of_cut_min"],
                    profile["depth_of_cut_max"],
                ),
                (10, 200, 0.05, 0.2, 0.5, 3),
            )
            self.assertEqual(profile["verification_status"], "manufacturer_verified")
            self.assertNotIn("reviewer", profile)
            self.assertNotIn("reviewed_at", profile)

    def test_generation_is_byte_deterministic(self) -> None:
        importer = load_importer()
        original_output = importer.BATCHES["sh7025"]["output"]
        try:
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "tungaloy.json"
                importer.BATCHES["sh7025"]["output"] = str(output)
                first = importer.generate("sh7025", "2026-07-24").read_bytes()
                second = importer.generate("sh7025", "2026-07-24").read_bytes()
                self.assertEqual(first, second)
                self.assertEqual(first, CANONICAL_IMPORT.read_bytes())
        finally:
            importer.BATCHES["sh7025"]["output"] = original_output


if __name__ == "__main__":
    unittest.main()
