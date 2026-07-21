from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build.py"
PROPOSAL_VALIDATOR = ROOT / "scripts" / "validate_cutting_proposal.py"
REVIEWED_IMPORTER = ROOT / "scripts" / "import_reviewed_proposal.py"
TOPSWISS_PROPOSAL = ROOT / "proposals" / "kennametal-topswiss-pilot.json"
TOPSWISS_LEDGER = ROOT / "reviews" / "kennametal-topswiss-pilot.decisions.json"
TOPSWISS_IMPORT = ROOT / "data" / "reviewed_imports" / "kennametal-topswiss-pilot.json"
ECAS20_SHOP_INPUT = ROOT / "data" / "shop_inputs" / "star-ecas20-stations.json"
DATA_DIR = ROOT / "data"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PipelineTests(unittest.TestCase):
    def build(self, directory: Path) -> tuple[Path, Path, Path]:
        db_path = directory / "toolbase.sqlite"
        json_path = directory / "catalog.json"
        published_path = directory / "published.sqlite"
        subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT),
                "--data-dir",
                str(DATA_DIR),
                "--db-out",
                str(db_path),
                "--json-out",
                str(json_path),
                "--published-db-out",
                str(published_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return db_path, json_path, published_path

    def test_build_preserves_tools_and_enforces_domain_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, published_path = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0],
                "3.3.0",
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM tools").fetchone()[0], 1222)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM manufacturers WHERE name='Horn'").fetchone()[0], 0)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM compatibility_claims WHERE relationship='compatible_with_machine' AND suppressed=0"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM compatibility_claims WHERE evidence_status='catalog_claim' AND source_id IS NOT NULL"
                ).fetchone()[0],
                17,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(DISTINCT tool_id) FROM tool_material_recommendations").fetchone()[0],
                203,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM tool_material_recommendations r
                    WHERE NOT EXISTS (
                      SELECT 1 FROM tool_material_recommendation_sources rs
                      WHERE rs.recommendation_id=r.id
                    )
                    """
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM compatibility_claims c
                    WHERE NOT EXISTS (
                      SELECT 1 FROM compatibility_claim_sources cs WHERE cs.claim_id=c.id
                    )
                    """
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(DISTINCT claim_id) FROM compatibility_claim_sources WHERE evidence_role='primary_source'"
                ).fetchone()[0],
                59,
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM usable_cutting_data").fetchone()[0], 12)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_batches").fetchone()[0], 1)
            cutting_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(cutting_data_profiles)")
            }
            self.assertIn("surface_speed_start", cutting_columns)
            fact_columns = {row[1] for row in connection.execute("PRAGMA table_info(facts)")}
            material_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(tool_material_recommendations)")
            }
            for column in {
                "verification_status", "source_page_ref", "source_table_ref", "source_raw_text",
                "extraction_method", "review_batch_id", "reviewer", "reviewed_at",
            }:
                self.assertIn(column, fact_columns)
                self.assertIn(column, material_columns)
            connection.close()

            proposal_result = subprocess.run(
                [
                    sys.executable,
                    str(PROPOSAL_VALIDATOR),
                    "--proposal",
                    str(TOPSWISS_PROPOSAL),
                    "--db",
                    str(db_path),
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            proposal_audit = json.loads(proposal_result.stdout)
            self.assertTrue(proposal_audit["valid"])
            self.assertEqual(proposal_audit["rows"], 12)
            self.assertTrue(proposal_audit["import_allowed"])

            projection = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(projection["tools"]), 1222)
            self.assertEqual(projection["meta"]["quality"]["suppressed_direct_machine_claims"], 172)
            self.assertEqual(len(projection["review_batches"]), 1)
            self.assertTrue(any(fact["source_ids"] for tool in projection["tools"] for fact in tool["facts"]))
            self.assertTrue(all("source_refs" in relationship for relationship in projection["relationships"]))
            search_index = json.loads(json_path.with_name("catalog-index.json").read_text(encoding="utf-8"))
            details = json.loads(json_path.with_name("catalog-details.json").read_text(encoding="utf-8"))
            self.assertEqual(len(search_index["tools"]), 1222)
            self.assertEqual(len(details["tools_by_id"]), 1222)
            self.assertEqual(search_index["meta"]["build_hash"], details["meta"]["build_hash"])
            self.assertTrue(all("verification_status" in tool for tool in search_index["tools"]))
            self.assertTrue(any(tool["geometry_shape"] for tool in search_index["tools"] if tool["component_type"] == "insert"))
            self.assertEqual(db_path.read_bytes(), published_path.read_bytes())

    def test_shop_confirmed_ecas20_stations_are_typed_and_auditable(self) -> None:
        square_stations = {1, 2, 3, 4, 11, 12}
        round_stations = {16, 17, 18, 19}
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            stations = connection.execute(
                """
                SELECT CAST(f.value_number AS INTEGER), i.interface_type, i.shape, i.size_mm,
                       t.evidence_status, i.evidence_status
                FROM tools t
                JOIN facts f ON f.tool_id=t.id AND f.fact_key='station_number'
                JOIN interfaces i ON i.tool_id=t.id AND i.interface_role='accepts'
                WHERE t.component_type='station'
                ORDER BY f.value_number
                """
            ).fetchall()
            self.assertEqual(len(stations), 10)
            self.assertEqual(
                {number for number, interface, shape, size, _, _ in stations if interface == "square_shank"},
                square_stations,
            )
            self.assertEqual(
                {number for number, interface, shape, size, _, _ in stations if interface == "round_shank"},
                round_stations,
            )
            self.assertTrue(
                all(
                    shape == ("square" if number in square_stations else "round")
                    and size == (16 if number in square_stations else 22)
                    and tool_evidence == "shop_verified"
                    and interface_evidence == "shop_verified"
                    for number, interface, shape, size, tool_evidence, interface_evidence in stations
                )
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM compatibility_claims c
                    WHERE c.relationship='station_of'
                      AND c.object_tool_id='ECAS20_GANG_BLOCK'
                      AND c.evidence_status='shop_verified'
                      AND c.review_status='accepted'
                      AND c.confidence=1.0
                      AND EXISTS (
                        SELECT 1 FROM compatibility_claim_sources s
                        WHERE s.claim_id=c.id AND s.evidence_role='primary_source'
                      )
                    """
                ).fetchone()[0],
                10,
            )
            square_tools = {
                "DGTR 16B-2D25SH": "accepts_holder",
                "KM16NCM10400": "accepts_shank",
                "KM16RCM1616100HPC": "accepts_shank",
                "QSM16-N1616": "accepts_shank",
            }
            round_tools = {
                "B105.0022.02": "accepts_holder",
                "B110.0022.02": "accepts_holder",
            }
            fit_claims = connection.execute(
                """
                SELECT CAST(f.value_number AS INTEGER), c.relationship, c.object_tool_id,
                       c.evidence_status, c.review_status, c.confidence,
                       EXISTS (
                         SELECT 1 FROM compatibility_claim_sources s
                         WHERE s.claim_id=c.id AND s.evidence_role='primary_source'
                       ),
                       EXISTS (
                         SELECT 1 FROM compatibility_claim_sources s
                         WHERE s.claim_id=c.id AND s.evidence_role='derivation_input'
                       )
                FROM compatibility_claims c
                JOIN facts f ON f.tool_id=c.subject_tool_id AND f.fact_key='station_number'
                WHERE c.relationship IN ('accepts_holder', 'accepts_shank')
                ORDER BY f.value_number, c.object_tool_id
                """
            ).fetchall()
            self.assertEqual(len(fit_claims), 32)
            for number, relationship, tool_id, evidence, review, confidence, primary, derivation in fit_claims:
                expected = square_tools if number in square_stations else round_tools
                self.assertIn(tool_id, expected)
                self.assertEqual(relationship, expected[tool_id])
                self.assertEqual((evidence, review, confidence), ("shop_verified", "accepted", 1.0))
                self.assertEqual((primary, derivation), (1, 1))
            for number in square_stations:
                self.assertEqual(
                    {tool_id for station, _, tool_id, *_ in fit_claims if station == number},
                    set(square_tools),
                )
            for number in round_stations:
                self.assertEqual(
                    {tool_id for station, _, tool_id, *_ in fit_claims if station == number},
                    set(round_tools),
                )
            self.assertNotIn("B110.0016.02", {row[2] for row in fit_claims})

            machine_interfaces = connection.execute(
                """
                SELECT tool_id, interface_type, shape, size_mm, evidence_status, source_id
                FROM interfaces
                WHERE interface_role='provides'
                  AND interface_type IN ('square_shank', 'round_shank')
                ORDER BY tool_id
                """
            ).fetchall()
            self.assertEqual(len(machine_interfaces), 6)
            self.assertEqual(
                {
                    tool_id: (interface, shape, size)
                    for tool_id, interface, shape, size, _, _ in machine_interfaces
                },
                {
                    **{tool_id: ("square_shank", "square", 16) for tool_id in square_tools},
                    **{tool_id: ("round_shank", "round", 22) for tool_id in round_tools},
                },
            )
            self.assertTrue(
                all(
                    evidence in {"imported", "catalog_claim", "manufacturer_claim"} and source_id
                    for _, _, _, _, evidence, source_id in machine_interfaces
                )
            )
            batch = connection.execute(
                "SELECT input_sha256, recorded_by, row_count FROM shop_input_batches"
            ).fetchone()
            self.assertEqual(batch, (sha256(ECAS20_SHOP_INPUT), "Greg", 10))
            connection.close()

            projection = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(projection["shop_input_batches"]), 1)
            projected_stations = [
                tool for tool in projection["tools"] if tool["component_type"] == "station"
            ]
            self.assertEqual(len(projected_stations), 10)
            self.assertTrue(all(tool["evidence_status"] == "shop_verified" for tool in projected_stations))
            self.assertTrue(all(tool["verification_status"] == "shop_verified" for tool in projected_stations))
            review_queue = json.loads((Path(temp) / "ecas20-review-queue.json").read_text(encoding="utf-8"))
            self.assertEqual(review_queue["counts"]["stations"], 10)
            self.assertEqual(review_queue["counts"]["station_fit_claims"], 32)
            self.assertGreater(review_queue["counts"]["needs_review"], 0)
            self.assertTrue(all("next_action" in item for item in review_queue["items"]))

    def test_reviewed_topswiss_import_is_exact_and_auditable(self) -> None:
        expected_speeds = {
            "CCET060200RPPS-KN10S": ("N", "N1", 198, 488, 616),
            "CCET060201RPPS-KN10S": ("N", "N4", 107, 259, 366),
            "CCET09T302LPPS-KTP25S": ("P", "P2", 122, 204, 312),
            "CCGT09T304MFFS-KCS25S": ("M", "M1", 59, 101, 149),
            "CCGT21502MRPPS-KCP20S": ("P", "P0/P1", 50, 165, 274),
            "CCGT32505MRPPS-KCM25S": ("M", "M1", 40, 59, 101),
            "CCMT060202FWS-KTP25S": ("P", "P2", 122, 204, 312),
            "CCMT060204FPS-KTP25S": ("P", "P0/P1", 122, 216, 351),
            "CCMT09T304MWS-KTP25S": ("P", "P3", 122, 189, 274),
            "DCGT070202MRPPS-KCP20S": ("P", "P3", 50, 110, 165),
            "DCGT11T301MRPPS-KCS25S": ("M", "M1", 59, 101, 149),
            "DCGT11T304MLFS-KCM25S": ("M", "M1", 40, 59, 101),
        }
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path, json_path, _ = self.build(temp_path)
            connection = sqlite3.connect(db_path)
            rows = connection.execute(
                """
                SELECT tool_id, iso_material_group, material_subgroup,
                       surface_speed_min, surface_speed_start, surface_speed_max
                FROM usable_cutting_data ORDER BY tool_id
                """
            ).fetchall()
            actual_speeds = {
                tool_id: (group, subgroup, minimum, start, maximum)
                for tool_id, group, subgroup, minimum, start, maximum in rows
            }
            self.assertEqual(actual_speeds, expected_speeds)
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM usable_cutting_data
                    WHERE source_id IS NOT NULL
                      AND source_page_ref IS NOT NULL
                      AND source_table_ref IS NOT NULL
                      AND source_raw_text IS NOT NULL
                      AND reviewer='Greg' AND reviewed_at='2026-07-21'
                    """
                ).fetchone()[0],
                12,
            )
            reviewed_tools = tuple(expected_speeds)
            placeholders = ",".join("?" for _ in reviewed_tools)
            lifecycle_counts = dict(
                connection.execute(
                    f"SELECT lifecycle_status, COUNT(*) FROM tools WHERE id IN ({placeholders}) GROUP BY lifecycle_status",
                    reviewed_tools,
                ).fetchall()
            )
            self.assertEqual(lifecycle_counts, {"discontinued": 4, "unknown": 8})
            direction_counts = dict(
                connection.execute(
                    f"""
                    SELECT value_text, COUNT(*) FROM facts
                    WHERE tool_id IN ({placeholders}) AND fact_key='cutting_direction'
                    GROUP BY value_text
                    """,
                    reviewed_tools,
                ).fetchall()
            )
            self.assertEqual(direction_counts, {"Left": 1, "Neutral": 5, "Right": 6})
            self.assertEqual(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM tool_material_recommendations r
                    WHERE r.tool_id IN ({placeholders})
                      AND NOT EXISTS (
                        SELECT 1 FROM tool_material_recommendation_sources s
                        WHERE s.recommendation_id=r.id
                      )
                    """,
                    reviewed_tools,
                ).fetchone()[0],
                0,
            )
            batch = connection.execute(
                "SELECT proposal_sha256, review_ledger_sha256, catalog_sha256, row_count FROM review_batches"
            ).fetchone()
            self.assertEqual(batch[0], sha256(TOPSWISS_PROPOSAL))
            self.assertEqual(batch[1], sha256(TOPSWISS_LEDGER))
            self.assertEqual(batch[3], 12)
            self.assertEqual(len(batch[2]), 64)
            catalog_source = connection.execute(
                """
                SELECT content_sha256, document_edition, retrieved_at
                FROM sources WHERE id=(SELECT source_id FROM review_batches LIMIT 1)
                """
            ).fetchone()
            self.assertEqual(catalog_source, (batch[2], "2024 copyright edition", "2026-07-21"))
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM facts
                    WHERE verification_status IN ('catalog_verified','manufacturer_verified')
                      AND review_batch_id IS NOT NULL AND reviewer='Greg' AND reviewed_at='2026-07-21'
                    """
                ).fetchone()[0],
                122,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM tool_material_recommendations
                    WHERE verification_status='catalog_verified'
                      AND source_page_ref IS NOT NULL AND source_table_ref IS NOT NULL
                      AND source_raw_text IS NOT NULL AND review_batch_id IS NOT NULL
                    """
                ).fetchone()[0],
                12,
            )
            connection.close()

            projection = json.loads(json_path.read_text(encoding="utf-8"))
            tools = {tool["id"]: tool for tool in projection["tools"]}
            self.assertNotIn("cermet", tools["CCET060200RPPS-KN10S"]["tags"])
            self.assertIn("carbide", tools["CCET060200RPPS-KN10S"]["tags"])
            self.assertIn("cermet", tools["CCMT060202FWS-KTP25S"]["tags"])
            profile = tools["CCGT21502MRPPS-KCP20S"]["cutting_data"][0]
            self.assertEqual(profile["source_part_number"], "CCGT060201MRPPS")
            self.assertEqual(profile["source_page_ref"], "PDF pages 14, 15")
            self.assertEqual(profile["reviewer"], "Greg")

            first_import = temp_path / "first-import.json"
            second_import = temp_path / "second-import.json"
            for output in (first_import, second_import):
                subprocess.run(
                    [
                        sys.executable,
                        str(REVIEWED_IMPORTER),
                        "--db",
                        str(db_path),
                        "--out",
                        str(output),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(first_import.read_bytes(), second_import.read_bytes())
            self.assertEqual(first_import.read_bytes(), TOPSWISS_IMPORT.read_bytes())

    def test_build_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_db, first_json, _ = self.build(Path(first))
            second_db, second_json, _ = self.build(Path(second))
            self.assertEqual(sha256(first_db), sha256(second_db))
            self.assertEqual(sha256(first_json), sha256(second_json))


if __name__ == "__main__":
    unittest.main()
