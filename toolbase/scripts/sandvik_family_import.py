#!/usr/bin/env python3
"""Generate seed rows and reviewed batches from a Sandvik family snapshot.

This script writes only canonical source inputs: tools.jsonl, its manifest, a schema-2
proposal, and the human decision ledger authorized by the user's family-scope
instruction. review_batch.py must still validate and compile the packet.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sandvik_family_adapter", SCRIPT_DIR / "sandvik_family_adapter.py")
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)

MATERIAL_NAMES = {
    "P": "Steel",
    "M": "Stainless steel",
    "K": "Cast iron",
    "N": "Non-ferrous materials",
    "S": "Heat-resistant superalloys",
    "H": "Hardened materials",
    "O": "Other materials",
}
MATERIAL_TAGS = {
    "P": "steel",
    "M": "stainless-steel",
    "K": "cast-iron",
    "N": "non-ferrous",
    "S": "heat-resistant-superalloys",
    "H": "hardened-materials",
    "O": "other-materials",
}
LIFECYCLE = {"20": "active", "30": "discontinued", "90": "obsolete"}
PROPOSAL_BASE_ID = "sandvik-coroturn107-dcgt-family-2026-07"
SNAPSHOT_REL = "toolbase/data/source_snapshots/sandvik-coroturn107-dcgt-family-2026-07-23.json"
PREEXISTING_MATERIAL_IDS = {"5730414", "5730415"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def product_pointer(material_id: str) -> str:
    return f"/products/{adapter.json_pointer_escape(material_id)}/response/product"


def ptr(material_id: str, suffix: str) -> str:
    return product_pointer(material_id) + suffix


def normalized_claim(source_id: str, source_values: dict[str, Any], value: Any, normalization: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_values": source_values,
        "normalized_value": value,
        "normalization": normalization,
    }


def direct_claim(source_id: str, pointer: str) -> dict[str, Any]:
    return {"source_id": source_id, "source_pointer": pointer}


def evidence(
    source_id: str,
    page_ref: str,
    table_ref: str,
    excerpt: Any,
    claims: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_page_ref": page_ref,
        "source_table_ref": table_ref,
        "source_raw_text": compact_json(excerpt),
        "value_claims": claims,
        "extraction_method": "manufacturer_page",
    }


def lifecycle_status(product: dict[str, Any]) -> str:
    code = str(product.get("LCS") or "")
    if code not in LIFECYCLE:
        raise ValueError(f"unsupported Sandvik lifecycle code {code!r} for {product.get('ORDCODE')}")
    status = LIFECYCLE[code]
    if code == "20" and product.get("TIBPAvailability") != "Available":
        raise ValueError(f"LCS 20 product is not available: {product.get('MaterialID')}")
    if code == "90" and product.get("TIBPAvailability") != "Obsolete":
        raise ValueError(f"LCS 90 product is not marked obsolete: {product.get('MaterialID')}")
    return status


def order_code(product: dict[str, Any]) -> str:
    return adapter.collapse_order_code(product.get("ORDCODE"))


def iso_designation(product: dict[str, Any]) -> str:
    code = order_code(product)
    grade = str(product.get("GRADE") or "")
    if not grade or not code.endswith(" " + grade):
        raise ValueError(f"order code does not end in exact grade: {code}")
    return code[: -(len(grade) + 1)]


def body_designation(product: dict[str, Any]) -> str:
    return iso_designation(product).rsplit("-", 1)[0]


def slug_id(code: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", code.upper()).strip("-")


def geometry_label(product: dict[str, Any]) -> str:
    if product.get("SC") != "Rhombic 55" or float(product.get("AN")) != 7.0:
        raise ValueError(f"unexpected DCGT geometry for {product.get('MaterialID')}")
    return "positive 55-degree rhombic precision turning insert"


def seed_row(product: dict[str, Any], tool_id: str) -> dict[str, Any]:
    material_id = str(product["MaterialID"])
    order = order_code(product)
    groups = [str(value) for value in product.get("TMC1ISO") or []]
    url = "https://www.sandvik.coromant.com/en-gb/product-details?" + adapter.urllib.parse.urlencode(
        {"c": order, "m": material_id}
    )
    return {
        "category": "CoroTurn 107 Inserts",
        "chipbreaker": product["CBMD"],
        "compatible_inserts": [],
        "compatible_machines": [],
        "component_type": "insert",
        "condition": "New",
        "description": f"Sandvik CoroTurn 107 precision turning insert, exact order code {order}, grade {product['GRADE']}, material ID {material_id}.",
        "geometry": geometry_label(product),
        "grade": product["GRADE"],
        "insert_seat": None,
        "iso_designation": iso_designation(product),
        "json_id": tool_id,
        "manufacturer": "Sandvik Coromant",
        "mounts_to": None,
        "price_range": None,
        "shape": "D (55° Rhombic)",
        "size": product["InsertSizeCode"],
        "sources": [url],
        "specs": {
            "clearance_angle_deg": product.get("AN"),
            "cutting_edge_count": product.get("CEDC"),
            "d1_mm": product.get("D1"),
            "hand": product.get("HAND"),
            "ic_mm": product.get("IC"),
            "le_mm": product.get("LE"),
            "manufacturer_material_id": material_id,
            "manufacturer_order_code": order,
            "material_groups": groups,
            "re_mm": product.get("RE"),
            "s_mm": product.get("S"),
            "ssc": str(product["InsertSizeCode"])[:2],
        },
        "tags": [
            "Sandvik",
            "CoroTurn 107",
            "DCGT",
            str(product["CBMD"]),
            str(product["GRADE"]),
            "turning",
            "precision",
            *[MATERIAL_TAGS[group] for group in groups if group in MATERIAL_TAGS],
            *groups,
        ],
        "type": "CoroTurn 107 precision turning insert",
    }


def text_fact(source_id: str, material_id: str, product: dict[str, Any], fact_key: str, source_key: str) -> dict[str, Any] | None:
    source_value = product.get(source_key)
    if source_value is None or source_value == "":
        return None
    value = str(source_value)
    pointer = ptr(material_id, "/" + adapter.json_pointer_escape(source_key))
    claim = direct_claim(source_id, pointer) if isinstance(source_value, str) and source_value == value else normalized_claim(
        source_id,
        {pointer: source_value},
        value,
        "Render the manufacturer value as searchable text without changing its meaning.",
    )
    return {
        "fact_key": fact_key,
        "value_text": value,
        "unit": None,
        "evidence": evidence(source_id, product_pointer(material_id), f"product.{source_key}", {source_key: source_value}, {"value_text": claim}),
    }


def derived_text_fact(
    source_id: str,
    material_id: str,
    product: dict[str, Any],
    fact_key: str,
    value: str,
    source_keys: list[str],
    normalization: str,
) -> dict[str, Any]:
    source_values = {ptr(material_id, "/" + adapter.json_pointer_escape(key)): product.get(key) for key in source_keys}
    excerpt = {key: product.get(key) for key in source_keys}
    return {
        "fact_key": fact_key,
        "value_text": value,
        "unit": None,
        "evidence": evidence(
            source_id,
            product_pointer(material_id),
            ", ".join(f"product.{key}" for key in source_keys),
            excerpt,
            {"value_text": normalized_claim(source_id, source_values, value, normalization)},
        ),
    }


def numeric_fact(
    source_id: str,
    material_id: str,
    product: dict[str, Any],
    fact_key: str,
    source_key: str,
    unit: str,
) -> dict[str, Any] | None:
    value = product.get(source_key)
    if value is None:
        return None
    pointer = ptr(material_id, "/" + adapter.json_pointer_escape(source_key))
    unit_sources = {pointer: value}
    if unit == "mm":
        unit_sources[ptr(material_id, "/UnitSystem")] = product.get("UnitSystem")
    return {
        "fact_key": fact_key,
        "value_number": float(value),
        "unit": unit,
        "evidence": evidence(
            source_id,
            product_pointer(material_id),
            f"product.{source_key}",
            {source_key: value},
            {
                "value_number": normalized_claim(source_id, {pointer: value}, float(value), "Represent the manufacturer number in the catalog numeric type."),
                "unit": normalized_claim(source_id, unit_sources, unit, f"Normalize the manufacturer {source_key} unit to {unit}."),
            },
        ),
    }


def json_fact(source_id: str, material_id: str, product: dict[str, Any], fact_key: str, source_key: str) -> dict[str, Any] | None:
    value = product.get(source_key)
    if value is None:
        return None
    pointer = ptr(material_id, "/" + adapter.json_pointer_escape(source_key))
    return {
        "fact_key": fact_key,
        "value_json": value,
        "unit": None,
        "evidence": evidence(source_id, product_pointer(material_id), f"product.{source_key}", {source_key: value}, {"value_json": direct_claim(source_id, pointer)}),
    }


def build_facts(source_id: str, material_id: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any] | None] = [
        text_fact(source_id, material_id, product, "manufacturer_material_id", "MaterialID"),
        text_fact(source_id, material_id, product, "manufacturer_material_number", "MaterialID"),
        derived_text_fact(source_id, material_id, product, "manufacturer_order_code", order_code(product), ["ORDCODE"], "Collapse manufacturer display padding while preserving every order-code segment."),
        text_fact(source_id, material_id, product, "ean", "EAN"),
        text_fact(source_id, material_id, product, "product_family", "PRODFAM"),
        text_fact(source_id, material_id, product, "operation_classification", "CTPT"),
        text_fact(source_id, material_id, product, "coating", "COATING"),
        text_fact(source_id, material_id, product, "substrate", "SUBSTRATE"),
        derived_text_fact(source_id, material_id, product, "iso_designation", body_designation(product), ["InsertDesignation", "InsertSizeCode"], "Format the exact designation and size code as the ISO body; chipbreaker and grade remain separate."),
        text_fact(source_id, material_id, product, "insert_designation", "InsertDesignation"),
        text_fact(source_id, material_id, product, "insert_size_code", "InsertSizeCode"),
        text_fact(source_id, material_id, product, "insert_shape", "SC"),
        derived_text_fact(source_id, material_id, product, "designation_shape_segment", str(product["InsertDesignation"])[0], ["InsertDesignation", "SC"], "Take ISO 1832 position 1 from InsertDesignation; SC states the exact shape."),
        derived_text_fact(source_id, material_id, product, "designation_clearance_segment", str(product["InsertDesignation"])[1], ["InsertDesignation", "AN"], "Take ISO 1832 position 2 from InsertDesignation; AN corroborates the clearance angle."),
        text_fact(source_id, material_id, product, "designation_tolerance_segment", "InsertTolerance"),
        text_fact(source_id, material_id, product, "designation_style_segment", "InsertGeometry"),
        text_fact(source_id, material_id, product, "insert_mounting_style", "IFS"),
        derived_text_fact(source_id, material_id, product, "designation_size_segment", str(product["InsertSizeCode"])[:2], ["InsertSizeCode", "IC"], "Take the leading size segment from InsertSizeCode; IC supplies the exact dimension."),
        derived_text_fact(source_id, material_id, product, "designation_thickness_segment", str(product["InsertSizeCode"])[2:4], ["InsertSizeCode", "S"], "Take the middle thickness segment from InsertSizeCode; S supplies the exact thickness."),
        derived_text_fact(source_id, material_id, product, "designation_radius_segment", str(product["InsertSizeCode"])[-2:], ["InsertSizeCode", "RE"], "Take the final radius segment from InsertSizeCode; RE supplies the exact nose radius."),
        text_fact(source_id, material_id, product, "designation_chipbreaker_segment", "CBMD"),
        text_fact(source_id, material_id, product, "designation_grade_segment", "GRADE"),
        numeric_fact(source_id, material_id, product, "inscribed_circle_mm", "IC", "mm"),
        numeric_fact(source_id, material_id, product, "cutting_edge_length", "LE", "mm"),
        numeric_fact(source_id, material_id, product, "thickness_mm", "S", "mm"),
        numeric_fact(source_id, material_id, product, "corner_radius_mm", "RE", "mm"),
        numeric_fact(source_id, material_id, product, "hole_size", "D1", "mm"),
        numeric_fact(source_id, material_id, product, "clearance_angle_deg", "AN", "deg"),
        numeric_fact(source_id, material_id, product, "cutting_edge_count", "CEDC", "count"),
        text_fact(source_id, material_id, product, "hand", "HAND"),
        json_fact(source_id, material_id, product, "workpiece_material_groups", "TMC1ISO"),
        text_fact(source_id, material_id, product, "manufacturer_lifecycle_code", "LCS"),
        text_fact(source_id, material_id, product, "manufacturer_availability", "TIBPAvailability"),
        json_fact(source_id, material_id, product, "manufacturer_global_availability", "GloballyAvailable"),
        derived_text_fact(source_id, material_id, product, "lifecycle_status", lifecycle_status(product), ["LCS", "TIBPAvailability", "GloballyAvailable"], "Normalize Sandvik lifecycle and availability fields to the catalog lifecycle vocabulary."),
        text_fact(source_id, material_id, product, "replacement_material_id", "ReplacementProductId"),
        text_fact(source_id, material_id, product, "replacement_cutoff", "NotReplenishedAfter"),
        text_fact(source_id, material_id, product, "replacement_notes", "ReplacementProductInfo"),
    ]
    return [fact for fact in facts if fact is not None]


def material_recommendations(source_id: str, material_id: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    groups = product.get("TMC1ISO") or []
    for index, group in enumerate(groups):
        group = str(group)
        name = MATERIAL_NAMES.get(group, group)
        group_pointer = ptr(material_id, f"/TMC1ISO/{index}")
        item = {
            "grade_code": str(product["GRADE"]),
            "iso_group": group,
            "material_subgroup": name,
            "suitability": "recommended",
            "notes": f"Exact product applicability from product.TMC1ISO; no applicability is inferred beyond the captured response.",
        }
        item["evidence"] = evidence(
            source_id,
            product_pointer(material_id),
            "product.TMC1ISO and product.GRADE",
            {"GRADE": product["GRADE"], "TMC1ISO": groups},
            {
                "grade_code": direct_claim(source_id, ptr(material_id, "/GRADE")),
                "iso_group": direct_claim(source_id, group_pointer),
                "material_subgroup": normalized_claim(source_id, {group_pointer: group}, name, "Expand the ISO 513 workpiece-material group code to its catalog label."),
                "suitability": normalized_claim(source_id, {group_pointer: group}, "recommended", "Presence in the exact product applicability list is normalized as recommended."),
            },
        )
        result.append(item)
    return result


def cutting_profiles(source_id: str, material_id: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for operation_index, operation in enumerate(product.get("CuttingOperations") or []):
        for material_index, material in enumerate(operation.get("materials") or []):
            base = ptr(material_id, f"/CuttingOperations/{operation_index}/materials/{material_index}")
            values = material["startValues"]
            vc, fn, ap = values["vc"], values["fn"], values["ap"]
            material_label = str(material["materialReference"])
            subgroup = f"{material_label} / {material['hardness']:g} {material['hardnessUnit']}"
            geometry = f"{body_designation(product)}, 55-degree rhombic, 7-degree positive"
            item = {
                "source_part_number": order_code(product),
                "source_grade": str(product["GRADE"]),
                "source_geometry": geometry,
                "source_chipbreaker": str(product["CBMD"]),
                "source_material_label": material_label,
                "iso_material_group": str(material["material"]),
                "material_subgroup": subgroup,
                "operation_type": "turning",
                "cut_condition": "unknown",

                "surface_speed_min": float(vc["min"]),
                "surface_speed_start": float(vc["nom"]),
                "surface_speed_max": float(vc["max"]),
                "surface_speed_unit": "m_per_min",
                "feed_min": float(fn["min"]),
                "feed_max": float(fn["max"]),
                "feed_unit": "mm_per_rev",
                "depth_of_cut_min": float(ap["min"]),
                "depth_of_cut_max": float(ap["max"]),
                "depth_of_cut_unit": "mm",
                "notes": f"Manufacturer nominal values retained in source: feed {fn['nom']} mm/rev, depth {ap['nom']} mm, KAPR {operation['calculation']['value']} deg, test life {material['lifeTime']} s. Coolant and cut-condition class are not stated.",
            }
            item["evidence"] = evidence(
                source_id,
                base,
                f"product.CuttingOperations[{operation_index}].materials[{material_index}]",
                material,
                {
                    "source_part_number": normalized_claim(source_id, {ptr(material_id, "/ORDCODE"): product["ORDCODE"]}, item["source_part_number"], "Collapse manufacturer display padding."),
                    "source_grade": direct_claim(source_id, ptr(material_id, "/GRADE")),
                    "source_geometry": normalized_claim(source_id, {ptr(material_id, "/InsertDesignation"): product["InsertDesignation"], ptr(material_id, "/InsertSizeCode"): product["InsertSizeCode"], ptr(material_id, "/SC"): product["SC"], ptr(material_id, "/AN"): product["AN"]}, geometry, "Combine exact designation, size, shape, and clearance into a readable geometry label."),
                    "source_chipbreaker": direct_claim(source_id, ptr(material_id, "/CBMD")),
                    "source_material_label": direct_claim(source_id, base + "/materialReference"),
                    "iso_material_group": direct_claim(source_id, base + "/material"),
                    "material_subgroup": normalized_claim(source_id, {base + "/materialReference": material["materialReference"], base + "/hardness": material["hardness"], base + "/hardnessUnit": material["hardnessUnit"]}, subgroup, "Join the exact material reference and hardness."),
                    "operation_type": normalized_claim(source_id, {ptr(material_id, "/PRODFAM"): product["PRODFAM"]}, "turning", "Normalize the CoroTurn product family to turning."),
                    "cut_condition": {"source_id": source_id, "source_absence": [base + "/cutCondition"], "normalized_value": "unknown", "normalization": "The exact cutting row does not state a cut-condition class."},

                    "surface_speed_min": direct_claim(source_id, base + "/startValues/vc/min"),
                    "surface_speed_start": direct_claim(source_id, base + "/startValues/vc/nom"),
                    "surface_speed_max": direct_claim(source_id, base + "/startValues/vc/max"),
                    "surface_speed_unit": normalized_claim(source_id, {base + "/startValues/vc/unit": vc["unit"]}, "m_per_min", "Normalize the manufacturer unit token to the catalog enum."),
                    "feed_min": direct_claim(source_id, base + "/startValues/fn/min"),
                    "feed_max": direct_claim(source_id, base + "/startValues/fn/max"),
                    "feed_unit": normalized_claim(source_id, {base + "/startValues/fn/unit": fn["unit"]}, "mm_per_rev", "Normalize the manufacturer unit token to the catalog enum."),
                    "depth_of_cut_min": direct_claim(source_id, base + "/startValues/ap/min"),
                    "depth_of_cut_max": direct_claim(source_id, base + "/startValues/ap/max"),
                    "depth_of_cut_unit": direct_claim(source_id, base + "/startValues/ap/unit"),
                },
            )
            result.append(item)
    return result


def proposal_row(source_id: str, material_id: str, product: dict[str, Any], tool_id: str) -> dict[str, Any]:
    order = order_code(product)
    status = lifecycle_status(product)
    geometry = geometry_label(product)
    description = f"Sandvik CoroTurn 107 precision turning insert {order}, material ID {material_id}, grade {product['GRADE']}."
    pbase = product_pointer(material_id)
    update_excerpt = {key: product.get(key) for key in ["ORDCODE", "MaterialID", "GRADE", "CBMD", "SC", "AN", "SubGroup", "LCS", "TIBPAvailability", "GloballyAvailable"]}
    updates = {
        "description": description,
        "geometry": geometry,
        "lifecycle_status": status,
        "grade": str(product["GRADE"]),
        "chipbreaker": str(product["CBMD"]),
    }
    updates["evidence"] = evidence(
        source_id,
        pbase,
        "Exact product identity, geometry, and commercial state",
        update_excerpt,
        {
            "description": normalized_claim(source_id, {ptr(material_id, "/ORDCODE"): product["ORDCODE"], ptr(material_id, "/MaterialID"): product["MaterialID"], ptr(material_id, "/GRADE"): product["GRADE"]}, description, "Collapse order-code spacing and compose a human-readable exact-product description."),
            "geometry": normalized_claim(source_id, {ptr(material_id, "/SC"): product["SC"], ptr(material_id, "/AN"): product["AN"], ptr(material_id, "/SubGroup"): product["SubGroup"]}, geometry, "Normalize Sandvik shape, clearance, and subgroup into the catalog geometry label."),
            "lifecycle_status": normalized_claim(source_id, {ptr(material_id, "/LCS"): product["LCS"], ptr(material_id, "/TIBPAvailability"): product["TIBPAvailability"], ptr(material_id, "/GloballyAvailable"): product["GloballyAvailable"]}, status, "Normalize Sandvik lifecycle and availability fields to the catalog lifecycle vocabulary."),
            "grade": direct_claim(source_id, ptr(material_id, "/GRADE")),
            "chipbreaker": direct_claim(source_id, ptr(material_id, "/CBMD")),
        },
    )
    aliases = [
        {"alias": order, "alias_type": "manufacturer_part_number"},
        {"alias": adapter.normalized_order_code(order), "alias_type": "search"},
        {"alias": material_id, "alias_type": "search"},
    ]
    if product.get("EAN"):
        aliases.append({"alias": str(product["EAN"]), "alias_type": "search"})
    groups = [str(value) for value in product.get("TMC1ISO") or []]
    tags = sorted({
        str(product["GRADE"]).casefold(),
        str(product["CBMD"]).casefold(),
        "coroturn-107",
        "dcgt",
        "precision",
        "sandvik",
        "standalone_exact_product",
        "turning",
        status,
        *[MATERIAL_TAGS[group] for group in groups if group in MATERIAL_TAGS],
    })
    facts = build_facts(source_id, material_id, product)
    return {
        "proposal_row_id": f"sandvik-dcgt-family-{material_id}",
        "tool_lookup": {"tool_id": tool_id, "manufacturer": "Sandvik Coromant", "component_type": "insert"},
        "current_summary": {"grade": str(product["GRADE"]), "geometry": geometry, "review_note": "Exact family product admitted from the captured Sandvik material-ID response."},
        "proposed": {
            "tool_updates": updates,
            "aliases": aliases,
            "tags": tags,
            "replace_fact_keys": sorted(fact["fact_key"] for fact in facts),
            "facts": facts,
            "grade_options": [],
            "replace_material_recommendations": True,
            "material_recommendations": material_recommendations(source_id, material_id, product),
            "cutting_profiles": cutting_profiles(source_id, material_id, product),
        },
    }


def generate(repo_root: Path, snapshot_path: Path) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not snapshot.get("size_query_union_matches_included_family"):
        raise ValueError("snapshot lacks a successful size-query completeness cross-check")
    included = snapshot["included_material_ids"]
    products = {mid: snapshot["products"][mid]["response"]["product"] for mid in included}

    tools_path = repo_root / "toolbase/data/tools.jsonl"
    original_lines = tools_path.read_text(encoding="utf-8").splitlines()
    existing_rows = [json.loads(line) for line in original_lines if line.strip()]
    existing_by_material: dict[str, str] = {}
    existing_ids = {str(row["json_id"]) for row in existing_rows}
    for row in existing_rows:
        material_id = str((row.get("specs") or {}).get("manufacturer_material_id") or "")
        if material_id:
            existing_by_material[material_id] = str(row["json_id"])

    tool_ids: dict[str, str] = {}
    new_rows: list[dict[str, Any]] = []
    for material_id in sorted(included, key=lambda mid: (order_code(products[mid]), mid)):
        product = products[material_id]
        tool_id = existing_by_material.get(material_id) or slug_id(order_code(product))
        if tool_id in existing_ids and material_id not in existing_by_material:
            tool_id = f"{tool_id}-{material_id}"
        if tool_id in tool_ids.values():
            raise ValueError(f"generated duplicate tool ID {tool_id}")
        tool_ids[material_id] = tool_id
        if material_id not in existing_by_material:
            new_rows.append(seed_row(product, tool_id))
            existing_ids.add(tool_id)

    if not set(PREEXISTING_MATERIAL_IDS).issubset(existing_by_material):
        raise ValueError("the two previously released exact DCGT products are missing")
    if len(included) - len(PREEXISTING_MATERIAL_IDS) != 65:
        raise ValueError("expected 65 family products beyond the two previously released products")
    insertion_index = next(
        (index + 1 for index, row in enumerate(existing_rows) if row.get("json_id") == "DCGT-11-T3-02-UM-1115"),
        None,
    )
    if insertion_index is None:
        raise ValueError("existing exact 1115 seed row was not found")
    new_lines = [compact_json(row) for row in new_rows]
    output_lines = original_lines[:insertion_index] + new_lines + original_lines[insertion_index:]
    tools_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8", newline="\n")

    manifest_path = repo_root / "toolbase/data/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_utc"] = snapshot["retrieved_at_utc"]
    manifest["counts"]["tools"] = len(existing_rows) + len(new_rows)
    manifest.pop("tool_count", None)
    manifest.pop("tools_sha256", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    snapshot_hash = sha256_file(snapshot_path)
    source_id = "source-" + snapshot_hash[:16]
    rows = [
        proposal_row(source_id, material_id, products[material_id], tool_ids[material_id])
        for material_id in sorted(included, key=lambda mid: (order_code(products[mid]), mid))
        if material_id not in PREEXISTING_MATERIAL_IDS
    ]
    source = {
        "source_id": source_id,
        "batch_role": "primary_catalog",
        "manufacturer": "Sandvik Coromant",
        "title": "Sandvik CoroTurn 107 DCGT family structured API snapshot",
        "source_type": "manufacturer_product_page",
        "artifact_format": "structured_json",
        "url": snapshot["discovery"]["captures"][-1]["url"],
        "local_path": SNAPSHOT_REL,
        "content_sha256": snapshot_hash,
        "page_ref": "Full structured family snapshot with exact material-ID responses",
        "document_edition": f"Live API responses retrieved {snapshot['retrieved_at_utc']}",
        "retrieved_at": snapshot["retrieved_at_utc"],
        "edition_evidence": "Two broad autocomplete limits agreed; 297 suggestions resolved to 152 material IDs; exact product responses admitted 67 CoroTurn 107 DCGT inserts; size queries reconciled 28 size-07 plus 39 size-11 products.",
        "notes": "The rendered product-details HTML shell is excluded as claim evidence because it can return unrelated product content. All claims point into exact structured responses captured by material ID.",
        "raw_reference": f"{SNAPSHOT_REL} | SHA-256 {snapshot_hash}",
    }
    stale_proposal = repo_root / f"toolbase/proposals/{PROPOSAL_BASE_ID}.json"
    stale_ledger = repo_root / f"toolbase/reviews/{PROPOSAL_BASE_ID}.decisions.json"
    stale_proposal.unlink(missing_ok=True)
    stale_ledger.unlink(missing_ok=True)
    for stale in (repo_root / "toolbase/proposals").glob(f"{PROPOSAL_BASE_ID}-part-*.json"):
        stale.unlink()
    for stale in (repo_root / "toolbase/reviews").glob(f"{PROPOSAL_BASE_ID}-part-*.decisions.json"):
        stale.unlink()
    packet_results = []
    chunks = [rows]
    for packet_number, packet_rows in enumerate(chunks, 1):
        proposal_id = PROPOSAL_BASE_ID if len(chunks) == 1 else f"{PROPOSAL_BASE_ID}-part-{packet_number:02d}"
        proposal = {
            "schema_version": 2,
            "proposal_id": proposal_id,
            "title": f"Sandvik CoroTurn 107 DCGT exact insert family, part {packet_number} of {len(chunks)}",
            "created_at": "2026-07-23",
            "status": "source_extracted",
            "import_allowed": False,
            "purpose": "Admit and enrich every manufacturer-listed CoroTurn 107 DCGT exact insert product discovered from the supplied seed. Preserve every grade-suffixed order code as a separate product, retain obsolete products, and exclude fuzzy DCGW/DCGX/holder matches through product-level identity gates.",
            "sources": [source],
            "rows": packet_rows,
        }
        proposal_path = repo_root / f"toolbase/proposals/{proposal_id}.json"
        proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        proposal_hash = sha256_file(proposal_path)
        ledger = {
            "schema_version": 2,
            "review_id": proposal_id + "-review",
            "proposal_id": proposal_id,
            "proposal_path": f"toolbase/proposals/{proposal_id}.json",
            "proposal_sha256": proposal_hash,
            "review_started_at": "2026-07-23",
            "status": "complete",
            "review_completed_at": "2026-07-23",
            "import_allowed": True,
            "decisions": [
                {
                    "proposal_row_id": row["proposal_row_id"],
                    "tool_id": row["tool_lookup"]["tool_id"],
                    "decision": "approved",
                    "reviewer": "Greg",
                    "decided_at": "2026-07-23",
                    "capture_method": "interactive_user_direction_in_hermes_chat",
                    "approved_scope": [
                        "use the supplied DCGT 11 T3 01-UM 1105 product as the seed for all manufacturer-listed CoroTurn 107 DCGT inserts",
                        "preserve every complete grade-suffixed Sandvik order code and material ID as a separate exact product",
                        "retain active, being-replaced, and obsolete products with source-backed lifecycle and replacement facts",
                        "publish exact product material applicability and cutting rows without generating hypothetical part-number combinations",
                    ],
                    "notes": "Greg selected all Sandvik CoroTurn 107 DCGT inserts as the standing family scope and supplied material ID 5730446 as the seed. This row is one exact manufacturer product admitted by the adapter's identity and family gates.",
                }
                for row in packet_rows
            ],
        }
        ledger_path = repo_root / f"toolbase/reviews/{proposal_id}.decisions.json"
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        packet_results.append(
            {
                "proposal_id": proposal_id,
                "rows": len(packet_rows),
                "proposal": str(proposal_path),
                "ledger": str(ledger_path),
                "proposal_sha256": proposal_hash,
            }
        )
    return {
        "family_products": len(included),
        "existing_products_preserved": len(PREEXISTING_MATERIAL_IDS),
        "new_seed_rows_added_this_run": len(new_rows),
        "family_products_admitted_by_packet": len(rows),
        "proposal_rows": len(rows),
        "material_recommendations": sum(len(row["proposed"]["material_recommendations"]) for row in rows),
        "cutting_profiles": sum(len(row["proposed"]["cutting_profiles"]) for row in rows),
        "packets": packet_results,
        "snapshot_sha256": snapshot_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.repo_root.resolve(), args.snapshot.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
