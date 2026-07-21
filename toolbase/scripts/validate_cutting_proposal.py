#!/usr/bin/env python3
"""Validate a review-only cutting-data proposal without importing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROPOSAL = REPO_ROOT / "toolbase" / "proposals" / "kennametal-topswiss-pilot.json"
DEFAULT_DB = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
DEFAULT_LEDGER = REPO_ROOT / "toolbase" / "reviews" / "kennametal-topswiss-pilot.decisions.json"
ALLOWED_ISO_GROUPS = {"P", "M", "K", "N", "S", "H", "O", "unknown"}
ALLOWED_SPEED_UNITS = {"m_per_min", "sfm"}
ALLOWED_FEED_UNITS = {"mm_per_rev", "ipr", "mm_per_tooth", "ipt", "mm_per_min"}
ALLOWED_DOC_UNITS = {"mm", "in"}
ALLOWED_DECISIONS = {"pending", "approved", "approved_with_corrections", "needs_evidence", "rejected"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def require(mapping: dict[str, Any], key: str, context: str, errors: list[str]) -> Any:
    value = mapping.get(key)
    if value is None or value == "":
        errors.append(f"{context}: missing {key}")
    return value


def validate_range(
    value: Any,
    context: str,
    allowed_units: set[str],
    pages: int,
    errors: list[str],
    *,
    require_start: bool = False,
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{context}: expected an object")
        return
    minimum = value.get("min")
    maximum = value.get("max")
    start = value.get("start")
    for field, number in (("min", minimum), ("max", maximum)):
        if not isinstance(number, (int, float)) or number < 0:
            errors.append(f"{context}: {field} must be a non-negative number")
    if require_start and (not isinstance(start, (int, float)) or start < 0):
        errors.append(f"{context}: start must be a non-negative number")
    if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum > maximum:
        errors.append(f"{context}: min exceeds max")
    if (
        require_start
        and isinstance(minimum, (int, float))
        and isinstance(start, (int, float))
        and isinstance(maximum, (int, float))
        and not minimum <= start <= maximum
    ):
        errors.append(f"{context}: start must fall between min and max")
    if value.get("unit") not in allowed_units:
        errors.append(f"{context}: unsupported unit {value.get('unit')!r}")
    page = value.get("source_page")
    if not isinstance(page, int) or not 1 <= page <= pages:
        errors.append(f"{context}: source_page must be within the catalog")
    if not value.get("source_table"):
        errors.append(f"{context}: missing source_table")


def validate_ledger(
    ledger_path: Path,
    proposal_path: Path,
    proposal: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, int], bool]:
    counts = {decision: 0 for decision in ALLOWED_DECISIONS}
    if not ledger_path.is_file():
        errors.append(f"ledger: file not found: {ledger_path}")
        return counts, False
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != 1:
        errors.append("ledger: schema_version must be 1")
    if ledger.get("proposal_id") != proposal.get("proposal_id"):
        errors.append("ledger: proposal_id does not match proposal")
    if ledger.get("proposal_sha256") != sha256(proposal_path):
        errors.append("ledger: proposal SHA-256 does not match the reviewed proposal")
    if ledger.get("catalog_sha256") != (proposal.get("source") or {}).get("sha256"):
        errors.append("ledger: catalog SHA-256 does not match proposal source")
    import_allowed = ledger.get("import_allowed")
    if not isinstance(import_allowed, bool):
        errors.append("ledger: import_allowed must be a boolean")
        import_allowed = False

    decisions = ledger.get("decisions")
    if not isinstance(decisions, list):
        errors.append("ledger: decisions must be an array")
        return counts, False
    proposal_rows = {
        row.get("proposal_row_id"): row.get("tool_lookup", {}).get("tool_id")
        for row in proposal.get("rows") or []
    }
    decision_rows: dict[str, str] = {}
    for index, decision_row in enumerate(decisions, start=1):
        context = f"ledger decision {index}"
        if not isinstance(decision_row, dict):
            errors.append(f"{context}: expected an object")
            continue
        row_id = decision_row.get("proposal_row_id")
        if row_id in decision_rows:
            errors.append(f"{context}: duplicate proposal_row_id {row_id}")
        decision_rows[str(row_id)] = str(decision_row.get("tool_id"))
        if row_id not in proposal_rows:
            errors.append(f"{context}: proposal_row_id is not in the proposal")
        elif decision_row.get("tool_id") != proposal_rows[row_id]:
            errors.append(f"{context}: tool_id does not match proposal row")
        decision = decision_row.get("decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"{context}: unsupported decision {decision!r}")
            continue
        counts[decision] += 1
        if decision != "pending":
            for field in ("reviewer", "decided_at", "capture_method", "notes"):
                if not decision_row.get(field):
                    errors.append(f"{context}: {field} is required for a completed decision")
        if decision == "approved_with_corrections":
            if not decision_row.get("corrections"):
                errors.append(f"{context}: corrections are required")
            if not decision_row.get("canonical_description"):
                errors.append(f"{context}: canonical_description is required")
    if set(decision_rows) != set(proposal_rows):
        errors.append("ledger: decisions must cover every proposal row exactly once")
    expected_status = "complete" if counts["pending"] == 0 else "in_progress"
    if ledger.get("status") != expected_status:
        errors.append(f"ledger: status must be {expected_status}")
    importable_decisions = counts["approved"] + counts["approved_with_corrections"]
    all_rows_importable = importable_decisions == len(proposal_rows)
    if import_allowed and ledger.get("status") != "complete":
        errors.append("ledger: import_allowed may be true only when status is complete")
    if import_allowed and not all_rows_importable:
        errors.append(
            "ledger: import_allowed may be true only when every row is approved or approved_with_corrections"
        )
    return counts, bool(import_allowed and all_rows_importable and ledger.get("status") == "complete")


def validate(proposal_path: Path, db_path: Path, ledger_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))

    if proposal.get("schema_version") != 1:
        errors.append("proposal: schema_version must be 1")
    if proposal.get("status") != "source_extracted":
        errors.append("proposal: status must remain source_extracted until human review")
    if proposal.get("import_allowed") is not False:
        errors.append("proposal: import_allowed must be false for this pilot")

    source = proposal.get("source") or {}
    source_path_value = require(source, "local_path", "source", errors)
    page_count = source.get("page_count")
    if not isinstance(page_count, int) or page_count < 1:
        errors.append("source: page_count must be a positive integer")
        page_count = 0
    source_path = REPO_ROOT / str(source_path_value or "")
    if not source_path.is_file():
        errors.append(f"source: file not found: {source_path}")
    elif sha256(source_path) != source.get("sha256"):
        errors.append("source: SHA-256 does not match the reviewed catalog file")
    for ambiguity in source.get("source_ambiguities") or []:
        warnings.append(f"SOURCE AMBIGUITY: {ambiguity}")

    rows = proposal.get("rows")
    if not isinstance(rows, list):
        errors.append("proposal: rows must be an array")
        rows = []
    elif not 10 <= len(rows) <= 25:
        errors.append("proposal: pilot must contain 10 to 25 rows")

    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    seen_ids: set[str] = set()
    seen_tools: set[str] = set()
    for index, row in enumerate(rows, start=1):
        context = f"row {index}"
        if not isinstance(row, dict):
            errors.append(f"{context}: expected an object")
            continue
        row_id = require(row, "proposal_row_id", context, errors)
        if row_id in seen_ids:
            errors.append(f"{context}: duplicate proposal_row_id {row_id}")
        seen_ids.add(str(row_id))

        lookup = row.get("tool_lookup") or {}
        tool_id = require(lookup, "tool_id", f"{context}.tool_lookup", errors)
        if tool_id in seen_tools:
            errors.append(f"{context}: duplicate tool_id {tool_id}")
        seen_tools.add(str(tool_id))
        db_tool = connection.execute(
            """
            SELECT t.id, t.part_number, t.grade, t.chipbreaker, t.component_type,
                   t.legacy_record_json, m.name AS manufacturer
            FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
            WHERE t.id=?
            """,
            (tool_id,),
        ).fetchone()
        if db_tool is None:
            errors.append(f"{context}: tool_id {tool_id!r} is not in the canonical database")
            continue
        if db_tool["component_type"] != "insert":
            errors.append(f"{context}: selected tool is not an insert")
        if lookup.get("manufacturer") != db_tool["manufacturer"]:
            errors.append(f"{context}: manufacturer does not match the database")

        match = row.get("source_match") or {}
        if match.get("grade") != db_tool["grade"]:
            errors.append(f"{context}: catalog grade does not match database grade")
        if match.get("geometry_code") != db_tool["chipbreaker"]:
            errors.append(f"{context}: catalog geometry code does not match database chipbreaker")
        legacy = json.loads(db_tool["legacy_record_json"])
        specs = legacy.get("specs") or {}
        if match.get("iso_catalog_number") != specs.get("iso_catalog_id"):
            errors.append(f"{context}: ISO catalog number does not match the preserved record")
        if match.get("ansi_catalog_number") != specs.get("ansi_catalog_id"):
            errors.append(f"{context}: ANSI catalog number does not match the preserved record")
        product_page = match.get("product_page")
        if not isinstance(product_page, int) or not 1 <= product_page <= page_count:
            errors.append(f"{context}: product_page must be within the catalog")
        if match.get("grade_availability") != "listed_for_catalog_number":
            errors.append(f"{context}: grade availability must be explicitly attested")

        material = row.get("work_material") or {}
        if material.get("iso_group") not in ALLOWED_ISO_GROUPS:
            errors.append(f"{context}: invalid ISO material group")
        require(material, "subgroup", f"{context}.work_material", errors)
        require(material, "catalog_label", f"{context}.work_material", errors)

        operation = row.get("operation") or {}
        if operation.get("operation_type") != "turning":
            errors.append(f"{context}: this catalog pilot is limited to turning")
        require(operation, "catalog_cut_condition", f"{context}.operation", errors)

        parameters = row.get("parameters") or {}
        validate_range(
            parameters.get("surface_speed"),
            f"{context}.surface_speed",
            ALLOWED_SPEED_UNITS,
            page_count,
            errors,
            require_start=True,
        )
        validate_range(
            parameters.get("feed"),
            f"{context}.feed",
            ALLOWED_FEED_UNITS,
            page_count,
            errors,
        )
        validate_range(
            parameters.get("depth_of_cut"),
            f"{context}.depth_of_cut",
            ALLOWED_DOC_UNITS,
            page_count,
            errors,
        )

        evidence = row.get("evidence") or {}
        if evidence.get("verification_status") != "source_extracted":
            errors.append(f"{context}: verification_status must be source_extracted")
        if evidence.get("visual_page_check") != "complete":
            errors.append(f"{context}: visual_page_check must be complete")
        if evidence.get("reviewer") is not None or evidence.get("reviewed_at") is not None:
            errors.append(f"{context}: reviewer fields must remain empty before human review")
        require(evidence, "source_raw_text", f"{context}.evidence", errors)

        if row.get("database_cleanup_note"):
            warnings.append(f"{tool_id}: {row['database_cleanup_note']}")

    connection.close()
    decision_counts, ledger_import_allowed = validate_ledger(
        ledger_path, proposal_path, proposal, errors
    )
    return {
        "proposal": display_path(proposal_path),
        "database": display_path(db_path),
        "ledger": display_path(ledger_path),
        "rows": len(rows),
        "decision_counts": decision_counts,
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
        "import_allowed": bool(ledger_import_allowed and not errors),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate(args.proposal.resolve(), args.db.resolve(), args.ledger.resolve())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = "VALID" if result["valid"] else "INVALID"
        import_state = str(result["import_allowed"]).lower()
        print(f"{state}: {result['rows']} review rows; import_allowed={import_state}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
