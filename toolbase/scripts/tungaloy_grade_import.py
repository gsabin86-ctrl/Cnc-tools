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
import hashlib
import importlib.util
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SOURCE_SPEC = importlib.util.spec_from_file_location(
    "tungaloy_grade_source", SCRIPT_DIR / "tungaloy_grade_source.py"
)
assert SOURCE_SPEC and SOURCE_SPEC.loader
_tungaloy_source = importlib.util.module_from_spec(SOURCE_SPEC)
SOURCE_SPEC.loader.exec_module(_tungaloy_source)
parse_standard_conditions = _tungaloy_source.parse_standard_conditions
validate_snapshot_against_html = _tungaloy_source.validate_snapshot_against_html


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


DB_PATH = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"

ISO_MATERIAL_SUBGROUP = {"P": "Carbon / alloy steel", "M": "Stainless steel"}

BATCHES = {
    "sh7025": {
        "import_id": "tungaloy-sh7025-grade-baselines-2026-07",
        "output": "toolbase/data/manufacturer_imports/tungaloy-sh7025-grade-baselines-2026-07.json",
        "title": "Tungaloy SH7025 grade baselines",
        "grade": "SH7025",
        "snapshot": "toolbase/data/source_snapshots/tungaloy-sh7025-grade-2026-07-24.json",
        "grade_class": "PVD-coated carbide for finishing / small-part machining",
        "cut_condition": "finishing",
        "purpose": (
            "Publish Tungaloy's SH7025 material applicability on every exact insert carrying "
            "the grade, and cutting profiles only where the exact chipbreaker and radius fit "
            "a strict manufacturer feed band."
        ),
        "decision_note": (
            "Tungaloy SH7025 source-bound starting conditions; unsupported radius or "
            "chipbreaker combinations omitted, and coolant remains unknown because the "
            "standard-condition table does not state it."
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
            SELECT DISTINCT t.id, t.part_number, t.geometry, t.description
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


def feed_range(
    code: str | None,
    suffix: str,
    conditions: dict[str, Any],
) -> tuple[float | None, float | None, str | None, dict[str, Any]]:
    radius_mm = float(int(code)) / 10 if code and code.isdigit() else None
    by_breaker = conditions["feed_mm_rev_by_chipbreaker_and_strict_radius_band"]
    source = {"radius_mm": radius_mm, "chipbreaker": suffix or "standard"}
    bands = by_breaker.get(suffix)
    if radius_mm is None:
        return None, None, "corner radius is not available for strict feed-band matching", source
    if bands is None:
        return None, None, "chipbreaker is not listed in the manufacturer feed table", source
    for band in bands:
        if radius_mm < band["max_corner_radius_exclusive_mm"]:
            source["selected_band"] = band
            if band["min"] is None or band["max"] is None:
                return None, None, "manufacturer table is blank for the matching strict feed band", source
            return band["min"], band["max"], None, source
    return (
        None,
        None,
        f"corner radius {radius_mm:g} mm is outside the strict published feed bands",
        source,
    )


def vc_verbatim(vc: dict[str, Any]) -> str:
    def fmt(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)
    return f"{fmt(vc['min'])} &#8211; {fmt(vc['max'])}"


def build_row(
    tool: dict[str, Any],
    config: dict[str, Any],
    snapshot: dict[str, Any],
    source_id: str,
    html_evidence: dict[str, Any] | None = None,
    normalized_source_id: str | None = None,
) -> dict[str, Any]:
    if snapshot.get("feed_value_semantics") != "minimum_and_maximum":
        raise ValueError("Tungaloy feed cells must be explicitly classified as min/max ranges")
    if snapshot.get("feed_radius_semantics") != "strict_exclusive_upper_bounds":
        raise ValueError("Tungaloy feed bands must retain their strict RE upper bounds")
    conditions = snapshot["standard_cutting_conditions"]
    application = snapshot["application_iso"]
    application_verbatim = snapshot["application_verbatim"]
    locator = snapshot["raw_page_locator"]
    part_number = tool["part_number"]
    geometry = tool["geometry"] or "unknown"
    code = radius_code(geometry)
    suffix = chipbreaker_suffix(part_number)
    grade = config["grade"]
    normalized_source_id = normalized_source_id or source_id

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
        feed_min, feed_max, feed_note, feed_source = feed_range(code, suffix, cond)
        if feed_min is None or feed_max is None:
            continue
        doc_min, doc_max, doc_note, _ = doc_range(suffix, cond)
        notes = "; ".join(n for n in (feed_note, doc_note) if n)
        feed_bands = cond["feed_mm_rev_by_chipbreaker_and_strict_radius_band"][suffix]
        selected_band = feed_source["selected_band"]
        try:
            selected_band_index = feed_bands.index(selected_band)
        except ValueError as error:
            raise ValueError("selected Tungaloy feed band is absent from the snapshot") from error
        condition_pointer = f"/standard_cutting_conditions/{iso}"
        numeric_claims = {
            "surface_speed_min": {
                "source_id": normalized_source_id,
                "source_pointer": f"{condition_pointer}/vc_m_min/min",
            },
            "surface_speed_max": {
                "source_id": normalized_source_id,
                "source_pointer": f"{condition_pointer}/vc_m_min/max",
            },
            "feed_min": {
                "source_id": normalized_source_id,
                "source_pointer": (
                    f"{condition_pointer}/feed_mm_rev_by_chipbreaker_and_strict_radius_band/"
                    f"{suffix}/{selected_band_index}/min"
                ),
            },
            "feed_max": {
                "source_id": normalized_source_id,
                "source_pointer": (
                    f"{condition_pointer}/feed_mm_rev_by_chipbreaker_and_strict_radius_band/"
                    f"{suffix}/{selected_band_index}/max"
                ),
            },
            "depth_of_cut_min": {
                "source_id": normalized_source_id,
                "source_pointer": (
                    f"{condition_pointer}/depth_of_cut_mm_by_chipbreaker/{suffix}/min"
                ),
            },
            "depth_of_cut_max": {
                "source_id": normalized_source_id,
                "source_pointer": (
                    f"{condition_pointer}/depth_of_cut_mm_by_chipbreaker/{suffix}/max"
                ),
            },
        }
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
                "coolant_condition": "unknown",
                "material_subgroup": ISO_MATERIAL_SUBGROUP[iso],
                "surface_speed_min": vc["min"],
                "surface_speed_max": vc["max"],
                "surface_speed_unit": "m_per_min",
                "feed_min": feed_min,
                "feed_max": feed_max,
                "feed_unit": "mm_per_rev" if feed_min is not None else None,
                "depth_of_cut_min": doc_min,
                "depth_of_cut_max": doc_max,
                "depth_of_cut_unit": "mm",
                "source_feed_bands": feed_source,
                "notes": "Coolant remains unknown; the standard-condition table does not state it.",
                "evidence": {
                    "source_id": source_id,
                    "source_page_ref": locator,
                    "source_table_ref": (
                        f"Tungaloy {grade} standard cutting conditions, ISO {iso} "
                        f"({cond['materials']}); cutting speed Vc m/min; depth of cut by "
                        f"chipbreaker; feed by strict corner-radius upper bound and chipbreaker "
                        f"row; coolant is not stated in this standard-condition table."
                        + (f" Baseline scope: {notes}." if notes else "")
                    ),
                    "source_raw_text": (
                        html_evidence["table_html"] if html_evidence else vc_verbatim(vc)
                    ),
                    "extraction_method": "manufacturer_page",
                    "value_claims": numeric_claims,
                    "sources": (
                        [
                            {
                                "source_id": source_id,
                                "evidence_role": role,
                                "source_page_ref": locator,
                                "source_table_ref": "Standard cutting conditions table",
                                "source_raw_text": html_evidence["table_html"],
                                "extraction_method": "manufacturer_page",
                            }
                            for role in ("cutting_speed", "geometry_parameters")
                        ]
                        if html_evidence
                        else []
                    )
                    + [
                        {
                            "source_id": normalized_source_id,
                            "evidence_role": "verification",
                            "source_page_ref": condition_pointer,
                            "source_table_ref": "Hash-verified normalized standard cutting conditions",
                            "source_raw_text": json.dumps(
                                cond,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            "extraction_method": "normalized_from_manufacturer_page",
                        }
                    ],
                },
            }
        )

    return {
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
        "tags": [],
        "additive_only": True,
    }


def canonicalize_row(
    tool: dict[str, Any],
    proposed: dict[str, Any],
    import_id: str,
) -> dict[str, Any]:
    tool_id = tool["tool_id"]
    recommendations = []
    for item in proposed["material_recommendations"]:
        evidence = item["evidence"]
        recommendations.append(
            {
                "id": stable_id(
                    "material-recommendation",
                    import_id,
                    tool_id,
                    item["grade_code"],
                    item["iso_group"],
                    item.get("material_subgroup"),
                ),
                "grade_code": item["grade_code"],
                "iso_group": item["iso_group"],
                "material_subgroup": item.get("material_subgroup"),
                "suitability": item["suitability"],
                "evidence_status": "manufacturer_claim",
                "verification_status": "manufacturer_verified",
                "source_id": evidence["source_id"],
                "source_ids": [evidence["source_id"]],
                "source_page_ref": evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manufacturer_page",
                "notes": item.get("notes"),
            }
        )

    profiles = []
    for item in proposed["cutting_profiles"]:
        evidence = item["evidence"]
        profile = {
            key: value
            for key, value in item.items()
            if key not in {"evidence", "source_feed_bands"}
        }
        profile.update(
            {
                "id": stable_id(
                    "cutting-profile",
                    import_id,
                    tool_id,
                    item["source_grade"],
                    item["iso_material_group"],
                    item["source_chipbreaker"],
                ),
                "source_id": evidence["source_id"],
                "source_page_ref": evidence.get("source_page_ref"),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manufacturer_page",
                "verification_status": "manufacturer_verified",
                "evidence_sources": evidence.get("sources") or [],
            }
        )
        profiles.append(profile)

    return {
        "tool_id": tool_id,
        "grade_code": BATCHES["sh7025"]["grade"],
        "material_recommendations": recommendations,
        "cutting_profiles": profiles,
    }


def select_sample(rows: list[dict[str, Any]]) -> set[str]:
    sample: set[str] = set()
    if not rows:
        return sample
    sample.add(rows[0]["tool_id"])
    sample.add(rows[-1]["tool_id"])
    for row in rows:
        if row["cutting_profiles"]:
            sample.add(row["tool_id"])
    for row in rows:
        if len(sample) >= min(10, len(rows)):
            break
        sample.add(row["tool_id"])
    return sample


def generate(batch: str, created_at: str) -> Path:
    config = BATCHES[batch]
    snapshot_path = REPO_ROOT / config["snapshot"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    html_path = REPO_ROOT / snapshot["raw_page_snapshot"]
    content_sha = file_sha256(html_path)
    if content_sha != snapshot["raw_page_sha256"]:
        raise SystemExit("raw HTML snapshot hash does not match the recorded value")
    html_evidence = validate_snapshot_against_html(
        snapshot, html_path.read_text(encoding="utf-8")
    )

    source_id = stable_id("source", snapshot["snapshot_id"])
    normalized_source_id = stable_id(
        "source", snapshot["snapshot_id"], "normalized-standard-conditions"
    )
    source = {
        "id": source_id,
        "manufacturer": "Tungaloy",
        "title": f"Tungaloy {config['grade']} grade page (standard cutting conditions and application)",
        "source_type": "manufacturer_product_page",
        "url": snapshot["source_url"],
        "local_path": snapshot["raw_page_snapshot"],
        "content_sha256": content_sha,
        "page_ref": snapshot["raw_page_locator"],
        "raw_reference": f"{snapshot['raw_page_snapshot']} | SHA-256 {content_sha}",
        "document_edition": f"Captured {snapshot['retrieved_at']}",
        "retrieved_at": snapshot["retrieved_at"],
        "notes": None,
    }
    normalized_source = {
        "id": normalized_source_id,
        "manufacturer": "Tungaloy",
        "title": f"Tungaloy {config['grade']} normalized standard cutting conditions",
        "source_type": "local_file",
        "url": snapshot["source_url"],
        "local_path": config["snapshot"],
        "content_sha256": file_sha256(snapshot_path),
        "page_ref": "/standard_cutting_conditions",
        "raw_reference": f"{config['snapshot']} | SHA-256 {file_sha256(snapshot_path)}",
        "document_edition": f"Parsed from Tungaloy HTML captured {snapshot['retrieved_at']}",
        "retrieved_at": snapshot["retrieved_at"],
        "notes": "Deterministic normalized rows used by the manufacturer import.",
    }

    tools = load_tools(config["grade"])
    if not tools:
        raise SystemExit(f"no Tungaloy tools found for grade {config['grade']}")
    rows = [
        canonicalize_row(
            tool,
            build_row(
                tool,
                config,
                snapshot,
                source_id,
                html_evidence,
                normalized_source_id,
            ),
            config["import_id"],
        )
        for tool in tools
    ]
    payload = {
        "schema_version": 1,
        "import_id": config["import_id"],
        "title": config["title"],
        "generated_at": created_at,
        "manufacturer": "Tungaloy",
        "sources": [source, normalized_source],
        "rows": rows,
    }
    output_path = REPO_ROOT / config["output"]
    write_json(output_path, payload)

    sample = select_sample(rows)
    profile_count = sum(len(row["cutting_profiles"]) for row in rows)
    rec_count = sum(len(row["material_recommendations"]) for row in rows)
    print(
        f"batch {batch}: {len(rows)} tools, {profile_count} cutting profiles, "
        f"{rec_count} material recommendations, {len(sample)} spot-check rows"
    )
    try:
        displayed_output = output_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        displayed_output = str(output_path)
    print(f"canonical import: {displayed_output}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--created-at", default="2026-07-24")
    arguments = parser.parse_args()
    generate(arguments.batch, arguments.created_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
