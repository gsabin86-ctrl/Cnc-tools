#!/usr/bin/env python3
"""Compile an authorized cutting-data review into a deterministic build input."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from validate_cutting_proposal import validate


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROPOSAL = REPO_ROOT / "toolbase" / "proposals" / "kennametal-topswiss-pilot.json"
DEFAULT_LEDGER = REPO_ROOT / "toolbase" / "reviews" / "kennametal-topswiss-pilot.decisions.json"
DEFAULT_DB = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
DEFAULT_OUT = REPO_ROOT / "toolbase" / "data" / "reviewed_imports" / "kennametal-topswiss-pilot.json"

GRADE_FACTS = {
    "KN10S": {
        "material": "uncoated fine-grain carbide",
        "coating": "none",
        "tags": ["carbide", "fine-grain", "uncoated"],
    },
    "KTP25S": {
        "material": "cermet",
        "coating": "multilayer PVD coating",
        "tags": ["cermet", "PVD-coated"],
    },
    "KCP20S": {
        "material": "cemented carbide",
        "coating": "TiCN multilayer PVD coating",
        "tags": ["carbide", "TiCN", "PVD-coated"],
    },
    "KCM25S": {
        "material": "cemented carbide",
        "coating": "AlTiN + AlCrN multilayer PVD coating",
        "tags": ["carbide", "AlTiN", "AlCrN", "PVD-coated"],
    },
    "KCS25S": {
        "material": "cemented carbide",
        "coating": "enriched multilayer PVD coating",
        "tags": ["carbide", "PVD-coated"],
    },
}

GEOMETRY_FACTS = {
    "PPS": ("positive parallel-positive", "medium", "medium-machining"),
    "FFS": ("positive fine-finishing", "finishing", "fine-finishing"),
    "FWS": ("positive finishing wiper Swiss", "finishing", "finishing-wiper"),
    "FPS": ("positive finish machining", "finishing", "finish-machining"),
    "MWS": ("positive medium wiper Swiss", "medium", "medium-wiper"),
    "LFS": ("positive light-machining", "finishing", "light-machining"),
}

MATERIAL_TAGS = {
    "P": "steel",
    "M": "stainless-steel",
    "K": "cast-iron",
    "N": "non-ferrous",
    "S": "high-temperature-alloys",
    "H": "hardened-materials",
    "O": "other-materials",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def source_id_for_url(url: str) -> str:
    return stable_id("source", url)


def source_record(source: dict[str, Any]) -> dict[str, Any]:
    url = str(source["url"])
    hostname = (urlparse(url).hostname or "").casefold()
    if url.casefold().endswith(".pdf"):
        source_type = "manufacturer_catalog"
    elif hostname == "www.kennametal.com" or hostname.endswith(".kennametal.com"):
        source_type = "manufacturer_product_page"
    else:
        source_type = "secondary_web"
    accessed = source.get("accessed_at")
    return {
        "id": source_id_for_url(url),
        "source_type": source_type,
        "title": source["title"],
        "url": url,
        "local_path": None,
        "page_ref": None,
        "manufacturer": "Kennametal" if "kennametal.com" in hostname else None,
        "raw_reference": url,
        "notes": f"Reviewer verification source; accessed {accessed}." if accessed else "Reviewer verification source.",
    }


def fact(
    tool_id: str,
    key: str,
    value: Any,
    source_id: str,
    evidence_status: str,
    *,
    unit: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": stable_id("fact", "reviewed", tool_id, key),
        "fact_key": key,
        "original_key": f"reviewed_{key}",
        "unit": unit,
        "evidence_status": evidence_status,
        "source_id": source_id,
        "source_ids": [source_id],
    }
    if isinstance(value, bool):
        result["value_boolean"] = value
    elif isinstance(value, (int, float)):
        result["value_number"] = value
    elif isinstance(value, (list, dict)):
        result["value_json"] = value
    else:
        result["value_text"] = str(value)
    return result


def catalog_page_ref(row: dict[str, Any]) -> str:
    parameters = row["parameters"]
    pages = sorted(
        {
            int(parameters["surface_speed"]["source_page"]),
            int(parameters["feed"]["source_page"]),
            int(parameters["depth_of_cut"]["source_page"]),
        }
    )
    label = "page" if len(pages) == 1 else "pages"
    return f"PDF {label} {', '.join(str(page) for page in pages)}"


def catalog_table_ref(row: dict[str, Any]) -> str:
    parameters = row["parameters"]
    return " | ".join(
        dict.fromkeys(
            [
                parameters["surface_speed"]["source_table"],
                parameters["feed"]["source_table"],
                parameters["depth_of_cut"]["source_table"],
            ]
        )
    )


def cutting_direction(iso_number: str) -> str:
    if "RPPS" in iso_number:
        return "Right"
    if "LPPS" in iso_number:
        return "Left"
    return "Neutral"


def exact_product_source_id(decision: dict[str, Any]) -> str | None:
    for source in decision.get("additional_sources") or []:
        url = str(source.get("url") or "")
        if "/products/p." in url or re.search(r"\bmaterial\s+\d+\b", str(source.get("title") or ""), re.I):
            return source_id_for_url(url)
    return None


def manufacturer_source_id(decision: dict[str, Any], catalog_source_id: str) -> str:
    for source in decision.get("additional_sources") or []:
        url = str(source.get("url") or "")
        if "kennametal.com" in urlparse(url).netloc.casefold():
            return source_id_for_url(url)
    return catalog_source_id


def canonical_tags(
    row: dict[str, Any],
    decision: dict[str, Any],
    direction: str,
    operation_tag: str,
) -> list[str]:
    match = row["source_match"]
    grade = match["grade"]
    geometry = match["geometry_code"]
    shape_match = re.match(r"[A-Z]{4}", match["iso_catalog_number"])
    tags = {
        "turning",
        "swiss-type",
        "kennametal",
        "topswiss",
        "positive",
        grade,
        geometry,
        operation_tag,
        MATERIAL_TAGS[row["work_material"]["iso_group"]],
    }
    if shape_match:
        tags.add(shape_match.group(0))
    if direction != "Neutral":
        tags.add(f"{direction.casefold()}-hand")
    for grade_tag in GRADE_FACTS[grade]["tags"]:
        tags.add(grade_tag)
    for iso_group in decision.get("manufacturer_supported_iso_groups") or []:
        if iso_group in MATERIAL_TAGS:
            tags.add(MATERIAL_TAGS[iso_group])
    return sorted(tags, key=lambda value: (value.casefold(), value))


def compile_packet(
    proposal_path: Path,
    ledger_path: Path,
    db_path: Path,
) -> dict[str, Any]:
    validation = validate(proposal_path, db_path, ledger_path)
    if not validation["valid"]:
        raise ValueError("Review validation failed:\n" + "\n".join(validation["errors"]))
    if not validation["import_allowed"]:
        raise ValueError("The review ledger has not authorized import")

    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    decisions = {item["proposal_row_id"]: item for item in ledger["decisions"]}
    source = proposal["source"]
    catalog_source_id = stable_id("source", source["catalog_id"])
    catalog_source = {
        "id": catalog_source_id,
        "source_type": "manufacturer_catalog",
        "title": source["title"],
        "url": None,
        "local_path": source["local_path"],
        "page_ref": "PDF pages " + ", ".join(str(page) for page in source["visual_reviewed_pages"]),
        "manufacturer": source["manufacturer"],
        "raw_reference": f"{source['local_path']} | SHA-256 {source['sha256']}",
        "notes": source.get("catalog_date_evidence"),
    }
    sources: dict[str, dict[str, Any]] = {catalog_source_id: catalog_source}
    compiled_rows: list[dict[str, Any]] = []

    for row in proposal["rows"]:
        row_id = row["proposal_row_id"]
        decision = decisions[row_id]
        if decision["decision"] not in {"approved", "approved_with_corrections"}:
            raise ValueError(f"{row_id}: decision is not importable")
        for additional in decision.get("additional_sources") or []:
            normalized = source_record(additional)
            sources[normalized["id"]] = normalized

        tool_id = row["tool_lookup"]["tool_id"]
        match = row["source_match"]
        grade = match["grade"]
        geometry_code = match["geometry_code"]
        geometry, cut_condition, operation_tag = GEOMETRY_FACTS[geometry_code]
        direction = cutting_direction(match["iso_catalog_number"])
        direct_source_id = manufacturer_source_id(decision, catalog_source_id)
        product_source_id = exact_product_source_id(decision)
        row_source_ids = [catalog_source_id] + [
            source_id_for_url(item["url"]) for item in decision.get("additional_sources") or []
        ]
        row_facts = [
            fact(tool_id, "ansi_catalog_id", match["ansi_catalog_number"], catalog_source_id, "catalog_claim"),
            fact(tool_id, "iso_catalog_id", match["iso_catalog_number"], catalog_source_id, "catalog_claim"),
            fact(tool_id, "geometry", geometry, catalog_source_id, "catalog_claim"),
            fact(tool_id, "cutting_direction", direction, catalog_source_id, "catalog_claim"),
            fact(tool_id, "grade_material", GRADE_FACTS[grade]["material"], direct_source_id, "manufacturer_claim"),
            fact(tool_id, "grade_coating", GRADE_FACTS[grade]["coating"], direct_source_id, "manufacturer_claim"),
            fact(
                tool_id,
                "catalog_grade_availability",
                "listed for exact catalog number",
                catalog_source_id,
                "catalog_claim",
            ),
        ]
        priority = decision.get("grade_selection_priority")
        first_choice = decision.get("first_choice_grade_for_condition")
        if priority:
            row_facts.append(
                fact(tool_id, "grade_selection_priority", priority, catalog_source_id, "catalog_claim")
            )
        if not first_choice and priority in {"first_choice", "sole_listed_grade"}:
            first_choice = grade
        if first_choice:
            row_facts.append(
                fact(tool_id, "first_choice_grade", first_choice, catalog_source_id, "catalog_claim")
            )
        material_number = decision.get("manufacturer_material_number")
        if material_number:
            if not product_source_id:
                raise ValueError(f"{row_id}: material number lacks an exact product source")
            row_facts.append(
                fact(tool_id, "material_number", material_number, product_source_id, "manufacturer_claim")
            )
        lifecycle = decision.get("lifecycle_status")
        if lifecycle == "no_longer_available":
            if not product_source_id:
                raise ValueError(f"{row_id}: discontinued lifecycle lacks an exact product source")
            row_facts.append(
                fact(
                    tool_id,
                    "manufacturer_lifecycle",
                    "no longer available",
                    product_source_id,
                    "manufacturer_claim",
                )
            )
        if match["product_page"] in {3, 6}:
            row_facts.append(
                fact(
                    tool_id,
                    "corner_radius_minus_tolerance",
                    -0.05,
                    catalog_source_id,
                    "catalog_claim",
                    unit="mm",
                )
            )
        ambiguities = list(source.get("source_ambiguities") or []) + list(
            decision.get("source_ambiguities") or []
        )
        if ambiguities and any(
            parameter["source_page"] == 18 for parameter in row["parameters"].values()
        ):
            row_facts.append(
                fact(
                    tool_id,
                    "source_ambiguities",
                    list(dict.fromkeys(ambiguities)),
                    catalog_source_id,
                    "catalog_claim",
                )
            )

        suitability = "primary" if priority in {"first_choice", "sole_listed_grade"} else "recommended"
        material = row["work_material"]
        recommendations = [
            {
                "id": stable_id("material", "reviewed", tool_id, material["iso_group"], material["subgroup"]),
                "iso_group": material["iso_group"],
                "material_subgroup": material["subgroup"],
                "suitability": suitability,
                "evidence_status": "catalog_claim",
                "source_id": catalog_source_id,
                "source_ids": [catalog_source_id],
                "notes": f"Reviewed catalog profile: {material['catalog_label']}.",
            }
        ]
        for iso_group in decision.get("manufacturer_supported_iso_groups") or []:
            if iso_group == material["iso_group"]:
                continue
            if not product_source_id:
                raise ValueError(f"{row_id}: manufacturer material group lacks an exact product source")
            recommendations.append(
                {
                    "id": stable_id("material", "reviewed", tool_id, iso_group, "manufacturer-group"),
                    "iso_group": iso_group,
                    "material_subgroup": None,
                    "suitability": "recommended",
                    "evidence_status": "manufacturer_claim",
                    "source_id": product_source_id,
                    "source_ids": [product_source_id],
                    "notes": "Manufacturer product-page applicability; no speeds and feeds are implied for this group.",
                }
            )

        parameters = row["parameters"]
        note_parts = [
            f"Review {row_id}: {decision['decision']} by {decision['reviewer']} on {decision['decided_at']}.",
            decision["notes"],
        ]
        if priority:
            note_parts.append(f"Grade selection priority: {priority}; first choice: {first_choice or 'not recorded'}.")
        if ambiguities and any(
            parameter["source_page"] == 18 for parameter in parameters.values()
        ):
            note_parts.append("Source ambiguity: " + " ".join(dict.fromkeys(ambiguities)))
        cutting_profile = {
            "id": stable_id("cutting-profile", proposal["proposal_id"], row_id, tool_id),
            "source_id": catalog_source_id,
            "source_part_number": match["iso_catalog_number"],
            "source_grade": grade,
            "source_geometry": match["catalog_section"],
            "source_chipbreaker": geometry_code,
            "source_material_label": material["catalog_label"],
            "iso_material_group": material["iso_group"],
            "material_subgroup": material["subgroup"],
            "operation_type": row["operation"]["operation_type"],
            "cut_condition": cut_condition,
            "coolant_condition": row["operation"]["coolant_condition"],
            "surface_speed_min": parameters["surface_speed"]["min"],
            "surface_speed_start": parameters["surface_speed"]["start"],
            "surface_speed_max": parameters["surface_speed"]["max"],
            "surface_speed_unit": parameters["surface_speed"]["unit"],
            "feed_min": parameters["feed"]["min"],
            "feed_max": parameters["feed"]["max"],
            "feed_unit": parameters["feed"]["unit"],
            "depth_of_cut_min": parameters["depth_of_cut"]["min"],
            "depth_of_cut_max": parameters["depth_of_cut"]["max"],
            "depth_of_cut_unit": parameters["depth_of_cut"]["unit"],
            "source_page_ref": catalog_page_ref(row),
            "source_table_ref": catalog_table_ref(row),
            "source_raw_text": row["evidence"]["source_raw_text"],
            "extraction_method": row["evidence"]["extraction_method"],
            "verification_status": "catalog_verified",
            "reviewer": decision["reviewer"],
            "reviewed_at": decision["decided_at"],
            "notes": " ".join(note_parts),
        }
        compiled_rows.append(
            {
                "proposal_row_id": row_id,
                "tool_id": tool_id,
                "decision": decision["decision"],
                "tool_updates": {
                    "description": decision.get("canonical_description"),
                    "geometry": geometry,
                    "lifecycle_status": "discontinued" if lifecycle == "no_longer_available" else "unknown",
                    "evidence_status": "catalog_source",
                },
                "aliases": [
                    {"alias": match["ansi_catalog_number"], "alias_type": "ansi"},
                    {"alias": match["iso_catalog_number"], "alias_type": "iso"},
                ],
                "source_ids": list(dict.fromkeys(row_source_ids)),
                "tags": canonical_tags(row, decision, direction, operation_tag),
                "replace_fact_keys": sorted({item["fact_key"] for item in row_facts}),
                "facts": row_facts,
                "replace_material_recommendations": True,
                "material_recommendations": recommendations,
                "cutting_profiles": [cutting_profile],
            }
        )

    batch_id = stable_id("review-batch", proposal["proposal_id"])
    return {
        "schema_version": 1,
        "import_id": batch_id,
        "proposal_id": proposal["proposal_id"],
        "proposal_path": relative_path(proposal_path),
        "proposal_sha256": sha256(proposal_path),
        "review_ledger_path": relative_path(ledger_path),
        "review_ledger_sha256": sha256(ledger_path),
        "catalog_sha256": source["sha256"],
        "reviewed_at": ledger["review_completed_at"],
        "row_count": len(compiled_rows),
        "catalog_source_id": catalog_source_id,
        "sources": sorted(sources.values(), key=lambda item: item["id"]),
        "rows": compiled_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify output is current without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet = compile_packet(args.proposal.resolve(), args.ledger.resolve(), args.db.resolve())
    rendered = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
    output = args.out.resolve()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print(f"STALE: {output}")
            return 1
        print(f"CURRENT: {output} ({packet['row_count']} reviewed rows)")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"WROTE: {output} ({packet['row_count']} reviewed rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
