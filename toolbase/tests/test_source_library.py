from __future__ import annotations

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
PROPOSAL_VALIDATOR = ROOT / "scripts" / "validate_cutting_proposal.py"
REVIEWED_IMPORTER = ROOT / "scripts" / "import_reviewed_proposal.py"
REVIEW_BATCH = ROOT / "scripts" / "review_batch.py"
TOPSWISS_PROPOSAL = ROOT / "proposals" / "kennametal-topswiss-pilot.json"
TOPSWISS_LEDGER = ROOT / "reviews" / "kennametal-topswiss-pilot.decisions.json"
TOPSWISS_IMPORT = ROOT / "data" / "reviewed_imports" / "kennametal-topswiss-pilot.json"
IDENTITY_PROPOSAL = ROOT / "proposals" / "kennametal-topswiss-identity-batch-01.json"
IDENTITY_LEDGER = ROOT / "reviews" / "kennametal-topswiss-identity-batch-01.decisions.json"
DATA_DIR = ROOT / "data"
TOPSWISS_CATALOG = ROOT.parent / "catalogs" / "kennametal" / "TopSwiss Inserts MetricInch.pdf"
SOURCE_LIBRARY_REQUIRED = (
    "requires the local TopSwiss manufacturer PDF; run the source-library suite "
    "only after restoring catalogs/"
)


@unittest.skipUnless(TOPSWISS_CATALOG.is_file(), SOURCE_LIBRARY_REQUIRED)
class SourceLibraryIntegrationTests(unittest.TestCase):
    """Checks that require original manufacturer files excluded from ordinary Git."""

    def build(self, directory: Path, data_dir: Path = DATA_DIR) -> tuple[Path, Path]:
        db_path = directory / "toolbase.sqlite"
        json_path = directory / "catalog.json"
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
                str(directory / "published.sqlite"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            self.fail(f"build failed:\n{result.stdout}\n{result.stderr}")
        return db_path, json_path

    def test_completed_topswiss_source_chain_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path, _ = self.build(temp_path)
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

    def test_pending_identity_batch_validates_but_cannot_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path, _ = self.build(temp_path)
            validation = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_BATCH),
                    "validate",
                    "--proposal",
                    str(IDENTITY_PROPOSAL),
                    "--ledger",
                    str(IDENTITY_LEDGER),
                    "--db",
                    str(db_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(validation.stdout)
            self.assertEqual(result["status"], "valid")
            self.assertEqual(result["rows"], 25)
            blocked = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_BATCH),
                    "compile",
                    "--proposal",
                    str(IDENTITY_PROPOSAL),
                    "--ledger",
                    str(IDENTITY_LEDGER),
                    "--db",
                    str(db_path),
                    "--out",
                    str(temp_path / "must-not-import.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse((temp_path / "must-not-import.json").exists())

    def test_schema_two_batch_imports_only_terminal_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source_db, _ = self.build(temp_path / "source")
            ledger = json.loads(IDENTITY_LEDGER.read_text(encoding="utf-8"))
            ledger.update(
                {
                    "status": "complete",
                    "review_completed_at": "2026-07-21",
                    "import_allowed": True,
                }
            )
            for decision in ledger["decisions"]:
                decision.update(
                    {
                        "decision": "approved",
                        "reviewer": "Unit Test",
                        "decided_at": "2026-07-21",
                        "notes": "Synthetic terminal decision used only in a temporary test build.",
                    }
                )
            ledger_path = temp_path / "terminal-ledger.json"
            ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
            packet_path = temp_path / "kennametal-identity-test.json"
            subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_BATCH),
                    "compile",
                    "--proposal",
                    str(IDENTITY_PROPOSAL),
                    "--ledger",
                    str(ledger_path),
                    "--db",
                    str(source_db),
                    "--out",
                    str(packet_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["schema_version"], 2)
            self.assertEqual(packet["row_count"], 25)
            self.assertEqual(len(packet["rows"]), 25)
            self.assertEqual(packet["quarantined_rows"], [])

            test_data = temp_path / "data"
            shutil.copytree(DATA_DIR, test_data)
            shutil.copy2(packet_path, test_data / "reviewed_imports" / packet_path.name)
            build_directory = temp_path / "built"
            build_directory.mkdir()
            db_path, _ = self.build(build_directory, test_data)
            connection = sqlite3.connect(db_path)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_batches").fetchone()[0], 2)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM tools WHERE review_status='verified' AND id LIKE 'CCGT%'"
                ).fetchone()[0],
                18,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM facts
                    WHERE review_batch_id=(SELECT id FROM review_batches WHERE row_count=25)
                      AND verification_status='catalog_verified' AND is_current=1
                    """
                ).fetchone()[0],
                200,
            )
            connection.close()


if __name__ == "__main__":
    unittest.main()
