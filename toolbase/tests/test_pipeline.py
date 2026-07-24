from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build.py"
TOPSWISS_PROPOSAL = ROOT / "proposals" / "kennametal-topswiss-pilot.json"
TOPSWISS_LEDGER = ROOT / "reviews" / "kennametal-topswiss-pilot.decisions.json"
SANDVIK_PROPOSAL = ROOT / "proposals" / "sandvik-corocut2-cs1225-pilot.json"
SANDVIK_LEDGER = ROOT / "reviews" / "sandvik-corocut2-cs1225-pilot.decisions.json"
SANDVIK_SNAPSHOT = ROOT / "data" / "source_snapshots" / "sandvik-corocut2-cs1225-pilot-2026-07-22.json"
SANDVIK_REMAINING_PROPOSAL = ROOT / "proposals" / "sandvik-corocut2-remaining.json"
SANDVIK_REMAINING_LEDGER = ROOT / "reviews" / "sandvik-corocut2-remaining.decisions.json"
SANDVIK_REMAINING_SNAPSHOT = ROOT / "data" / "source_snapshots" / "sandvik-corocut2-remaining-2026-07-22.json"
KENNAMETAL_7154831_PROPOSAL = ROOT / "proposals" / "kennametal-topswiss-7154831.json"
KENNAMETAL_7154831_LEDGER = ROOT / "reviews" / "kennametal-topswiss-7154831.decisions.json"
KENNAMETAL_7154831_PDF = ROOT / "data" / "source_snapshots" / "kennametal-topswiss-application-data-109435299.pdf"
KENNAMETAL_7154831_SNAPSHOT = ROOT / "data" / "source_snapshots" / "kennametal-topswiss-7154831-product-page-2026-07-22.json"
ECAS20_SHOP_INPUT = ROOT / "data" / "shop_inputs" / "star-ecas20-stations.json"
DATA_DIR = ROOT / "data"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PipelineTests(unittest.TestCase):
    def build(self, directory: Path, data_dir: Path = DATA_DIR) -> tuple[Path, Path, Path]:
        db_path = directory / "toolbase.sqlite"
        json_path = directory / "catalog.json"
        published_path = directory / "published.sqlite"
        result = subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT),
                "--data-dir",
                str(data_dir),
                "--db-out",
                str(db_path),
                "--json-out",
                str(json_path),
                "--published-db-out",
                str(published_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            self.fail(f"build failed:\n{result.stdout}\n{result.stderr}")
        return db_path, json_path, published_path

    def test_build_preserves_tools_and_enforces_domain_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, published_path = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0],
                "3.4.0",
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM tools").fetchone()[0], 1289)
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
            self.assertGreaterEqual(
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
            self.assertGreaterEqual(connection.execute("SELECT COUNT(*) FROM usable_cutting_data").fetchone()[0], 12)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM review_batches WHERE proposal_id='kennametal-topswiss-pilot-2026-07'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM review_batch_sources s
                    JOIN review_batches b ON b.id=s.review_batch_id
                    WHERE b.proposal_id='kennametal-topswiss-pilot-2026-07'
                    """
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM cutting_data_profile_sources s
                    JOIN cutting_data_profiles p ON p.id=s.profile_id
                    WHERE p.reviewer='Greg' AND p.reviewed_at='2026-07-21'
                    """
                ).fetchone()[0],
                36,
            )
            self.assertGreaterEqual(connection.execute("SELECT COUNT(*) FROM grades").fetchone()[0], 70)
            self.assertGreaterEqual(connection.execute("SELECT COUNT(*) FROM tool_grade_options").fetchone()[0], 1348)
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
                "extraction_method", "review_batch_id", "reviewer", "reviewed_at", "is_current",
            }:
                self.assertIn(column, fact_columns)
                self.assertIn(column, material_columns)
            connection.close()

            projection = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(projection["tools"]), 1289)
            self.assertEqual(projection["meta"]["quality"]["suppressed_direct_machine_claims"], 172)
            review_proposals = {batch["proposal_id"] for batch in projection["review_batches"]}
            self.assertIn("kennametal-topswiss-pilot-2026-07", review_proposals)
            self.assertIn("sandvik-corocut2-cs1225-pilot-2026-07", review_proposals)
            self.assertIn("sandvik-corocut2-remaining-2026-07", review_proposals)
            self.assertTrue(any(fact["source_ids"] for tool in projection["tools"] for fact in tool["facts"]))
            self.assertTrue(all("source_refs" in relationship for relationship in projection["relationships"]))
            search_index = json.loads(json_path.with_name("catalog-index.json").read_text(encoding="utf-8"))
            details = json.loads(json_path.with_name("catalog-details.json").read_text(encoding="utf-8"))
            self.assertEqual(len(search_index["tools"]), 1289)
            self.assertEqual(len(details["tools_by_id"]), 1289)
            self.assertEqual(search_index["meta"]["build_hash"], details["meta"]["build_hash"])
            self.assertTrue(all("verification_status" in tool for tool in search_index["tools"]))
            self.assertTrue(all("review_status" in tool for tool in search_index["tools"]))
            self.assertTrue(all("grade_codes" in tool for tool in search_index["tools"]))
            self.assertTrue(all("corner_radius_mm" in tool for tool in search_index["tools"]))
            index_by_id = {tool["id"]: tool for tool in search_index["tools"]}
            self.assertEqual(index_by_id["DCGT-11-T3-01-UM-1105"]["corner_radius_mm"], 0.1)
            self.assertEqual(index_by_id["DGN 2002J IC908"]["corner_radius_mm"], 0.2)
            self.assertTrue(any(tool["corner_radius_mm"] is None for tool in search_index["tools"]))
            self.assertTrue(any(tool["geometry_shape"] for tool in search_index["tools"] if tool["component_type"] == "insert"))
            sandvik_t3 = details["tools_by_id"]["TCMX-16-T3-08-WF"]["geometry_display"]
            self.assertIsNotNone(sandvik_t3)
            self.assertEqual(sandvik_t3["designation"], "TCMX16T308")
            self.assertEqual(sandvik_t3["shape_name"], "Triangle")
            self.assertEqual(sandvik_t3["clearance"], "7 degrees")
            sandvik_coroturn = [
                tool
                for tool in details["tools_by_id"].values()
                if tool["manufacturer"] == "Sandvik Coromant"
                and tool["family"] == "CoroTurn 107 Inserts"
            ]
            self.assertEqual(len(sandvik_coroturn), 120)
            self.assertTrue(all(tool["geometry_display"] for tool in sandvik_coroturn))
            material_tools = [tool for tool in search_index["tools"] if tool["material_groups"]]
            cutting_tools = [tool for tool in search_index["tools"] if tool["has_cutting_data"]]
            self.assertGreaterEqual(len(material_tools), 12)
            self.assertGreaterEqual(len(cutting_tools), 12)
            self.assertTrue(all(tool["review_status"] == "verified" for tool in material_tools + cutting_tools))
            self.assertEqual(
                sum(bool(tool["unreviewed_material_claims"]) for tool in details["tools_by_id"].values()),
                191,
            )
            self.assertEqual(db_path.read_bytes(), published_path.read_bytes())

    def test_source_units_are_human_readable(self) -> None:
        app = (ROOT.parent / "docs" / "v3" / "app.js").read_text(encoding="utf-8")
        self.assertIn("m_per_min: 'm/min'", app)
        self.assertIn("mm_per_rev: 'mm/rev'", app)
        self.assertIn("sourceUnitLabel(unit)", app)
        self.assertIn("const display = a.value != null ? a : b", app)
        self.assertIn("${display.unit}", app)
        self.assertIn("profile.coolant_condition !== 'unknown'", app)

    def test_corner_radius_normalization_rejects_nonfinite_and_malformed_values(self) -> None:
        scripts_path = str(ROOT / "scripts")
        sys.path.insert(0, scripts_path)
        try:
            spec = importlib.util.spec_from_file_location("toolbase_build_radius_test", BUILD_SCRIPT)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            build_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build_module)
        finally:
            sys.path.remove(scripts_path)

        def geometry(value: object, unit: object) -> dict[str, object]:
            return {
                "dimensions": [
                    {
                        "label": "Corner radius",
                        "value": value,
                        "unit": unit,
                        "source_ids": ["source-test"],
                    }
                ]
            }

        cases = [
            (geometry(0.2, "mm"), 0.2),
            (geometry(0, "mm"), 0.0),
            (geometry(True, "mm"), None),
            (geometry(-0.2, "mm"), None),
            (geometry(float("nan"), "mm"), None),
            (geometry(float("inf"), "mm"), None),
            (geometry(float("-inf"), "mm"), None),
            (geometry(0.2, "in"), None),
            (geometry(0.2, None), None),
            (geometry("0.2", "mm"), None),
            (geometry("0.2 mm", None), 0.2),
            (geometry(" 0.2 MM ", None), 0.2),
            (geometry("none", None), None),
            (geometry("0.2 in", None), None),
            (geometry("R 0.2 mm", None), None),
            (geometry("0.2 mm trailing", None), None),
            (geometry(f"{'9' * 400} mm", None), None),
            ({"dimensions": [{"label": "Corner radius", "value": 0.2, "unit": "mm"}]}, None),
            (
                {
                    "dimensions": [
                        {"label": "Corner radius", "value": 0.2, "unit": "mm", "source_ids": []}
                    ]
                },
                None,
            ),
            ({"dimensions": []}, None),
        ]
        for source_geometry, expected in cases:
            with self.subTest(source_geometry=source_geometry):
                self.assertEqual(build_module.corner_radius_mm_from_geometry(source_geometry), expected)

    def test_corner_radius_filter_is_index_backed_and_url_shareable(self) -> None:
        viewer_root = ROOT.parent / "docs" / "v3"
        index_html = (viewer_root / "index.html").read_text(encoding="utf-8")
        viewer_script = (viewer_root / "app.js").read_text(encoding="utf-8")

        self.assertIn('<label>Corner radius<select id="corner-radius-filter">', index_html)
        self.assertIn("cornerRadius: $('#corner-radius-filter')", viewer_script)
        self.assertIn("radius: elements.cornerRadius", viewer_script)
        self.assertIn("bump(buckets.cornerRadius, tool.corner_radius_mm)", viewer_script)
        self.assertIn("Number(tool.corner_radius_mm) === Number(elements.cornerRadius.value)", viewer_script)
        self.assertIn("`${rounded(value)} mm`", viewer_script)
        self.assertGreaterEqual(viewer_script.count("elements.cornerRadius, elements.cutting"), 3)

    def test_manufacturer_specific_insert_geometry_uses_existing_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, json_path, _ = self.build(Path(temp))
            details = json.loads(json_path.with_name("catalog-details.json").read_text(encoding="utf-8"))
            tools = details["tools_by_id"]

            horn = tools["L105.0005.2.4"]["geometry_display"]
            self.assertEqual(horn["mode"], "manufacturer")
            self.assertIn("internal grooving", horn["summary"])
            self.assertEqual(
                {item["label"]: (item["value"], item["unit"]) for item in horn["dimensions"]},
                {"Corner radius": (0.5, "mm"), "Width": (1.0, "mm")},
            )

            corocut = tools["C2I-E2N-0200-0001-CO"]["geometry_display"]
            self.assertEqual(corocut["mode"], "manufacturer")
            self.assertEqual(corocut["shape_name"], "CoroCut 2")
            self.assertEqual(
                {item["label"]: (item["value"], item["unit"]) for item in corocut["dimensions"]},
                {
                    "Clearance angle": (7.0, "deg"),
                    "Cutting width": (2.0, "mm"),
                    "Sandvik cutting depth max": (19.39, "mm"),
                    "Sandvik insert gauge length": (19.98, "mm"),
                    "Sandvik insert thickness": (4.3321, "mm"),
                    "Width code": ("E", None),
                },
            )

            iscar = tools["DGN 2002J IC908"]["geometry_display"]
            self.assertEqual(iscar["mode"], "manufacturer")
            self.assertIn("J-type chipformer", iscar["summary"])
            self.assertIn("Cutting width", {item["label"] for item in iscar["dimensions"]})

    def test_manufacturer_geometry_renderer_does_not_draw_an_iso_schematic(self) -> None:
        viewer_script = (ROOT.parent / "docs" / "v3" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const isIso = geometry.mode === 'iso'", viewer_script)
        self.assertIn("Manufacturer-specific geometry", viewer_script)

    def test_mobile_geometry_layout_allows_long_values_to_wrap(self) -> None:
        viewer_css = (ROOT.parent / "docs" / "v3" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".detail-description {", viewer_css)
        self.assertIn("overflow-wrap: anywhere", viewer_css.split(".detail-description {", 1)[1].split("}", 1)[0])
        self.assertIn(".geometry-line strong {", viewer_css)
        geometry_value_rule = viewer_css.split(".geometry-line strong {", 1)[1].split("}", 1)[0]
        self.assertIn("min-width: 0", geometry_value_rule)
        self.assertIn("overflow-wrap: anywhere", geometry_value_rule)

    def test_detail_relationship_count_matches_visible_claims(self) -> None:
        viewer_script = (ROOT.parent / "docs" / "v3" / "app.js").read_text(encoding="utf-8")
        self.assertIn(".filter(item => !item.suppressed).length", viewer_script)
        self.assertIn("relationshipCount === 1 ? 'connection' : 'connections'", viewer_script)

    def test_standalone_exact_product_does_not_synthesize_a_grade_selector(self) -> None:
        viewer_script = (ROOT.parent / "docs" / "v3" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (tool.standalone_exact_product) return []", viewer_script)

    def test_app_and_service_worker_cache_versions_match(self) -> None:
        viewer_root = ROOT.parent / "docs" / "v3"
        viewer_script = (viewer_root / "app.js").read_text(encoding="utf-8")
        service_worker = (viewer_root / "sw.js").read_text(encoding="utf-8")
        index_html = (viewer_root / "index.html").read_text(encoding="utf-8")
        app_version = viewer_script.split("const STATIC_VERSION = '", 1)[1].split("'", 1)[0]
        worker_version = service_worker.split("const VERSION = '", 1)[1].split("'", 1)[0]
        self.assertEqual(app_version, worker_version)
        self.assertEqual(app_version, "3.4.0-shell-10")
        for asset in ("manifest.webmanifest", "app.css", "app.js"):
            self.assertIn(f'{asset}?v={app_version}', index_html)

    def test_homepage_opens_directly_to_catalog_without_promotional_hero(self) -> None:
        viewer_root = ROOT.parent / "docs" / "v3"
        index_html = (viewer_root / "index.html").read_text(encoding="utf-8")
        viewer_script = (viewer_root / "app.js").read_text(encoding="utf-8")
        viewer_css = (viewer_root / "app.css").read_text(encoding="utf-8")

        self.assertNotIn('<section class="hero"', index_html)
        self.assertNotIn('id="stats"', index_html)
        self.assertNotIn("stats: $('#stats')", viewer_script)
        self.assertNotIn("function renderStats()", viewer_script)
        self.assertIn("elements.build.textContent", viewer_script)
        self.assertNotIn(".hero {", viewer_css)
        self.assertNotIn(".stats {", viewer_css)

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
                FROM usable_cutting_data
                WHERE reviewer='Greg' AND reviewed_at='2026-07-21'
                ORDER BY tool_id
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
                    WHERE tool_id IN ({placeholders}) AND fact_key='cutting_direction' AND is_current=1
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
                """
                SELECT proposal_sha256, review_ledger_sha256, catalog_sha256, row_count
                FROM review_batches WHERE proposal_id='kennametal-topswiss-pilot-2026-07'
                """
            ).fetchone()
            self.assertEqual(batch[0], sha256(TOPSWISS_PROPOSAL))
            self.assertEqual(batch[1], sha256(TOPSWISS_LEDGER))
            self.assertEqual(batch[3], 12)
            self.assertEqual(len(batch[2]), 64)
            catalog_source = connection.execute(
                """
                SELECT content_sha256, document_edition, retrieved_at
                FROM sources WHERE id=(
                  SELECT source_id FROM review_batches
                  WHERE proposal_id='kennametal-topswiss-pilot-2026-07'
                )
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
                      AND source_raw_text IS NOT NULL
                      AND review_batch_id=(
                        SELECT id FROM review_batches
                        WHERE proposal_id='kennametal-topswiss-pilot-2026-07'
                      )
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

    def test_kennametal_7154831_imports_exact_kcs25s_profiles_without_replacing_legacy_grade(self) -> None:
        expected = {
            "P5": (53.0, 75.0, 107.0),
            "P6": (50.0, 70.0, 101.0),
            "M1": (59.0, 101.0, 149.0),
            "M2": (59.0, 101.0, 149.0),
            "M3": (50.0, 101.0, 180.0),
            "S1": (40.0, 79.0, 140.0),
            "S2": (40.0, 79.0, 140.0),
            "S3": (40.0, 79.0, 140.0),
            "S4": (40.0, 79.0, 140.0),
        }
        with tempfile.TemporaryDirectory() as temp:
            db_path, _, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                batch = connection.execute(
                    """
                    SELECT proposal_sha256, review_ledger_sha256, catalog_sha256, row_count
                    FROM review_batches
                    WHERE proposal_id='kennametal-topswiss-7154831-2026-07'
                    """
                ).fetchone()
                self.assertIsNotNone(batch)
                self.assertEqual(batch[0], sha256(KENNAMETAL_7154831_PROPOSAL))
                self.assertEqual(batch[1], sha256(KENNAMETAL_7154831_LEDGER))
                self.assertEqual(batch[2], sha256(KENNAMETAL_7154831_PDF))
                self.assertEqual(batch[3], 1)

                tool = connection.execute(
                    "SELECT grade FROM tools WHERE id='CCGT060202MFFS'"
                ).fetchone()
                self.assertEqual(tool[0], "S52MCK")
                grade_options = connection.execute(
                    """
                    SELECT g.code, o.option_kind, o.verification_status
                    FROM tool_grade_options o JOIN grades g ON g.id=o.grade_id
                    WHERE o.tool_id='CCGT060202MFFS' ORDER BY g.code
                    """
                ).fetchall()
                self.assertIn(("S52MCK", "legacy_claim", "source_located"), grade_options)
                self.assertIn(("KCS25S", "available_grade", "manufacturer_verified"), grade_options)

                profiles = connection.execute(
                    """
                    SELECT material_subgroup, source_part_number, source_grade, source_chipbreaker,
                           surface_speed_min, surface_speed_start, surface_speed_max,
                           feed_min, feed_max, depth_of_cut_min, depth_of_cut_max,
                           verification_status
                    FROM cutting_data_profiles
                    WHERE tool_id='CCGT060202MFFS'
                    ORDER BY material_subgroup
                    """
                ).fetchall()
                self.assertEqual(len(profiles), 9)
                self.assertEqual({row[0] for row in profiles}, set(expected))
                for subgroup, source_part, grade, chipbreaker, speed_min, speed_start, speed_max, feed_min, feed_max, doc_min, doc_max, status in profiles:
                    self.assertEqual((source_part, grade, chipbreaker), ("CCGT060202MFFS", "KCS25S", "FFS"))
                    self.assertEqual((speed_min, speed_start, speed_max), expected[subgroup])
                    self.assertEqual((feed_min, feed_max), (0.02, 0.12))
                    self.assertEqual((doc_min, doc_max), (0.13, 1.26))
                    self.assertEqual(status, "catalog_verified")

                recommendations = connection.execute(
                    """
                    SELECT r.material_subgroup, g.code, r.verification_status
                    FROM tool_material_recommendations r
                    JOIN grades g ON g.id=r.grade_id
                    WHERE r.tool_id='CCGT060202MFFS' AND r.is_current=1
                    ORDER BY r.material_subgroup
                    """
                ).fetchall()
                self.assertEqual(len(recommendations), 9)
                self.assertEqual({row[0] for row in recommendations}, set(expected))
                self.assertTrue(all(row[1:] == ("KCS25S", "catalog_verified") for row in recommendations))

                product_snapshot = json.loads(KENNAMETAL_7154831_SNAPSHOT.read_text(encoding="utf-8"))
                self.assertEqual(product_snapshot["identity"]["material_number"], "7154831")
                self.assertEqual(product_snapshot["identity"]["iso_catalog_id"], "CCGT060202MFFS")
                self.assertEqual(product_snapshot["identity"]["grade"], "KCS25S")
                self.assertEqual(product_snapshot["feeds_and_speeds_pdf"]["sha256"], sha256(KENNAMETAL_7154831_PDF))
            finally:
                connection.close()

    def test_sandvik_corocut2_pilot_matches_exact_manufacturer_snapshot(self) -> None:
        snapshot = json.loads(SANDVIK_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot["products"]), 10)
        with tempfile.TemporaryDirectory() as temp:
            db_path, _, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                batch = connection.execute(
                    """
                    SELECT proposal_sha256, review_ledger_sha256, catalog_sha256, row_count
                    FROM review_batches
                    WHERE proposal_id='sandvik-corocut2-cs1225-pilot-2026-07'
                    """
                ).fetchone()
                self.assertEqual(batch[0], sha256(SANDVIK_PROPOSAL))
                self.assertEqual(batch[1], sha256(SANDVIK_LEDGER))
                self.assertEqual(batch[2], sha256(SANDVIK_SNAPSHOT))
                self.assertEqual(batch[3], 10)
                for product in snapshot["products"]:
                    tool_id = product["database_tool_id"]
                    order_code = product["order_code"]
                    expected_materials = {
                        material["material_reference"]: material
                        for operation in product["cutting_operations"]
                        for material in operation["materials"]
                    }
                    self.assertEqual(len(expected_materials), 5)
                    profiles = connection.execute(
                        """
                        SELECT material_subgroup, source_part_number,
                               surface_speed_min, surface_speed_start, surface_speed_max,
                               feed_min, feed_max, depth_of_cut_max, verification_status
                        FROM cutting_data_profiles WHERE tool_id=?
                        """,
                        (tool_id,),
                    ).fetchall()
                    recommendations = connection.execute(
                        """
                        SELECT material_subgroup, verification_status
                        FROM tool_material_recommendations
                        WHERE tool_id=? AND is_current=1
                        """,
                        (tool_id,),
                    ).fetchall()
                    self.assertEqual(len(profiles), 5)
                    self.assertEqual(len(recommendations), 5)
                    self.assertEqual({row[0] for row in profiles}, set(expected_materials))
                    self.assertEqual({row[0] for row in recommendations}, set(expected_materials))
                    for subgroup, source_part, speed_min, speed_start, speed_max, feed_min, feed_max, doc_max, status in profiles:
                        expected = expected_materials[subgroup]
                        self.assertEqual(source_part, order_code)
                        self.assertEqual((speed_min, speed_start, speed_max), (
                            expected["surface_speed"]["min"],
                            expected["surface_speed"]["nom"],
                            expected["surface_speed"]["max"],
                        ))
                        self.assertEqual((feed_min, feed_max), (
                            expected["feed"]["min"], expected["feed"]["max"]
                        ))
                        self.assertEqual(doc_max, product["specifications"]["CDX"])
                        self.assertEqual(status, "manufacturer_verified")
                    self.assertTrue(all(row[1] == "manufacturer_verified" for row in recommendations))
            finally:
                connection.close()

    def test_sandvik_corocut2_remaining_batch_matches_exact_manufacturer_snapshot(self) -> None:
        snapshot = json.loads(SANDVIK_REMAINING_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot["products"]), 48)
        self.assertEqual(
            {grade: sum(product["identity"]["grade"] == grade for product in snapshot["products"]) for grade in {"1205", "1225"}},
            {"1205": 4, "1225": 44},
        )
        self.assertEqual(
            {
                operation: sum(product["identity"]["application_operation"] == operation for product in snapshot["products"])
                for operation in {"grooving", "parting", "profiling", "turning"}
            },
            {"grooving": 22, "parting": 20, "profiling": 4, "turning": 2},
        )
        with tempfile.TemporaryDirectory() as temp:
            db_path, _, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                batch = connection.execute(
                    """
                    SELECT proposal_sha256, review_ledger_sha256, catalog_sha256, row_count
                    FROM review_batches
                    WHERE proposal_id='sandvik-corocut2-remaining-2026-07'
                    """
                ).fetchone()
                self.assertEqual(batch[0], sha256(SANDVIK_REMAINING_PROPOSAL))
                self.assertEqual(batch[1], sha256(SANDVIK_REMAINING_LEDGER))
                self.assertEqual(batch[2], sha256(SANDVIK_REMAINING_SNAPSHOT))
                self.assertEqual(batch[3], 48)
                total_profiles = 0
                for product in snapshot["products"]:
                    tool_id = product["database_tool_id"]
                    order_code = product["order_code"]
                    grade = product["identity"]["grade"]
                    chipbreaker = product["identity"]["chipbreaker"]
                    operation_type = {
                        "parting": "parting",
                        "grooving": "grooving",
                        "parting and grooving": "grooving",
                        "profiling": "turning",
                        "turning": "turning",
                    }[product["identity"]["application_operation"]]
                    self.assertEqual("".join(order_code.split()), tool_id + grade)
                    expected_materials = {
                        material["material_reference"]: material
                        for operation in product["cutting_operations"]
                        for material in operation["materials"]
                    }
                    profiles = connection.execute(
                        """
                        SELECT material_subgroup, source_part_number, source_grade, source_chipbreaker,
                               operation_type, surface_speed_min, surface_speed_start, surface_speed_max,
                               feed_min, feed_max, depth_of_cut_max, verification_status
                        FROM cutting_data_profiles WHERE tool_id=?
                        """,
                        (tool_id,),
                    ).fetchall()
                    recommendations = connection.execute(
                        """
                        SELECT r.material_subgroup, r.verification_status, g.code
                        FROM tool_material_recommendations r
                        JOIN grades g ON g.id=r.grade_id
                        WHERE r.tool_id=? AND r.is_current=1
                        """,
                        (tool_id,),
                    ).fetchall()
                    total_profiles += len(profiles)
                    self.assertEqual(len(profiles), len(expected_materials))
                    self.assertEqual(len(recommendations), len(expected_materials))
                    self.assertEqual({row[0] for row in profiles}, set(expected_materials))
                    self.assertEqual({row[0] for row in recommendations}, set(expected_materials))
                    for subgroup, source_part, source_grade, source_chipbreaker, operation, speed_min, speed_start, speed_max, feed_min, feed_max, doc_max, status in profiles:
                        expected = expected_materials[subgroup]
                        self.assertEqual((source_part, source_grade, source_chipbreaker), (order_code, grade, chipbreaker))
                        self.assertEqual(operation, operation_type)
                        self.assertEqual((speed_min, speed_start, speed_max), (
                            expected["surface_speed"]["min"],
                            expected["surface_speed"]["nom"],
                            expected["surface_speed"]["max"],
                        ))
                        self.assertEqual((feed_min, feed_max), (
                            expected["feed"]["min"], expected["feed"]["max"]
                        ))
                        self.assertEqual(doc_max, product["specifications"]["CDX"])
                        self.assertEqual(status, "manufacturer_verified")
                    self.assertTrue(all(row[1] == "manufacturer_verified" and row[2] == grade for row in recommendations))
                self.assertEqual(total_profiles, 227)
            finally:
                connection.close()

    def test_grade_options_are_split_and_reviewed_sources_are_multi_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path, _, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            horn_options = connection.execute(
                """
                SELECT g.code FROM tool_grade_options o
                JOIN grades g ON g.id=o.grade_id
                WHERE o.tool_id='L106.0150.2.00'
                ORDER BY g.code
                """
            ).fetchall()
            self.assertEqual([row[0] for row in horn_options], ["EG55", "TH35"])
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM tool_grade_options o
                    JOIN grades g ON g.id=o.grade_id
                    WHERE o.tool_id='CCET060200RPPS-KN10S' AND g.code='KN10S'
                      AND o.verification_status='catalog_verified'
                      AND o.review_batch_id IS NOT NULL
                    """
                ).fetchone()[0],
                1,
            )
            role_counts = dict(
                connection.execute(
                    """
                    SELECT s.evidence_role, COUNT(*)
                    FROM cutting_data_profile_sources s
                    JOIN cutting_data_profiles p ON p.id=s.profile_id
                    WHERE p.reviewer='Greg' AND p.reviewed_at='2026-07-21'
                    GROUP BY s.evidence_role
                    """
                ).fetchall()
            )
            self.assertEqual(role_counts, {"cutting_speed": 12, "geometry_parameters": 12, "identity": 12})
            connection.close()

    def test_build_rejects_empty_schema_2_corrected_proposed_before_replacing_outputs(self) -> None:
        packet_name = "kennametal-topswiss-7154831.json"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            data_dir = temp_path / "data"
            shutil.copytree(DATA_DIR, data_dir)
            proposal_path = temp_path / KENNAMETAL_7154831_PROPOSAL.name
            ledger_path = temp_path / KENNAMETAL_7154831_LEDGER.name
            shutil.copy2(KENNAMETAL_7154831_PROPOSAL, proposal_path)
            shutil.copy2(KENNAMETAL_7154831_LEDGER, ledger_path)

            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["decisions"][0]["decision"] = "approved_with_corrections"
            ledger["decisions"][0]["corrected_proposed"] = {}
            ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

            spec = importlib.util.spec_from_file_location(
                "review_batch_for_regression", ROOT / "scripts" / "review_batch.py"
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            review_batch = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(review_batch)
            review_batch.compile_packet(
                proposal_path,
                proposal,
                ledger_path,
                ledger,
                data_dir / "reviewed_imports" / packet_name,
            )

            output_paths = [
                temp_path / "toolbase.sqlite",
                temp_path / "catalog.json",
                temp_path / "published.sqlite",
            ]
            for output_path in output_paths:
                output_path.write_bytes(b"existing-output")
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--data-dir",
                    str(data_dir),
                    "--db-out",
                    str(output_paths[0]),
                    "--json-out",
                    str(output_paths[1]),
                    "--published-db-out",
                    str(output_paths[2]),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no auditable assertions were proposed", result.stderr)
            self.assertTrue(all(path.read_bytes() == b"existing-output" for path in output_paths))

    def test_build_rejects_tampered_schema_2_reviewed_import_before_replacing_outputs(self) -> None:
        packet_name = "mitsubishi-insert-identities-bf-bm-baselines-2026-07-part-01.json"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            data_dir = temp_path / "data"
            shutil.copytree(DATA_DIR, data_dir)
            packet_path = data_dir / "reviewed_imports" / packet_name
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["rows"][0]["grade_options"][0]["code"], "BC8210")
            packet["rows"][0]["grade_options"][0]["code"] = "UNREVIEWED999"
            packet_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

            output_paths = [
                temp_path / "toolbase.sqlite",
                temp_path / "catalog.json",
                temp_path / "published.sqlite",
            ]
            for output_path in output_paths:
                output_path.write_bytes(b"existing-output")
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--data-dir",
                    str(data_dir),
                    "--db-out",
                    str(output_paths[0]),
                    "--json-out",
                    str(output_paths[1]),
                    "--published-db-out",
                    str(output_paths[2]),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match canonical proposal and ledger compilation", result.stderr)
            self.assertTrue(all(path.read_bytes() == b"existing-output" for path in output_paths))

    def test_schema_2_accepts_truthful_non_pdf_source_locator(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_structured_locator", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        source = {
            "source_id": "source-structured-api",
            "source_type": "manufacturer_product_page",
            "artifact_format": "structured_json",
            "local_path": "toolbase/data/source_snapshots/example.json",
            "page_count": 1,
        }
        proposed = {
            "facts": [
                {
                    "fact_key": "manufacturer_material_number",
                    "value_text": "5730414",
                    "evidence": {
                        "source_id": source["source_id"],
                        "source_page_ref": "Structured product API snapshot",
                        "source_table_ref": "Product identity",
                        "source_raw_text": "MaterialID 5730414",
                        "extraction_method": "manufacturer_page",
                    },
                }
            ]
        }
        self.assertEqual(
            review_batch.validate_proposed_payload(
                proposed,
                "structured locator",
                {source["source_id"]: source},
            ),
            [],
        )
        both_locators = json.loads(json.dumps(proposed))
        both_locators["facts"][0]["evidence"]["pdf_page"] = 1
        self.assertIn(
            "structured locator facts[1]: structured source must not use pdf_page",
            review_batch.validate_proposed_payload(
                both_locators,
                "structured locator",
                {source["source_id"]: source},
            ),
        )
        missing_locator = json.loads(json.dumps(proposed))
        del missing_locator["facts"][0]["evidence"]["source_page_ref"]
        self.assertIn(
            "structured locator facts[1]: structured source requires source_page_ref",
            review_batch.validate_proposed_payload(
                missing_locator,
                "structured locator",
                {source["source_id"]: source},
            ),
        )

        compiled = review_batch.compile_row(
            {
                "proposal_row_id": "structured-locator-001",
                "tool_lookup": {"tool_id": "DCGT-11-T3-02-UM"},
                "current_summary": {},
                "proposed": proposed,
            },
            {
                "decision": "approved",
                "reviewer": "Greg",
                "decided_at": "2026-07-23",
            },
            {source["source_id"]: source},
        )
        self.assertEqual(
            compiled["facts"][0]["source_page_ref"],
            "Structured product API snapshot",
        )
        self.assertNotIn("PDF", compiled["facts"][0]["source_page_ref"])

    def test_sandvik_grade_suffixes_are_distinct_seed_tools(self) -> None:
        records = {
            row["json_id"]: row
            for row in (
                json.loads(line)
                for line in (ROOT / "data" / "tools.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }
        expected = {
            "DCGT-11-T3-02-UM": (
                "DCGT 11 T3 02-UM 1105",
                "1105",
                "5730414",
            ),
            "DCGT-11-T3-02-UM-1115": (
                "DCGT 11 T3 02-UM 1115",
                "1115",
                "5730415",
            ),
        }
        for tool_id, (order_code, grade, material_id) in expected.items():
            record = records[tool_id]
            self.assertEqual(record["specs"]["manufacturer_order_code"], order_code)
            self.assertEqual(record["grade"], grade)
            self.assertEqual(record["specs"]["manufacturer_material_id"], material_id)
        self.assertNotEqual(*expected.keys())

    def test_schema_2_allows_review_batches_larger_than_25_rows(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_without_row_cap", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = (
            ROOT
            / "proposals"
            / "sandvik-coroturn107-dcgt-family-2026-07.json"
        )
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        self.assertGreater(len(proposal["rows"]), 25)
        with tempfile.TemporaryDirectory() as temp:
            db_path, _, _ = self.build(Path(temp))
            _, errors = review_batch.validate_proposal(proposal_path, db_path)
        self.assertEqual(errors, [])

    def test_schema_2_rejects_structured_fact_value_claim_mismatch(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_value_claim", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = ROOT / "proposals" / "sandvik-dcgt-11t302-um-1115-2026-07.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        coating = next(
            fact
            for fact in proposal["rows"][0]["proposed"]["facts"]
            if fact["fact_key"] == "coating"
        )
        coating["value_text"] = "SOURCE-INCONSISTENT COATING"

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path, _, _ = self.build(temp_path)
            mutated_path = temp_path / "proposal.json"
            mutated_path.write_text(
                json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _, errors = review_batch.validate_proposal(mutated_path, db_path)
            self.assertIn(
                "row 1 facts[6]: value claim for value_text does not match proposed value",
                errors,
            )

    def test_schema_2_requires_complete_structured_value_claims(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_claim_coverage", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = ROOT / "proposals" / "sandvik-dcgt-11t302-um-1115-2026-07.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        coating = next(
            fact
            for fact in proposal["rows"][0]["proposed"]["facts"]
            if fact["fact_key"] == "coating"
        )
        del coating["evidence"]["value_claims"]["value_text"]
        inscribed_circle = next(
            fact
            for fact in proposal["rows"][0]["proposed"]["facts"]
            if fact["fact_key"] == "inscribed_circle_mm"
        )
        inscribed_circle["evidence"]["value_claims"].pop("unit", None)
        tool_updates = proposal["rows"][0]["proposed"]["tool_updates"]
        tool_updates.setdefault("evidence", {}).setdefault("value_claims", {}).pop(
            "grade", None
        )

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path, _, _ = self.build(temp_path)
            mutated_path = temp_path / "proposal.json"
            mutated_path.write_text(
                json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _, errors = review_batch.validate_proposal(mutated_path, db_path)
            self.assertIn(
                "row 1 facts[6]: missing value claim for value_text",
                errors,
            )
            self.assertIn(
                "row 1 facts[22]: missing value claim for unit",
                errors,
            )
            self.assertIn(
                "row 1 tool_updates: missing value claim for grade",
                errors,
            )

    def test_schema_2_rejects_structured_value_claim_mismatch_in_corrections(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_corrected_claim", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = ROOT / "proposals" / "sandvik-dcgt-11t302-um-1115-2026-07.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        corrected = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        coating = next(
            fact for fact in corrected["facts"] if fact["fact_key"] == "coating"
        )
        coating["value_text"] = "SOURCE-INCONSISTENT COATING"
        inscribed_circle = next(
            fact
            for fact in corrected["facts"]
            if fact["fact_key"] == "inscribed_circle_mm"
        )
        inscribed_circle["unit"] = "inch"
        corrected["tool_updates"]["grade"] = "1105"
        ledger = {
            "schema_version": 2,
            "review_id": "corrected-claim-review",
            "proposal_id": proposal["proposal_id"],
            "proposal_path": "toolbase/proposals/sandvik-dcgt-11t302-um-1115-2026-07.json",
            "proposal_sha256": sha256(proposal_path),
            "review_started_at": "2026-07-23",
            "status": "complete",
            "review_completed_at": "2026-07-23",
            "import_allowed": True,
            "decisions": [
                {
                    "proposal_row_id": "sandvik-dcgt-11t302-um-1115-001",
                    "tool_id": "DCGT-11-T3-02-UM-1115",
                    "decision": "approved_with_corrections",
                    "reviewer": "test-reviewer",
                    "decided_at": "2026-07-23",
                    "corrected_proposed": corrected,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            ledger_path = Path(temp) / "ledger.json"
            ledger_path.write_text(
                json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _, errors = review_batch.validate_ledger(
                proposal_path, proposal, ledger_path
            )
            self.assertIn(
                "ledger decision 1 corrected_proposed facts[6]: value claim for value_text does not match proposed value",
                errors,
            )
            self.assertIn(
                "ledger decision 1 corrected_proposed facts[22]: value claim for unit normalized_value does not match proposed value",
                errors,
            )
            self.assertIn(
                "ledger decision 1 corrected_proposed tool_updates: value claim for grade does not match proposed value",
                errors,
            )
            db_path, _, _ = self.build(Path(temp) / "build")
            output_path = Path(temp) / "compiled.json"
            sentinel = b"do-not-replace-invalid-output"
            output_path.write_bytes(sentinel)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "review_batch.py"),
                    "compile",
                    "--proposal",
                    str(proposal_path),
                    "--ledger",
                    str(ledger_path),
                    "--db",
                    str(db_path),
                    "--out",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output_path.read_bytes(), sentinel)

    def test_schema_2_rejects_correction_publication_shape_changes(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_correction_shape", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = ROOT / "proposals" / "sandvik-dcgt-11t302-um-1115-2026-07.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))

        def ledger_for(corrected: dict[str, object]) -> dict[str, object]:
            return {
                "schema_version": 2,
                "review_id": "corrected-shape-review",
                "proposal_id": proposal["proposal_id"],
                "proposal_path": "toolbase/proposals/sandvik-dcgt-11t302-um-1115-2026-07.json",
                "proposal_sha256": sha256(proposal_path),
                "review_started_at": "2026-07-23",
                "status": "complete",
                "review_completed_at": "2026-07-23",
                "import_allowed": True,
                "decisions": [
                    {
                        "proposal_row_id": "sandvik-dcgt-11t302-um-1115-001",
                        "tool_id": "DCGT-11-T3-02-UM-1115",
                        "decision": "approved_with_corrections",
                        "reviewer": "test-reviewer",
                        "decided_at": "2026-07-23",
                        "corrected_proposed": corrected,
                    }
                ],
            }

        mutations: list[tuple[str, dict[str, object], str]] = []
        fact_key = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        next(fact for fact in fact_key["facts"] if fact["fact_key"] == "coating")[
            "fact_key"
        ] = "substrate"
        mutations.append(("fact_key", fact_key, "immutable field fact_key differs"))

        alias_injection = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        alias_injection["aliases"].append(
            {"alias": "UNREVIEWED-ALIAS", "alias_type": "search"}
        )
        mutations.append(("aliases", alias_injection, "immutable field aliases differs"))

        omitted_update = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        omitted_update["tool_updates"].pop("grade")
        omitted_update["tool_updates"]["evidence"]["value_claims"].pop("grade")
        mutations.append(("tool_update", omitted_update, "tool_updates fields differ"))

        nulled_update = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        nulled_update["tool_updates"]["grade"] = None
        nulled_update["tool_updates"]["evidence"]["value_claims"].pop("grade")
        mutations.append(
            (
                "nulled_tool_update",
                nulled_update,
                "tool_updates null/non-null fields differ",
            )
        )

        dropped_fact = json.loads(json.dumps(proposal["rows"][0]["proposed"]))
        dropped_fact["facts"].pop()
        mutations.append(("fact_count", dropped_fact, "facts length differs"))

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            for label, corrected, expected_error in mutations:
                with self.subTest(label=label):
                    ledger_path = temp_path / f"{label}.json"
                    ledger_path.write_text(
                        json.dumps(ledger_for(corrected), ensure_ascii=False, indent=2)
                        + "\n",
                        encoding="utf-8",
                    )
                    _, errors = review_batch.validate_ledger(
                        proposal_path, proposal, ledger_path
                    )
                    self.assertTrue(
                        any(expected_error in error for error in errors), errors
                    )

            nulled_ledger_path = temp_path / "nulled-tool-update.json"
            nulled_ledger_path.write_text(
                json.dumps(ledger_for(nulled_update), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            db_path, _, _ = self.build(temp_path / "build")
            output_path = temp_path / "compiled.json"
            sentinel = b"do-not-replace-invalid-shape"
            output_path.write_bytes(sentinel)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "review_batch.py"),
                    "compile",
                    "--proposal",
                    str(proposal_path),
                    "--ledger",
                    str(nulled_ledger_path),
                    "--db",
                    str(db_path),
                    "--out",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output_path.read_bytes(), sentinel)

    def test_review_json_writer_uses_explicit_lf_bytes(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_json_bytes", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        payload = {"label": "1115 µm", "nested": {"value": 1}}
        expected = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        with tempfile.TemporaryDirectory() as temp:
            output_path = Path(temp) / "packet.json"
            review_batch.write_json(output_path, payload)
            written = output_path.read_bytes()
        self.assertEqual(written, expected)
        self.assertNotIn(b"\r\n", written)

    def test_compiler_preserves_structured_value_claims(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "review_batch_for_compiled_claims", ROOT / "scripts" / "review_batch.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        review_batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review_batch)

        proposal_path = ROOT / "proposals" / "sandvik-dcgt-11t302-um-1115-2026-07.json"
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        row = proposal["rows"][0]
        compiled = review_batch.compile_row(
            row,
            {
                "decision": "approved",
                "reviewer": "test-reviewer",
                "decided_at": "2026-07-23",
            },
            {source["source_id"]: source for source in proposal["sources"]},
        )
        for group in ("facts", "material_recommendations", "cutting_profiles"):
            self.assertTrue(compiled[group])
            self.assertTrue(
                all(item.get("value_claims") for item in compiled[group]),
                group,
            )
        self.assertTrue(compiled["tool_updates"].get("value_claims"))

    def test_sandvik_dcgt_11t302_um_1105_is_exact_and_source_scoped(self) -> None:
        tool_id = "DCGT-11-T3-02-UM"
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT t.part_number, m.name, t.component_type, t.family, t.grade,
                               t.chipbreaker, t.geometry, t.lifecycle_status
                        FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
                        WHERE t.id=?
                        """,
                        (tool_id,),
                    ).fetchone(),
                    (
                        "DCGT 11 T3 02-UM 1105",
                        "Sandvik Coromant",
                        "insert",
                        "CoroTurn 107 Inserts",
                        "1105",
                        "UM",
                        "positive 55-degree rhombic precision turning insert",
                        "discontinued",
                    ),
                )
                aliases = set(connection.execute(
                    "SELECT alias, alias_type FROM tool_aliases WHERE tool_id=?",
                    (tool_id,),
                ).fetchall())
                required_aliases = {
                    ("DCGT 11 T3 02-UM 1105", "manufacturer_part_number"),
                    ("DCGT11T302UM1105", "search"),
                    ("DCGT 3(2.5)0-UM 1105", "ansi"),
                    ("5730414", "search"),
                    ("12096976", "search"),
                }
                self.assertTrue(required_aliases.issubset(aliases), aliases)
                facts = dict(connection.execute(
                    """
                    SELECT fact_key, COALESCE(value_text, CAST(value_number AS TEXT))
                    FROM facts WHERE tool_id=? AND is_current=1
                    """,
                    (tool_id,),
                ).fetchall())
                self.assertEqual(facts["manufacturer_material_number"], "5730414")
                self.assertEqual(facts["manufacturer_order_code"], "DCGT 11 T3 02-UM 1105")
                self.assertEqual(facts["operation_classification"], "pre-machining with demand on surface")
                self.assertEqual(facts["coating"], "PVD TiAlN")
                self.assertEqual(facts["substrate"], "HC")
                self.assertEqual(facts["manufacturer_lifecycle_code"], "30")
                self.assertEqual(facts["manufacturer_availability"], "Available")
                self.assertEqual(facts["lifecycle_status"], "being_replaced")
                self.assertEqual(
                    facts["replacement_note"],
                    "Different grade vs. the original product – Please check cutting speed.",
                )

                source_id = "source-718d750d3903ffc2"
                source_sha256 = "718d750d3903ffc22dc75a7f1d4f8a3356f4416aa643ef0b4297c2396a6eaa3e"
                dimension_keys = (
                    "inscribed_circle_mm",
                    "thickness_mm",
                    "corner_radius_mm",
                    "hole_size",
                    "cutting_edge_length",
                    "clearance_angle_deg",
                    "cutting_edge_count",
                )
                dimension_rows = {
                    row[0]: row[1:]
                    for row in connection.execute(
                        f"""
                        SELECT f.fact_key, f.value_number, f.unit, f.verification_status,
                               f.source_id, f.source_page_ref, s.content_sha256
                        FROM facts f JOIN sources s ON s.id=f.source_id
                        WHERE f.tool_id=? AND f.is_current=1
                          AND f.fact_key IN ({','.join('?' for _ in dimension_keys)})
                        """,
                        (tool_id, *dimension_keys),
                    ).fetchall()
                }
                self.assertEqual(
                    dimension_rows,
                    {
                        "inscribed_circle_mm": (9.525, "mm", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "thickness_mm": (3.96875, "mm", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "corner_radius_mm": (0.2, "mm", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "hole_size": (4.4, "mm", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "cutting_edge_length": (11.4279, "mm", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "clearance_angle_deg": (7.0, "deg", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                        "cutting_edge_count": (2.0, "count", "manufacturer_verified", source_id, "/product/specifications", source_sha256),
                    },
                )
                self.assertEqual(
                    set(connection.execute(
                        """
                        SELECT source_page_ref FROM facts
                        WHERE tool_id=? AND verification_status='manufacturer_verified'
                        UNION
                        SELECT source_page_ref FROM tool_grade_options
                        WHERE tool_id=? AND verification_status='manufacturer_verified'
                        UNION
                        SELECT source_page_ref FROM tool_material_recommendations
                        WHERE tool_id=? AND verification_status='manufacturer_verified'
                        UNION
                        SELECT source_page_ref FROM cutting_data_profiles
                        WHERE tool_id=? AND verification_status='manufacturer_verified'
                        """,
                        (tool_id, tool_id, tool_id, tool_id),
                    ).fetchall()),
                    {
                        ("/autocomplete_match",),
                        ("/product",),
                        ("/product/identity",),
                        ("/product/specifications",),
                        ("/product/cutting_operations/0/materials/0",),
                    },
                )

                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM tool_grade_options
                        WHERE tool_id=? AND verification_status <> 'rejected'
                        """,
                        (tool_id,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT iso_group, material_subgroup FROM tool_material_recommendations
                        WHERE tool_id=? AND is_current=1 ORDER BY iso_group
                        """,
                        (tool_id,),
                    ).fetchall(),
                    [("M", "Stainless steel"), ("S", "Heat-resistant superalloys")],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT source_part_number, source_grade, source_chipbreaker,
                               source_material_label, iso_material_group, material_subgroup,
                               operation_type, cut_condition, coolant_condition,
                               surface_speed_min, surface_speed_start, surface_speed_max,
                               feed_min, feed_max, depth_of_cut_min, depth_of_cut_max,
                               surface_speed_unit, feed_unit, depth_of_cut_unit,
                               verification_status
                        FROM cutting_data_profiles WHERE tool_id=?
                        """,
                        (tool_id,),
                    ).fetchall(),
                    [(
                        "DCGT 11 T3 02-UM 1105", "1105", "UM",
                        "S2.0.Z.AG", "S", "S2.0.Z.AG / 350 HB",
                        "turning", "unknown", "unknown",
                        70.0, 70.0, 70.0,
                        0.01, 0.08, 0.1, 1.05,
                        "m_per_min", "mm_per_rev", "mm",
                        "manufacturer_verified",
                    )],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM cutting_data_profiles WHERE tool_id=? AND iso_material_group='M'",
                        (tool_id,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT row_count FROM review_batches WHERE proposal_id='sandvik-dcgt-11t302-um-1105-2026-07'"
                    ).fetchone(),
                    (1,),
                )

                public_tools = {
                    item["id"]: item for item in json.loads(json_path.read_text(encoding="utf-8"))["tools"]
                }
                self.assertIn(tool_id, public_tools)
                self.assertEqual(public_tools[tool_id]["part_number"], "DCGT 11 T3 02-UM 1105")
                self.assertEqual(public_tools[tool_id]["grade"], "1105")
                self.assertEqual(public_tools[tool_id]["chipbreaker"], "UM")
                self.assertEqual(public_tools[tool_id]["lifecycle_status"], "discontinued")
                self.assertTrue(public_tools[tool_id]["standalone_exact_product"])
                self.assertEqual(public_tools[tool_id]["grade_options"], [])
                self.assertEqual(len(public_tools[tool_id]["cutting_data"]), 1)
                self.assertEqual(
                    public_tools[tool_id]["geometry_display"]["dimensions"],
                    [
                        {"label": "Inscribed circle", "value": 9.525, "unit": "mm", "verification_status": "manufacturer_verified", "source_ids": [source_id]},
                        {"label": "Thickness", "value": 3.96875, "unit": "mm", "verification_status": "manufacturer_verified", "source_ids": [source_id]},
                        {"label": "Corner radius", "value": 0.2, "unit": "mm", "verification_status": "manufacturer_verified", "source_ids": [source_id]},
                        {"label": "Fixing hole", "value": 4.4, "unit": "mm", "verification_status": "manufacturer_verified", "source_ids": [source_id]},
                        {"label": "Cutting edge", "value": 11.4279, "unit": "mm", "verification_status": "manufacturer_verified", "source_ids": [source_id]},
                    ],
                )
            finally:
                connection.close()

    def test_sandvik_dcgt_11t302_um_1115_is_a_distinct_exact_product(self) -> None:
        tool_id = "DCGT-11-T3-02-UM-1115"
        source_id = "source-ea2b2d84fdbf16f8"
        source_sha256 = "ea2b2d84fdbf16f83e2410feb85bd189a63a45edc29e73452c17c4ab6cdfb845"
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT id, part_number, grade, chipbreaker, lifecycle_status
                        FROM tools WHERE id IN (?, ?) ORDER BY id
                        """,
                        ("DCGT-11-T3-02-UM", tool_id),
                    ).fetchall(),
                    [
                        ("DCGT-11-T3-02-UM", "DCGT 11 T3 02-UM 1105", "1105", "UM", "discontinued"),
                        (tool_id, "DCGT 11 T3 02-UM 1115", "1115", "UM", "active"),
                    ],
                )
                aliases = set(
                    connection.execute(
                        "SELECT alias, alias_type FROM tool_aliases WHERE tool_id=?",
                        (tool_id,),
                    ).fetchall()
                )
                self.assertTrue(
                    {
                        ("12385284", "search"),
                        ("5730415", "search"),
                        ("DCGT 11 T3 02-UM 1115", "manufacturer_part_number"),
                        ("DCGT11T302UM1115", "search"),
                    }.issubset(aliases),
                    aliases,
                )
                self.assertFalse(any("1105" in alias for alias, _ in aliases), aliases)
                fact_rows = {
                    row[0]: row[1:]
                    for row in connection.execute(
                        """
                        SELECT f.fact_key,
                               COALESCE(f.value_text, CAST(f.value_number AS TEXT), f.value_json),
                               f.verification_status, f.source_id, s.content_sha256
                        FROM facts f JOIN sources s ON s.id=f.source_id
                        WHERE f.tool_id=? AND f.is_current=1
                          AND f.fact_key IN (
                            'manufacturer_material_number', 'manufacturer_order_code',
                            'coating', 'substrate', 'iso_designation',
                            'designation_shape_segment', 'designation_clearance_segment',
                            'designation_tolerance_segment', 'designation_style_segment',
                            'designation_size_segment', 'designation_thickness_segment',
                            'designation_radius_segment', 'designation_chipbreaker_segment',
                            'designation_grade_segment', 'manufacturer_lifecycle_code',
                            'manufacturer_availability', 'lifecycle_status'
                          )
                        """,
                        (tool_id,),
                    ).fetchall()
                }
                expected_values = {
                    "manufacturer_material_number": "5730415",
                    "manufacturer_order_code": "DCGT 11 T3 02-UM 1115",
                    "coating": "PVD TiAlN+TiAlN",
                    "substrate": "HC",
                    "iso_designation": "DCGT 11 T3 02",
                    "designation_shape_segment": "D",
                    "designation_clearance_segment": "C",
                    "designation_tolerance_segment": "G",
                    "designation_style_segment": "T",
                    "designation_size_segment": "11",
                    "designation_thickness_segment": "T3",
                    "designation_radius_segment": "02",
                    "designation_chipbreaker_segment": "UM",
                    "designation_grade_segment": "1115",
                    "manufacturer_lifecycle_code": "20",
                    "manufacturer_availability": "Available",
                    "lifecycle_status": "active",
                }
                self.assertEqual(set(fact_rows), set(expected_values))
                for key, value in expected_values.items():
                    self.assertEqual(
                        fact_rows[key],
                        (value, "manufacturer_verified", source_id, source_sha256),
                        key,
                    )

                grade_codes = {}
                for candidate in ("DCGT-11-T3-02-UM", tool_id):
                    grade_codes[candidate] = {
                        row[0]
                        for row in connection.execute(
                            """
                            SELECT g.code FROM tool_grade_options o
                            JOIN grades g ON g.id=o.grade_id
                            WHERE o.tool_id=? AND o.verification_status <> 'rejected'
                            """,
                            (candidate,),
                        ).fetchall()
                    }
                self.assertEqual(grade_codes["DCGT-11-T3-02-UM"], set())
                self.assertEqual(grade_codes[tool_id], set())
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM tool_grade_options
                        WHERE tool_id=? AND verification_status <> 'rejected'
                        """,
                        (tool_id,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM tool_grade_options
                        WHERE tool_id=? AND option_kind='legacy_claim'
                          AND verification_status='rejected'
                        """,
                        (tool_id,),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT option_kind, full_order_number, verification_status
                        FROM tool_grade_options WHERE tool_id=?
                        """,
                        (tool_id,),
                    ).fetchone(),
                    ("legacy_claim", "DCGT 11 T3 02-UM 1115", "rejected"),
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT g.code, r.iso_group, r.material_subgroup, r.suitability
                        FROM tool_material_recommendations r
                        LEFT JOIN grades g ON g.id=r.grade_id
                        WHERE r.tool_id=? AND r.is_current=1 ORDER BY r.iso_group
                        """,
                        (tool_id,),
                    ).fetchall(),
                    [
                        ("1115", "M", "Stainless steel", "recommended"),
                        ("1115", "S", "Heat-resistant superalloys", "recommended"),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT source_grade, iso_material_group,
                               surface_speed_min, surface_speed_start, surface_speed_max,
                               feed_min, feed_max, depth_of_cut_min, depth_of_cut_max
                        FROM cutting_data_profiles WHERE tool_id=? ORDER BY iso_material_group
                        """,
                        (tool_id,),
                    ).fetchall(),
                    [
                        ("1115", "M", 240.0, 260.0, 260.0, 0.01, 0.06, 0.1, 1.5),
                        ("1115", "S", 55.0, 55.0, 55.0, 0.01, 0.08, 0.1, 1.05),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT row_count FROM review_batches WHERE proposal_id='sandvik-dcgt-11t302-um-1115-2026-07'"
                    ).fetchone(),
                    (1,),
                )

                public = {
                    item["id"]: item
                    for item in json.loads(json_path.read_text(encoding="utf-8"))["tools"]
                }[tool_id]
                self.assertEqual(public["part_number"], "DCGT 11 T3 02-UM 1115")
                self.assertEqual(public["grade"], "1115")
                self.assertEqual(public["chipbreaker"], "UM")
                self.assertTrue(public["standalone_exact_product"])
                self.assertIn("standalone_exact_product", public["tags"])
                self.assertEqual(public["grade_options"], [])
                self.assertEqual(len(public["cutting_data"]), 2)
                self.assertEqual(public["geometry_display"]["designation"], "DCGT11T302")
                self.assertEqual(
                    public["geometry_display"]["designation_verification_status"],
                    "manufacturer_verified",
                )
                self.assertEqual(
                    public["geometry_display"]["designation_source_ids"],
                    [source_id],
                )
            finally:
                connection.close()

    def test_mitsubishi_insert_identities_and_bf_bm_baselines_are_exact(self) -> None:
        mitsubishi_grade_counts = {
            "BC5110": 10,
            "BC8105": 23,
            "BC8110": 43,
            "BC8120": 41,
            "BC8130": 26,
            "BC8210": 30,
            "BC8220": 26,
            "MB4120": 50,
            "MB8110": 14,
            "MB8120": 20,
            "MB8130": 6,
            "MD220": 23,
        }
        bf_tools = {
            "BF-CCGT09T304TS2", "BF-CCGT09T308TS2",
            "BF-DCGT11T304TS2", "BF-DCGT11T308TS2",
        }
        bm_tools = {
            "BM-CCGT09T304TA2", "BM-CCGT09T308TA2",
            "BM-DCGT11T304TA2", "BM-DCGT11T308TA2",
        }
        with tempfile.TemporaryDirectory() as temp:
            db_path, json_path, _ = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
                        WHERE m.name='Mitsubishi Materials' AND t.component_type='insert' AND t.grade IS NULL
                        """
                    ).fetchone()[0],
                    132,
                )
                actual_grade_counts = dict(
                    connection.execute(
                        """
                        SELECT g.code, COUNT(*)
                        FROM tool_grade_options o
                        JOIN tools t ON t.id=o.tool_id
                        JOIN manufacturers m ON m.id=t.manufacturer_id
                        JOIN grades g ON g.id=o.grade_id
                        WHERE m.name='Mitsubishi Materials' AND t.component_type='insert'
                          AND o.option_kind='available_grade'
                          AND o.verification_status IN ('catalog_verified','manufacturer_verified')
                        GROUP BY g.code ORDER BY g.code
                        """
                    ).fetchall()
                )
                self.assertEqual(actual_grade_counts, mitsubishi_grade_counts)
                self.assertEqual(sum(actual_grade_counts.values()), 312)
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM tool_grade_options o
                        JOIN tools t ON t.id=o.tool_id
                        JOIN manufacturers m ON m.id=t.manufacturer_id
                        WHERE m.name='Mitsubishi Materials' AND t.component_type='insert'
                          AND o.option_kind='legacy_claim' AND o.verification_status='rejected'
                        """
                    ).fetchone()[0],
                    132,
                )

                expected_exact_grades = {
                    "BF-CCGT09T304TS2": ["BC8110", "BC8210"],
                    "BM-DCGT11T308TA2": ["BC8120", "BC8220"],
                    "NP-DCGW11T304FS2": ["BC8105", "BC8110", "BC8120", "BC8210", "MB4120", "MB8110"],
                    "NP-TCGW110208GS3": ["BC5110", "BC8110", "MB4120"],
                    "DCMW070204": ["MD220"],
                }
                for tool_id, expected in expected_exact_grades.items():
                    actual = [
                        row[0] for row in connection.execute(
                            """
                            SELECT g.code FROM tool_grade_options o JOIN grades g ON g.id=o.grade_id
                            WHERE o.tool_id=? AND o.option_kind='available_grade'
                            ORDER BY g.code
                            """,
                            (tool_id,),
                        )
                    ]
                    self.assertEqual(actual, expected)

                tool_rows = connection.execute(
                    "SELECT id, chipbreaker FROM tools WHERE id IN ({})".format(
                        ",".join("?" for _ in bf_tools | bm_tools)
                    ),
                    tuple(sorted(bf_tools | bm_tools)),
                ).fetchall()
                self.assertEqual(
                    {tool_id: chipbreaker for tool_id, chipbreaker in tool_rows},
                    {**{tool_id: "BF" for tool_id in bf_tools}, **{tool_id: "BM" for tool_id in bm_tools}},
                )

                profile_counts = dict(
                    connection.execute(
                        """
                        SELECT tool_id, COUNT(*) FROM cutting_data_profiles
                        WHERE tool_id IN ({}) GROUP BY tool_id
                        """.format(",".join("?" for _ in bf_tools | bm_tools)),
                        tuple(sorted(bf_tools | bm_tools)),
                    ).fetchall()
                )
                self.assertEqual(
                    profile_counts,
                    {**{tool_id: 3 for tool_id in bf_tools}, **{tool_id: 5 for tool_id in bm_tools}},
                )
                self.assertEqual(sum(profile_counts.values()), 32)

                expected_profiles = {
                    ("BF-CCGT09T304TS2", "BC8110", "Hardened steel / continuous", "general"): (
                        "flood", 100.584, 199.644, 300.228, None, 0.2032, None, 0.3556, "BF"
                    ),
                    ("BF-CCGT09T304TS2", "BC8210", "Hardened steel / BF breaker", "finishing"): (
                        "flood", 79.248, None, 199.644, None, 0.3048, 0.1016, 0.3048, "BF"
                    ),
                    ("BM-DCGT11T304TA2", "BC8120", "Hardened steel / continuous", "general"): (
                        "flood", 100.584, 199.644, 230.124, None, 0.3048, None, 0.7874, "BM"
                    ),
                    ("BM-DCGT11T304TA2", "BC8220", "Hardened steel / medium interrupted", "medium"): (
                        "flood", 59.436, 149.352, 199.644, None, 0.2032, None, 0.3048, "BM"
                    ),
                    ("BM-DCGT11T304TA2", "BC8220", "Hardened steel / BM breaker", "medium"): (
                        "flood", 79.248, None, 199.644, None, 0.3048, 0.3048, 0.7874, "BM"
                    ),
                }
                for key, expected in expected_profiles.items():
                    row = connection.execute(
                        """
                        SELECT coolant_condition, surface_speed_min, surface_speed_start, surface_speed_max,
                               feed_min, feed_max, depth_of_cut_min, depth_of_cut_max, source_chipbreaker
                        FROM cutting_data_profiles
                        WHERE tool_id=? AND source_grade=? AND material_subgroup=? AND cut_condition=?
                        """,
                        key,
                    ).fetchone()
                    self.assertEqual(row, expected)

                public_tools = {
                    item["id"]: item
                    for item in json.loads(json_path.read_text(encoding="utf-8"))["tools"]
                    if item["manufacturer"] == "Mitsubishi Materials" and item["component_type"] == "insert"
                }
                self.assertEqual(len(public_tools), 132)
                self.assertTrue(all(tool["grade"] is None for tool in public_tools.values()))
                self.assertEqual(
                    [option["code"] for option in public_tools["DCMW070204"]["grade_options"]],
                    ["MD220"],
                )

                batches = connection.execute(
                    """
                    SELECT row_count, catalog_sha256 FROM review_batches
                    WHERE proposal_id LIKE 'mitsubishi-insert-identities-bf-bm-baselines-2026-07-part-%'
                    ORDER BY proposal_id
                    """
                ).fetchall()
                self.assertEqual(len(batches), 6)
                self.assertEqual(sum(row[0] for row in batches), 132)
                self.assertTrue(
                    all(
                        row[1] == sha256(ROOT / "data" / "source_snapshots" / "mitsubishi-c010a-cbn-pcd-inserts.pdf")
                        for row in batches
                    )
                )
            finally:
                connection.close()

    def test_mitsubishi_c010a_profile_batches_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path, _json_path, _published_path = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                mitsubishi = "SELECT id FROM manufacturers WHERE name='Mitsubishi Materials'"

                self.assertEqual(
                    connection.execute(
                        f"SELECT COUNT(*) FROM tools WHERE manufacturer_id IN ({mitsubishi}) AND geometry='unknown'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        f"SELECT COUNT(*) FROM tools WHERE manufacturer_id IN ({mitsubishi}) AND description LIKE '%Grade:%'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(DISTINCT p.tool_id) FROM cutting_data_profiles p
                        JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({mitsubishi})
                        """
                    ).fetchone()[0],
                    132,
                )

                # Every materialized row must stay unique per (tool, grade, class).
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) FROM (
                          SELECT tool_id, source_grade, material_subgroup, cut_condition, COUNT(*) AS n
                          FROM cutting_data_profiles p JOIN tools t ON t.id=p.tool_id
                          WHERE t.manufacturer_id IN ({mitsubishi})
                          GROUP BY 1, 2, 3, 4 HAVING n > 1
                        )
                        """
                    ).fetchone()[0],
                    0,
                )

                # Batch totals: B008 hardened steel (292 new + 32 shipped BF/BM rows),
                # B015 PCD MD220 (207 profiles; wood inorganic board is rec-only),
                # B008 sintered alloy (150).
                subgroup_counts = {
                    "Hardened steel%": 324,
                    "General Sintered Alloy": 50,
                    "High Density Sintered Alloy": 50,
                    "Sintered Alloy": 50,
                    "Wood Inorganic Board": 0,
                }
                for pattern, expected in subgroup_counts.items():
                    self.assertEqual(
                        connection.execute(
                            f"""
                            SELECT COUNT(*) FROM cutting_data_profiles p
                            JOIN tools t ON t.id=p.tool_id
                            WHERE t.manufacturer_id IN ({mitsubishi})
                              AND p.material_subgroup LIKE ?
                            """,
                            (pattern,),
                        ).fetchone()[0],
                        expected,
                        pattern,
                    )
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) FROM cutting_data_profiles p
                        JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({mitsubishi}) AND p.source_grade='MD220'
                        """
                    ).fetchone()[0],
                    207,
                )

                # One spot value per condition-class row, in exact source units.
                spot_checks = [
                    ("BC8105", "Hardened steel / high-speed finishing", "finishing",
                     330.0, 820.0, 1150.0, "sfm", 0.006, "ipr", 0.008, "in", "flood"),
                    ("BC8210", "Hardened steel / continuous", "general",
                     330.0, 655.0, 985.0, "sfm", 0.008, "ipr", 0.014, "in", "flood"),
                    ("BC8120", "Hardened steel / medium interrupted", "medium",
                     195.0, 490.0, 655.0, "sfm", 0.008, "ipr", 0.012, "in", "flood"),
                    ("BC8130", "Hardened steel / interrupted", "medium",
                     195.0, 390.0, 490.0, "sfm", 0.008, "ipr", 0.012, "in", "flood"),
                    ("MB8110", "Hardened steel / continuous", "general",
                     330.0, 655.0, 820.0, "sfm", 0.008, "ipr", 0.012, "in", "flood"),
                    ("MB8130", "Hardened steel / interrupted", "medium",
                     195.0, 330.0, 490.0, "sfm", 0.008, "ipr", 0.012, "in", "flood"),
                    ("MD220", "Aluminum Alloy (Si < 12%)", "general",
                     655.0, 2625.0, 3935.0, "sfm", 0.008, "ipr", 0.039, "in", "unknown"),
                    ("MD220", "Cemented Carbide", "general",
                     15.0, 50.0, 65.0, "sfm", 0.008, "ipr", 0.020, "in", "unknown"),
                    ("MB4120", "General Sintered Alloy", "general",
                     260.0, 590.0, 985.0, "sfm", 0.008, "ipr", 0.012, "in", "unknown"),
                    ("BC5110", "Gray cast iron", "general",
                     100.0, None, 600.0, "m_per_min", 0.5, "mm_per_rev", 0.5, "mm", "flood"),
                    ("MB4120", "Gray cast iron", "general",
                     2625.0, 3280.0, 4100.0, "sfm", 0.016, "ipr", 0.020, "in", "flood"),
                ]
                for (grade, subgroup, cut_condition, vc_min, vc_start, vc_max,
                     vc_unit, feed_max, feed_unit, doc_max, doc_unit, coolant) in spot_checks:
                    rows = connection.execute(
                        f"""
                        SELECT DISTINCT p.surface_speed_min, p.surface_speed_start,
                          p.surface_speed_max, p.surface_speed_unit, p.feed_min, p.feed_max,
                          p.feed_unit, p.depth_of_cut_min, p.depth_of_cut_max,
                          p.depth_of_cut_unit, p.coolant_condition, p.cut_condition,
                          p.verification_status
                        FROM cutting_data_profiles p JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({mitsubishi})
                          AND p.source_grade=? AND p.material_subgroup=?
                          AND p.reviewed_at='2026-07-23'
                        """,
                        (grade, subgroup),
                    ).fetchall()
                    self.assertEqual(
                        rows,
                        [(vc_min, vc_start, vc_max, vc_unit, None, feed_max, feed_unit,
                          None, doc_max, doc_unit, coolant, cut_condition, "catalog_verified")],
                        f"{grade} / {subgroup}",
                    )

                # Wood inorganic board keeps its missing depth-of-cut bound as a
                # recommendation-only entry on all 23 PCD inserts.
                wood = connection.execute(
                    f"""
                    SELECT COUNT(*), SUM(r.notes LIKE '%no depth-of-cut bound%')
                    FROM tool_material_recommendations r JOIN tools t ON t.id=r.tool_id
                    WHERE t.manufacturer_id IN ({mitsubishi})
                      AND r.material_subgroup='Wood Inorganic Board'
                    """
                ).fetchone()
                self.assertEqual(wood, (23, 23))

                # B015 first/second recommendation ranks for MD220.
                ranks = dict(
                    connection.execute(
                        f"""
                        SELECT r.material_subgroup, COUNT(DISTINCT r.suitability) || ':' || MAX(r.suitability)
                        FROM tool_material_recommendations r JOIN tools t ON t.id=r.tool_id
                        JOIN grades g ON g.id=r.grade_id
                        WHERE t.manufacturer_id IN ({mitsubishi}) AND g.code='MD220'
                          AND r.material_subgroup IN ('Ceramics', 'Copper Alloy')
                        GROUP BY r.material_subgroup
                        """
                    ).fetchall()
                )
                self.assertEqual(
                    ranks, {"Ceramics": "1:recommended", "Copper Alloy": "1:primary"}
                )

                # The reviewed BF/BM identity work stays intact: breakers preserved,
                # no duplicate baselines added by the profile batches.
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM cutting_data_profiles p
                        JOIN tools t ON t.id=p.tool_id
                        WHERE (t.part_number LIKE 'BF-%' OR t.part_number LIKE 'BM-%')
                          AND p.reviewed_at='2026-07-23'
                        """
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) FROM tools
                        WHERE manufacturer_id IN ({mitsubishi})
                          AND part_number LIKE 'BF-%' AND chipbreaker != 'BF'
                        """
                    ).fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_tungaloy_sh7025_grade_baselines_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path, _json_path, _published_path = self.build(Path(temp))
            connection = sqlite3.connect(db_path)
            try:
                tungaloy = "SELECT id FROM manufacturers WHERE name='Tungaloy'"

                # Every SH7025 insert carries P and M baselines, manufacturer-verified, flood.
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(DISTINCT p.tool_id) FROM cutting_data_profiles p
                        JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({tungaloy}) AND p.source_grade='SH7025'
                        """
                    ).fetchone()[0],
                    34,
                )
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) FROM cutting_data_profiles p JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({tungaloy}) AND p.source_grade='SH7025'
                          AND (p.verification_status != 'manufacturer_verified'
                               OR p.coolant_condition != 'flood'
                               OR p.surface_speed_min != 10 OR p.surface_speed_max != 200
                               OR p.surface_speed_unit != 'm_per_min')
                        """
                    ).fetchone()[0],
                    0,
                )

                # Feed keyed to corner radius, depth of cut keyed to chipbreaker.
                cases = {
                    "CCGT060204FN-JS": (0.05, 0.2, 0.5, 3.0),   # RE0.4, JS
                    "DCGT11T302FN-JP": (0.02, 0.1, 0.05, 2.5),  # RE0.2, JP
                    "CCGT060204F-01": (0.05, 0.2, 0.05, 3.0),   # RE0.4, other -> grade DOC span
                    "TCGT16T308-01": (0.02, 0.2, 0.05, 3.0),    # RE0.8 untabulated -> grade feed span
                }
                for part_number, (fmin, fmax, dmin, dmax) in cases.items():
                    row = connection.execute(
                        f"""
                        SELECT DISTINCT p.feed_min, p.feed_max, p.depth_of_cut_min, p.depth_of_cut_max
                        FROM cutting_data_profiles p JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({tungaloy}) AND t.part_number=?
                        """,
                        (part_number,),
                    ).fetchall()
                    self.assertEqual(row, [(fmin, fmax, dmin, dmax)], part_number)

                # Baselines are traceable to the captured Tungaloy grade page.
                self.assertEqual(
                    connection.execute(
                        f"""
                        SELECT COUNT(*) FROM cutting_data_profiles p JOIN tools t ON t.id=p.tool_id
                        WHERE t.manufacturer_id IN ({tungaloy}) AND p.source_grade='SH7025'
                          AND p.source_raw_text != '10 &#8211; 200'
                        """
                    ).fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_build_hash_is_independent_of_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            shell_output = directory / "with-shell"
            plain_output = directory / "plain"
            for output in (shell_output, plain_output):
                (output / "data").mkdir(parents=True)
            for name in (
                "index.html",
                "app.css",
                "app.js",
                "manifest.webmanifest",
                "sw.js",
                "toolbase-card.png",
            ):
                shutil.copyfile(ROOT.parent / "docs" / "v3" / name, shell_output / name)

            shell_db, shell_json, _ = self.build(shell_output / "data")
            plain_db, plain_json, _ = self.build(plain_output / "data")
            self.assertEqual(sha256(shell_db), sha256(plain_db))
            self.assertEqual(sha256(shell_json), sha256(plain_json))
            shell_meta = json.loads(
                shell_json.with_name("build-meta.json").read_text(encoding="utf-8")
            )
            plain_meta = json.loads(
                plain_json.with_name("build-meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(shell_meta["build_hash"], plain_meta["build_hash"])

    def test_build_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_db, first_json, _ = self.build(Path(first))
            second_db, second_json, _ = self.build(Path(second))
            self.assertEqual(sha256(first_db), sha256(second_db))
            self.assertEqual(sha256(first_json), sha256(second_json))


if __name__ == "__main__":
    unittest.main()
