#!/usr/bin/env python3
"""Create the first 25-row Kennametal identity/geometry review proposal."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
DEFAULT_MANIFEST = REPO_ROOT / "toolbase" / "data" / "source_documents.json"
DEFAULT_INDEX_DIR = REPO_ROOT / "toolbase" / "build" / "catalog_indexes"
DEFAULT_OUT = REPO_ROOT / "toolbase" / "proposals" / "kennametal-topswiss-identity-batch-01.json"
CATALOG_ID = "kennametal-topswiss-inserts-metricinch"
GRADES = ["KCP20S", "KCM25S", "KCS25S", "KN10S", "KTP25S"]
SYMBOLS = {"•", "-"}


def evidence(source_id: str, page: int, table: str, raw_text: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "pdf_page": page,
        "source_table_ref": table,
        "source_raw_text": raw_text,
        "extraction_method": "pdf_table",
    }


def parse_page(page_text: str, page_number: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    section = None
    for raw_line in page_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        heading = re.match(r"^([A-Z]{4}) Insert [•·] Positive [•·] (.+)$", line)
        if heading:
            section = f"{heading.group(1)} Insert - Positive - {heading.group(2)}"
            continue
        tokens = line.split()
        if not section or len(tokens) != 17 or any(token not in SYMBOLS for token in tokens[-5:]):
            continue
        try:
            dimensions = [float(token) for token in tokens[2:12]]
        except ValueError:
            continue
        available_grades = [grade for grade, symbol in zip(GRADES, tokens[-5:]) if symbol == "•"]
        rows.append(
            {
                "ansi": tokens[0],
                "iso": tokens[1],
                "diameter_mm": dimensions[0],
                "length_mm": dimensions[2],
                "corner_radius_mm": dimensions[4],
                "hole_diameter_mm": dimensions[6],
                "thickness_mm": dimensions[8],
                "available_grades": available_grades,
                "section": section,
                "page": page_number,
                "raw_text": (
                    f"{tokens[0]} {tokens[1]} D {dimensions[0]:g} mm L10 {dimensions[2]:g} mm "
                    f"Rε {dimensions[4]:g} mm D1 {dimensions[6]:g} mm S {dimensions[8]:g} mm"
                ),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    source = next(item for item in manifest["documents"] if item["catalog_id"] == CATALOG_ID)
    index_path = args.index_dir / f"{source['content_sha256']}.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    catalog_rows = []
    for page in index["pages"]:
        if page["pdf_page"] in {3, 6}:
            catalog_rows.extend(parse_page(page["text"], page["pdf_page"]))

    chosen = sorted((row for row in catalog_rows if row["iso"].startswith("CCGT")), key=lambda row: row["iso"])
    chosen += sorted((row for row in catalog_rows if row["iso"].startswith("DCGT")), key=lambda row: row["iso"])[:10]
    if len(chosen) != 25:
        raise ValueError(f"expected exactly 25 deterministic catalog rows, found {len(chosen)}")

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row
    proposal_rows = []
    try:
        for number, catalog_row in enumerate(chosen, 1):
            tool = connection.execute(
                """
                SELECT t.id, t.part_number, t.description, t.geometry, t.lifecycle_status,
                       t.evidence_status, t.review_status, m.name AS manufacturer,
                       t.component_type
                FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
                WHERE t.id=? AND m.name='Kennametal' AND t.component_type='insert'
                """,
                (catalog_row["iso"],),
            ).fetchone()
            if tool is None:
                raise ValueError(f"catalog row has no exact database tool: {catalog_row['iso']}")
            if tool["review_status"] != "pending":
                raise ValueError(f"catalog row is already reviewed: {catalog_row['iso']}")
            row_evidence = evidence(
                source["source_id"], catalog_row["page"], catalog_row["section"], catalog_row["raw_text"]
            )
            geometry_code = catalog_row["section"].rsplit(" - ", 1)[-1]
            facts = [
                {"fact_key": "ansi_catalog_id", "value_text": catalog_row["ansi"], "evidence": row_evidence},
                {"fact_key": "iso_catalog_id", "value_text": catalog_row["iso"], "evidence": row_evidence},
                {"fact_key": "geometry", "value_text": f"positive {geometry_code}", "evidence": row_evidence},
            ]
            for key, value in (
                ("inscribed_circle", catalog_row["diameter_mm"]),
                ("cutting_edge_length", catalog_row["length_mm"]),
                ("corner_radius", catalog_row["corner_radius_mm"]),
                ("hole_diameter", catalog_row["hole_diameter_mm"]),
                ("thickness", catalog_row["thickness_mm"]),
            ):
                facts.append(
                    {"fact_key": key, "value_number": value, "unit": "mm", "evidence": row_evidence}
                )
            grade_options = [
                {
                    "code": grade,
                    "option_kind": "available_grade",
                    "availability_status": "listed",
                    "is_primary": position == 0,
                    "evidence": row_evidence,
                }
                for position, grade in enumerate(catalog_row["available_grades"])
            ]
            proposed_description = (
                f"Kennametal TopSwiss {catalog_row['iso']} positive insert, ANSI {catalog_row['ansi']}; "
                f"{catalog_row['diameter_mm']:g} mm IC, {catalog_row['thickness_mm']:g} mm thick, "
                f"{catalog_row['corner_radius_mm']:g} mm corner radius, {geometry_code} geometry."
            )
            proposal_rows.append(
                {
                    "proposal_row_id": f"kenna-id-01-{number:03d}",
                    "tool_lookup": {
                        "tool_id": tool["id"],
                        "manufacturer": tool["manufacturer"],
                        "component_type": tool["component_type"],
                    },
                    "current_summary": {
                        "part_number": tool["part_number"],
                        "description": tool["description"],
                        "geometry": tool["geometry"],
                        "lifecycle_status": tool["lifecycle_status"],
                        "evidence_status": tool["evidence_status"],
                        "review_status": tool["review_status"],
                    },
                    "proposed": {
                        "tool_updates": {
                            "description": proposed_description,
                            "geometry": f"positive {geometry_code}",
                            "lifecycle_status": "unknown",
                        },
                        "aliases": [
                            {"alias": catalog_row["ansi"], "alias_type": "ansi"},
                            {"alias": catalog_row["iso"], "alias_type": "iso"},
                        ],
                        "grade_options": grade_options,
                        "replace_fact_keys": [item["fact_key"] for item in facts],
                        "facts": facts,
                        "replace_material_recommendations": False,
                        "material_recommendations": [],
                        "cutting_profiles": [],
                        "tags": [
                            "Kennametal",
                            "TopSwiss",
                            "insert",
                            catalog_row["iso"][:4],
                            geometry_code,
                        ],
                    },
                    "conflicts": [
                        "Legacy descriptions and grade claims remain untrusted until this row is approved.",
                        "This identity batch does not propose work-material or cutting-data recommendations.",
                    ],
                    "notes": "Exact ISO catalog-number match to a manufacturer table row; human visual review is still required.",
                }
            )
    finally:
        connection.close()

    proposal_source = dict(source)
    proposal_source["batch_role"] = "primary_catalog"
    proposal_source["page_ref"] = "PDF pages 3 and 6"
    proposal = {
        "schema_version": 2,
        "proposal_id": "kennametal-topswiss-identity-batch-01-2026-07",
        "title": "Kennametal TopSwiss identity and grade-option review - batch 01",
        "created_at": "2026-07-21",
        "status": "source_extracted",
        "import_allowed": False,
        "purpose": "Human review of exact manufacturer catalog identities, metric dimensions, geometry codes, and listed grade options. No speeds, feeds, or work-material recommendation is proposed in this batch.",
        "sources": [proposal_source],
        "rows": proposal_rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "path": str(args.out), "rows": len(proposal_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
