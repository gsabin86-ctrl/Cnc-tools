#!/usr/bin/env python3
"""Upsert the exact Iscar SCIR/L-22-BR/BL/BRA/BLA family into tools.jsonl.

The source is a frozen response from Iscar USA's public product endpoint. Each
ProductName/ManufacturerNo/product_id tuple remains a separate sellable identity.
The source contains no speeds or feeds, so this importer creates none.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any


FAMILY_NAME = "SCIR/L-22-BR/BL/BRA/BLA"
EXPECTED_COUNT = 16
SEED_PRODUCT_ID = 1953152
SNAPSHOT_INDEX_KEY = "__snapshot_index"
SNAPSHOT_REL = "toolbase/data/source_snapshots/iscar-scir-l-22-br-bl-bra-bla-family-2026-07-24.json"
IMPORT_REL = "toolbase/data/manufacturer_imports/iscar-scirl22-family-2026-07.json"
IMPORT_ID = "iscar-scirl22-family-2026-07"
MATERIAL_GROUPS = {
    "Steel": "P",
    "Stainless Steel": "M",
    "Cast Iron": "K",
    "Aluminum / Non-Ferrous Materials": "N",
    "Hard Materials": "H",
    "Super-Alloys / Titanium": "S",
}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def inches_to_mm(value: float) -> float:
    return float(Decimal(str(value)) * Decimal("25.4"))


def family_documents(snapshot_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    response = payload.get("response")
    documents = response.get("docs") if isinstance(response, dict) else None
    if not isinstance(documents, list):
        raise ValueError("Iscar snapshot lacks response.docs")
    if response.get("numFound") != EXPECTED_COUNT or len(documents) != EXPECTED_COUNT:
        raise ValueError(
            f"expected {EXPECTED_COUNT} Iscar family products; "
            f"numFound={response.get('numFound')!r}, docs={len(documents)}"
        )
    required = {
        "product_id_i", "sku", "ManufacturerNo_s", "ProductName_s",
        "FamilyName_s", "FamilyDesc_s", "APP1Name_s", "F_SIG_1_pf",
        "F_SIG_2_s", "F_SIG_4_pf", "F_SIG_7_pf", "F_SIG_9_pf",
        "F_SIG_12_s", "F_SIG_14_s", "F_SIG_15_s", "F_SIG_17_s",
        "F_SIG_19_ss", "F_SIG_38_s", "F_SIG_42_s",
    }
    normalized: list[dict[str, Any]] = []
    for index, raw_document in enumerate(documents):
        if not isinstance(raw_document, dict):
            raise ValueError(f"Iscar family document {index} is not an object")
        document = dict(raw_document)
        missing = sorted(required - set(document))
        if missing:
            raise ValueError(f"Iscar family document {index} lacks {missing}")
        if document["FamilyName_s"] != FAMILY_NAME:
            raise ValueError(f"out-of-family Iscar document: {document['ProductName_s']}")
        if document.get("BrandName_s") != "Iscar" or document.get("group_id_s") != "5502":
            raise ValueError(f"wrong brand/group for {document['ProductName_s']}")
        document[SNAPSHOT_INDEX_KEY] = index
        normalized.append(document)
    for field, label in (
        ("product_id_i", "webshop product IDs"),
        ("ManufacturerNo_s", "manufacturer numbers"),
        ("ProductName_s", "exact order codes"),
    ):
        if len({document[field] for document in normalized}) != EXPECTED_COUNT:
            raise ValueError(f"duplicate Iscar {label}")
    if SEED_PRODUCT_ID not in {document["product_id_i"] for document in normalized}:
        raise ValueError("user-supplied Iscar seed product is absent")
    return sorted(
        normalized,
        key=lambda item: (str(item["ManufacturerNo_s"]), int(item["product_id_i"])),
    )


def slug_id(product_name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", product_name.upper()).strip("-")


def manufacturer_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def existing_order_code(row: dict[str, Any]) -> str:
    specs = row.get("specs") if isinstance(row.get("specs"), dict) else {}
    return str(specs.get("manufacturer_order_code") or row.get("part_number") or "").strip()


def existing_material_number(row: dict[str, Any]) -> str:
    specs = row.get("specs") if isinstance(row.get("specs"), dict) else {}
    return str(specs.get("manufacturer_material_number") or "").strip()


def normalized_order_code(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def decimal_field(document: dict[str, Any], key: str) -> float:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{document.get('ProductName_s')}: {key} is not numeric")
    return float(value)


def inch_value(document: dict[str, Any], source_prefix: str) -> float:
    numeric = document.get(f"{source_prefix}_pf")
    if isinstance(numeric, (int, float)) and not isinstance(numeric, bool):
        return float(numeric)
    if document.get(f"{source_prefix}_s") == "0″":
        return 0.0
    raise ValueError(f"{document.get('ProductName_s')}: no numeric value for {source_prefix}")


def angle_field(document: dict[str, Any], key: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?) Degrees", str(document.get(key) or ""))
    if not match:
        raise ValueError(f"{document.get('ProductName_s')}: unsupported angle {key}")
    return float(match.group(1))


def product_url(document: dict[str, Any]) -> str:
    return f"https://webshop.iscarusa.com/catalogue/product/{int(document['product_id_i'])}"


def seed_row(document: dict[str, Any], tool_id: str) -> dict[str, Any]:
    corner_radius_in = inch_value(document, "F_SIG_2")
    product_name = str(document["ProductName_s"])
    description = str(document["FamilyDesc_s"])
    source_materials = [str(value).strip() for value in document["F_SIG_19_ss"]]
    unknown_materials = sorted(set(source_materials) - set(MATERIAL_GROUPS))
    if unknown_materials:
        raise ValueError(f"{product_name}: unknown work-material groups {unknown_materials}")
    specs = {
        "application": str(document["APP1Name_s"]),
        "body_material": str(document["F_SIG_42_s"]),
        "coating": str(document["F_SIG_14_s"]),
        "corner_radius_in": corner_radius_in,
        "corner_radius_mm": inches_to_mm(corner_radius_in),
        "cutting_depth_max_in": decimal_field(document, "F_SIG_4_pf"),
        "cutting_edge_material": str(document["F_SIG_17_s"]),
        "cutting_width_in": decimal_field(document, "F_SIG_1_pf"),
        "insert_length_in": decimal_field(document, "F_SIG_9_pf"),
        "insert_thickness_in": decimal_field(document, "F_SIG_7_pf"),
        "manufacturer_material_number": str(document["ManufacturerNo_s"]),
        "manufacturer_order_code": product_name,
        "product_family": str(document["FamilyName_s"]),
        "rake_angle_deg": angle_field(document, "F_SIG_12_s"),
        "webshop_item_number": str(document["sku"]),
        "webshop_product_id": int(document["product_id_i"]),
        "workpiece_material_groups": source_materials,
    }
    if document.get("F_SIG_5_s"):
        specs["clearance_angle_deg"] = angle_field(document, "F_SIG_5_s")
    return {
        "category": "Groove/Turn Indexable Inserts",
        "chipbreaker": None,
        "compatible_inserts": [],
        "compatible_machines": [],
        "component_type": "insert",
        "condition": None,
        "description": f"Iscar {product_name}. {description}",
        "geometry": description,
        "grade": str(document["F_SIG_15_s"]),
        "insert_seat": None,
        "iso_designation": None,
        "json_id": tool_id,
        "manufacturer": "Iscar",
        "mounts_to": None,
        "part_number": product_name,
        "price_range": None,
        "shape": None,
        "size": None,
        "sources": [product_url(document)],
        "specs": specs,
        "tags": [
            "Iscar", FAMILY_NAME, str(document["F_SIG_15_s"]), "back-turning",
            "groove-turn", "swiss-turning", "standalone_exact_product",
        ],
        "type": str(document["F_SIG_38_s"]),
    }


def canonical_import(
    documents: list[dict[str, Any]],
    tool_ids: dict[str, str],
    snapshot_path: Path,
) -> dict[str, Any]:
    snapshot_hash = sha256_file(snapshot_path)
    source_id = stable_id("source", IMPORT_ID, snapshot_hash)
    rows = []
    for document in documents:
        tool_id = tool_ids[str(document["ManufacturerNo_s"])]
        recommendations = []
        for label in document["F_SIG_19_ss"]:
            material_label = str(label).strip()
            iso_group = MATERIAL_GROUPS[material_label]
            recommendations.append(
                {
                    "id": stable_id(
                        "material-recommendation",
                        IMPORT_ID,
                        tool_id,
                        document["F_SIG_15_s"],
                        iso_group,
                        material_label,
                    ),
                    "grade_code": str(document["F_SIG_15_s"]),
                    "iso_group": iso_group,
                    "material_subgroup": material_label,
                    "suitability": "recommended",
                    "evidence_status": "manufacturer_claim",
                    "verification_status": "manufacturer_verified",
                    "source_id": source_id,
                    "source_ids": [source_id],
                    "source_page_ref": f"/response/docs/{document[SNAPSHOT_INDEX_KEY]}",
                    "source_table_ref": "F_SIG_19_ss",
                    "source_raw_text": compact_json(
                        {
                            "ProductName_s": document["ProductName_s"],
                            "F_SIG_15_s": document["F_SIG_15_s"],
                            "F_SIG_19_ss": document["F_SIG_19_ss"],
                        }
                    ),
                    "extraction_method": "manufacturer_page",
                    "notes": "Manufacturer applicability list; the source does not publish a preference ranking.",
                }
            )
        rows.append(
            {
                "tool_id": tool_id,
                "grade_code": str(document["F_SIG_15_s"]),
                "material_recommendations": recommendations,
                "cutting_profiles": [],
            }
        )
    return {
        "schema_version": 1,
        "import_id": IMPORT_ID,
        "title": "Iscar SCIR/L-22 exact family applicability",
        "generated_at": "2026-07-24",
        "manufacturer": "Iscar",
        "sources": [
            {
                "id": source_id,
                "manufacturer": "Iscar",
                "title": "Iscar SCIR/L-22-BR/BL/BRA/BLA exact family response",
                "source_type": "manufacturer_product_page",
                "url": "https://webshop.iscarusa.com/api/solr?q=%2A%3A%2A&fq%5B%5D=%7B%21term%20f%3DFamilyName_s%7DSCIR%2FL-22-BR%2FBL%2FBRA%2FBLA&fl=%2A&rows=500&sort=ManufacturerNo_s%20asc",
                "local_path": SNAPSHOT_REL,
                "content_sha256": snapshot_hash,
                "page_ref": "/response/docs/0 through /response/docs/15",
                "raw_reference": f"{SNAPSHOT_REL} | SHA-256 {snapshot_hash}",
                "document_edition": "Live Iscar USA family response retrieved 2026-07-24",
                "retrieved_at": "2026-07-24",
                "notes": "Exact 16-product manufacturer family response.",
            }
        ],
        "rows": rows,
    }


def generate(repo_root: Path, snapshot_path: Path) -> dict[str, Any]:
    documents = family_documents(snapshot_path)
    tools_path = repo_root / "toolbase/data/tools.jsonl"
    original_lines = tools_path.read_text(encoding="utf-8").splitlines()
    existing_rows = [json.loads(line) for line in original_lines if line.strip()]
    existing_ids = {str(row["json_id"]) for row in existing_rows}
    row_indexes = {id(row): index for index, row in enumerate(existing_rows)}
    existing_by_material: dict[str, dict[str, Any]] = {}
    existing_by_order: dict[str, dict[str, Any]] = {}
    existing_by_normalized_order: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        if manufacturer_key(row.get("manufacturer")) != manufacturer_key("Iscar"):
            continue
        material_number = existing_material_number(row)
        order_code = existing_order_code(row)
        if material_number:
            if material_number in existing_by_material:
                raise ValueError(f"duplicate existing Iscar material number {material_number}")
            existing_by_material[material_number] = row
        if order_code:
            if order_code in existing_by_order:
                raise ValueError(f"duplicate existing Iscar order code {order_code}")
            existing_by_order[order_code] = row
            normalized = normalized_order_code(order_code)
            if normalized in existing_by_normalized_order:
                raise ValueError(f"normalized existing Iscar order-code collision {order_code}")
            existing_by_normalized_order[normalized] = row

    output_lines = list(original_lines)
    new_rows: list[dict[str, Any]] = []
    tool_ids: dict[str, str] = {}
    updated_rows = 0
    for document in documents:
        material_number = str(document["ManufacturerNo_s"])
        order_code = str(document["ProductName_s"])
        material_match = existing_by_material.get(material_number)
        order_match = existing_by_order.get(order_code)
        normalized_match = existing_by_normalized_order.get(normalized_order_code(order_code))
        if normalized_match is not None and normalized_match is not order_match:
            raise ValueError(f"normalized order-code collision for {order_code}")
        if material_match is not None and existing_order_code(material_match) != order_code:
            raise ValueError(f"material-number conflict for {material_number}")
        if order_match is not None:
            known_material = existing_material_number(order_match)
            if known_material and known_material != material_number:
                raise ValueError(f"material-number conflict for {order_code}")
        if material_match is not None and order_match is not None and material_match is not order_match:
            raise ValueError(f"identity maps to multiple Iscar tools: {order_code}")
        existing = material_match or order_match
        if existing is not None:
            tool_id = str(existing["json_id"])
            tool_ids[material_number] = tool_id
            output_lines[row_indexes[id(existing)]] = compact_json(seed_row(document, tool_id))
            updated_rows += 1
            continue
        tool_id = slug_id(order_code)
        if tool_id in existing_ids:
            tool_id = f"{tool_id}-{material_number}"
        if tool_id in existing_ids:
            raise ValueError(f"unable to create unique tool ID for {order_code}")
        existing_ids.add(tool_id)
        tool_ids[material_number] = tool_id
        new_rows.append(seed_row(document, tool_id))

    if new_rows:
        iscar_indexes = [
            index for index, row in enumerate(existing_rows)
            if manufacturer_key(row.get("manufacturer")) == manufacturer_key("Iscar")
        ]
        insertion_index = (iscar_indexes[-1] + 1) if iscar_indexes else len(output_lines)
        output_lines[insertion_index:insertion_index] = [compact_json(row) for row in new_rows]
    tools_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8", newline="\n")

    manifest_path = repo_root / "toolbase/data/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("counts", {})["tools"] = len(existing_rows) + len(new_rows)
    manifest.pop("tool_count", None)
    manifest.pop("tools_sha256", None)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    import_payload = canonical_import(documents, tool_ids, snapshot_path)
    import_path = repo_root / IMPORT_REL
    write_json(import_path, import_payload)
    return {
        "family_products": len(documents),
        "new_seed_rows_added": len(new_rows),
        "seed_rows_updated": updated_rows,
        "material_recommendations": sum(
            len(row["material_recommendations"]) for row in import_payload["rows"]
        ),
        "canonical_import": str(import_path),
        "snapshot_sha256": sha256_file(snapshot_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--snapshot", type=Path)
    arguments = parser.parse_args()
    repo_root = arguments.repo_root.resolve()
    snapshot = arguments.snapshot or repo_root / SNAPSHOT_REL
    print(json.dumps(generate(repo_root, snapshot.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
