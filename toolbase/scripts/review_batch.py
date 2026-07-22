#!/usr/bin/env python3
"""Validate, scaffold, and compile auditable tool review batches.

Proposal schema 2 is deliberately review-only.  The public database build reads
only compiled packets in ``toolbase/data/reviewed_imports``; this script refuses
to compile a packet until every proposal row has a terminal human decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
ALLOWED_DECISIONS = {
    "pending",
    "approved",
    "approved_with_corrections",
    "rejected",
    "quarantined",
}
TERMINAL_DECISIONS = ALLOWED_DECISIONS - {"pending"}
VERIFICATION_BY_SOURCE = {
    "manufacturer_catalog": "catalog_verified",
    "manufacturer_product_page": "manufacturer_verified",
    "manufacturer_technical_guide": "manufacturer_verified",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def evidence_for(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("evidence")
    return value if isinstance(value, dict) else {}


def validate_proposal(proposal_path: Path, database_path: Path) -> tuple[dict[str, Any], list[str]]:
    proposal = read_json(proposal_path)
    errors: list[str] = []
    if proposal.get("schema_version") != 2:
        errors.append("proposal: schema_version must be 2")
    if proposal.get("status") != "source_extracted":
        errors.append("proposal: status must remain source_extracted")
    if proposal.get("import_allowed") is not False:
        errors.append("proposal: import_allowed must be false")
    for key in ("proposal_id", "title", "created_at"):
        if not proposal.get(key):
            errors.append(f"proposal: missing {key}")

    sources = proposal.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("proposal: sources must contain at least one source")
        sources = []
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources, 1):
        context = f"source {index}"
        source_id = source.get("source_id")
        if not source_id:
            errors.append(f"{context}: missing source_id")
            continue
        if source_id in source_by_id:
            errors.append(f"{context}: duplicate source_id {source_id}")
        source_by_id[source_id] = source
        for key in ("manufacturer", "title", "source_type", "content_sha256"):
            if not source.get(key):
                errors.append(f"{context}: missing {key}")
        local = repo_path(source.get("local_path"))
        if local:
            if not local.is_file():
                errors.append(f"{context}: local source is missing: {display_path(local)}")
            else:
                actual_hash = file_sha256(local)
                if source.get("content_sha256") != actual_hash:
                    errors.append(f"{context}: SHA-256 does not match local source")
        elif not source.get("url"):
            errors.append(f"{context}: a local_path or url is required")

    rows = proposal.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 25:
        errors.append("proposal: rows must contain 1 through 25 tools")
        rows = []
    row_ids: set[str] = set()
    tool_ids: set[str] = set()
    connection = sqlite3.connect(database_path)
    try:
        for index, row in enumerate(rows, 1):
            context = f"row {index}"
            row_id = row.get("proposal_row_id")
            lookup = row.get("tool_lookup") or {}
            tool_id = lookup.get("tool_id")
            if not row_id:
                errors.append(f"{context}: missing proposal_row_id")
            elif row_id in row_ids:
                errors.append(f"{context}: duplicate proposal_row_id {row_id}")
            row_ids.add(row_id)
            if not tool_id:
                errors.append(f"{context}: missing tool_lookup.tool_id")
                continue
            if tool_id in tool_ids:
                errors.append(f"{context}: duplicate tool id {tool_id}")
            tool_ids.add(tool_id)
            db_row = connection.execute(
                """
                SELECT t.id, m.name, t.component_type
                FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
                WHERE t.id=?
                """,
                (tool_id,),
            ).fetchone()
            if not db_row:
                errors.append(f"{context}: database tool does not exist: {tool_id}")
                continue
            if lookup.get("manufacturer") and lookup["manufacturer"] != db_row[1]:
                errors.append(f"{context}: manufacturer does not match database")
            if lookup.get("component_type") and lookup["component_type"] != db_row[2]:
                errors.append(f"{context}: component_type does not match database")

            proposed = row.get("proposed")
            if not isinstance(proposed, dict):
                errors.append(f"{context}: proposed object is required")
                continue
            assertion_groups = (
                "facts",
                "grade_options",
                "material_recommendations",
                "cutting_profiles",
            )
            if not any(proposed.get(group) for group in assertion_groups):
                errors.append(f"{context}: no auditable assertions were proposed")
            for group in assertion_groups:
                for item_index, item in enumerate(proposed.get(group) or [], 1):
                    item_context = f"{context} {group}[{item_index}]"
                    evidence = evidence_for(item)
                    source_id = evidence.get("source_id") or item.get("source_id")
                    if source_id not in source_by_id:
                        errors.append(f"{item_context}: evidence source is missing from proposal")
                        continue
                    page = evidence.get("pdf_page")
                    source = source_by_id[source_id]
                    if source.get("local_path"):
                        if not isinstance(page, int):
                            errors.append(f"{item_context}: pdf_page is required for a catalog assertion")
                        elif not 1 <= page <= int(source.get("page_count") or 0):
                            errors.append(f"{item_context}: pdf_page is outside the source")
                    if not evidence.get("source_table_ref"):
                        errors.append(f"{item_context}: source_table_ref is required")
                    if not evidence.get("source_raw_text"):
                        errors.append(f"{item_context}: source_raw_text is required")

            for profile_index, profile in enumerate(proposed.get("cutting_profiles") or [], 1):
                context_profile = f"{context} cutting_profiles[{profile_index}]"
                for key in (
                    "source_part_number",
                    "source_grade",
                    "source_geometry",
                    "source_chipbreaker",
                    "source_material_label",
                    "iso_material_group",
                    "operation_type",
                    "cut_condition",
                ):
                    if not profile.get(key):
                        errors.append(f"{context_profile}: missing {key}")
                for prefix in ("surface_speed", "feed", "depth_of_cut"):
                    minimum = profile.get(f"{prefix}_min")
                    maximum = profile.get(f"{prefix}_max")
                    unit = profile.get(f"{prefix}_unit")
                    if minimum is None and maximum is None:
                        continue
                    if minimum is not None and not isinstance(minimum, (int, float)):
                        errors.append(f"{context_profile}: {prefix} minimum must be numeric when stated")
                    if maximum is not None and not isinstance(maximum, (int, float)):
                        errors.append(f"{context_profile}: {prefix} maximum must be numeric when stated")
                    if (
                        isinstance(minimum, (int, float))
                        and isinstance(maximum, (int, float))
                        and minimum > maximum
                    ):
                        errors.append(f"{context_profile}: {prefix} minimum exceeds maximum")
                    if not unit:
                        errors.append(f"{context_profile}: {prefix}_unit is required")

                speed_start = profile.get("surface_speed_start")
                speed_min = profile.get("surface_speed_min")
                speed_max = profile.get("surface_speed_max")
                if speed_start is not None and not (
                    isinstance(speed_min, (int, float))
                    and isinstance(speed_max, (int, float))
                    and speed_min <= speed_start <= speed_max
                ):
                    errors.append(f"{context_profile}: surface speed start is outside the range")
    finally:
        connection.close()
    return proposal, errors


def validate_ledger(
    proposal_path: Path,
    proposal: dict[str, Any],
    ledger_path: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not ledger_path.is_file():
        return None, [f"ledger: file not found: {display_path(ledger_path)}"]
    ledger = read_json(ledger_path)
    if ledger.get("schema_version") != 2:
        errors.append("ledger: schema_version must be 2")
    if ledger.get("proposal_id") != proposal.get("proposal_id"):
        errors.append("ledger: proposal_id does not match")
    if ledger.get("proposal_sha256") != file_sha256(proposal_path):
        errors.append("ledger: proposal SHA-256 does not match")
    decisions = ledger.get("decisions")
    if not isinstance(decisions, list):
        errors.append("ledger: decisions must be a list")
        decisions = []
    expected_rows = {row["proposal_row_id"]: row for row in proposal.get("rows") or []}
    seen: set[str] = set()
    for index, decision in enumerate(decisions, 1):
        context = f"ledger decision {index}"
        row_id = decision.get("proposal_row_id")
        if row_id not in expected_rows:
            errors.append(f"{context}: unknown proposal row {row_id!r}")
            continue
        if row_id in seen:
            errors.append(f"{context}: duplicate decision for {row_id}")
        seen.add(row_id)
        expected_tool = (expected_rows[row_id].get("tool_lookup") or {}).get("tool_id")
        if decision.get("tool_id") != expected_tool:
            errors.append(f"{context}: tool_id does not match proposal")
        if decision.get("decision") not in ALLOWED_DECISIONS:
            errors.append(f"{context}: invalid decision {decision.get('decision')!r}")
        if decision.get("decision") in TERMINAL_DECISIONS:
            for key in ("reviewer", "decided_at"):
                if not decision.get(key):
                    errors.append(f"{context}: terminal decision requires {key}")
        if decision.get("decision") == "approved_with_corrections" and not isinstance(
            decision.get("corrected_proposed"), dict
        ):
            errors.append(f"{context}: corrected_proposed is required")
        if decision.get("decision") in {"rejected", "quarantined"} and not decision.get("notes"):
            errors.append(f"{context}: rejection/quarantine reason is required")
    missing = sorted(set(expected_rows) - seen)
    if missing:
        errors.append(f"ledger: missing decisions for {', '.join(missing)}")
    complete = len(decisions) == len(expected_rows) and all(
        decision.get("decision") in TERMINAL_DECISIONS for decision in decisions
    )
    if ledger.get("status") == "complete" and not complete:
        errors.append("ledger: status cannot be complete while decisions are pending")
    if ledger.get("import_allowed") is True and not complete:
        errors.append("ledger: import_allowed cannot be true while decisions are pending")
    if complete and (ledger.get("status") != "complete" or ledger.get("import_allowed") is not True):
        errors.append("ledger: terminal decisions require status complete and import_allowed true")
    return ledger, errors


def assertion_evidence(
    item: dict[str, Any], source_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], str, str]:
    evidence = evidence_for(item)
    source_id = evidence.get("source_id") or item.get("source_id")
    source = source_by_id[source_id]
    verification = VERIFICATION_BY_SOURCE.get(source.get("source_type"), "source_extracted")
    evidence_status = (
        "manufacturer_claim" if verification == "manufacturer_verified" else "catalog_claim"
    )
    return evidence, verification, evidence_status


def compile_row(
    row: dict[str, Any],
    decision: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    proposed = deepcopy(
        decision.get("corrected_proposed")
        if decision["decision"] == "approved_with_corrections"
        else row["proposed"]
    )
    tool_id = row["tool_lookup"]["tool_id"]
    reviewer = decision["reviewer"]
    reviewed_at = decision["decided_at"]
    tool_updates = proposed.get("tool_updates") or {}
    compiled: dict[str, Any] = {
        "proposal_row_id": row["proposal_row_id"],
        "tool_id": tool_id,
        "decision": decision["decision"],
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "tool_updates": {
            "description": tool_updates.get("description"),
            "geometry": tool_updates.get("geometry") or row.get("current_summary", {}).get("geometry") or "unknown",
            "lifecycle_status": tool_updates.get("lifecycle_status") or "unknown",
            "evidence_status": "catalog_source",
            "grade": tool_updates.get("grade"),
            "grade_reviewed": "grade" in tool_updates,
            "chipbreaker": tool_updates.get("chipbreaker"),
            "chipbreaker_reviewed": "chipbreaker" in tool_updates,
        },
        "aliases": proposed.get("aliases") or [],
        "source_ids": sorted(
            {
                (evidence_for(item).get("source_id") or item.get("source_id"))
                for group in (
                    "facts",
                    "grade_options",
                    "material_recommendations",
                    "cutting_profiles",
                )
                for item in proposed.get(group) or []
                if evidence_for(item).get("source_id") or item.get("source_id")
            }
        ),
        "tags": proposed.get("tags") or [],
        "replace_fact_keys": proposed.get("replace_fact_keys")
        or sorted({item["fact_key"] for item in proposed.get("facts") or []}),
        "facts": [],
        "grade_options": [],
        "reject_grade_codes": proposed.get("reject_grade_codes") or [],
        "replace_material_recommendations": bool(proposed.get("replace_material_recommendations")),
        "material_recommendations": [],
        "cutting_profiles": [],
    }

    for item in proposed.get("facts") or []:
        evidence, verification, evidence_status = assertion_evidence(item, source_by_id)
        fact = {key: value for key, value in item.items() if key != "evidence"}
        fact.update(
            {
                "id": stable_id("fact", tool_id, item["fact_key"], item.get("value_text"), item.get("value_number"), reviewed_at),
                "original_key": item.get("original_key") or f"reviewed_{item['fact_key']}",
                "evidence_status": evidence_status,
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_ids": evidence.get("source_ids") or [evidence["source_id"]],
                "source_page_ref": f"PDF page {evidence['pdf_page']}" if evidence.get("pdf_page") else evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
            }
        )
        compiled["facts"].append(fact)

    for item in proposed.get("grade_options") or []:
        evidence, verification, _ = assertion_evidence(item, source_by_id)
        option = {key: value for key, value in item.items() if key != "evidence"}
        option.update(
            {
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_page_ref": f"PDF page {evidence['pdf_page']}" if evidence.get("pdf_page") else evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
            }
        )
        compiled["grade_options"].append(option)

    for item in proposed.get("material_recommendations") or []:
        evidence, verification, evidence_status = assertion_evidence(item, source_by_id)
        recommendation = {key: value for key, value in item.items() if key != "evidence"}
        recommendation.update(
            {
                "id": stable_id("material", tool_id, item.get("grade_code"), item["iso_group"], item.get("material_subgroup"), reviewed_at),
                "evidence_status": evidence_status,
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_ids": evidence.get("source_ids") or [evidence["source_id"]],
                "source_page_ref": f"PDF page {evidence['pdf_page']}" if evidence.get("pdf_page") else evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
            }
        )
        compiled["material_recommendations"].append(recommendation)

    for item in proposed.get("cutting_profiles") or []:
        evidence, verification, _ = assertion_evidence(item, source_by_id)
        profile = {key: value for key, value in item.items() if key != "evidence"}
        profile.update(
            {
                "id": stable_id("cutting-profile", tool_id, item.get("source_grade"), item.get("material_subgroup"), item.get("cut_condition"), reviewed_at),
                "source_id": evidence["source_id"],
                "source_page_ref": f"PDF page {evidence['pdf_page']}" if evidence.get("pdf_page") else evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
                "verification_status": verification,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "notes": decision.get("notes"),
                "coolant_condition": item.get("coolant_condition") or "unknown",
            }
        )
        profile["evidence_sources"] = evidence.get("sources") or [
            {
                "source_id": evidence["source_id"],
                "evidence_role": role,
                "source_page_ref": profile["source_page_ref"],
                "source_table_ref": profile["source_table_ref"],
                "source_raw_text": profile["source_raw_text"],
                "extraction_method": profile["extraction_method"],
            }
            for role in ("identity", "geometry_parameters", "cutting_speed")
        ]
        compiled["cutting_profiles"].append(profile)
    return compiled


def scaffold(proposal_path: Path, output_path: Path) -> None:
    proposal = read_json(proposal_path)
    payload = {
        "schema_version": 2,
        "review_id": f"{proposal['proposal_id']}-review",
        "proposal_id": proposal["proposal_id"],
        "proposal_path": display_path(proposal_path),
        "proposal_sha256": file_sha256(proposal_path),
        "review_started_at": str(date.today()),
        "status": "pending",
        "review_completed_at": None,
        "import_allowed": False,
        "decisions": [
            {
                "proposal_row_id": row["proposal_row_id"],
                "tool_id": row["tool_lookup"]["tool_id"],
                "decision": "pending",
                "reviewer": None,
                "decided_at": None,
                "capture_method": "local_review_screen",
                "notes": None,
            }
            for row in proposal.get("rows") or []
        ],
    }
    write_json(output_path, payload)


def compile_packet(
    proposal_path: Path,
    proposal: dict[str, Any],
    ledger_path: Path,
    ledger: dict[str, Any],
    output_path: Path,
) -> None:
    decision_by_row = {item["proposal_row_id"]: item for item in ledger["decisions"]}
    source_by_id = {item["source_id"]: item for item in proposal["sources"]}
    primary_source = next(
        (item for item in proposal["sources"] if item.get("batch_role") == "primary_catalog"),
        proposal["sources"][0],
    )
    approved_rows: list[dict[str, Any]] = []
    quarantined_rows: list[dict[str, Any]] = []
    for row in proposal["rows"]:
        decision = decision_by_row[row["proposal_row_id"]]
        if decision["decision"] in {"approved", "approved_with_corrections"}:
            approved_rows.append(compile_row(row, decision, source_by_id))
        else:
            quarantined_rows.append(
                {
                    "proposal_row_id": row["proposal_row_id"],
                    "tool_id": row["tool_lookup"]["tool_id"],
                    "decision": decision["decision"],
                    "reason": decision["notes"],
                    "reviewer": decision["reviewer"],
                    "reviewed_at": decision["decided_at"],
                }
            )
    reviewed_at = ledger.get("review_completed_at") or max(
        item["decided_at"] for item in ledger["decisions"]
    )
    packet_sources = []
    review_sources = []
    for source in proposal["sources"]:
        packet_sources.append(
            {
                "id": source["source_id"],
                "source_type": source["source_type"],
                "title": source["title"],
                "url": source.get("url"),
                "local_path": source.get("local_path"),
                "page_ref": source.get("page_ref"),
                "manufacturer": source.get("manufacturer"),
                "raw_reference": source.get("raw_reference")
                or f"{source.get('local_path') or source.get('url')} | SHA-256 {source['content_sha256']}",
                "content_sha256": source.get("content_sha256"),
                "document_edition": source.get("document_edition"),
                "notes": source.get("edition_evidence") or source.get("notes"),
            }
        )
        review_sources.append(
            {
                "source_id": source["source_id"],
                "evidence_role": source.get("batch_role") or "supporting_source",
                "content_sha256": source.get("content_sha256"),
                "document_edition": source.get("document_edition"),
                "page_ref": source.get("page_ref"),
            }
        )
    packet = {
        "schema_version": 2,
        "import_id": stable_id("review-batch", proposal["proposal_id"], file_sha256(ledger_path)),
        "proposal_id": proposal["proposal_id"],
        "proposal_path": display_path(proposal_path),
        "proposal_sha256": file_sha256(proposal_path),
        "review_ledger_path": display_path(ledger_path),
        "review_ledger_sha256": file_sha256(ledger_path),
        "catalog_sha256": primary_source["content_sha256"],
        "catalog_source_id": primary_source["source_id"],
        "reviewed_at": reviewed_at,
        "row_count": len(approved_rows) + len(quarantined_rows),
        "sources": packet_sources,
        "review_sources": review_sources,
        "rows": approved_rows,
        "quarantined_rows": quarantined_rows,
    }
    write_json(output_path, packet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scaffold_parser = subparsers.add_parser("scaffold-ledger")
    scaffold_parser.add_argument("--proposal", type=Path, required=True)
    scaffold_parser.add_argument("--out", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--proposal", type=Path, required=True)
    validate_parser.add_argument("--ledger", type=Path)
    validate_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--proposal", type=Path, required=True)
    compile_parser.add_argument("--ledger", type=Path, required=True)
    compile_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    compile_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    proposal_path = args.proposal.resolve()
    if args.command == "scaffold-ledger":
        scaffold(proposal_path, args.out.resolve())
        print(json.dumps({"status": "created", "ledger": display_path(args.out)}, indent=2))
        return 0

    proposal, errors = validate_proposal(proposal_path, args.db.resolve())
    ledger = None
    if args.ledger:
        ledger, ledger_errors = validate_ledger(proposal_path, proposal, args.ledger.resolve())
        errors.extend(ledger_errors)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, indent=2), file=sys.stderr)
        return 1
    if args.command == "compile":
        if not ledger or ledger.get("status") != "complete" or ledger.get("import_allowed") is not True:
            print("ledger does not authorize import", file=sys.stderr)
            return 1
        compile_packet(proposal_path, proposal, args.ledger.resolve(), ledger, args.out.resolve())
        print(json.dumps({"status": "compiled", "packet": display_path(args.out)}, indent=2))
    else:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "proposal": display_path(proposal_path),
                    "rows": len(proposal.get("rows") or []),
                    "ledger": display_path(args.ledger) if args.ledger else None,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
