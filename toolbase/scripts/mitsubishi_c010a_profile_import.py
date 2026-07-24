#!/usr/bin/env python3
"""Generate reviewed cutting-data batches for the Mitsubishi C010A insert inventory.

This script writes only a schema-2 proposal and its decision ledger for one batch at a
time. review_batch.py remains the only validate/compile path, and build.py remains the
only import path. Every numeric condition below is transcribed from one manufacturer
condition-class table; per-tool rows are materialized from that single literal so a
correction is a one-line edit plus regeneration.

Batches:
  cbn-hardened   C010A B008 (PDF page 9) hardened-steel grade-level baselines.
  pcd-md220      C010A B015 (PDF page 16) PCD material-level baselines for MD220.
  mb4120-sintered C010A B008 (PDF page 9) sintered-alloy baselines for MB4120.
  cast-iron      Tool News B234G / B246A gray-cast-iron grade-level baselines.

The identity gate is the reviewed grade matrix snapshot: a condition class attaches to a
tool only when that tool's exact C010A product row lists a grade the class covers.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("review_batch", SCRIPT_DIR / "review_batch.py")
assert SPEC and SPEC.loader
review_batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_batch)

DB_PATH = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
MATRIX_PATH = REPO_ROOT / "toolbase" / "data" / "source_snapshots" / "mitsubishi-c010a-grade-matrix-2026-07-22.json"
C010A_PATH = "toolbase/data/source_snapshots/mitsubishi-c010a-cbn-pcd-inserts.pdf"
BC5110_PATH = "toolbase/data/source_snapshots/mitsubishi-bc5110-b234g.pdf"
MB4120_PATH = "toolbase/data/source_snapshots/mitsubishi-mb4120-b246a.pdf"

C010A_SOURCE_ID = "source-140cd7506a42b01f"
BC5110_SOURCE_ID = "source-mitsubishi-b234g"
MB4120_SOURCE_ID = "source-mitsubishi-b246a"

GENERATOR_VERSION = "mitsubishi_c010a_profile_import v1"

# Honing/edge-preparation order tokens (C010A B009); never grades.
HONING_TOKENS = {
    "TS2", "TA2", "FS2", "GS2", "GA2", "GH2", "TH2", "VA2", "SF2", "SE2",
    "TS3", "TA3", "FS3", "GS3", "GA3", "GH3", "TH3", "VA3", "SF3", "SE3",
    "FSWS2", "GAWS2", "GBWL2", "FBWL2", "GSWS2",
}

# Insert-family geometry wording keyed by the ISO family letters of the order code.
GEOMETRY_BY_FAMILY = {
    "CC": "positive 80-degree rhombic",
    "DC": "positive 55-degree rhombic",
    "TC": "positive triangular",
    "VB": "positive 35-degree rhombic",
    "VC": "positive 35-degree rhombic",
}

HARDENED_GRADES = {
    "BC8105", "BC8210", "BC8110", "BC8220", "BC8120", "BC8130",
    "MB8110", "MB8120", "MB8130",
}

# C010A B008 (PDF page 9) "Heat Treated Steel" recommended cutting conditions.
# One entry per printed table row: (grade label, member grades, coated section,
# cutting mode, cut_condition, subgroup, vc start, vc min, vc max SFM,
# feed max IPR, DOC max inch).
B008_HARDENED_ROWS = [
    ("BC8105", ("BC8105",), "Coated", "High speed finishing cutting", "finishing",
     "Hardened steel / high-speed finishing", 820, 330, 1150, 0.006, 0.008),
    ("BC8210 and BC8110", ("BC8210", "BC8110"), "Coated",
     "Continuous cutting for general purpose", "general",
     "Hardened steel / continuous", 655, 330, 985, 0.008, 0.014),
    ("BC8220 and BC8120", ("BC8220", "BC8120"), "Coated",
     "Continuous cutting for general purpose", "general",
     "Hardened steel / continuous", 655, 330, 755, 0.012, 0.031),
    ("BC8220 and BC8120", ("BC8220", "BC8120"), "Coated",
     "Medium interrupted cutting", "medium",
     "Hardened steel / medium interrupted", 490, 195, 655, 0.008, 0.012),
    ("BC8130", ("BC8130",), "Coated", "Interrupted cutting", "medium",
     "Hardened steel / interrupted", 390, 195, 490, 0.008, 0.012),
    ("MB8110", ("MB8110",), "Non-coated", "Continuous cutting for general purpose",
     "general", "Hardened steel / continuous", 655, 330, 820, 0.008, 0.012),
    ("MB8120", ("MB8120",), "Non-coated", "Continuous cutting for general purpose",
     "general", "Hardened steel / continuous", 490, 260, 720, 0.008, 0.020),
    ("MB8120", ("MB8120",), "Non-coated", "Medium interrupted cutting", "medium",
     "Hardened steel / medium interrupted", 425, 280, 590, 0.008, 0.012),
    ("MB8130", ("MB8130",), "Non-coated", "Interrupted cutting", "medium",
     "Hardened steel / interrupted", 330, 195, 490, 0.008, 0.012),
]

# C010A B008 (PDF page 9) "Sintered Alloy" recommended cutting conditions for MB4120.
# The printed rows state no cutting mode, so coolant remains unknown.
B008_SINTERED_ROWS = [
    ("General Sintered Alloy", 590, 260, 985, 0.008, 0.012),
    ("High Density Sintered Alloy", 490, 260, 755, 0.008, 0.012),
    ("Sintered Alloy", 425, 260, 590, 0.008, 0.012),
]

# C010A B015 (PDF page 16) PCD selection standard / recommended cutting conditions.
# (material label, iso group, MD220 recommendation rank, vc start, vc min, vc max SFM,
# feed max IPR, DOC max inch or None when the catalog states no bound).
B015_PCD_ROWS = [
    ("Aluminum Alloy (Si < 12%)", "N", "primary", 2625, 655, 3935, 0.008, 0.039),
    ("Aluminum Alloy (Si >13%)", "N", "recommended", 1970, 655, 3280, 0.008, 0.039),
    ("Copper Alloy", "N", "primary", 2295, 655, 3935, 0.008, 0.039),
    ("Strengthened Plastic", "O", "primary", 1970, 330, 3280, 0.016, 0.039),
    ("Glass Fiber Reinforced Plastic", "O", "primary", 1640, 330, 2625, 0.010, 0.039),
    ("Carbon", "O", "primary", 1310, 330, 1970, 0.012, 0.039),
    ("Ceramics", "O", "recommended", 165, 100, 260, 0.004, 0.039),
    ("Hard Rubber", "O", "primary", 1970, 985, 2625, 0.006, 0.039),
    ("Wood Inorganic Board", "O", "primary", 4265, 985, 13120, 0.016, None),
    ("Cemented Carbide", "O", "recommended", 50, 15, 65, 0.008, 0.020),
]

# Tool News brochure gray-cast-iron tables, metric source units preserved exactly.
# B234G final-page table (BC5110); B246A final-page table (MB4120).
CAST_IRON_ROWS = {
    "BC5110": {
        "source_id": BC5110_SOURCE_ID,
        "material_label": "Gray cast iron (FC250, FC300 etc.)",
        "speed_start": None, "speed_min": 100.0, "speed_max": 600.0,
        "speed_unit": "m_per_min",
        "feed_max": 0.5, "feed_unit": "mm_per_rev",
        "doc_max": 0.5, "doc_unit": "mm",
        "raw_text": "Recommended Cutting Conditions; Work material: gray cast irons "
                    "(FC250, FC300 etc.); Cutting speed vc 100-600 m/min; Feed f <=0.5 "
                    "mm/rev; Depth of cut ap <=0.5 mm; Dry or wet.",
        "table_ref": "Tool News B234G final-page Recommended Cutting Conditions / BC5110",
    },
    "MB4120": {
        "source_id": MB4120_SOURCE_ID,
        "material_label": "Gray cast iron",
        "speed_start": 3280, "speed_min": 2625, "speed_max": 4100,
        "speed_unit": "sfm",
        "feed_max": 0.016, "feed_unit": "ipr",
        "doc_max": 0.020, "doc_unit": "in",
        "raw_text": "Recommended Cutting Conditions; Work material: gray cast irons; "
                    "Cutting speed vc 3280 (2625-4100) SFM; Feed f <=.016 IPR; Depth of "
                    "cut ap <=.020 inch; Dry or wet.",
        "table_ref": "Tool News B246A final-page Recommended Cutting Conditions / MB4120",
    },
}

FLOOD_NOTE = (
    "C010A grade-level and breaker-level starting conditions; shop profile selects "
    "flood from manufacturer Dry/Wet wording."
)


def load_matrix() -> dict[str, dict[str, Any]]:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload
    return {row["tool_id"]: row for row in rows}


def load_tools() -> dict[str, dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH)
    try:
        tools: dict[str, dict[str, Any]] = {}
        for tool_id, part_number, description in connection.execute(
            """
            SELECT t.id, t.part_number, t.description
            FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
            WHERE m.name='Mitsubishi Materials'
            """
        ):
            tools[tool_id] = {"part_number": part_number, "description": description}
        existing_profiles = set()
        for part_number, grade, subgroup in connection.execute(
            """
            SELECT t.part_number, p.source_grade, p.material_subgroup
            FROM cutting_data_profiles p
            JOIN tools t ON t.id=p.tool_id
            JOIN manufacturers m ON m.id=t.manufacturer_id
            WHERE m.name='Mitsubishi Materials'
            """
        ):
            existing_profiles.add((part_number, grade, subgroup))
        existing_recommendations = set()
        for part_number, grade_code, iso_group, subgroup in connection.execute(
            """
            SELECT t.part_number, g.code, r.iso_group, r.material_subgroup
            FROM tool_material_recommendations r
            JOIN tools t ON t.id=r.tool_id
            JOIN manufacturers m ON m.id=t.manufacturer_id
            LEFT JOIN grades g ON g.id=r.grade_id
            WHERE m.name='Mitsubishi Materials' AND r.is_current=1
            """
        ):
            existing_recommendations.add((part_number, grade_code, iso_group, subgroup))
    finally:
        connection.close()
    return {
        "tools": tools,
        "profiles": existing_profiles,
        "recommendations": existing_recommendations,
    }


def family_letters(part_number: str) -> str:
    designation = part_number
    for prefix in ("NP-", "BF-", "BM-"):
        if designation.startswith(prefix):
            designation = designation[len(prefix):]
    return designation[:2]


def is_pcd(matrix_row: dict[str, Any]) -> bool:
    return any(
        option["grade"].startswith("MD") for option in matrix_row["actual_grade_options"]
    )


def technology(matrix_row: dict[str, Any]) -> str:
    return "PCD" if is_pcd(matrix_row) else "CBN"


def geometry_text(part_number: str, matrix_row: dict[str, Any]) -> str:
    shape = GEOMETRY_BY_FAMILY[family_letters(part_number)]
    return f"{shape} {technology(matrix_row)}"


def edge_token(matrix_row: dict[str, Any]) -> str | None:
    token = matrix_row.get("edge_preparation_or_order_suffix")
    return token if token in HONING_TOKENS else None


def grade_codes(matrix_row: dict[str, Any]) -> list[str]:
    return [option["grade"] for option in matrix_row["actual_grade_options"]]


def c010a_source() -> dict[str, Any]:
    return {
        "source_id": C010A_SOURCE_ID,
        "batch_role": "primary_catalog",
        "manufacturer": "Mitsubishi Materials",
        "title": "Mitsubishi Materials CBN & PCD Inserts Catalog C010A",
        "source_type": "manufacturer_catalog",
        "artifact_format": "pdf",
        "url": "https://data.mmc-carbide.com/5316/9575/0325/catalog_c010a_cbn_pcd_inserts.pdf",
        "local_path": C010A_PATH,
        "content_sha256": review_batch.file_sha256(REPO_ROOT / C010A_PATH),
        "page_count": 64,
        "document_edition": "C010A",
    }


def brochure_source(source_id: str, title: str, edition: str, url: str, local: str) -> dict[str, Any]:
    local_path = REPO_ROOT / local
    if not local_path.is_file():
        raise SystemExit(f"missing brochure snapshot: {local} (download it first)")
    with (REPO_ROOT / local).open("rb") as stream:
        import pypdf

        page_count = len(pypdf.PdfReader(stream).pages)
    return {
        "source_id": source_id,
        "batch_role": "grade_brochure",
        "manufacturer": "Mitsubishi Materials",
        "title": title,
        "source_type": "manufacturer_catalog",
        "artifact_format": "pdf",
        "url": url,
        "local_path": local,
        "content_sha256": review_batch.file_sha256(local_path),
        "page_count": page_count,
        "document_edition": edition,
    }


def legacy_token_sentence(matrix_row: dict[str, Any]) -> str:
    token = matrix_row.get("legacy_grade_token")
    if token in HONING_TOKENS:
        return f" The order token {token} is edge preparation, not the material grade."
    if token == "MD22":
        return " The legacy grade value MD22 is a typo for catalog grade MD220."
    return ""


def identity_evidence(matrix_row: dict[str, Any], part_number: str) -> dict[str, Any]:
    page = matrix_row["catalog_pdf_page"]
    printed = matrix_row["catalog_printed_page"]
    grades = ", ".join(grade_codes(matrix_row))
    return {
        "source_id": C010A_SOURCE_ID,
        "pdf_page": page,
        "source_table_ref": f"C010A product standards table, printed page {printed}",
        "source_raw_text": (
            f"Exact order designation {part_number} is listed on PDF page {page} with "
            f"actual grade options {grades}." + legacy_token_sentence(matrix_row)
        ),
        "extraction_method": "pdf_table",
    }


def breaker_code(part_number: str) -> str | None:
    for prefix in ("BF", "BM"):
        if part_number.startswith(f"{prefix}-"):
            return prefix
    return None


def tool_updates_for(matrix_row: dict[str, Any], part_number: str) -> dict[str, Any]:
    geometry = geometry_text(part_number, matrix_row)
    breaker = breaker_code(part_number)
    if breaker == "BF":
        # Matches the reviewed part-01 wording for the BF finishing breaker.
        geometry = f"{geometry} finishing"
    token = edge_token(matrix_row)
    grades = ", ".join(grade_codes(matrix_row))
    if breaker and token:
        edge_clause = f", with {breaker} breaker and {token} edge preparation"
    elif token:
        edge_clause = f", with {token} edge preparation"
    else:
        edge_clause = ""
    description = (
        f"Mitsubishi Materials {geometry_text(part_number, matrix_row)} insert "
        f"{part_number}{edge_clause}. Catalog grade options are {grades}. Published "
        "cutting conditions are manufacturer grade- or breaker-level baselines "
        "intended for machinist adjustment."
    )
    return {
        "description": description,
        "geometry": geometry,
        "lifecycle_status": "active",
        "grade": None,
        "chipbreaker": breaker,
        "evidence": identity_evidence(matrix_row, part_number),
    }


def grade_option_entries(matrix_row: dict[str, Any], part_number: str) -> list[dict[str, Any]]:
    page = matrix_row["catalog_pdf_page"]
    printed = matrix_row["catalog_printed_page"]
    entries = []
    for option in matrix_row["actual_grade_options"]:
        grade = option["grade"]
        stock = option.get("stock_mark") or "catalog-listed"
        entries.append(
            {
                "code": grade,
                "option_kind": "available_grade",
                "full_order_number": f"{part_number} {grade}",
                "availability_status": "listed",
                "is_primary": False,
                "evidence": {
                    "source_id": C010A_SOURCE_ID,
                    "pdf_page": page,
                    "source_table_ref": f"C010A product standards table, printed page {printed}",
                    "source_raw_text": (
                        f"Exact ISO order designation {part_number} is listed on PDF "
                        f"page {page} under actual grade column {grade} with catalog "
                        f"stock mark {stock}." + legacy_token_sentence(matrix_row)
                    ),
                    "extraction_method": "pdf_table",
                },
            }
        )
    return entries


def source_geometry_for(matrix_row: dict[str, Any], part_number: str) -> str:
    token = edge_token(matrix_row)
    base = f"{geometry_text(part_number, matrix_row)} insert"
    return f"{base}, {token} edge preparation" if token else base


def hardened_profile(matrix_row: dict[str, Any], part_number: str, grade: str,
                     row: tuple) -> dict[str, Any]:
    (label, _members, section, mode, cut_condition, subgroup,
     start, minimum, maximum, feed_max, doc_max) = row
    raw = (
        f"Heat Treated Steel; {mode}; {section}; {label}; Cutting Speed vc "
        f"{start} ({minimum}-{maximum}) SFM; Feed f <=.{f'{feed_max:.3f}'.split('.')[1]} IPR; "
        f"Depth of Cut ap <=.{f'{doc_max:.3f}'.split('.')[1]} inch; Dry, Wet."
    )
    return {
        "source_part_number": part_number,
        "source_grade": grade,
        "source_geometry": source_geometry_for(matrix_row, part_number),
        "source_chipbreaker": "none",
        "source_material_label": "Hardened Steel",
        "iso_material_group": "H",
        "operation_type": "turning",
        "cut_condition": cut_condition,
        "coolant_condition": "flood",
        "material_subgroup": subgroup,
        "surface_speed_min": minimum,
        "surface_speed_start": start,
        "surface_speed_max": maximum,
        "surface_speed_unit": "sfm",
        "feed_min": None,
        "feed_max": feed_max,
        "feed_unit": "ipr",
        "depth_of_cut_min": None,
        "depth_of_cut_max": doc_max,
        "depth_of_cut_unit": "in",
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 9,
            "source_table_ref": (
                f"B008 Heat Treated Steel Recommended Cutting Conditions / {section} / {label}"
            ),
            "source_raw_text": raw,
            "extraction_method": "pdf_table",
        },
    }


def hardened_recommendation(part_number: str, grade: str) -> dict[str, Any]:
    return {
        "grade_code": grade,
        "iso_group": "H",
        "material_subgroup": "Hardened steel",
        "suitability": "recommended",
        "notes": FLOOD_NOTE,
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 9,
            "source_table_ref": "B008 Heat Treated Steel Recommended Cutting Conditions",
            "source_raw_text": (
                f"{part_number} grade option {grade} is listed for hardened-material "
                "CBN turning on B008."
            ),
            "extraction_method": "pdf_table",
        },
    }


def build_cbn_hardened_row(matrix_row: dict[str, Any], part_number: str,
                           state: dict[str, Any]) -> dict[str, Any] | None:
    grades = [g for g in grade_codes(matrix_row) if g in HARDENED_GRADES]
    if not grades:
        return None
    profiles = []
    recommendations = []
    for grade in grades:
        for row in B008_HARDENED_ROWS:
            if grade not in row[1]:
                continue
            if (part_number, grade, row[5]) in state["profiles"]:
                continue
            profiles.append(hardened_profile(matrix_row, part_number, grade, row))
        if (part_number, grade, "H", "Hardened steel") not in state["recommendations"]:
            recommendations.append(hardened_recommendation(part_number, grade))
    if not profiles and not recommendations and not breaker_code(part_number):
        return None
    return {
        "tool_updates": tool_updates_for(matrix_row, part_number),
        "grade_options": grade_option_entries(matrix_row, part_number),
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
    }


def pcd_profile(matrix_row: dict[str, Any], part_number: str, row: tuple) -> dict[str, Any]:
    label, iso_group, _rank, start, minimum, maximum, feed_max, doc_max = row
    doc_text = f"<=.{f'{doc_max:.3f}'.split('.')[1]} inch" if doc_max is not None else "not stated"
    raw = (
        f"PCD Selection Standard, Turning; Work Material {label}; MD220; Cutting Speed "
        f"vc {start} ({minimum}-{maximum}) SFM; Feed f <=.{f'{feed_max:.3f}'.split('.')[1]} IPR; "
        f"Depth of Cut ap {doc_text}."
    )
    return {
        "source_part_number": part_number,
        "source_grade": "MD220",
        "source_geometry": source_geometry_for(matrix_row, part_number),
        "source_chipbreaker": "none",
        "source_material_label": label,
        "iso_material_group": iso_group,
        "operation_type": "turning",
        "cut_condition": "general",
        "coolant_condition": "unknown",
        "material_subgroup": label,
        "surface_speed_min": minimum,
        "surface_speed_start": start,
        "surface_speed_max": maximum,
        "surface_speed_unit": "sfm",
        "feed_min": None,
        "feed_max": feed_max,
        "feed_unit": "ipr",
        "depth_of_cut_min": None,
        "depth_of_cut_max": doc_max,
        "depth_of_cut_unit": "in",
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 16,
            "source_table_ref": f"B015 PCD Selection Standard, Turning / {label}",
            "source_raw_text": raw,
            "extraction_method": "pdf_table",
        },
    }


def pcd_recommendation(part_number: str, row: tuple) -> dict[str, Any]:
    label, iso_group, rank, start, minimum, maximum, feed_max, doc_max = row
    doc_note = (
        " The catalog states no depth-of-cut bound for this material."
        if doc_max is None
        else ""
    )
    return {
        "grade_code": "MD220",
        "iso_group": iso_group,
        "material_subgroup": label,
        "suitability": rank,
        "notes": "C010A B015 material-level starting conditions for MD220." + doc_note,
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 16,
            "source_table_ref": f"B015 PCD Selection Standard, Turning / {label}",
            "source_raw_text": (
                f"MD220 is the {'1st' if rank == 'primary' else '2nd'} recommendation "
                f"for {label}; cutting speed vc {start} ({minimum}-{maximum}) SFM."
            ),
            "extraction_method": "pdf_table",
        },
    }


def build_pcd_row(matrix_row: dict[str, Any], part_number: str,
                  state: dict[str, Any]) -> dict[str, Any] | None:
    if "MD220" not in grade_codes(matrix_row):
        return None
    profiles = []
    recommendations = []
    for row in B015_PCD_ROWS:
        label = row[0]
        doc_max = row[7]
        if doc_max is not None and (part_number, "MD220", label) not in state["profiles"]:
            profiles.append(pcd_profile(matrix_row, part_number, row))
        if (part_number, "MD220", row[1], label) not in state["recommendations"]:
            recommendations.append(pcd_recommendation(part_number, row))
    if not profiles and not recommendations:
        return None
    return {
        "tool_updates": tool_updates_for(matrix_row, part_number),
        "grade_options": grade_option_entries(matrix_row, part_number),
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
    }


def sintered_profile(matrix_row: dict[str, Any], part_number: str, row: tuple) -> dict[str, Any]:
    label, start, minimum, maximum, feed_max, doc_max = row
    raw = (
        f"Sintered Alloy Recommended Cutting Conditions; Work Material {label}; "
        f"MB4120; Cutting Speed vc {start} ({minimum}-{maximum}) SFM; Feed f "
        f"<=.{f'{feed_max:.3f}'.split('.')[1]} IPR; Depth of Cut ap "
        f"<=.{f'{doc_max:.3f}'.split('.')[1]} inch. The printed rows state no cutting mode."
    )
    return {
        "source_part_number": part_number,
        "source_grade": "MB4120",
        "source_geometry": source_geometry_for(matrix_row, part_number),
        "source_chipbreaker": "none",
        "source_material_label": label,
        "iso_material_group": "O",
        "operation_type": "turning",
        "cut_condition": "general",
        "coolant_condition": "unknown",
        "material_subgroup": label,
        "surface_speed_min": minimum,
        "surface_speed_start": start,
        "surface_speed_max": maximum,
        "surface_speed_unit": "sfm",
        "feed_min": None,
        "feed_max": feed_max,
        "feed_unit": "ipr",
        "depth_of_cut_min": None,
        "depth_of_cut_max": doc_max,
        "depth_of_cut_unit": "in",
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 9,
            "source_table_ref": f"B008 Sintered Alloy Recommended Cutting Conditions / {label}",
            "source_raw_text": raw,
            "extraction_method": "pdf_table",
        },
    }


def sintered_recommendation(part_number: str, row: tuple) -> dict[str, Any]:
    label = row[0]
    return {
        "grade_code": "MB4120",
        "iso_group": "O",
        "material_subgroup": label,
        "suitability": "recommended",
        "notes": "C010A B008 sintered-alloy starting conditions; the catalog states no cutting mode for these rows.",
        "evidence": {
            "source_id": C010A_SOURCE_ID,
            "pdf_page": 9,
            "source_table_ref": f"B008 Sintered Alloy Recommended Cutting Conditions / {label}",
            "source_raw_text": (
                f"MB4120 is recommended for {label} sintered-alloy turning on B008."
            ),
            "extraction_method": "pdf_table",
        },
    }


def build_sintered_row(matrix_row: dict[str, Any], part_number: str,
                       state: dict[str, Any]) -> dict[str, Any] | None:
    if "MB4120" not in grade_codes(matrix_row):
        return None
    profiles = []
    recommendations = []
    for row in B008_SINTERED_ROWS:
        label = row[0]
        if (part_number, "MB4120", label) not in state["profiles"]:
            profiles.append(sintered_profile(matrix_row, part_number, row))
        if (part_number, "MB4120", "O", label) not in state["recommendations"]:
            recommendations.append(sintered_recommendation(part_number, row))
    if not profiles and not recommendations:
        return None
    return {
        "tool_updates": tool_updates_for(matrix_row, part_number),
        "grade_options": grade_option_entries(matrix_row, part_number),
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
    }


def cast_iron_profile(matrix_row: dict[str, Any], part_number: str, grade: str) -> dict[str, Any]:
    spec = CAST_IRON_ROWS[grade]
    return {
        "source_part_number": part_number,
        "source_grade": grade,
        "source_geometry": source_geometry_for(matrix_row, part_number),
        "source_chipbreaker": "none",
        "source_material_label": spec["material_label"],
        "iso_material_group": "K",
        "operation_type": "turning",
        "cut_condition": "general",
        "coolant_condition": "flood",
        "material_subgroup": "Gray cast iron",
        "surface_speed_min": spec["speed_min"],
        "surface_speed_start": spec["speed_start"],
        "surface_speed_max": spec["speed_max"],
        "surface_speed_unit": spec["speed_unit"],
        "feed_min": None,
        "feed_max": spec["feed_max"],
        "feed_unit": spec["feed_unit"],
        "depth_of_cut_min": None,
        "depth_of_cut_max": spec["doc_max"],
        "depth_of_cut_unit": spec["doc_unit"],
        "evidence": {
            "source_id": spec["source_id"],
            "pdf_page": None,
            "source_table_ref": spec["table_ref"],
            "source_raw_text": spec["raw_text"],
            "extraction_method": "pdf_table",
        },
    }


def cast_iron_recommendation(part_number: str, grade: str) -> dict[str, Any]:
    spec = CAST_IRON_ROWS[grade]
    return {
        "grade_code": grade,
        "iso_group": "K",
        "material_subgroup": "Gray cast iron",
        "suitability": "recommended",
        "notes": (
            "Grade-level gray-cast-iron starting conditions; shop profile selects "
            "flood from manufacturer dry/wet wording."
        ),
        "evidence": {
            "source_id": spec["source_id"],
            "pdf_page": None,
            "source_table_ref": spec["table_ref"],
            "source_raw_text": spec["raw_text"],
            "extraction_method": "pdf_table",
        },
    }


def build_cast_iron_row(matrix_row: dict[str, Any], part_number: str,
                        state: dict[str, Any], page_counts: dict[str, int]) -> dict[str, Any] | None:
    grades = [g for g in grade_codes(matrix_row) if g in CAST_IRON_ROWS]
    if not grades:
        return None
    profiles = []
    recommendations = []
    for grade in grades:
        if (part_number, grade, "Gray cast iron") not in state["profiles"]:
            profile = cast_iron_profile(matrix_row, part_number, grade)
            profile["evidence"]["pdf_page"] = page_counts[profile["evidence"]["source_id"]]
            profiles.append(profile)
        if (part_number, grade, "K", "Gray cast iron") not in state["recommendations"]:
            recommendation = cast_iron_recommendation(part_number, grade)
            recommendation["evidence"]["pdf_page"] = page_counts[
                recommendation["evidence"]["source_id"]
            ]
            recommendations.append(recommendation)
    if not profiles and not recommendations:
        return None
    return {
        "tool_updates": tool_updates_for(matrix_row, part_number),
        "grade_options": grade_option_entries(matrix_row, part_number),
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
    }


BATCHES = {
    "cbn-hardened": {
        "proposal_id": "mitsubishi-profiles-cbn-hardened-2026-07",
        "title": "Mitsubishi C010A hardened-steel grade-level baselines",
        "purpose": (
            "Publish C010A B008 hardened-steel grade-level starting conditions on every "
            "exact CBN insert whose catalog row lists a covered grade, and correct the "
            "remaining legacy geometry and description text."
        ),
        "builder": "cbn",
        "decision_note": (
            "C010A B008 grade-level hardened-steel baselines; limits preserved as "
            "one-sided maxima; flood selected as the shop practical mode from "
            "manufacturer Dry/Wet wording."
        ),
    },
    "pcd-md220": {
        "proposal_id": "mitsubishi-profiles-pcd-md220-2026-07",
        "title": "Mitsubishi C010A PCD MD220 material-level baselines",
        "purpose": (
            "Publish C010A B015 material-level starting conditions and first/second "
            "recommendations for MD220 on every exact PCD insert, preserving the "
            "missing depth-of-cut bound for wood inorganic board."
        ),
        "builder": "pcd",
        "decision_note": (
            "C010A B015 material-level MD220 baselines; limits preserved as one-sided "
            "maxima; the catalog states no cutting mode, so coolant remains unknown."
        ),
    },
    "mb4120-sintered": {
        "proposal_id": "mitsubishi-profiles-mb4120-sintered-2026-07",
        "title": "Mitsubishi C010A MB4120 sintered-alloy baselines",
        "purpose": (
            "Publish C010A B008 sintered-alloy starting conditions for MB4120 on every "
            "exact CBN insert whose catalog row lists MB4120."
        ),
        "builder": "sintered",
        "decision_note": (
            "C010A B008 sintered-alloy MB4120 baselines; limits preserved as one-sided "
            "maxima; the catalog states no cutting mode for these rows, so coolant "
            "remains unknown."
        ),
    },
    "cast-iron": {
        "proposal_id": "mitsubishi-profiles-castiron-2026-07",
        "title": "Mitsubishi gray-cast-iron BC5110 and MB4120 baselines",
        "purpose": (
            "Publish Tool News B234G (BC5110) and B246A (MB4120) gray-cast-iron "
            "grade-level starting conditions in their exact source units on every "
            "insert whose C010A row lists the grade."
        ),
        "builder": "cast-iron",
        "decision_note": (
            "Tool News B234G/B246A grade-level gray-cast-iron baselines in exact "
            "source units; flood selected as the shop practical mode from "
            "manufacturer dry/wet wording."
        ),
    },
}


def select_sample(rows: list[dict[str, Any]]) -> set[str]:
    """Deterministic owner spot-check sample: first row, last row, the first row
    carrying each distinct condition-class table reference, topped up to ten rows."""
    sample: set[str] = set()
    if not rows:
        return sample
    sample.add(rows[0]["proposal_row_id"])
    sample.add(rows[-1]["proposal_row_id"])
    seen_refs: set[str] = set()
    for row in rows:
        for profile in row["proposed"]["cutting_profiles"]:
            ref = profile["evidence"]["source_table_ref"]
            if ref not in seen_refs:
                seen_refs.add(ref)
                sample.add(row["proposal_row_id"])
    for row in rows:
        if len(sample) >= min(10, len(rows)):
            break
        sample.add(row["proposal_row_id"])
    return sample


def generate(batch: str, created_at: str) -> tuple[Path, Path]:
    config = BATCHES[batch]
    matrix = load_matrix()
    state = load_tools()
    missing = sorted(set(matrix) - set(state["tools"]))
    if missing:
        raise SystemExit(f"matrix tools missing from database: {missing}")

    sources = [c010a_source()]
    page_counts: dict[str, int] = {}
    if config["builder"] == "cast-iron":
        b234g = brochure_source(
            BC5110_SOURCE_ID,
            "Mitsubishi Tool News B234G: BC5110 CBN grade for gray cast iron",
            "B234G",
            "https://data.mmc-carbide.com/7916/5821/5217/bc5110_b234g.pdf",
            BC5110_PATH,
        )
        b246a = brochure_source(
            MB4120_SOURCE_ID,
            "Mitsubishi Tool News B246A: MB4120 CBN grade for gray cast iron and sintered alloy",
            "B246A",
            "https://data.mmc-carbide.com/2616/6501/2762/mb4120_b246a.pdf",
            MB4120_PATH,
        )
        sources.extend([b234g, b246a])
        page_counts = {
            BC5110_SOURCE_ID: b234g["page_count"],
            MB4120_SOURCE_ID: b246a["page_count"],
        }

    rows = []
    for tool_id in sorted(matrix):
        matrix_row = matrix[tool_id]
        part_number = state["tools"][tool_id]["part_number"]
        if config["builder"] == "cbn":
            # BF-CCGT09T304TS2 is fully reviewed (part-01 set geometry, breaker, and
            # baselines); every other BF/BM tool still needs its geometry text fixed.
            if tool_id == "BF-CCGT09T304TS2" or is_pcd(matrix_row):
                continue
            proposed = build_cbn_hardened_row(matrix_row, part_number, state)
        elif config["builder"] == "pcd":
            proposed = build_pcd_row(matrix_row, part_number, state)
        elif config["builder"] == "sintered":
            proposed = build_sintered_row(matrix_row, part_number, state)
        else:
            proposed = build_cast_iron_row(matrix_row, part_number, state, page_counts)
        if proposed is None:
            continue
        rows.append(
            {
                "proposal_row_id": f"{config['proposal_id']}-row-{len(rows) + 1:03d}",
                "tool_lookup": {
                    "tool_id": tool_id,
                    "manufacturer": "Mitsubishi Materials",
                    "component_type": "insert",
                },
                "current_summary": {
                    "part_number": part_number,
                    "description": state["tools"][tool_id]["description"],
                },
                "proposed": proposed,
            }
        )
    if not rows:
        raise SystemExit(f"batch {batch}: nothing to propose (already published?)")

    proposal = {
        "schema_version": 2,
        "proposal_id": config["proposal_id"],
        "title": config["title"],
        "created_at": created_at,
        "status": "source_extracted",
        "import_allowed": False,
        "purpose": config["purpose"],
        "sources": sources,
        "rows": rows,
    }
    proposal_path = REPO_ROOT / "toolbase" / "proposals" / f"{config['proposal_id']}.json"
    review_batch.write_json(proposal_path, proposal)

    sample = select_sample(rows)
    decisions = []
    for row in rows:
        row_id = row["proposal_row_id"]
        if row_id in sample:
            reviewer = "Greg"
            capture = "owner_spot_check"
        else:
            reviewer = f"scripted:{GENERATOR_VERSION}; batch rules approved by Greg {created_at}"
            capture = "scripted_batch_generation"
        decisions.append(
            {
                "proposal_row_id": row_id,
                "tool_id": row["tool_lookup"]["tool_id"],
                "decision": "approved",
                "reviewer": reviewer,
                "decided_at": created_at,
                "capture_method": capture,
                "notes": config["decision_note"],
            }
        )
    ledger = {
        "schema_version": 2,
        "review_id": f"{config['proposal_id']}-review",
        "proposal_id": config["proposal_id"],
        "proposal_path": f"toolbase/proposals/{config['proposal_id']}.json",
        "proposal_sha256": review_batch.file_sha256(proposal_path),
        "review_started_at": created_at,
        "status": "complete",
        "review_completed_at": created_at,
        "import_allowed": True,
        "decisions": decisions,
    }
    ledger_path = REPO_ROOT / "toolbase" / "reviews" / f"{config['proposal_id']}.decisions.json"
    review_batch.write_json(ledger_path, ledger)

    profile_count = sum(len(r["proposed"]["cutting_profiles"]) for r in rows)
    recommendation_count = sum(
        len(r["proposed"]["material_recommendations"]) for r in rows
    )
    print(f"batch {batch}: {len(rows)} tools, {profile_count} cutting profiles, "
          f"{recommendation_count} material recommendations, "
          f"{len(sample)} owner spot-check rows")
    print(f"proposal: {proposal_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"ledger:   {ledger_path.relative_to(REPO_ROOT).as_posix()}")
    return proposal_path, ledger_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--created-at", default="2026-07-23")
    arguments = parser.parse_args()
    generate(arguments.batch, arguments.created_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
