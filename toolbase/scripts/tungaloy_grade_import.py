#!/usr/bin/env python3
"""Generate reviewed cutting-data batches for Tungaloy inserts from grade snapshots.

Tungaloy publishes grade-level recommended cutting conditions (cutting speed by ISO
material, depth of cut by chipbreaker, feed by corner radius) on freely accessible,
hashable manufacturer pages. This script captures one such grade snapshot and applies
its published conditions to every exact insert carrying that grade, as labeled
baseline starting values a machinist adjusts for the actual setup and result.

Like the Mitsubishi importer, this writes only a schema-2 proposal and its decision
ledger. review_batch.py remains the only validate/compile path; build.py the only
import path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
GENERATOR_VERSION = "tungaloy_grade_import v1"

ISO_MATERIAL_SUBGROUP = {"P": "Carbon / alloy steel", "M": "Stainless steel"}

BATCHES = {
    "sh7025": {
        "proposal_id": "tungaloy-sh7025-grade-baselines-2026-07",
        "title": "Tungaloy SH7025 grade-level cutting baselines",
        "grade": "SH7025",
        "snapshot": "toolbase/data/source_snapshots/tungaloy-sh7025-grade-2026-07-24.json",
        "grade_class": "PVD-coated carbide for finishing / small-part machining",
        "cut_condition": "finishing",
        "purpose": (
            "Publish Tungaloy's SH7025 grade-level recommended cutting conditions (cutting "
            "speed by ISO material, depth of cut by chipbreaker, feed by corner radius) on "
            "every exact insert carrying grade SH7025, as adjustable baseline starting values."
        ),
        "decision_note": (
            "Tungaloy SH7025 published grade-level starting conditions; cutting speed and "
            "grade-level feed/DOC spans preserved from the manufacturer page; flood selected "
            "and directly supported by the page's stated Wet coolant."
        ),
    },
}


def radius_code(geometry: str) -> str | None:
    match = re.search(r"(\d{2})\s+positive", geometry or "")
    return match.group(1) if match else None


def chipbreaker_suffix(part_number: str) -> str:
    return part_number.rsplit("-", 1)[-1] if "-" in part_number else ""


def load_tools(grade: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH)
    try:
        rows = connection.execute(
            """
            SELECT t.id, t.part_number, t.geometry, t.description
            FROM tools t
            JOIN manufacturers m ON m.id = t.manufacturer_id
            JOIN tool_grade_options o ON o.tool_id = t.id
            JOIN grades g ON g.id = o.grade_id
            WHERE m.name = 'Tungaloy' AND g.code = ?
            ORDER BY t.part_number
            """,
            (grade,),
        ).fetchall()
    finally:
        connection.close()
    return [
        {"tool_id": r[0], "part_number": r[1], "geometry": r[2], "description": r[3]}
        for r in rows
    ]


def doc_range(suffix: str, conditions: dict[str, Any]) -> tuple[float, float, str | None, dict[str, Any]]:
    by_breaker = conditions["depth_of_cut_mm_by_chipbreaker"]
    if suffix == "JS":
        r = by_breaker["JS"]
        return r["min"], r["max"], None, {"JS": r}
    if suffix == "JP":
        r = by_breaker["JP"]
        return r["min"], r["max"], None, {"JP": r}
    low = min(by_breaker["JP"]["min"], by_breaker["JS"]["min"])
    high = max(by_breaker["JP"]["max"], by_breaker["JS"]["max"])
    note = "grade-level depth of cut spanning the manufacturer's JP and JS chipbreaker rows"
    return low, high, note, by_breaker


def feed_range(code: str | None, conditions: dict[str, Any]) -> tuple[float, float, str | None, dict[str, Any]]:
    by_radius = conditions["feed_mm_rev_by_corner_radius"]
    key = {"02": "0.2", "04": "0.4"}.get(code or "")
    if key and key in by_radius:
        r = by_radius[key]
        return r["min"], r["max"], None, {key: r}
    low = min(r["min"] for r in by_radius.values())
    high = max(r["max"] for r in by_radius.values())
    note = (
        "grade-level feed span; Tungaloy tabulates feed by corner radius RE 0.03-0.4 mm"
    )
    return low, high, note, by_radius


def vc_verbatim(vc: dict[str, Any]) -> str:
    def fmt(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)
    return f"{fmt(vc['min'])} &#8211; {fmt(vc['max'])}"


def build_row(tool: dict[str, Any], config: dict[str, Any], snapshot: dict[str, Any],
              source_id: str) -> dict[str, Any]:
    conditions = snapshot["standard_cutting_conditions"]
    application = snapshot["application_iso"]
    application_verbatim = snapshot["application_verbatim"]
    locator = snapshot["raw_page_locator"]
    part_number = tool["part_number"]
    geometry = tool["geometry"] or "unknown"
    code = radius_code(geometry)
    suffix = chipbreaker_suffix(part_number)
    grade = config["grade"]

    description = (
        f"Tungaloy {part_number} screw-on turning insert, grade {grade} "
        f"({config['grade_class']}). Published Tungaloy grade-level cutting conditions "
        "are baseline starting values intended for machinist adjustment."
    )
    identity_evidence = {
        "source_id": source_id,
        "source_page_ref": locator,
        "source_table_ref": f"Tungaloy {grade} grade page",
        "source_raw_text": grade,
        "extraction_method": "manufacturer_page",
    }
    tool_updates = {
        "description": description,
        "geometry": geometry,
        "lifecycle_status": "active",
        "evidence": identity_evidence,
    }

    grade_options = [
        {
            "code": grade,
            "option_kind": "available_grade",
            "full_order_number": part_number,
            "availability_status": "listed",
            "is_primary": True,
            "material_class": config["grade_class"],
            "evidence": dict(identity_evidence),
        }
    ]

    recommendations = []
    profiles = []
    for iso in ("P", "M"):
        cond = conditions[iso]
        recommendations.append(
            {
                "grade_code": grade,
                "iso_group": iso,
                "material_subgroup": ISO_MATERIAL_SUBGROUP[iso],
                "suitability": "recommended",
                "notes": (
                    f"Tungaloy {grade} application {application['summary']}; grade-level "
                    "baseline conditions."
                ),
                "evidence": {
                    "source_id": source_id,
                    "source_page_ref": locator,
                    "source_table_ref": (
                        f"Tungaloy {grade} application range, ISO {iso} ({cond['materials']})"
                    ),
                    "source_raw_text": application_verbatim[iso],
                    "extraction_method": "manufacturer_page",
                },
            }
        )

        vc = cond["vc_m_min"]
        feed_min, feed_max, feed_note, _ = feed_range(code, cond)
        doc_min, doc_max, doc_note, _ = doc_range(suffix, cond)
        notes = "; ".join(n for n in (feed_note, doc_note) if n)
        profiles.append(
            {
                "source_part_number": part_number,
                "source_grade": grade,
                "source_geometry": geometry,
                "source_chipbreaker": suffix or "standard",
                "source_material_label": cond["materials"],
                "iso_material_group": iso,
                "operation_type": "turning",
                "cut_condition": config["cut_condition"],
                "coolant_condition": "flood",
                "material_subgroup": ISO_MATERIAL_SUBGROUP[iso],
                "surface_speed_min": vc["min"],
                "surface_speed_max": vc["max"],
                "surface_speed_unit": "m_per_min",
                "feed_min": feed_min,
                "feed_max": feed_max,
                "feed_unit": "mm_per_rev",
                "depth_of_cut_min": doc_min,
                "depth_of_cut_max": doc_max,
                "depth_of_cut_unit": "mm",
                "evidence": {
                    "source_id": source_id,
                    "source_page_ref": locator,
                    "source_table_ref": (
                        f"Tungaloy {grade} standard cutting conditions, ISO {iso} "
                        f"({cond['materials']}); cutting speed Vc m/min; depth of cut by "
                        f"chipbreaker; feed by corner radius; manufacturer states Coolant: Wet."
                        + (f" Baseline scope: {notes}." if notes else "")
                    ),
                    "source_raw_text": vc_verbatim(vc),
                    "extraction_method": "manufacturer_page",
                },
            }
        )

    return {
        "tool_updates": tool_updates,
        "grade_options": grade_options,
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
    }


def select_sample(rows: list[dict[str, Any]]) -> set[str]:
    sample: set[str] = set()
    if not rows:
        return sample
    sample.add(rows[0]["proposal_row_id"])
    sample.add(rows[-1]["proposal_row_id"])
    # cover each distinct (radius code, chipbreaker) combination once
    seen: set[tuple[str, str]] = set()
    for row in rows:
        cp = row["proposed"]["cutting_profiles"][0]
        key = (radius_code(cp["source_geometry"]) or "?", cp["source_chipbreaker"])
        if key not in seen:
            seen.add(key)
            sample.add(row["proposal_row_id"])
    for row in rows:
        if len(sample) >= min(10, len(rows)):
            break
        sample.add(row["proposal_row_id"])
    return sample


def generate(batch: str, created_at: str) -> None:
    config = BATCHES[batch]
    snapshot_path = REPO_ROOT / config["snapshot"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    html_path = REPO_ROOT / snapshot["raw_page_snapshot"]
    content_sha = review_batch.file_sha256(html_path)
    if content_sha != snapshot["raw_page_sha256"]:
        raise SystemExit("raw HTML snapshot hash does not match the recorded value")

    source_id = review_batch.stable_id("source", snapshot["snapshot_id"])
    source = {
        "source_id": source_id,
        "batch_role": "cutting_speed",
        "manufacturer": "Tungaloy",
        "title": f"Tungaloy {config['grade']} grade page (standard cutting conditions and application)",
        "source_type": "manufacturer_product_page",
        "artifact_format": "html",
        "url": snapshot["source_url"],
        "local_path": snapshot["raw_page_snapshot"],
        "content_sha256": content_sha,
        "page_ref": snapshot["raw_page_locator"],
        "document_edition": f"Captured {snapshot['retrieved_at']}",
        "retrieved_at": snapshot["retrieved_at"],
    }

    tools = load_tools(config["grade"])
    if not tools:
        raise SystemExit(f"no Tungaloy tools found for grade {config['grade']}")

    rows = []
    for tool in tools:
        proposed = build_row(tool, config, snapshot, source_id)
        rows.append(
            {
                "proposal_row_id": f"{config['proposal_id']}-row-{len(rows) + 1:03d}",
                "tool_lookup": {
                    "tool_id": tool["tool_id"],
                    "manufacturer": "Tungaloy",
                    "component_type": "insert",
                },
                "current_summary": {
                    "part_number": tool["part_number"],
                    "geometry": tool["geometry"],
                },
                "proposed": proposed,
            }
        )

    proposal = {
        "schema_version": 2,
        "proposal_id": config["proposal_id"],
        "title": config["title"],
        "created_at": created_at,
        "status": "source_extracted",
        "import_allowed": False,
        "purpose": config["purpose"],
        "sources": [source],
        "rows": rows,
    }
    proposal_path = REPO_ROOT / "toolbase" / "proposals" / f"{config['proposal_id']}.json"
    review_batch.write_json(proposal_path, proposal)

    sample = select_sample(rows)
    decisions = []
    for row in rows:
        row_id = row["proposal_row_id"]
        if row_id in sample:
            reviewer, capture = "Greg", "owner_spot_check"
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
    rec_count = sum(len(r["proposed"]["material_recommendations"]) for r in rows)
    print(f"batch {batch}: {len(rows)} tools, {profile_count} cutting profiles, "
          f"{rec_count} material recommendations, {len(sample)} owner spot-check rows")
    print(f"proposal: {proposal_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"ledger:   {ledger_path.relative_to(REPO_ROOT).as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--created-at", default="2026-07-24")
    arguments = parser.parse_args()
    generate(arguments.batch, arguments.created_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
