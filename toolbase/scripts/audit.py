#!/usr/bin/env python3
"""Read-only audit for the canonical CNC Toolbase database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def scalar(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return connection.execute(sql, params).fetchone()[0]


def rows(connection: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def audit(path: Path) -> dict[str, Any]:
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    integrity = scalar(connection, "PRAGMA integrity_check")
    if integrity != "ok":
        errors.append({"code": "integrity", "message": integrity})
    foreign_keys = rows(connection, "PRAGMA foreign_key_check")
    if foreign_keys:
        errors.append(
            {"code": "foreign_keys", "message": "Foreign key violations found", "count": len(foreign_keys)}
        )

    required_tables = {
        "schema_meta",
        "manufacturers",
        "tools",
        "sources",
        "review_batches",
        "shop_input_batches",
        "reviewed_tool_tags",
        "tool_sources",
        "facts",
        "fact_sources",
        "work_material_groups",
        "tool_material_recommendations",
        "tool_material_recommendation_sources",
        "cutting_data_profiles",
        "interfaces",
        "compatibility_claims",
        "compatibility_claim_sources",
    }
    actual_tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing_tables = sorted(required_tables - actual_tables)
    if missing_tables:
        errors.append({"code": "schema", "message": "Required tables are missing", "tables": missing_tables})

    counts = {
        table: scalar(connection, f"SELECT COUNT(*) FROM {table}")
        for table in sorted(required_tables - {"schema_meta"})
        if table in actual_tables
    }
    if counts.get("tools", 0) < 1212:
        errors.append(
            {
                "code": "tool_loss",
                "message": "Canonical database contains fewer tools than the preserved seed",
                "count": counts.get("tools", 0),
            }
        )

    duplicate_parts = rows(
        connection,
        """
        SELECT manufacturer_id, normalized_part_number, COUNT(*) AS count
        FROM tools GROUP BY manufacturer_id, normalized_part_number HAVING COUNT(*) > 1
        """,
    )
    if duplicate_parts:
        errors.append(
            {"code": "duplicate_part", "message": "Duplicate normalized manufacturer part numbers", "count": len(duplicate_parts)}
        )

    stations_without_interface = scalar(
        connection,
        """
        SELECT COUNT(*) FROM tools t
        WHERE t.component_type='station'
          AND NOT EXISTS (
            SELECT 1 FROM interfaces i
            WHERE i.tool_id=t.id AND i.interface_role='accepts'
          )
        """,
    )
    if stations_without_interface:
        errors.append(
            {
                "code": "station_without_interface",
                "message": "Machine stations must state the physical interface they accept",
                "count": stations_without_interface,
            }
        )

    invalid_exact_station_fit = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM compatibility_claims c
        JOIN tools station ON station.id=c.subject_tool_id
        JOIN tools fitted_tool ON fitted_tool.id=c.object_tool_id
        WHERE c.generated_by='shop_input_exact_interface_match'
          AND (
            station.component_type != 'station'
            OR c.relationship NOT IN ('accepts_holder', 'accepts_shank')
            OR (c.relationship='accepts_holder' AND fitted_tool.component_type != 'holder')
            OR (c.relationship='accepts_shank' AND fitted_tool.component_type != 'shank')
            OR c.evidence_status != 'shop_verified'
            OR c.review_status != 'accepted'
            OR c.confidence != 1.0
            OR c.suppressed != 0
            OR NOT EXISTS (
              SELECT 1 FROM compatibility_claim_sources source_link
              WHERE source_link.claim_id=c.id AND source_link.evidence_role='primary_source'
            )
            OR NOT EXISTS (
              SELECT 1 FROM compatibility_claim_sources source_link
              WHERE source_link.claim_id=c.id AND source_link.evidence_role='derivation_input'
            )
            OR NOT EXISTS (
              SELECT 1
              FROM interfaces station_interface
              JOIN interfaces tool_interface
                ON tool_interface.interface_type=station_interface.interface_type
               AND tool_interface.shape=station_interface.shape
               AND tool_interface.size_mm=station_interface.size_mm
              WHERE station_interface.tool_id=station.id
                AND station_interface.interface_role='accepts'
                AND tool_interface.tool_id=fitted_tool.id
                AND tool_interface.interface_role='provides'
            )
          )
        """,
    )
    if invalid_exact_station_fit:
        errors.append(
            {
                "code": "invalid_exact_station_fit",
                "message": "Shop-verified station fit must have matching typed station and tool interfaces",
                "count": invalid_exact_station_fit,
            }
        )

    old_alias_rows = scalar(connection, "SELECT COUNT(*) FROM manufacturers WHERE name='Horn'")
    if old_alias_rows:
        errors.append({"code": "manufacturer_alias", "message": "Horn was not canonicalized to PH Horn"})

    placeholder_rows = scalar(
        connection,
        """
        SELECT COUNT(*) FROM tools
        WHERE lower(coalesce(grade, '') || ' ' || coalesce(size, '') || ' ' || coalesce(geometry, ''))
          LIKE '%to be verified%'
        """,
    )
    if placeholder_rows:
        errors.append(
            {"code": "typed_placeholder", "message": "Placeholder prose remains in typed columns", "count": placeholder_rows}
        )

    direct_machine = rows(
        connection,
        """
        SELECT t.component_type, c.suppressed, COUNT(*) AS count
        FROM compatibility_claims c
        JOIN tools t ON t.id = c.subject_tool_id
        WHERE c.relationship = 'compatible_with_machine'
        GROUP BY t.component_type, c.suppressed
        ORDER BY count DESC
        """,
    )
    unsuppressed_direct_machine = sum(row["count"] for row in direct_machine if row["suppressed"] == 0)
    if unsuppressed_direct_machine:
        errors.append(
            {
                "code": "invalid_machine_shortcut",
                "message": "Direct machine claims bypass the required physical stack",
                "count": unsuppressed_direct_machine,
            }
        )

    tools_without_source = scalar(
        connection,
        "SELECT COUNT(*) FROM tools t WHERE NOT EXISTS (SELECT 1 FROM tool_sources ts WHERE ts.tool_id=t.id)",
    )
    if tools_without_source:
        warnings.append(
            {
                "code": "tools_without_source",
                "message": "Tools need source evidence before typed facts can be trusted",
                "count": tools_without_source,
            }
        )

    facts_without_source = scalar(
        connection,
        """
        SELECT COUNT(*) FROM facts f
        WHERE NOT EXISTS (SELECT 1 FROM fact_sources fs WHERE fs.fact_id=f.id)
        """,
    )
    if facts_without_source:
        warnings.append(
            {
                "code": "facts_without_source",
                "message": "Imported facts have no source lineage because their parent tool has no source",
                "count": facts_without_source,
            }
        )

    material_recommendations_without_source = scalar(
        connection,
        """
        SELECT COUNT(*) FROM tool_material_recommendations r
        WHERE NOT EXISTS (
          SELECT 1 FROM tool_material_recommendation_sources rs WHERE rs.recommendation_id=r.id
        )
        """,
    )
    if material_recommendations_without_source:
        errors.append(
            {
                "code": "material_recommendation_without_source",
                "message": "Material recommendations must retain explicit source lineage",
                "count": material_recommendations_without_source,
            }
        )

    sources_without_locator = scalar(
        connection,
        """
        SELECT COUNT(*) FROM sources
        WHERE coalesce(trim(url), '') = ''
          AND coalesce(trim(local_path), '') = ''
          AND coalesce(trim(page_ref), '') = ''
        """,
    )
    if sources_without_locator:
        warnings.append(
            {
                "code": "source_without_locator",
                "message": "Source references lack a URL, local file, and page reference",
                "count": sources_without_locator,
            }
        )

    claims_without_any_lineage = scalar(
        connection,
        """
        SELECT COUNT(*) FROM compatibility_claims c
        WHERE NOT EXISTS (
          SELECT 1 FROM compatibility_claim_sources cs WHERE cs.claim_id=c.id
        )
        """,
    )
    if claims_without_any_lineage:
        errors.append(
            {
                "code": "claim_without_lineage",
                "message": "Compatibility claims must retain either primary evidence or derivation context",
                "count": claims_without_any_lineage,
            }
        )

    claims_without_primary_source = rows(
        connection,
        """
        SELECT c.evidence_status, COUNT(*) AS count
        FROM compatibility_claims c
        WHERE NOT EXISTS (
          SELECT 1 FROM compatibility_claim_sources cs
          WHERE cs.claim_id=c.id AND cs.evidence_role='primary_source'
        )
        GROUP BY c.evidence_status ORDER BY count DESC
        """,
    )
    if claims_without_primary_source:
        warnings.append(
            {
                "code": "claims_without_primary_source",
                "message": "Legacy compatibility candidates have auditable context or derivation inputs, but not direct proof",
                "groups": claims_without_primary_source,
            }
        )

    pending_claims = scalar(
        connection,
        "SELECT COUNT(*) FROM compatibility_claims WHERE review_status='needs_review'",
    )
    if pending_claims:
        warnings.append(
            {
                "code": "claims_need_review",
                "message": "Compatibility claims remain candidates until reviewed",
                "count": pending_claims,
            }
        )

    verified_cutting_data = scalar(
        connection,
        "SELECT COUNT(*) FROM usable_cutting_data",
    )
    if verified_cutting_data == 0:
        warnings.append(
            {
                "code": "no_verified_cutting_data",
                "message": "No source-reviewed speeds and feeds are available yet; the UI must say so explicitly",
                "count": 0,
            }
        )

    incomplete_verified_cutting_data = scalar(
        connection,
        """
        SELECT COUNT(*) FROM usable_cutting_data
        WHERE coalesce(trim(source_page_ref), '') = ''
           OR coalesce(trim(source_table_ref), '') = ''
           OR coalesce(trim(source_raw_text), '') = ''
           OR coalesce(trim(reviewer), '') = ''
           OR coalesce(trim(reviewed_at), '') = ''
        """,
    )
    if incomplete_verified_cutting_data:
        errors.append(
            {
                "code": "incomplete_verified_cutting_data",
                "message": "Verified cutting profiles must retain source-page and human-review evidence",
                "count": incomplete_verified_cutting_data,
            }
        )

    tools_with_materials = scalar(
        connection,
        "SELECT COUNT(DISTINCT tool_id) FROM tool_material_recommendations",
    )
    if tools_with_materials < counts.get("tools", 0):
        warnings.append(
            {
                "code": "incomplete_material_coverage",
                "message": "Only explicit structured material groups were promoted; tags were not treated as evidence",
                "count": tools_with_materials,
            }
        )

    evidence_counts = rows(
        connection,
        "SELECT evidence_status, COUNT(*) AS count FROM tools GROUP BY evidence_status ORDER BY count DESC",
    )
    component_counts = rows(
        connection,
        "SELECT component_type, COUNT(*) AS count FROM tools GROUP BY component_type ORDER BY count DESC",
    )
    relationship_counts = rows(
        connection,
        """
        SELECT relationship, evidence_status, review_status, suppressed, COUNT(*) AS count
        FROM compatibility_claims
        GROUP BY relationship, evidence_status, review_status, suppressed
        ORDER BY count DESC
        """,
    )
    source_counts = rows(
        connection,
        "SELECT source_type, COUNT(*) AS count FROM sources GROUP BY source_type ORDER BY count DESC",
    )
    numeric_fact_counts = rows(
        connection,
        """
        SELECT fact_key, COUNT(*) AS count
        FROM facts WHERE value_number IS NOT NULL
        GROUP BY fact_key ORDER BY count DESC LIMIT 25
        """,
    )
    lineage_role_counts = {
        "facts": rows(
            connection,
            "SELECT evidence_role, COUNT(*) AS count FROM fact_sources GROUP BY evidence_role ORDER BY count DESC",
        ),
        "materials": rows(
            connection,
            """
            SELECT evidence_role, COUNT(*) AS count
            FROM tool_material_recommendation_sources
            GROUP BY evidence_role ORDER BY count DESC
            """,
        ),
        "compatibility": rows(
            connection,
            """
            SELECT evidence_role, COUNT(*) AS count
            FROM compatibility_claim_sources
            GROUP BY evidence_role ORDER BY count DESC
            """,
        ),
    }
    connection.close()

    return {
        "database": str(path),
        "integrity": integrity,
        "foreign_key_issues": len(foreign_keys),
        "counts": counts,
        "component_counts": component_counts,
        "evidence_counts": evidence_counts,
        "source_counts": source_counts,
        "relationship_counts": relationship_counts,
        "direct_machine_claims": direct_machine,
        "top_numeric_facts": numeric_fact_counts,
        "verified_cutting_data": verified_cutting_data,
        "tools_with_material_recommendations": tools_with_materials,
        "facts_without_source": facts_without_source,
        "material_recommendations_without_source": material_recommendations_without_source,
        "claims_without_any_lineage": claims_without_any_lineage,
        "lineage_role_counts": lineage_role_counts,
        "errors": errors,
        "warnings": warnings,
        "status": "error" if errors else "warning" if warnings else "ok",
    }


def human(report: dict[str, Any]) -> str:
    lines = [
        f"Canonical database: {report['database']}",
        f"Status: {report['status']}",
        f"Integrity: {report['integrity']}; foreign key issues: {report['foreign_key_issues']}",
        "Counts: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()),
    ]
    if report["errors"]:
        lines.append("Errors:")
        lines.extend(f"  - {item['code']}: {item['message']}" for item in report["errors"])
    if report["warnings"]:
        lines.append("Warnings:")
        lines.extend(
            f"  - {item['code']}: {item['message']}"
            + (f" ({item['count']})" if "count" in item else "")
            for item in report["warnings"]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", nargs="?", type=Path, default=ROOT / "build" / "toolbase.sqlite")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as a failing exit status")
    args = parser.parse_args()

    report = audit(args.database.resolve())
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else human(report))
    if report["errors"] or (args.strict and report["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
