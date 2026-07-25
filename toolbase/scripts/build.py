#!/usr/bin/env python3
"""Build the canonical v3 database and its dependency-free web projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from review_batch import compile_packet, validate_ledger, validate_proposal


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema.sql"
NORMALIZATION_PATH = ROOT / "config" / "normalization.json"
VALID_COMPONENT_TYPES = {
    "machine",
    "station",
    "shank",
    "module",
    "holder",
    "insert",
    "adapter",
    "spare",
}
MANUFACTURER_DOMAINS = {
    "iscar.com",
    "kennametal.com",
    "mmc-carbide.com",
    "mitsubishicarbide.com",
    "horn-group.com",
    "hornusa.com",
    "phorn.de",
    "sandvik.com",
    "sandvik.coromant.com",
    "starmicronics.com",
    "tungaloy.com",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return records


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return clean or stable_id("manufacturer", value)


def normalize_part_number(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def legacy_grade_codes(value: object) -> list[str]:
    raw = clean_text(value)
    if not raw or "see catalog" in raw.casefold():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def public_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def clean_optional(value: object, empty_markers: set[str]) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    if not clean or clean.casefold() in empty_markers:
        return None
    return clean


def source_type_for(reference: str) -> str:
    lower = reference.casefold()
    if re.match(r"^https?://", reference, re.IGNORECASE):
        hostname = (urlparse(reference).hostname or "").casefold()
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in MANUFACTURER_DOMAINS):
            return "manufacturer_product_page"
        return "secondary_web"
    if "shop" in lower:
        return "shop_note"
    if "manual" in lower or "machine documentation" in lower:
        return "machine_manual"
    if ".pdf" in lower or "catalog" in lower or "katalog" in lower:
        return "manufacturer_catalog"
    if re.search(r"\.(?:json|csv|txt|xlsx?)\b", lower):
        return "local_file"
    if reference:
        return "legacy_reference"
    return "unknown"


def parse_legacy_source(reference: object, manufacturer_id: str | None) -> dict[str, Any]:
    raw = str(reference or "").strip()
    source_type = source_type_for(raw)
    is_url = bool(re.match(r"^https?://", raw, re.IGNORECASE))
    file_match = re.search(r"([^/\\]+?\.pdf)\b", raw, re.IGNORECASE)
    page_match = re.search(
        r"\b(?:catalog\s+page|page|p\.)\s*\d+(?:\s*[-–]\s*\d+)?\b",
        raw,
        re.IGNORECASE,
    )
    return {
        "id": stable_id("source", raw),
        "source_type": source_type,
        "title": raw or "Unknown legacy source",
        "url": raw if is_url else None,
        "local_path": file_match.group(1).strip() if file_match else None,
        "page_ref": page_match.group(0).strip() if page_match else None,
        "manufacturer_id": manufacturer_id,
        "raw_reference": raw,
        "notes": None,
    }


def parse_claim_source(claim: dict[str, Any], manufacturer_id: str | None) -> dict[str, Any]:
    url = clean_text(claim.get("source_url"))
    local_path = clean_text(claim.get("source_file_name"))
    title = clean_text(claim.get("source_title")) or url or local_path or "Catalog claim source"
    page_ref = (
        clean_text(claim.get("source_catalog_page_ref"))
        or clean_text(claim.get("structured_source_page_ref"))
        or clean_text(claim.get("source_page_ref"))
    )
    raw = url or " | ".join(part for part in (local_path, page_ref, title) if part)
    source_type = clean_text(claim.get("source_type")) or source_type_for(raw)
    if source_type not in {
        "manufacturer_product_page",
        "manufacturer_catalog",
        "machine_manual",
        "shop_note",
        "secondary_web",
        "local_file",
        "legacy_reference",
        "unknown",
    }:
        source_type = source_type_for(raw)
    return {
        "id": stable_id("source", claim.get("source_key") or raw),
        "source_type": source_type,
        "title": title,
        "url": url,
        "local_path": local_path,
        "page_ref": page_ref,
        "manufacturer_id": manufacturer_id,
        "raw_reference": raw,
        "notes": clean_text(claim.get("source_notes")),
    }


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def evidence_for_sources(sources: list[dict[str, Any]]) -> str:
    types = {source["source_type"] for source in sources}
    if "manufacturer_product_page" in types:
        return "manufacturer_source"
    if "manufacturer_catalog" in types or "machine_manual" in types:
        return "catalog_source"
    if types:
        return "legacy_source"
    return "unverified"


def lifecycle_for(condition: object) -> str:
    value = str(condition or "").casefold()
    if "discontinued" in value or "no longer available" in value:
        return "discontinued"
    if "obsolete" in value:
        return "obsolete"
    if "active" in value or "new" in value:
        return "active"
    return "unknown"


def normalized_fact_key(original_key: str, aliases: dict[str, str]) -> str:
    if original_key in aliases:
        return aliases[original_key]
    clean = re.sub(r"[^a-z0-9]+", "_", original_key.casefold()).strip("_")
    return clean or "unnamed_fact"


def fact_value(value: Any, key: str) -> tuple[str | None, float | None, int | None, str | None, str | None]:
    unit = None
    if key.endswith("_mm"):
        unit = "mm"
    elif key.endswith("_deg"):
        unit = "deg"
    elif key.endswith("_nm"):
        unit = "N·m"

    if isinstance(value, bool):
        return None, None, int(value), None, unit
    if isinstance(value, (int, float)):
        return None, float(value), None, None, unit
    if isinstance(value, (dict, list)):
        return None, None, None, json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), unit
    if value is None:
        return None, None, None, None, unit

    text = str(value).strip()
    if not text:
        return None, None, None, None, unit
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None, float(text), None, None, unit
    return text, None, None, None, unit


def insert_source(connection: sqlite3.Connection, source: dict[str, Any]) -> None:
    payload = {
        "content_sha256": None,
        "document_edition": None,
        "retrieved_at": None,
        **source,
    }
    connection.execute(
        """
        INSERT INTO sources
          (id, source_type, title, url, local_path, page_ref, manufacturer_id,
           raw_reference, content_sha256, document_edition, retrieved_at, notes)
        VALUES
          (:id, :source_type, :title, :url, :local_path, :page_ref, :manufacturer_id,
           :raw_reference, :content_sha256, :document_edition, :retrieved_at, :notes)
        ON CONFLICT(id) DO UPDATE SET
          title=CASE WHEN excluded.content_sha256 IS NOT NULL THEN excluded.title ELSE sources.title END,
          url=coalesce(excluded.url, sources.url),
          local_path=coalesce(excluded.local_path, sources.local_path),
          page_ref=coalesce(excluded.page_ref, sources.page_ref),
          content_sha256=coalesce(excluded.content_sha256, sources.content_sha256),
          document_edition=coalesce(excluded.document_edition, sources.document_edition),
          retrieved_at=coalesce(excluded.retrieved_at, sources.retrieved_at),
          notes=coalesce(excluded.notes, sources.notes)
        """,
        payload,
    )


def insert_legacy_grade_options(
    connection: sqlite3.Connection,
    tool_id: str,
    manufacturer_id: str,
    raw_grade: object,
    source_records: list[dict[str, Any]],
) -> None:
    codes = legacy_grade_codes(raw_grade)
    source = source_records[0] if len(source_records) == 1 else None
    verification = "source_located" if source_records else "legacy"
    for code in codes:
        normalized = normalize_part_number(code)
        if not normalized:
            continue
        grade_id = stable_id("grade", manufacturer_id, normalized)
        connection.execute(
            """
            INSERT OR IGNORE INTO grades (
              id, manufacturer_id, code, normalized_code, evidence_status,
              verification_status, source_id, source_page_ref
            ) VALUES (?, ?, ?, ?, 'imported', ?, ?, ?)
            """,
            (
                grade_id,
                manufacturer_id,
                code,
                normalized,
                verification,
                source["id"] if source else None,
                source.get("page_ref") if source else None,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO tool_grade_options (
              id, tool_id, grade_id, option_kind, availability_status, is_primary,
              verification_status, source_id, source_page_ref, extraction_method
            ) VALUES (?, ?, ?, 'legacy_claim', 'unknown', ?, ?, ?, ?, 'legacy_import')
            """,
            (
                stable_id("tool-grade", tool_id, grade_id, "legacy_claim"),
                tool_id,
                grade_id,
                int(len(codes) == 1),
                verification,
                source["id"] if source else None,
                source.get("page_ref") if source else None,
            ),
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source_documents(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "source_documents.json"
    if not path.is_file():
        return []
    payload = load_json(path)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("documents"), list):
        raise ValueError(f"{path}: unsupported source-document manifest")
    return payload["documents"]


def create_review_validation_database(data_dir: Path, database_path: Path) -> None:
    """Create the minimal seed view required by review_batch proposal validation."""
    config = load_json(NORMALIZATION_PATH)
    manufacturer_aliases = config["manufacturer_aliases"]
    tools = load_jsonl(data_dir / "tools.jsonl")
    manufacturers = sorted(
        {
            manufacturer_aliases.get(raw, raw)
            for record in tools
            for raw in [clean_text(record.get("manufacturer")) or "Unknown"]
        },
        key=str.casefold,
    )
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE manufacturers (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
            CREATE TABLE tools (
              id TEXT PRIMARY KEY,
              manufacturer_id TEXT NOT NULL,
              component_type TEXT NOT NULL
            );
            """
        )
        manufacturer_ids = {name: stable_id("review-manufacturer", name) for name in manufacturers}
        connection.executemany(
            "INSERT INTO manufacturers (id, name) VALUES (?, ?)",
            ((manufacturer_ids[name], name) for name in manufacturers),
        )
        connection.executemany(
            "INSERT INTO tools (id, manufacturer_id, component_type) VALUES (?, ?, ?)",
            (
                (
                    str(record["json_id"]).strip(),
                    manufacturer_ids[
                        manufacturer_aliases.get(
                            clean_text(record.get("manufacturer")) or "Unknown",
                            clean_text(record.get("manufacturer")) or "Unknown",
                        )
                    ],
                    str(record.get("component_type") or "").strip().casefold(),
                )
                for record in tools
            ),
        )
        connection.commit()
    finally:
        connection.close()


def load_reviewed_imports(data_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    import_dir = data_dir / "reviewed_imports"
    if not import_dir.is_dir():
        return []
    packets: list[tuple[Path, dict[str, Any]]] = []
    with tempfile.TemporaryDirectory(prefix="toolbase-review-validation-") as temp:
        validation_database = Path(temp) / "seed.sqlite"
        canonical_packet_path = Path(temp) / "canonical.json"
        for path in sorted(import_dir.glob("*.json"), key=lambda item: item.name.casefold()):
            packet = load_json(path)
            packet_version = packet.get("schema_version")
            if packet_version not in {1, 2}:
                raise ValueError(f"{path}: unsupported reviewed-import schema")
            expected_rows = len(packet.get("rows") or []) + len(packet.get("quarantined_rows") or [])
            if packet.get("row_count") != expected_rows:
                raise ValueError(f"{path}: reviewed row count does not match")
            proposal_path = (ROOT.parent / str(packet.get("proposal_path") or "")).resolve()
            ledger_path = (ROOT.parent / str(packet.get("review_ledger_path") or "")).resolve()
            for label, checked_path, expected_hash in (
                ("proposal", proposal_path, packet.get("proposal_sha256")),
                ("review ledger", ledger_path, packet.get("review_ledger_sha256")),
            ):
                if not checked_path.is_file():
                    raise ValueError(f"{path}: {label} file is missing: {checked_path}")
                if file_sha256(checked_path) != expected_hash:
                    raise ValueError(f"{path}: {label} hash no longer matches")
            ledger = load_json(ledger_path)
            if ledger.get("proposal_id") != packet.get("proposal_id"):
                raise ValueError(f"{path}: ledger proposal id does not match")
            if ledger.get("import_allowed") is not True or ledger.get("status") != "complete":
                raise ValueError(f"{path}: review ledger does not authorize import")
            allowed_decisions = (
                {"approved", "approved_with_corrections"}
                if packet_version == 1
                else {"approved", "approved_with_corrections", "rejected", "quarantined"}
            )
            if any(item.get("decision") not in allowed_decisions for item in ledger.get("decisions") or []):
                raise ValueError(f"{path}: review ledger contains an incomplete decision")
            if packet_version == 2:
                if not validation_database.exists():
                    create_review_validation_database(data_dir, validation_database)
                proposal, semantic_errors = validate_proposal(proposal_path, validation_database)
                validated_ledger, ledger_errors = validate_ledger(
                    proposal_path, proposal, ledger_path
                )
                semantic_errors.extend(ledger_errors)
                if semantic_errors:
                    raise ValueError(
                        f"{path}: proposal or review ledger is invalid: "
                        + "; ".join(semantic_errors)
                    )
                compile_packet(
                    proposal_path,
                    proposal,
                    ledger_path,
                    validated_ledger,
                    canonical_packet_path,
                )
                if packet != load_json(canonical_packet_path):
                    raise ValueError(
                        f"{path}: reviewed import does not match canonical proposal and ledger compilation"
                    )
            packets.append((path, packet))
    return packets


def load_manufacturer_imports(data_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    import_dir = data_dir / "manufacturer_imports"
    if not import_dir.is_dir():
        return []
    imports: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(import_dir.glob("*.json"), key=lambda item: item.name.casefold()):
        payload = load_json(path)
        if payload.get("schema_version") != 1:
            raise ValueError(f"{path}: unsupported manufacturer-import schema")
        if not clean_text(payload.get("import_id")) or not clean_text(payload.get("manufacturer")):
            raise ValueError(f"{path}: import_id and manufacturer are required")
        sources = payload.get("sources")
        rows = payload.get("rows")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{path}: sources must be a nonempty list")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{path}: rows must be a nonempty list")
        source_ids: set[str] = set()
        for source in sources:
            source_id = clean_text(source.get("id"))
            if not source_id or source_id in source_ids:
                raise ValueError(f"{path}: source IDs must be unique and nonblank")
            source_ids.add(source_id)
            local_path = ROOT.parent / str(source.get("local_path") or "")
            if not local_path.is_file():
                raise ValueError(f"{path}: source is missing: {local_path}")
            if source.get("content_sha256") != file_sha256(local_path):
                raise ValueError(f"{path}: source hash does not match: {local_path}")
        tool_ids = [clean_text(row.get("tool_id")) for row in rows]
        if any(not tool_id for tool_id in tool_ids) or len(set(tool_ids)) != len(tool_ids):
            raise ValueError(f"{path}: tool IDs must be unique and nonblank")
        imports.append((path, payload))
    return imports


def apply_reviewed_import(
    connection: sqlite3.Connection,
    packet_path: Path,
    packet: dict[str, Any],
    manufacturer_ids: dict[str, str],
) -> None:
    for source_record in packet["sources"]:
        source = dict(source_record)
        manufacturer = source.pop("manufacturer", None)
        source["manufacturer_id"] = manufacturer_ids.get(manufacturer) if manufacturer else None
        source["retrieved_at"] = source.get("retrieved_at") or packet["reviewed_at"]
        if source["id"] == packet["catalog_source_id"]:
            source["content_sha256"] = packet["catalog_sha256"]
            source["document_edition"] = source.get("document_edition") or "2024 copyright edition"
        insert_source(connection, source)

    batch_id = packet["import_id"]
    connection.execute(
        """
        INSERT INTO review_batches (
          id, proposal_id, proposal_path, proposal_sha256,
          review_ledger_path, review_ledger_sha256, catalog_sha256,
          reviewed_at, source_id, row_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            packet["proposal_id"],
            packet["proposal_path"],
            packet["proposal_sha256"],
            packet["review_ledger_path"],
            packet["review_ledger_sha256"],
            packet["catalog_sha256"],
            packet["reviewed_at"],
            packet["catalog_source_id"],
            packet["row_count"],
        ),
    )
    review_sources = packet.get("review_sources") or [
        {
            "source_id": packet["catalog_source_id"],
            "evidence_role": "primary_catalog",
            "content_sha256": packet["catalog_sha256"],
            "document_edition": next(
                (
                    source.get("document_edition")
                    for source in packet["sources"]
                    if source["id"] == packet["catalog_source_id"]
                ),
                "2024 copyright edition",
            ),
            "page_ref": next(
                (
                    source.get("page_ref")
                    for source in packet["sources"]
                    if source["id"] == packet["catalog_source_id"]
                ),
                None,
            ),
        }
    ]
    for review_source in review_sources:
        connection.execute(
            """
            INSERT INTO review_batch_sources (
              review_batch_id, source_id, evidence_role, content_sha256,
              document_edition, page_ref
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                review_source["source_id"],
                review_source["evidence_role"],
                review_source.get("content_sha256"),
                review_source.get("document_edition"),
                review_source.get("page_ref"),
            ),
        )

    for row in packet["rows"]:
        tool_id = row["tool_id"]
        primary_profile = (row.get("cutting_profiles") or [{}])[0]
        row_reviewer = row.get("reviewer") or primary_profile.get("reviewer")
        row_reviewed_at = (
            row.get("reviewed_at") or primary_profile.get("reviewed_at") or packet["reviewed_at"]
        )
        tool_row = connection.execute(
            "SELECT manufacturer_id, part_number FROM tools WHERE id=?", (tool_id,)
        ).fetchone()
        if tool_row is None:
            raise ValueError(f"{packet_path}: reviewed tool is missing: {tool_id}")
        tool_manufacturer_id, tool_part_number = tool_row
        updates = row["tool_updates"]
        connection.execute(
            """
            UPDATE tools
            SET description=coalesce(?, description), geometry=?, lifecycle_status=?,
                evidence_status=?,
                grade=CASE WHEN ? THEN ? ELSE grade END,
                chipbreaker=CASE WHEN ? THEN ? ELSE chipbreaker END,
                review_status='verified', quarantine_reason=NULL
            WHERE id=?
            """,
            (
                clean_text(updates.get("description")),
                updates["geometry"],
                updates["lifecycle_status"],
                updates["evidence_status"],
                int(bool(updates.get("grade_reviewed"))),
                clean_text(updates.get("grade")),
                int(bool(updates.get("chipbreaker_reviewed"))),
                clean_text(updates.get("chipbreaker")),
                tool_id,
            ),
        )

        standalone_exact_product = "standalone_exact_product" in set(row.get("tags") or [])
        if standalone_exact_product:
            manufacturer_part_number = next(
                (
                    alias.get("alias")
                    for alias in row.get("aliases") or []
                    if alias.get("alias_type") == "manufacturer_part_number"
                ),
                None,
            )
            if manufacturer_part_number:
                connection.execute(
                    """
                    UPDATE tools
                    SET part_number=?, normalized_part_number=?
                    WHERE id=?
                    """,
                    (
                        manufacturer_part_number,
                        normalize_part_number(manufacturer_part_number),
                        tool_id,
                    ),
                )
                tool_part_number = manufacturer_part_number
            connection.execute(
                """
                UPDATE tool_grade_options
                SET verification_status='rejected',
                    full_order_number=coalesce(?, full_order_number),
                    review_batch_id=?, reviewer=?, reviewed_at=?
                WHERE tool_id=?
                """,
                (
                    manufacturer_part_number,
                    batch_id,
                    row_reviewer,
                    row_reviewed_at,
                    tool_id,
                ),
            )

        for rejected_grade_code in row.get("reject_grade_codes") or []:
            connection.execute(
                """
                UPDATE tool_grade_options
                SET verification_status='rejected', review_batch_id=?, reviewer=?, reviewed_at=?
                WHERE tool_id=? AND grade_id IN (
                  SELECT id FROM grades
                  WHERE manufacturer_id=? AND normalized_code=?
                )
                """,
                (
                    batch_id,
                    row_reviewer,
                    row_reviewed_at,
                    tool_id,
                    tool_manufacturer_id,
                    normalize_part_number(rejected_grade_code),
                ),
            )

        fact_values = {item["fact_key"]: item for item in row.get("facts") or []}
        grade_ids: dict[str, str] = {}
        if standalone_exact_product:
            for existing_grade_id, existing_code, existing_normalized_code in connection.execute(
                """
                SELECT g.id, g.code, g.normalized_code
                FROM tool_grade_options o JOIN grades g ON g.id=o.grade_id
                WHERE o.tool_id=?
                """,
                (tool_id,),
            ):
                grade_ids[existing_code] = existing_grade_id
                grade_ids[existing_normalized_code] = existing_grade_id
        grade_inputs = [] if standalone_exact_product else list(row.get("grade_options") or [])
        existing_grade_codes = {
            normalize_part_number(option.get("code")) for option in grade_inputs
        }
        if not standalone_exact_product:
            for profile in row.get("cutting_profiles") or []:
                if normalize_part_number(profile.get("source_grade")) in existing_grade_codes:
                    continue
                grade_inputs.append(
                    {
                        "code": profile.get("source_grade"),
                        "option_kind": "exact_order_grade",
                        "full_order_number": tool_part_number,
                        "availability_status": "listed",
                        "is_primary": True,
                        "verification_status": profile.get("verification_status"),
                        "source_id": profile.get("source_id"),
                        "source_page_ref": profile.get("source_page_ref"),
                        "source_table_ref": profile.get("source_table_ref"),
                        "source_raw_text": profile.get("source_raw_text"),
                        "extraction_method": profile.get("extraction_method"),
                        "reviewer": profile.get("reviewer"),
                        "reviewed_at": profile.get("reviewed_at"),
                    }
                )
        for option in grade_inputs:
            grade_code = clean_text(option.get("code"))
            if not grade_code:
                continue
            normalized_grade = normalize_part_number(grade_code)
            grade_id = stable_id("grade", tool_manufacturer_id, normalized_grade)
            grade_ids[grade_code] = grade_id
            grade_ids[normalized_grade] = grade_id
            verified_status = option.get("verification_status") or "catalog_verified"
            evidence_status = (
                "manufacturer_claim"
                if verified_status == "manufacturer_verified"
                else "catalog_claim"
            )
            grade_material = fact_values.get("grade_material") or {}
            grade_coating = fact_values.get("grade_coating") or {}
            connection.execute(
                """
                INSERT INTO grades (
                  id, manufacturer_id, code, normalized_code, material_class, coating,
                  evidence_status, verification_status, source_id, source_page_ref,
                  source_table_ref, review_batch_id, reviewer, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(manufacturer_id, normalized_code) DO UPDATE SET
                  material_class=coalesce(excluded.material_class, grades.material_class),
                  coating=coalesce(excluded.coating, grades.coating),
                  evidence_status=excluded.evidence_status,
                  verification_status=excluded.verification_status,
                  source_id=excluded.source_id,
                  source_page_ref=excluded.source_page_ref,
                  source_table_ref=excluded.source_table_ref,
                  review_batch_id=excluded.review_batch_id,
                  reviewer=excluded.reviewer,
                  reviewed_at=excluded.reviewed_at
                """,
                (
                    grade_id,
                    tool_manufacturer_id,
                    grade_code,
                    normalized_grade,
                    option.get("material_class") or grade_material.get("value_text"),
                    option.get("coating") or grade_coating.get("value_text"),
                    evidence_status,
                    verified_status,
                    option.get("source_id"),
                    option.get("source_page_ref"),
                    option.get("source_table_ref"),
                    batch_id,
                    option.get("reviewer") or row_reviewer,
                    option.get("reviewed_at") or row_reviewed_at,
                ),
            )
            option_kind = option.get("option_kind") or "exact_order_grade"
            connection.execute(
                f"""
                INSERT INTO tool_grade_options (
                  id, tool_id, grade_id, option_kind, full_order_number,
                  availability_status, is_primary, verification_status, source_id,
                  source_page_ref, source_table_ref, source_raw_text,
                  extraction_method, review_batch_id, reviewer, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_id, grade_id, option_kind) DO UPDATE SET
                  full_order_number=excluded.full_order_number,
                  availability_status=excluded.availability_status,
                  is_primary=excluded.is_primary,
                  verification_status=excluded.verification_status,
                  source_id=excluded.source_id,
                  source_page_ref=excluded.source_page_ref,
                  source_table_ref=excluded.source_table_ref,
                  source_raw_text=excluded.source_raw_text,
                  extraction_method=excluded.extraction_method,
                  review_batch_id=excluded.review_batch_id,
                  reviewer=excluded.reviewer,
                  reviewed_at=excluded.reviewed_at
                """,
                (
                    stable_id("tool-grade", tool_id, grade_id, option_kind),
                    tool_id,
                    grade_id,
                    option_kind,
                    option.get("full_order_number") or tool_part_number,
                    option.get("availability_status") or "listed",
                    int(bool(option.get("is_primary", True))),
                    verified_status,
                    option.get("source_id"),
                    option.get("source_page_ref"),
                    option.get("source_table_ref"),
                    option.get("source_raw_text"),
                    option.get("extraction_method") or "manual",
                    batch_id,
                    option.get("reviewer") or row_reviewer,
                    option.get("reviewed_at") or row_reviewed_at,
                ),
            )
        for alias in row["aliases"]:
            connection.execute(
                "INSERT OR IGNORE INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, ?)",
                (tool_id, alias["alias"], alias["alias_type"]),
            )
        for source_id in row["source_ids"]:
            connection.execute(
                "INSERT OR IGNORE INTO tool_sources (tool_id, source_id, evidence_role) VALUES (?, ?, 'verification')",
                (tool_id, source_id),
            )
        for tag in row["tags"]:
            connection.execute(
                """
                INSERT INTO reviewed_tool_tags (tool_id, tag, source_id, review_batch_id)
                VALUES (?, ?, ?, ?)
                """,
                (tool_id, tag, packet["catalog_source_id"], batch_id),
            )

        superseded_facts: dict[str, str] = {}
        for fact_key in row["replace_fact_keys"]:
            existing = connection.execute(
                """
                SELECT id FROM facts
                WHERE tool_id=? AND fact_key=? AND is_current=1
                ORDER BY verification_status DESC, id LIMIT 1
                """,
                (tool_id, fact_key),
            ).fetchone()
            if existing:
                superseded_facts[fact_key] = existing[0]
                connection.execute(
                    "UPDATE facts SET is_current=0 WHERE tool_id=? AND fact_key=? AND is_current=1",
                    (tool_id, fact_key),
                )
        for item in row["facts"]:
            value_json = item.get("value_json")
            if value_json is not None:
                value_json = json.dumps(
                    value_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            connection.execute(
                """
                INSERT INTO facts (
                  id, tool_id, fact_key, original_key, value_text, value_number,
                  value_boolean, value_json, unit, evidence_status, verification_status,
                  source_id, source_page_ref, source_table_ref, source_raw_text,
                  extraction_method, review_batch_id, reviewer, reviewed_at,
                  supersedes_fact_id, is_current
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    item["id"],
                    tool_id,
                    item["fact_key"],
                    item["original_key"],
                    item.get("value_text"),
                    item.get("value_number"),
                    int(item["value_boolean"]) if "value_boolean" in item else None,
                    value_json,
                    item.get("unit"),
                    item["evidence_status"],
                    item.get("verification_status") or (
                        "manufacturer_verified"
                        if item["evidence_status"] == "manufacturer_claim"
                        else "catalog_verified"
                    ),
                    item.get("source_id"),
                    item.get("source_page_ref") or primary_profile.get("source_page_ref"),
                    item.get("source_table_ref") or primary_profile.get("source_table_ref"),
                    item.get("source_raw_text"),
                    item.get("extraction_method") or (
                        "manual"
                        if item.get("source_id") == packet["catalog_source_id"]
                        else "manufacturer_page"
                    ),
                    batch_id,
                    row_reviewer,
                    row_reviewed_at,
                    superseded_facts.get(item["fact_key"]),
                ),
            )
            for source_id in item["source_ids"]:
                connection.execute(
                    """
                    INSERT INTO fact_sources (
                      fact_id, source_id, evidence_role, source_page_ref,
                      source_table_ref, extraction_method
                    ) VALUES (?, ?, 'direct_source', ?, ?, ?)
                    """,
                    (
                        item["id"],
                        source_id,
                        item.get("source_page_ref") or primary_profile.get("source_page_ref"),
                        item.get("source_table_ref") or primary_profile.get("source_table_ref"),
                        item.get("extraction_method") or primary_profile.get("extraction_method") or "manual",
                    ),
                )

        if row.get("replace_material_recommendations"):
            connection.execute(
                "UPDATE tool_material_recommendations SET is_current=0 WHERE tool_id=? AND is_current=1",
                (tool_id,),
            )
        for item in row["material_recommendations"]:
            recommendation_grade_id = item.get("grade_id") or grade_ids.get(
                normalize_part_number(item.get("grade_code"))
            ) or grade_ids.get(primary_profile.get("source_grade"))
            connection.execute(
                """
                INSERT INTO tool_material_recommendations (
                  id, tool_id, grade_id, iso_group, material_subgroup, suitability,
                  evidence_status, verification_status, source_id, source_page_ref,
                  source_table_ref, source_raw_text, extraction_method,
                  review_batch_id, reviewer, reviewed_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    tool_id,
                    recommendation_grade_id,
                    item["iso_group"],
                    item.get("material_subgroup"),
                    item["suitability"],
                    item["evidence_status"],
                    (
                        item.get("verification_status") or (
                            "manufacturer_verified"
                            if item["evidence_status"] == "manufacturer_claim"
                            else "catalog_verified"
                        )
                    ),
                    item.get("source_id"),
                    (
                        item.get("source_page_ref") or primary_profile.get("source_page_ref")
                    ),
                    (
                        item.get("source_table_ref") or primary_profile.get("source_table_ref")
                    ),
                    (
                        item.get("source_raw_text") or primary_profile.get("source_raw_text")
                    ),
                    (
                        item.get("extraction_method") or primary_profile.get("extraction_method") or "manual"
                    ),
                    batch_id,
                    row_reviewer,
                    row_reviewed_at,
                    item.get("notes"),
                ),
            )
            for source_id in item["source_ids"]:
                connection.execute(
                    """
                    INSERT INTO tool_material_recommendation_sources
                      (recommendation_id, source_id, evidence_role)
                    VALUES (?, ?, 'direct_source')
                    """,
                    (item["id"], source_id),
                )

        for profile in row["cutting_profiles"]:
            profile_grade_id = grade_ids.get(normalize_part_number(profile.get("source_grade")))
            connection.execute(
                """
                INSERT INTO cutting_data_profiles (
                  id, tool_id, grade_id, source_id, source_part_number, source_grade,
                  source_geometry, source_chipbreaker, source_material_label,
                  iso_material_group, material_subgroup, operation_type,
                  cut_condition, coolant_condition, surface_speed_min,
                  surface_speed_start, surface_speed_max, surface_speed_unit,
                  feed_min, feed_max, feed_unit, depth_of_cut_min,
                  depth_of_cut_max, depth_of_cut_unit, source_page_ref,
                  source_table_ref, source_raw_text, extraction_method,
                  verification_status, reviewer, reviewed_at, notes
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    profile["id"],
                    tool_id,
                    profile_grade_id,
                    profile["source_id"],
                    profile["source_part_number"],
                    profile.get("source_grade"),
                    profile.get("source_geometry"),
                    profile.get("source_chipbreaker"),
                    profile.get("source_material_label"),
                    profile["iso_material_group"],
                    profile.get("material_subgroup"),
                    profile["operation_type"],
                    profile["cut_condition"],
                    profile["coolant_condition"],
                    profile.get("surface_speed_min"),
                    profile.get("surface_speed_start"),
                    profile.get("surface_speed_max"),
                    profile.get("surface_speed_unit"),
                    profile.get("feed_min"),
                    profile.get("feed_max"),
                    profile.get("feed_unit"),
                    profile.get("depth_of_cut_min"),
                    profile.get("depth_of_cut_max"),
                    profile.get("depth_of_cut_unit"),
                    profile.get("source_page_ref"),
                    profile.get("source_table_ref"),
                    profile.get("source_raw_text"),
                    profile["extraction_method"],
                    profile["verification_status"],
                    profile.get("reviewer"),
                    profile.get("reviewed_at"),
                    profile.get("notes"),
                ),
            )
            evidence_sources = profile.get("evidence_sources") or [
                {
                    "source_id": profile["source_id"],
                    "evidence_role": role,
                    "source_page_ref": profile.get("source_page_ref"),
                    "source_table_ref": profile.get("source_table_ref"),
                    "source_raw_text": profile.get("source_raw_text"),
                    "extraction_method": profile.get("extraction_method"),
                }
                for role in ("identity", "geometry_parameters", "cutting_speed")
            ]
            for evidence in evidence_sources:
                connection.execute(
                    """
                    INSERT INTO cutting_data_profile_sources (
                      profile_id, source_id, evidence_role, source_page_ref,
                      source_printed_page_ref, source_table_ref, source_raw_text,
                      extraction_method
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile["id"],
                        evidence["source_id"],
                        evidence["evidence_role"],
                        evidence.get("source_page_ref"),
                        evidence.get("source_printed_page_ref"),
                        evidence.get("source_table_ref"),
                        evidence.get("source_raw_text"),
                        evidence.get("extraction_method"),
                    ),
                )

    for quarantined in packet.get("quarantined_rows") or []:
        connection.execute(
            """
            UPDATE tools SET review_status='quarantined', quarantine_reason=?
            WHERE id=?
            """,
            (quarantined["reason"], quarantined["tool_id"]),
        )


def apply_manufacturer_import(
    connection: sqlite3.Connection,
    import_path: Path,
    payload: dict[str, Any],
    manufacturer_ids: dict[str, str],
) -> None:
    manufacturer = payload["manufacturer"]
    manufacturer_id = manufacturer_ids.get(manufacturer)
    if not manufacturer_id:
        raise ValueError(f"{import_path}: unknown manufacturer {manufacturer!r}")
    source_ids = {source["id"] for source in payload["sources"]}
    for source_record in payload["sources"]:
        source = dict(source_record)
        source.pop("manufacturer", None)
        source["manufacturer_id"] = manufacturer_id
        insert_source(connection, source)

    for row in payload["rows"]:
        tool_id = row["tool_id"]
        tool = connection.execute(
            "SELECT manufacturer_id FROM tools WHERE id=?", (tool_id,)
        ).fetchone()
        if tool is None:
            raise ValueError(f"{import_path}: tool is missing: {tool_id}")
        if tool[0] != manufacturer_id:
            raise ValueError(f"{import_path}: tool manufacturer does not match: {tool_id}")
        grade_code = normalize_part_number(row.get("grade_code"))
        grade_rows = connection.execute(
            """
            SELECT DISTINCT g.id
            FROM tool_grade_options o JOIN grades g ON g.id=o.grade_id
            WHERE o.tool_id=? AND g.normalized_code=?
              AND o.verification_status != 'rejected'
            """,
            (tool_id, grade_code),
        ).fetchall()
        if len(grade_rows) != 1:
            raise ValueError(
                f"{import_path}: {tool_id} must have exactly one active grade {row.get('grade_code')}"
            )
        grade_id = grade_rows[0][0]

        for item in row.get("material_recommendations") or []:
            if item.get("source_id") not in source_ids:
                raise ValueError(f"{import_path}: unknown recommendation source")
            connection.execute(
                """
                INSERT INTO tool_material_recommendations (
                  id, tool_id, grade_id, iso_group, material_subgroup, suitability,
                  evidence_status, verification_status, source_id, source_page_ref,
                  source_table_ref, source_raw_text, extraction_method, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    tool_id,
                    grade_id,
                    item["iso_group"],
                    item.get("material_subgroup"),
                    item["suitability"],
                    item.get("evidence_status") or "manufacturer_claim",
                    item.get("verification_status") or "manufacturer_verified",
                    item["source_id"],
                    item.get("source_page_ref"),
                    item.get("source_table_ref"),
                    item.get("source_raw_text"),
                    item.get("extraction_method") or "manufacturer_page",
                    item.get("notes"),
                ),
            )
            for source_id in item.get("source_ids") or [item["source_id"]]:
                if source_id not in source_ids:
                    raise ValueError(f"{import_path}: unknown recommendation source")
                connection.execute(
                    """
                    INSERT INTO tool_material_recommendation_sources
                      (recommendation_id, source_id, evidence_role)
                    VALUES (?, ?, 'direct_source')
                    """,
                    (item["id"], source_id),
                )

        for profile in row.get("cutting_profiles") or []:
            if profile.get("source_id") not in source_ids:
                raise ValueError(f"{import_path}: unknown cutting-profile source")
            connection.execute(
                """
                INSERT INTO cutting_data_profiles (
                  id, tool_id, grade_id, source_id, source_part_number, source_grade,
                  source_geometry, source_chipbreaker, source_material_label,
                  iso_material_group, material_subgroup, operation_type,
                  cut_condition, coolant_condition, surface_speed_min,
                  surface_speed_start, surface_speed_max, surface_speed_unit,
                  feed_min, feed_max, feed_unit, depth_of_cut_min,
                  depth_of_cut_max, depth_of_cut_unit, source_page_ref,
                  source_table_ref, source_raw_text, extraction_method,
                  verification_status, reviewer, reviewed_at, notes
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?
                )
                """,
                (
                    profile["id"],
                    tool_id,
                    grade_id,
                    profile["source_id"],
                    profile["source_part_number"],
                    profile.get("source_grade"),
                    profile.get("source_geometry"),
                    profile.get("source_chipbreaker"),
                    profile.get("source_material_label"),
                    profile["iso_material_group"],
                    profile.get("material_subgroup"),
                    profile["operation_type"],
                    profile["cut_condition"],
                    profile["coolant_condition"],
                    profile.get("surface_speed_min"),
                    profile.get("surface_speed_start"),
                    profile.get("surface_speed_max"),
                    profile.get("surface_speed_unit"),
                    profile.get("feed_min"),
                    profile.get("feed_max"),
                    profile.get("feed_unit"),
                    profile.get("depth_of_cut_min"),
                    profile.get("depth_of_cut_max"),
                    profile.get("depth_of_cut_unit"),
                    profile.get("source_page_ref"),
                    profile.get("source_table_ref"),
                    profile.get("source_raw_text"),
                    profile.get("extraction_method") or "manufacturer_page",
                    profile.get("verification_status") or "manufacturer_verified",
                    profile.get("notes"),
                ),
            )
            evidence_sources = profile.get("evidence_sources") or [
                {
                    "source_id": profile["source_id"],
                    "evidence_role": "cutting_speed",
                    "source_page_ref": profile.get("source_page_ref"),
                    "source_table_ref": profile.get("source_table_ref"),
                    "source_raw_text": profile.get("source_raw_text"),
                    "extraction_method": profile.get("extraction_method"),
                }
            ]
            for evidence in evidence_sources:
                if evidence.get("source_id") not in source_ids:
                    raise ValueError(f"{import_path}: unknown profile evidence source")
                connection.execute(
                    """
                    INSERT INTO cutting_data_profile_sources (
                      profile_id, source_id, evidence_role, source_page_ref,
                      source_printed_page_ref, source_table_ref, source_raw_text,
                      extraction_method
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile["id"],
                        evidence["source_id"],
                        evidence["evidence_role"],
                        evidence.get("source_page_ref"),
                        evidence.get("source_printed_page_ref"),
                        evidence.get("source_table_ref"),
                        evidence.get("source_raw_text"),
                        evidence.get("extraction_method"),
                    ),
                )


def load_shop_inputs(data_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    input_dir = data_dir / "shop_inputs"
    if not input_dir.is_dir():
        return []
    inputs: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(input_dir.glob("*.json"), key=lambda item: item.name.casefold()):
        payload = load_json(path)
        if payload.get("schema_version") != 1:
            raise ValueError(f"{path}: unsupported shop-input schema")
        if not clean_text(payload.get("input_id")) or not clean_text(payload.get("machine_tool_id")):
            raise ValueError(f"{path}: input_id and machine_tool_id are required")
        source = payload.get("source") or {}
        for key in ("title", "recorded_by", "recorded_at", "capture_method", "raw_text"):
            if not clean_text(source.get(key)):
                raise ValueError(f"{path}: source.{key} is required")
        fit_rule = payload.get("fit_rule")
        if fit_rule is not None:
            for key in ("recorded_by", "recorded_at", "capture_method", "raw_text"):
                if not clean_text(fit_rule.get(key)):
                    raise ValueError(f"{path}: fit_rule.{key} is required")
            if fit_rule.get("match_method") != "exact_source_backed_machine_side_interface":
                raise ValueError(f"{path}: unsupported fit-rule match method")
            component_types = fit_rule.get("component_types") or []
            if not component_types or any(item not in {"holder", "shank"} for item in component_types):
                raise ValueError(f"{path}: fit_rule.component_types must contain holder and/or shank")
        station_numbers: set[int] = set()
        for group in payload.get("station_groups") or []:
            interface_type = group.get("accepted_interface_type")
            if interface_type not in {"square_shank", "round_shank"}:
                raise ValueError(f"{path}: unsupported station interface {interface_type!r}")
            size = group.get("accepted_size_mm")
            if not isinstance(size, (int, float)) or size <= 0:
                raise ValueError(f"{path}: accepted_size_mm must be positive")
            for number in group.get("station_numbers") or []:
                if not isinstance(number, int) or number <= 0:
                    raise ValueError(f"{path}: station numbers must be positive integers")
                if number in station_numbers:
                    raise ValueError(f"{path}: duplicate station number {number}")
                station_numbers.add(number)
        if not station_numbers:
            raise ValueError(f"{path}: at least one station is required")
        inputs.append((path, payload))
    return inputs


def metric_fact_value(row: sqlite3.Row) -> float | None:
    """Return a fact's millimetre value only when its unit is explicit."""
    if row["value_number"] is not None and row["unit"] == "mm":
        return float(row["value_number"])
    text = clean_text(row["value_text"])
    if not text:
        return None
    match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*mm\b", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def source_lineage_for_facts(
    connection: sqlite3.Connection,
    fact_ids: list[str],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in fact_ids)
    return connection.execute(
        f"""
        SELECT DISTINCT s.id, s.source_type
        FROM fact_sources fs
        JOIN sources s ON s.id=fs.source_id
        WHERE fs.fact_id IN ({placeholders})
        ORDER BY CASE s.source_type
          WHEN 'manufacturer_product_page' THEN 1
          WHEN 'manufacturer_catalog' THEN 2
          WHEN 'machine_manual' THEN 3
          WHEN 'shop_note' THEN 4
          WHEN 'local_file' THEN 5
          WHEN 'legacy_reference' THEN 6
          WHEN 'secondary_web' THEN 7
          ELSE 8
        END, s.id
        """,
        fact_ids,
    ).fetchall()


def discover_source_backed_machine_interfaces(
    connection: sqlite3.Connection,
    station_groups: list[dict[str, Any]],
    component_types: list[str],
) -> dict[tuple[str, float], list[dict[str, Any]]]:
    """Promote only exact, source-backed shank dimensions into typed interfaces."""
    target_specs = {
        (group["accepted_interface_type"], float(group["accepted_size_mm"]))
        for group in station_groups
    }
    fact_keys = {
        "shank_height",
        "shank_height_mm",
        "shank_width",
        "shank_width_mm",
        "shank_diameter",
        "shank_diameter_mm",
        "shank_clamping_diameter",
        "shank_clamping_diameter_mm",
    }
    placeholders = ",".join("?" for _ in component_types)
    fact_placeholders = ",".join("?" for _ in fact_keys)
    rows = connection.execute(
        f"""
        SELECT t.id AS tool_id, t.component_type, f.id AS fact_id, f.fact_key,
               f.value_text, f.value_number, f.unit
        FROM tools t
        JOIN facts f ON f.tool_id=t.id
        WHERE t.component_type IN ({placeholders})
          AND f.fact_key IN ({fact_placeholders})
        ORDER BY t.id, f.fact_key, f.id
        """,
        [*component_types, *sorted(fact_keys)],
    ).fetchall()
    facts_by_tool: dict[str, dict[str, list[sqlite3.Row]]] = {}
    component_by_tool: dict[str, str] = {}
    for row in rows:
        component_by_tool[row["tool_id"]] = row["component_type"]
        facts_by_tool.setdefault(row["tool_id"], {}).setdefault(row["fact_key"], []).append(row)

    def first_exact(
        tool_facts: dict[str, list[sqlite3.Row]], keys: tuple[str, ...], size_mm: float
    ) -> sqlite3.Row | None:
        return next(
            (
                row
                for key in keys
                for row in tool_facts.get(key, [])
                if metric_fact_value(row) == size_mm
            ),
            None,
        )

    matches: dict[tuple[str, float], list[dict[str, Any]]] = {
        target: [] for target in target_specs
    }
    for tool_id, tool_facts in sorted(facts_by_tool.items()):
        for interface_type, size_mm in sorted(target_specs):
            if interface_type == "square_shank":
                matched_facts = [
                    first_exact(tool_facts, ("shank_height_mm", "shank_height"), size_mm),
                    first_exact(tool_facts, ("shank_width_mm", "shank_width"), size_mm),
                ]
            elif interface_type == "round_shank":
                matched_facts = [
                    first_exact(
                        tool_facts,
                        (
                            "shank_diameter_mm",
                            "shank_diameter",
                            "shank_clamping_diameter_mm",
                            "shank_clamping_diameter",
                        ),
                        size_mm,
                    )
                ]
            else:
                continue
            if any(row is None for row in matched_facts):
                continue
            fact_ids = [row["fact_id"] for row in matched_facts if row is not None]
            source_rows = source_lineage_for_facts(connection, fact_ids)
            if not source_rows:
                continue
            best_source = source_rows[0]
            interface_evidence = {
                "manufacturer_product_page": "manufacturer_claim",
                "manufacturer_catalog": "catalog_claim",
                "machine_manual": "catalog_claim",
            }.get(best_source["source_type"], "imported")
            shape = "square" if interface_type == "square_shank" else "round"
            connection.execute(
                """
                INSERT INTO interfaces (
                  id, tool_id, interface_role, interface_type, designation,
                  shape, size_mm, system_name, evidence_status, source_id, notes
                ) VALUES (?, ?, 'provides', ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    stable_id("interface", "source-backed-machine-side", tool_id, interface_type, size_mm),
                    tool_id,
                    interface_type,
                    f"{size_mm:g} mm {shape} machine-side shank",
                    shape,
                    size_mm,
                    interface_evidence,
                    best_source["id"],
                    "Promoted only from explicit, source-linked shank dimension facts for exact station matching.",
                ),
            )
            matches[(interface_type, size_mm)].append(
                {
                    "tool_id": tool_id,
                    "component_type": component_by_tool[tool_id],
                    "source_ids": [row["id"] for row in source_rows],
                }
            )
    return matches


def apply_shop_input(
    connection: sqlite3.Connection,
    input_path: Path,
    payload: dict[str, Any],
    tool_by_public_key: dict[str, str],
    tool_by_normalized_part: dict[str, str],
    tool_components: dict[str, str],
    build_source_ids_by_tool: dict[str, list[str]],
) -> None:
    machine_id = payload["machine_tool_id"]
    machine = connection.execute(
        "SELECT manufacturer_id, manufacturer_raw, component_type FROM tools WHERE id=?",
        (machine_id,),
    ).fetchone()
    if machine is None or machine["component_type"] != "machine":
        raise ValueError(f"{input_path}: machine tool is missing or invalid: {machine_id}")
    source_data = payload["source"]
    fit_rule = payload.get("fit_rule")
    source_id = stable_id("source", "shop-input", payload["input_id"])
    try:
        stored_path = input_path.resolve().relative_to(ROOT.parent).as_posix()
    except ValueError:
        stored_path = str(input_path.resolve())
    source = {
        "id": source_id,
        "source_type": "shop_note",
        "title": source_data["title"],
        "url": None,
        "local_path": stored_path,
        "page_ref": None,
        "manufacturer_id": machine["manufacturer_id"],
        "raw_reference": " ".join(
            text for text in (source_data["raw_text"], (fit_rule or {}).get("raw_text")) if text
        ),
        "retrieved_at": source_data["recorded_at"],
        "notes": (
            f"Recorded by {source_data['recorded_by']} on {source_data['recorded_at']} "
            f"via {source_data['capture_method']}."
        ),
    }
    insert_source(connection, source)
    station_count = sum(len(group["station_numbers"]) for group in payload["station_groups"])
    batch_id = stable_id("shop-input", payload["input_id"])
    connection.execute(
        """
        INSERT INTO shop_input_batches (
          id, input_path, input_sha256, recorded_by, recorded_at,
          capture_method, source_id, row_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            stored_path,
            file_sha256(input_path),
            source_data["recorded_by"],
            source_data["recorded_at"],
            source_data["capture_method"],
            source_id,
            station_count,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO tool_sources (tool_id, source_id, evidence_role) VALUES (?, ?, 'verification')",
        (machine_id, source_id),
    )
    build_source_ids_by_tool.setdefault(machine_id, []).append(source_id)

    created_stations: list[dict[str, Any]] = []
    for group in payload["station_groups"]:
        interface_type = group["accepted_interface_type"]
        shape = group["accepted_shape"]
        size_mm = float(group["accepted_size_mm"])
        size_label = f"{size_mm:g} mm {shape}"
        for station_number in group["station_numbers"]:
            station_id = f"{machine_id}_STATION_{station_number:02d}"
            part_number = f"ECAS20-ST{station_number:02d}"
            normalized_part = normalize_part_number(part_number)
            raw_record = {
                "origin": "shop_input",
                "input_id": payload["input_id"],
                "machine_tool_id": machine_id,
                "station_number": station_number,
                "accepted_interface_type": interface_type,
                "accepted_shape": shape,
                "accepted_size_mm": size_mm,
            }
            connection.execute(
                """
                INSERT INTO tools (
                  id, part_number, normalized_part_number, manufacturer_id, manufacturer_raw,
                  component_type, family, tool_type, description, size, geometry,
                  insert_seat, iso_designation, grade, shape, chipbreaker,
                  lifecycle_status, evidence_status, legacy_mounts_to, legacy_record_json
                ) VALUES (?, ?, ?, ?, ?, 'station', ?, 'Machine station', ?, ?, ?,
                          NULL, NULL, NULL, ?, NULL, 'unknown', 'shop_verified', NULL, ?)
                """,
                (
                    station_id,
                    part_number,
                    normalized_part,
                    machine["manufacturer_id"],
                    machine["manufacturer_raw"],
                    f"{payload['machine_model']} gang block",
                    f"{payload['machine_model']} station {station_number}; accepts {size_label} shanks.",
                    size_label,
                    f"accepts {size_label} shank",
                    shape,
                    json.dumps(raw_record, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
            for alias, alias_type in (
                (station_id, "legacy_id"),
                (f"ECAS20 station {station_number}", "search"),
                (f"Station {station_number}", "search"),
            ):
                connection.execute(
                    "INSERT INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, ?)",
                    (station_id, alias, alias_type),
                )
            for role in ("row_source", "specification"):
                connection.execute(
                    "INSERT INTO tool_sources (tool_id, source_id, evidence_role) VALUES (?, ?, ?)",
                    (station_id, source_id, role),
                )

            station_facts = (
                ("station_number", "Station number", None, float(station_number), None),
                ("accepted_shank_shape", "Accepted shank shape", shape, None, None),
                ("accepted_shank_size_mm", "Accepted shank size", None, size_mm, "mm"),
                ("machine_model", "Machine model", payload["machine_model"], None, None),
            )
            for fact_key, original_key, text_value, number_value, unit in station_facts:
                fact_id = stable_id("fact", "shop-input", station_id, fact_key)
                connection.execute(
                    """
                    INSERT INTO facts (
                      id, tool_id, fact_key, original_key, value_text, value_number,
                      value_boolean, value_json, unit, evidence_status, verification_status,
                      source_id, source_raw_text, extraction_method, reviewer, reviewed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'shop_verified',
                              'shop_verified', ?, ?, 'shop_entry', ?, ?)
                    """,
                    (
                        fact_id,
                        station_id,
                        fact_key,
                        original_key,
                        text_value,
                        number_value,
                        unit,
                        source_id,
                        source_data["raw_text"],
                        source_data["recorded_by"],
                        source_data["recorded_at"],
                    ),
                )
                connection.execute(
                    "INSERT INTO fact_sources (fact_id, source_id, evidence_role) VALUES (?, ?, 'direct_source')",
                    (fact_id, source_id),
                )

            connection.execute(
                """
                INSERT INTO interfaces (
                  id, tool_id, interface_role, interface_type, designation,
                  shape, size_mm, system_name, evidence_status, source_id, notes
                ) VALUES (?, ?, 'accepts', ?, ?, ?, ?, ?, 'shop_verified', ?, ?)
                """,
                (
                    stable_id("interface", "shop-input", station_id, interface_type, size_mm),
                    station_id,
                    interface_type,
                    f"{size_mm:g} mm {shape} shank",
                    shape,
                    size_mm,
                    payload["machine_model"],
                    source_id,
                    "Direct shop confirmation; no holder or shank assignment is implied.",
                ),
            )
            claim_id = stable_id("claim", "shop-input", station_id, "station-of", machine_id)
            connection.execute(
                """
                INSERT INTO compatibility_claims (
                  id, subject_tool_id, relationship, object_kind, object_tool_id,
                  object_value, evidence_status, review_status, confidence, source_id,
                  evidence_kind, source_raw_text, notes, generated_by, suppressed
                ) VALUES (?, ?, 'station_of', 'tool', ?, NULL, 'shop_verified',
                          'accepted', 1.0, ?, 'direct_shop_confirmation', ?, ?, 'shop_input', 0)
                """,
                (
                    claim_id,
                    station_id,
                    machine_id,
                    source_id,
                    source_data["raw_text"],
                    f"Station {station_number} belongs to the {payload['machine_model']} gang block.",
                ),
            )
            connection.execute(
                "INSERT INTO compatibility_claim_sources (claim_id, source_id, evidence_role) VALUES (?, ?, 'primary_source')",
                (claim_id, source_id),
            )
            tool_by_public_key[public_key(station_id)] = station_id
            tool_by_normalized_part[normalized_part] = station_id
            tool_components[station_id] = "station"
            build_source_ids_by_tool[station_id] = [source_id]
            created_stations.append(
                {
                    "station_id": station_id,
                    "station_number": station_number,
                    "interface_type": interface_type,
                    "shape": shape,
                    "size_mm": size_mm,
                }
            )

    if fit_rule:
        matches = discover_source_backed_machine_interfaces(
            connection,
            payload["station_groups"],
            fit_rule["component_types"],
        )
        for station in created_stations:
            target = (station["interface_type"], station["size_mm"])
            for candidate in matches[target]:
                relationship = (
                    "accepts_holder"
                    if candidate["component_type"] == "holder"
                    else "accepts_shank"
                )
                claim_id = stable_id(
                    "claim",
                    "shop-input-exact-interface",
                    station["station_id"],
                    relationship,
                    candidate["tool_id"],
                )
                connection.execute(
                    """
                    INSERT INTO compatibility_claims (
                      id, subject_tool_id, relationship, object_kind, object_tool_id,
                      object_value, evidence_status, review_status, confidence, source_id,
                      evidence_kind, source_raw_text, notes, generated_by, suppressed
                    ) VALUES (?, ?, ?, 'tool', ?, NULL, 'shop_verified', 'accepted', 1.0, ?,
                              'direct_shop_confirmation_plus_source_dimensions', ?, ?,
                              'shop_input_exact_interface_match', 0)
                    """,
                    (
                        claim_id,
                        station["station_id"],
                        relationship,
                        candidate["tool_id"],
                        source_id,
                        fit_rule["raw_text"],
                        (
                            f"Station {station['station_number']} accepts {candidate['tool_id']} by an exact "
                            f"{station['size_mm']:g} mm {station['shape']} machine-side shank match."
                        ),
                    ),
                )
                connection.execute(
                    "INSERT INTO compatibility_claim_sources (claim_id, source_id, evidence_role) VALUES (?, ?, 'primary_source')",
                    (claim_id, source_id),
                )
                for candidate_source_id in candidate["source_ids"]:
                    connection.execute(
                        """
                        INSERT INTO compatibility_claim_sources (claim_id, source_id, evidence_role)
                        VALUES (?, ?, 'derivation_input')
                        """,
                        (claim_id, candidate_source_id),
                    )


def build_database(data_dir: Path, db_out: Path) -> dict[str, Any]:
    config = load_json(NORMALIZATION_PATH)
    manifest = load_json(data_dir / "manifest.json")
    tools = load_jsonl(data_dir / "tools.jsonl")
    legacy_relationships = load_jsonl(data_dir / "legacy_relationships.jsonl")
    catalog_claims = load_jsonl(data_dir / "catalog_claims.jsonl")
    source_documents = load_source_documents(data_dir)
    reviewed_imports = load_reviewed_imports(data_dir)
    manufacturer_imports = load_manufacturer_imports(data_dir)
    shop_inputs = load_shop_inputs(data_dir)

    expected_tools = int(manifest["counts"]["tools"])
    if len(tools) != expected_tools:
        raise ValueError(f"Seed manifest expects {expected_tools} tools; found {len(tools)}")

    manufacturer_aliases = config["manufacturer_aliases"]
    manufacturer_websites = config["manufacturer_websites"]
    spec_aliases = config["spec_key_aliases"]
    empty_markers = {item.casefold() for item in config["empty_markers"]}

    db_out.parent.mkdir(parents=True, exist_ok=True)
    if db_out.exists():
        db_out.unlink()
    connection = sqlite3.connect(db_out)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    seed_hash = hashlib.sha256((data_dir / "manifest.json").read_bytes()).hexdigest()
    connection.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('seed_manifest_sha256', ?)",
        (seed_hash,),
    )
    connection.executemany(
        "INSERT INTO work_material_groups (iso_group, name, description, sort_order) VALUES (?, ?, ?, ?)",
        [
            ("P", "Steel", "Unalloyed, low-alloy, and high-alloy steels", 10),
            ("M", "Stainless steel", "Ferritic, martensitic, austenitic, and duplex stainless steels", 20),
            ("K", "Cast iron", "Grey, nodular, and malleable cast irons", 30),
            ("N", "Non-ferrous", "Aluminum, copper, brass, and other non-ferrous materials", 40),
            ("S", "Heat-resistant alloys", "Nickel, cobalt, titanium, and heat-resistant superalloys", 50),
            ("H", "Hardened materials", "Hardened steels and chilled cast iron", 60),
            ("O", "Other", "Materials outside the primary ISO P/M/K/N/S/H groups", 70),
            ("unknown", "Unknown", "Material group has not been established", 99),
        ],
    )

    canonical_manufacturers: set[str] = set()
    for record in tools:
        raw = clean_text(record.get("manufacturer")) or "Unknown"
        canonical_manufacturers.add(manufacturer_aliases.get(raw, raw))
    canonical_manufacturers.add("Unknown")
    for document in source_documents:
        raw = clean_text(document.get("manufacturer")) or "Unknown"
        canonical_manufacturers.add(manufacturer_aliases.get(raw, raw))
    for _path, manufacturer_import in manufacturer_imports:
        raw = clean_text(manufacturer_import.get("manufacturer")) or "Unknown"
        canonical_manufacturers.add(manufacturer_aliases.get(raw, raw))

    manufacturer_ids: dict[str, str] = {}
    used_ids: set[str] = set()
    for name in sorted(canonical_manufacturers, key=str.casefold):
        manufacturer_id = slug(name)
        if manufacturer_id in used_ids:
            manufacturer_id = stable_id("manufacturer", name)
        used_ids.add(manufacturer_id)
        manufacturer_ids[name] = manufacturer_id
        connection.execute(
            "INSERT INTO manufacturers (id, name, website_url) VALUES (?, ?, ?)",
            (manufacturer_id, name, manufacturer_websites.get(name)),
        )
        connection.execute(
            "INSERT INTO manufacturer_aliases (alias, manufacturer_id) VALUES (?, ?)",
            (name, manufacturer_id),
        )
    for alias, canonical in sorted(manufacturer_aliases.items()):
        connection.execute(
            "INSERT OR IGNORE INTO manufacturer_aliases (alias, manufacturer_id) VALUES (?, ?)",
            (alias, manufacturer_ids[canonical]),
        )

    for document in source_documents:
        manufacturer_raw = clean_text(document.get("manufacturer")) or "Unknown"
        manufacturer = manufacturer_aliases.get(manufacturer_raw, manufacturer_raw)
        insert_source(
            connection,
            {
                "id": document["source_id"],
                "source_type": document.get("source_type") or "manufacturer_catalog",
                "title": document["title"],
                "url": document.get("url"),
                "local_path": document["local_path"],
                "page_ref": None,
                "manufacturer_id": manufacturer_ids[manufacturer],
                "raw_reference": (
                    f"{document['local_path']} | SHA-256 {document['content_sha256']}"
                ),
                "content_sha256": document["content_sha256"],
                "document_edition": document.get("document_edition"),
                "retrieved_at": document.get("retrieved_at"),
                "notes": document.get("edition_evidence"),
            },
        )

    tool_by_public_key: dict[str, str] = {}
    tool_by_normalized_part: dict[str, str] = {}
    tool_components: dict[str, str] = {}
    build_source_ids_by_tool: dict[str, list[str]] = {}
    source_count_before = 0

    for record in tools:
        tool_id = str(record["json_id"]).strip()
        if not tool_id:
            raise ValueError("Tool record has a blank json_id")
        component_type = str(record.get("component_type") or "").strip().casefold()
        if component_type not in VALID_COMPONENT_TYPES:
            raise ValueError(f"{tool_id}: unsupported component_type {component_type!r}")

        manufacturer_raw = clean_text(record.get("manufacturer")) or "Unknown"
        manufacturer = manufacturer_aliases.get(manufacturer_raw, manufacturer_raw)
        manufacturer_id = manufacturer_ids[manufacturer]
        source_records = [
            parse_legacy_source(reference, manufacturer_id)
            for reference in (record.get("sources") or [])
            if clean_text(reference)
        ]
        evidence_status = evidence_for_sources(source_records)
        normalized_part = normalize_part_number(tool_id)
        if not normalized_part:
            raise ValueError(f"{tool_id}: part number normalizes to blank")

        connection.execute(
            """
            INSERT INTO tools (
              id, part_number, normalized_part_number, manufacturer_id, manufacturer_raw,
              component_type, family, tool_type, description, size, geometry,
              insert_seat, iso_designation, grade, shape, chipbreaker,
              lifecycle_status, evidence_status, legacy_mounts_to, legacy_record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_id,
                tool_id,
                normalized_part,
                manufacturer_id,
                manufacturer_raw,
                component_type,
                clean_optional(record.get("category"), empty_markers),
                clean_optional(record.get("type"), empty_markers),
                clean_text(record.get("description")) or "Description missing",
                clean_optional(record.get("size"), empty_markers),
                clean_optional(record.get("geometry"), empty_markers),
                clean_optional(record.get("insert_seat"), empty_markers),
                clean_optional(record.get("iso_designation"), empty_markers),
                clean_optional(record.get("grade"), empty_markers),
                clean_optional(record.get("shape"), empty_markers),
                clean_optional(record.get("chipbreaker"), empty_markers),
                lifecycle_for(record.get("condition")),
                evidence_status,
                clean_text(record.get("mounts_to")),
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ),
        )
        connection.execute(
            "INSERT INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, 'legacy_id')",
            (tool_id, tool_id),
        )
        if clean_text(record.get("iso_designation")):
            connection.execute(
                "INSERT OR IGNORE INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, 'iso')",
                (tool_id, clean_text(record.get("iso_designation"))),
            )
        specs_for_aliases = record.get("specs") or {}
        for spec_key, alias_type in (
            ("manufacturer_order_code", "manufacturer_part_number"),
            ("manufacturer_material_number", "search"),
            ("webshop_item_number", "search"),
            ("webshop_product_id", "search"),
        ):
            alias = clean_text(specs_for_aliases.get(spec_key))
            if alias:
                connection.execute(
                    "INSERT OR IGNORE INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, ?)",
                    (tool_id, alias, alias_type),
                )

        tool_by_public_key[public_key(tool_id)] = tool_id
        tool_by_normalized_part[normalized_part] = tool_id
        tool_components[tool_id] = component_type

        for source in source_records:
            insert_source(connection, source)
            connection.execute(
                "INSERT OR IGNORE INTO tool_sources (tool_id, source_id, evidence_role) VALUES (?, ?, 'row_source')",
                (tool_id, source["id"]),
            )
            source_count_before += 1
        build_source_ids_by_tool[tool_id] = [source["id"] for source in source_records]

        insert_legacy_grade_options(
            connection,
            tool_id,
            manufacturer_id,
            record.get("grade"),
            source_records,
        )

        specs = record.get("specs") or {}
        if not isinstance(specs, dict):
            raise ValueError(f"{tool_id}: specs must be an object")
        for original_key, value in sorted(specs.items(), key=lambda item: item[0].casefold()):
            fact_key = normalized_fact_key(original_key, spec_aliases)
            text_value, number_value, bool_value, json_value, unit = fact_value(value, fact_key)
            if all(item is None for item in (text_value, number_value, bool_value, json_value)):
                continue
            fact_id = stable_id("fact", tool_id, original_key)
            connection.execute(
                """
                INSERT INTO facts (
                  id, tool_id, fact_key, original_key, value_text, value_number,
                  value_boolean, value_json, unit, evidence_status, verification_status,
                  source_id, extraction_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?, ?, 'legacy_import')
                """,
                (
                    fact_id,
                    tool_id,
                    fact_key,
                    original_key,
                    text_value,
                    number_value,
                    bool_value,
                    json_value,
                    unit,
                    "source_located" if source_records else "legacy",
                    source_records[0]["id"] if len(source_records) == 1 else None,
                ),
            )
            for source in source_records:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO fact_sources (fact_id, source_id, evidence_role)
                    VALUES (?, ?, 'legacy_row_source')
                    """,
                    (fact_id, source["id"]),
                )

        material_groups = specs.get("material_groups") or []
        if isinstance(material_groups, str):
            material_groups = [material_groups]
        if isinstance(material_groups, list):
            recommendation_source_id = source_records[0]["id"] if len(source_records) == 1 else None
            recommendation_evidence = {
                "manufacturer_source": "manufacturer_claim",
                "catalog_source": "catalog_claim",
                "legacy_source": "imported",
                "unverified": "unverified",
            }[evidence_status]
            for material_group in sorted({str(value).strip().upper() for value in material_groups if clean_text(value)}):
                if material_group not in {"P", "M", "K", "N", "S", "H", "O", "unknown"}:
                    continue
                recommendation_id = stable_id("material", tool_id, material_group)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO tool_material_recommendations
                      (id, tool_id, iso_group, suitability, evidence_status,
                       verification_status, source_id, extraction_method, notes)
                    VALUES (?, ?, ?, 'recommended', ?, ?, ?, 'legacy_import', ?)
                    """,
                    (
                        recommendation_id,
                        tool_id,
                        material_group,
                        recommendation_evidence,
                        "source_located" if source_records else "legacy",
                        recommendation_source_id,
                        "Imported only from the explicit specs.material_groups field; not inferred from tags.",
                    ),
                )
                for source in source_records:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO tool_material_recommendation_sources
                          (recommendation_id, source_id, evidence_role)
                        VALUES (?, ?, 'legacy_row_source')
                        """,
                        (recommendation_id, source["id"]),
                    )

        insert_seat = clean_optional(record.get("insert_seat"), empty_markers)
        iso_designation = clean_optional(record.get("iso_designation"), empty_markers)
        if component_type in {"holder", "module"} and insert_seat:
            connection.execute(
                """
                INSERT INTO interfaces
                  (id, tool_id, interface_role, interface_type, designation, evidence_status)
                VALUES (?, ?, 'accepts', 'insert_seat', ?, 'imported')
                """,
                (stable_id("interface", tool_id, "accepts", insert_seat), tool_id, insert_seat),
            )
        if component_type == "insert" and iso_designation:
            connection.execute(
                """
                INSERT INTO interfaces
                  (id, tool_id, interface_role, interface_type, designation, evidence_status)
                VALUES (?, ?, 'provides', 'insert_seat', ?, 'imported')
                """,
                (stable_id("interface", tool_id, "provides", iso_designation), tool_id, iso_designation),
            )

    connection.row_factory = sqlite3.Row
    for input_path, payload in shop_inputs:
        apply_shop_input(
            connection,
            input_path,
            payload,
            tool_by_public_key,
            tool_by_normalized_part,
            tool_components,
            build_source_ids_by_tool,
        )
    connection.row_factory = None

    for relationship in legacy_relationships:
        subject = tool_by_public_key.get(public_key(relationship.get("subject_json_id")))
        if not subject:
            continue
        raw_object = clean_text(relationship.get("object_json_id")) or "Unknown object"
        object_tool = tool_by_public_key.get(public_key(raw_object))
        relation = str(relationship.get("relationship") or "").strip()
        direct_machine_claim = relation == "compatible_with_machine"
        if object_tool:
            object_kind = "tool"
            object_value = None
        elif direct_machine_claim:
            object_kind = "machine_model"
            object_value = raw_object
        else:
            object_kind = "external_reference"
            object_value = raw_object

        source_status = str(relationship.get("verification_status") or "").casefold()
        if source_status == "inferred":
            evidence_status = "inferred"
        elif source_status == "rejected":
            evidence_status = "rejected"
        else:
            evidence_status = "imported"
        notes = clean_text(relationship.get("notes"))
        if direct_machine_claim:
            model_note = "Suppressed: machine fit must be proven through a physical tool-to-station path."
            notes = f"{notes} {model_note}".strip() if notes else model_note

        claim_id = stable_id("claim", "legacy", relationship.get("edge_key"))
        connection.execute(
            """
            INSERT INTO compatibility_claims (
              id, subject_tool_id, relationship, object_kind, object_tool_id,
              object_value, evidence_status, review_status, confidence,
              evidence_kind, notes, generated_by, suppressed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'needs_review', ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                subject,
                relation,
                object_kind,
                object_tool,
                object_value,
                evidence_status,
                relationship.get("confidence"),
                clean_text(relationship.get("evidence_kind")),
                notes,
                clean_text(relationship.get("generated_by")) or "legacy_migration",
                int(direct_machine_claim),
            ),
        )
        subject_role = "derivation_input" if evidence_status == "inferred" else "subject_record_context"
        object_role = "derivation_input" if evidence_status == "inferred" else "object_record_context"
        for source_id in build_source_ids_by_tool.get(subject, []):
            connection.execute(
                "INSERT OR IGNORE INTO compatibility_claim_sources (claim_id, source_id, evidence_role) VALUES (?, ?, ?)",
                (claim_id, source_id, subject_role),
            )
        if object_tool:
            for source_id in build_source_ids_by_tool.get(object_tool, []):
                connection.execute(
                    "INSERT OR IGNORE INTO compatibility_claim_sources (claim_id, source_id, evidence_role) VALUES (?, ?, ?)",
                    (claim_id, source_id, object_role),
                )

    for claim in catalog_claims:
        subject = tool_by_public_key.get(public_key(claim.get("subject_public_id")))
        if not subject:
            subject = tool_by_normalized_part.get(normalize_part_number(claim.get("subject_part_number")))
        if not subject:
            raise ValueError(f"Catalog claim subject is missing: {claim.get('subject_part_number')}")

        manufacturer_id = connection.execute(
            "SELECT manufacturer_id FROM tools WHERE id = ?", (subject,)
        ).fetchone()[0]
        source = parse_claim_source(claim, manufacturer_id)
        insert_source(connection, source)
        raw_object_tool = clean_text(claim.get("object_public_id"))
        object_tool = tool_by_public_key.get(public_key(raw_object_tool)) if raw_object_tool else None
        object_value = clean_text(claim.get("object_value"))
        object_kind = clean_text(claim.get("object_kind")) or ("tool" if object_tool else "external_reference")
        if object_kind not in {"tool", "insert_seat", "machine_model", "interface", "external_reference"}:
            object_kind = "external_reference"
        if object_tool:
            object_kind = "tool"
            object_value = None
        elif not object_value:
            object_value = raw_object_tool or "Unknown object"

        claim_id = stable_id("claim", "catalog", claim.get("claim_key"))
        connection.execute(
            """
            INSERT OR IGNORE INTO compatibility_claims (
              id, subject_tool_id, relationship, object_kind, object_tool_id,
              object_value, evidence_status, review_status, confidence, source_id,
              evidence_kind, source_page_ref, source_raw_text, notes, generated_by, suppressed
            ) VALUES (?, ?, ?, ?, ?, ?, 'catalog_claim', 'needs_review', ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                claim_id,
                subject,
                claim.get("relationship"),
                object_kind,
                object_tool,
                object_value,
                claim.get("confidence"),
                source["id"],
                clean_text(claim.get("extraction_method")) or "manufacturer_catalog",
                clean_text(claim.get("source_catalog_page_ref"))
                or clean_text(claim.get("source_page_ref")),
                clean_text(claim.get("source_raw_text")),
                clean_text(claim.get("notes")),
                clean_text(claim.get("extraction_method")) or "catalog_proposal",
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO compatibility_claim_sources (claim_id, source_id, evidence_role)
            VALUES (?, ?, 'primary_source')
            """,
            (claim_id, source["id"]),
        )

    for packet_path, packet in reviewed_imports:
        apply_reviewed_import(connection, packet_path, packet, manufacturer_ids)
    for import_path, manufacturer_import in manufacturer_imports:
        apply_manufacturer_import(
            connection, import_path, manufacturer_import, manufacturer_ids
        )

    connection.commit()
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "tools",
            "manufacturers",
            "sources",
            "review_batches",
            "review_batch_sources",
            "shop_input_batches",
            "reviewed_tool_tags",
            "grades",
            "grade_aliases",
            "tool_grade_options",
            "tool_sources",
            "facts",
            "fact_sources",
            "interfaces",
            "compatibility_claims",
            "work_material_groups",
            "tool_material_recommendations",
            "tool_material_recommendation_sources",
            "cutting_data_profiles",
            "cutting_data_profile_sources",
            "compatibility_claim_sources",
        )
    }
    connection.execute("VACUUM")
    connection.close()
    return {
        "schema_version": "3.4.0",
        "seed_manifest_sha256": seed_hash,
        "integrity": integrity,
        "foreign_key_issues": len(foreign_key_issues),
        "counts": counts,
        "source_links_seen": source_count_before,
        "reviewed_imports": len(reviewed_imports),
        "manufacturer_imports": len(manufacturer_imports),
        "source_documents": len(source_documents),
        "shop_inputs": len(shop_inputs),
    }


def rows_as_dicts(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fact_display_value(fact: dict[str, Any]) -> Any:
    if fact["value_number"] is not None:
        value: Any = fact["value_number"]
    elif fact["value_boolean"] is not None:
        value = bool(fact["value_boolean"])
    elif fact["value_json"] is not None:
        value = json.loads(fact["value_json"])
    else:
        value = fact["value_text"]
    return value


VERIFICATION_RANK = {
    "legacy": 0,
    "source_located": 1,
    "catalog_verified": 2,
    "manufacturer_verified": 3,
    "shop_verified": 4,
    "rejected": -1,
}

INSERT_SHAPES = {
    "A": ("Parallelogram", "85 degrees"),
    "B": ("Parallelogram", "82 degrees"),
    "C": ("Diamond", "80 degrees"),
    "D": ("Diamond", "55 degrees"),
    "H": ("Hexagon", "120 degrees"),
    "L": ("Rectangle", "90 degrees"),
    "O": ("Octagon", "135 degrees"),
    "P": ("Pentagon", "108 degrees"),
    "R": ("Round", "Round"),
    "S": ("Square", "90 degrees"),
    "T": ("Triangle", "60 degrees"),
    "V": ("Diamond", "35 degrees"),
    "W": ("Trigon", "80 degrees"),
}

INSERT_CLEARANCE = {
    "N": "0 degrees",
    "B": "5 degrees",
    "C": "7 degrees",
    "P": "11 degrees",
    "D": "15 degrees",
    "E": "20 degrees",
    "F": "25 degrees",
    "G": "30 degrees",
}


def strongest_verification(statuses: list[str], fallback: str = "legacy") -> str:
    usable = [status for status in statuses if status in VERIFICATION_RANK and status != "rejected"]
    return max(usable, key=lambda item: VERIFICATION_RANK[item]) if usable else fallback


def extract_iso_insert_designation(candidate: str | None) -> str | None:
    """Return the ISO insert code without swallowing a chipbreaker suffix.

    The metric size block is normally six characters. Its thickness pair may
    contain a letter (for example ``09T304``), so a digits-only expression
    incorrectly rejects common designations such as ``CCMT 09 T3 04``.
    Short four- and five-digit legacy designations remain supported because
    the seed contains a small number of those abbreviated codes.
    """
    if not candidate:
        return None
    normalized = normalize_part_number(candidate)
    full_match = re.search(r"([A-Z]{4}\d{2}[A-Z0-9]\d\d{2})", normalized)
    if full_match:
        return full_match.group(1)
    short_match = re.search(r"([A-Z]{4}\d{4,5})(?!\d)", normalized)
    return short_match.group(1) if short_match else None


GEOMETRY_FACT_TERMS = (
    "angle",
    "circle",
    "depth",
    "diameter",
    "height",
    "length",
    "radius",
    "thickness",
    "width",
)


def manufacturer_geometry_dimensions(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    for fact in facts:
        fact_key = str(fact.get("key") or "")
        if not any(term in fact_key.casefold() for term in GEOMETRY_FACT_TERMS):
            continue
        label_key = str(fact.get("original_key") or fact_key)
        unit = fact.get("unit")
        if unit and label_key.casefold().endswith(f"_{str(unit).casefold()}"):
            label_key = label_key[: -(len(str(unit)) + 1)]
        dimensions.append(
            {
                "label": label_key.replace("_", " ").strip().capitalize(),
                "value": fact["value"],
                "unit": unit,
                "verification_status": fact.get("verification_status", "legacy"),
                "source_ids": fact.get("source_ids") or [],
            }
        )
    return dimensions


def insert_geometry_display(tool: dict[str, Any]) -> dict[str, Any] | None:
    if tool["component_type"] != "insert":
        return None
    aliases = tool.get("aliases") or []
    candidates = [tool.get("iso_designation"), *aliases, tool.get("part_number")]
    designation = next(
        (
            designation
            for candidate in candidates
            if (designation := extract_iso_insert_designation(candidate))
        ),
        None,
    )
    if not designation or designation[0] not in INSERT_SHAPES:
        dimensions = manufacturer_geometry_dimensions(tool.get("facts") or [])
        summary = tool.get("geometry")
        shape_name = tool.get("shape")
        size = tool.get("size")
        manufacturer_designation = tool.get("iso_designation")
        if not any((summary, shape_name, size, manufacturer_designation, dimensions)):
            return None
        return {
            "mode": "manufacturer",
            "designation": manufacturer_designation,
            "shape_code": None,
            "shape_name": shape_name,
            "included_angle": None,
            "clearance_code": None,
            "clearance": None,
            "tolerance_code": None,
            "style_code": None,
            "summary": summary,
            "size": size,
            "dimensions": dimensions,
            "note": "Manufacturer-specific geometry shown from the specifications stored for this tool; no generic ISO schematic is implied.",
        }
    shape_code = designation[0] if designation else None
    clearance_code = designation[1] if designation else None
    tolerance_code = designation[2] if designation else None
    style_code = designation[3] if designation else None
    shape_name, included_angle = INSERT_SHAPES[shape_code]

    facts_by_key = {fact["key"]: fact for fact in tool.get("facts") or []}
    designation_facts = [
        facts_by_key[key]
        for key in ("iso_catalog_id", "iso_designation", "iso_id")
        if key in facts_by_key
    ]
    designation_status = strongest_verification(
        [fact.get("verification_status", "legacy") for fact in designation_facts],
        "source_located" if tool.get("source_ids") else "legacy",
    )
    dimension_groups = (
        ("Inscribed circle", ("inscribed_circle_mm", "inscribed_circle_d", "ic_size")),
        ("Thickness", ("thickness_mm", "thickness_s", "thickness")),
        ("Corner radius", ("corner_radius_mm", "corner_radius_re", "corner_radius")),
        ("Fixing hole", ("hole_size",)),
        ("Cutting edge", ("cutting_edge_length", "cutting_length_l10")),
    )
    dimensions: list[dict[str, Any]] = []
    for label, keys in dimension_groups:
        fact = next((facts_by_key[key] for key in keys if key in facts_by_key), None)
        if fact:
            dimensions.append(
                {
                    "label": label,
                    "value": fact["value"],
                    "unit": fact.get("unit"),
                    "verification_status": fact.get("verification_status", "legacy"),
                    "source_ids": fact.get("source_ids") or [],
                }
            )
    return {
        "mode": "iso",
        "designation": designation,
        "designation_verification_status": designation_status,
        "designation_source_ids": unique_source_ids if (
            unique_source_ids := sorted({
                source_id
                for fact in designation_facts
                for source_id in fact.get("source_ids") or []
            })
        ) else [],
        "shape_code": shape_code,
        "shape_name": shape_name,
        "included_angle": included_angle,
        "clearance_code": clearance_code,
        "clearance": INSERT_CLEARANCE.get(clearance_code),
        "tolerance_code": tolerance_code,
        "style_code": style_code,
        "summary": tool.get("geometry"),
        "size": tool.get("size"),
        "dimensions": dimensions,
        "note": "Normalized ISO-style schematic; not manufacturer artwork. Dimensions are shown only when present in the database.",
    }


def corner_radius_mm_from_geometry(geometry: dict[str, Any]) -> float | None:
    dimension = next(
        (
            item
            for item in geometry.get("dimensions") or []
            if str(item.get("label") or "").casefold() == "corner radius"
        ),
        None,
    )
    if not dimension:
        return None
    source_ids = dimension.get("source_ids")
    if not isinstance(source_ids, list) or not any(
        isinstance(source_id, str) and source_id.strip() for source_id in source_ids
    ):
        return None
    value = dimension.get("value")
    unit = str(dimension.get("unit") or "").casefold()
    if unit == "mm" and isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            normalized = float(value)
        except (OverflowError, ValueError):
            return None
        return normalized if math.isfinite(normalized) and normalized >= 0 else None
    if unit:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*mm\s*", str(value or ""), re.IGNORECASE)
    if not match:
        return None
    try:
        normalized = float(match.group(1))
    except (OverflowError, ValueError):
        return None
    return normalized if math.isfinite(normalized) and normalized >= 0 else None


def build_web_projection(db_path: Path, json_out: Path, build_report: dict[str, Any]) -> dict[str, Any]:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row

    tool_rows = rows_as_dicts(
        connection,
        """
        SELECT
          t.id, t.part_number, t.normalized_part_number, m.name AS manufacturer,
          t.component_type, t.family, t.tool_type, t.description, t.size,
          t.geometry, t.insert_seat, t.iso_designation, t.grade, t.shape,
          t.chipbreaker, t.lifecycle_status, t.evidence_status, t.review_status,
          t.quarantine_reason, t.superseded_by_tool_id, t.legacy_record_json
        FROM tools t
        JOIN manufacturers m ON m.id = t.manufacturer_id
        ORDER BY t.component_type, m.name, t.part_number
        """,
    )
    aliases_by_tool: dict[str, list[str]] = {}
    for alias_row in rows_as_dicts(
        connection,
        "SELECT tool_id, alias FROM tool_aliases ORDER BY tool_id, lower(alias), alias",
    ):
        aliases_by_tool.setdefault(alias_row["tool_id"], []).append(alias_row["alias"])
    fact_source_refs: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT fact_id, source_id, evidence_role, source_page_ref,
               source_printed_page_ref, source_table_ref, source_raw_text,
               extraction_method
        FROM fact_sources ORDER BY fact_id, evidence_role, source_id
        """,
    ):
        fact_source_refs.setdefault(row.pop("fact_id"), []).append(row)

    facts_by_tool: dict[str, list[dict[str, Any]]] = {}
    fact_history_by_tool: dict[str, list[dict[str, Any]]] = {}
    for fact in rows_as_dicts(
        connection,
        """
        SELECT id, tool_id, fact_key, original_key, value_text, value_number,
               value_boolean, value_json, unit, evidence_status, verification_status,
               source_id, source_page_ref, source_table_ref, source_raw_text,
               extraction_method, review_batch_id, reviewer, reviewed_at,
               supersedes_fact_id, is_current
        FROM facts
        ORDER BY tool_id, fact_key, original_key
        """,
    ):
        evidence = fact_source_refs.get(fact["id"], [])
        item = {
                "key": fact["fact_key"],
                "original_key": fact["original_key"],
                "value": fact_display_value(fact),
                "unit": fact["unit"],
                "evidence_status": fact["evidence_status"],
                "verification_status": fact["verification_status"],
                "source_ids": sorted({ref["source_id"] for ref in evidence}),
                "evidence": evidence,
                "source_id": fact["source_id"],
                "source_page_ref": fact["source_page_ref"],
                "source_table_ref": fact["source_table_ref"],
                "source_raw_text": fact["source_raw_text"],
                "extraction_method": fact["extraction_method"],
                "review_batch_id": fact["review_batch_id"],
                "reviewer": fact["reviewer"],
                "reviewed_at": fact["reviewed_at"],
                "supersedes_fact_id": fact["supersedes_fact_id"],
                "is_current": bool(fact["is_current"]),
            }
        target = facts_by_tool if fact["is_current"] else fact_history_by_tool
        target.setdefault(fact["tool_id"], []).append(item)

    source_ids_by_tool: dict[str, list[str]] = {}
    for row in rows_as_dicts(
        connection,
        "SELECT tool_id, source_id FROM tool_sources ORDER BY tool_id, source_id",
    ):
        source_ids_by_tool.setdefault(row["tool_id"], []).append(row["source_id"])

    material_source_refs: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT recommendation_id, source_id, evidence_role, source_page_ref,
               source_printed_page_ref, source_table_ref, source_raw_text,
               extraction_method
        FROM tool_material_recommendation_sources
        ORDER BY recommendation_id, source_id
        """,
    ):
        material_source_refs.setdefault(row.pop("recommendation_id"), []).append(row)

    materials_by_tool: dict[str, list[dict[str, Any]]] = {}
    material_history_by_tool: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT r.id, r.tool_id, r.grade_id, gr.code AS grade_code,
               r.iso_group, g.name, r.material_subgroup,
               r.suitability, r.evidence_status, r.verification_status,
               r.source_id, r.source_page_ref, r.source_table_ref, r.source_raw_text,
               r.extraction_method, r.review_batch_id, r.reviewer, r.reviewed_at,
               r.supersedes_recommendation_id, r.is_current, r.notes
        FROM tool_material_recommendations r
        JOIN work_material_groups g ON g.iso_group = r.iso_group
        LEFT JOIN grades gr ON gr.id = r.grade_id
        ORDER BY r.tool_id, g.sort_order, r.material_subgroup
        """,
    ):
        tool_id = row.pop("tool_id")
        evidence = material_source_refs.get(row.pop("id"), [])
        row["source_ids"] = sorted({ref["source_id"] for ref in evidence})
        row["evidence"] = evidence
        target = materials_by_tool if row.pop("is_current") else material_history_by_tool
        target.setdefault(tool_id, []).append(row)

    grade_options_by_tool: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT o.id, o.tool_id, o.grade_id, g.code, g.material_class, g.coating,
               g.description, g.lifecycle_status, o.option_kind, o.full_order_number,
               o.availability_status, o.is_primary, o.verification_status,
               o.source_id, o.source_page_ref, o.source_table_ref, o.source_raw_text,
               o.extraction_method, o.review_batch_id, o.reviewer, o.reviewed_at
        FROM tool_grade_options o JOIN grades g ON g.id=o.grade_id
        WHERE o.verification_status <> 'rejected'
        ORDER BY o.tool_id, lower(g.code), o.option_kind
        """,
    ):
        grade_options_by_tool.setdefault(row.pop("tool_id"), []).append(row)

    cutting_source_refs: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT profile_id, source_id, evidence_role, source_page_ref,
               source_printed_page_ref, source_table_ref, source_raw_text,
               extraction_method
        FROM cutting_data_profile_sources
        ORDER BY profile_id, evidence_role, source_id
        """,
    ):
        cutting_source_refs.setdefault(row.pop("profile_id"), []).append(row)

    cutting_data_by_tool: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT id, tool_id, grade_id, source_id, source_part_number, source_grade, source_geometry,
               source_chipbreaker, source_material_label, iso_material_group,
               material_subgroup, operation_type, cut_condition, coolant_condition,
               surface_speed_min, surface_speed_start, surface_speed_max, surface_speed_unit,
               feed_min, feed_max, feed_unit,
               depth_of_cut_min, depth_of_cut_max, depth_of_cut_unit,
               source_page_ref, source_table_ref, source_raw_text, extraction_method,
               verification_status, reviewer, reviewed_at, notes
        FROM cutting_data_profiles
        WHERE verification_status IN ('catalog_verified', 'manufacturer_verified')
        ORDER BY tool_id, iso_material_group, operation_type, id
        """,
    ):
        tool_id = row.pop("tool_id")
        row["evidence"] = cutting_source_refs.get(row["id"], [])
        cutting_data_by_tool.setdefault(tool_id, []).append(row)

    reviewed_tags_by_tool: dict[str, list[str]] = {}
    for tag_row in rows_as_dicts(
        connection,
        "SELECT tool_id, tag FROM reviewed_tool_tags ORDER BY tool_id, lower(tag), tag",
    ):
        reviewed_tags_by_tool.setdefault(tag_row["tool_id"], []).append(tag_row["tag"])

    tools: list[dict[str, Any]] = []
    public_verification_statuses = {
        "catalog_verified",
        "manufacturer_verified",
        "shop_verified",
    }
    for row in tool_rows:
        legacy = json.loads(row.pop("legacy_record_json"))
        row["aliases"] = aliases_by_tool.get(row["id"], [])
        row["tags"] = reviewed_tags_by_tool.get(row["id"], legacy.get("tags") or [])
        if "standalone_exact_product" in set(row["tags"]):
            row["standalone_exact_product"] = True
        row["facts"] = facts_by_tool.get(row["id"], [])
        row["fact_history"] = fact_history_by_tool.get(row["id"], [])
        row["source_ids"] = source_ids_by_tool.get(row["id"], [])
        current_materials = materials_by_tool.get(row["id"], [])
        row["materials"] = [
            item
            for item in current_materials
            if item["verification_status"] in public_verification_statuses
        ]
        row["unreviewed_material_claims"] = [
            item
            for item in current_materials
            if item["verification_status"] not in public_verification_statuses
        ]
        row["material_history"] = material_history_by_tool.get(row["id"], [])
        row["grade_options"] = grade_options_by_tool.get(row["id"], [])
        row["cutting_data"] = cutting_data_by_tool.get(row["id"], [])
        if row["review_status"] in {"quarantined", "rejected", "superseded"}:
            row["materials"] = []
            row["cutting_data"] = []
        statuses = [fact["verification_status"] for fact in row["facts"]]
        statuses.extend(item["verification_status"] for item in row["materials"])
        statuses.extend(item["verification_status"] for item in row["cutting_data"])
        if row["evidence_status"] == "shop_verified":
            statuses.append("shop_verified")
        elif row["source_ids"]:
            statuses.append("source_located")
        row["verification_status"] = strongest_verification(statuses)
        row["geometry_display"] = insert_geometry_display(row)
        tools.append(row)

    sources = rows_as_dicts(
        connection,
        """
        SELECT id, source_type, title, url, local_path, page_ref, raw_reference,
               content_sha256, document_edition, retrieved_at, notes
        FROM sources ORDER BY source_type, title, id
        """,
    )
    review_batches = rows_as_dicts(
        connection,
        """
        SELECT id, proposal_id, proposal_path, proposal_sha256,
               review_ledger_path, review_ledger_sha256, catalog_sha256,
               reviewed_at, source_id, row_count
        FROM review_batches ORDER BY reviewed_at, proposal_id
        """,
    )
    review_batch_source_refs: dict[str, list[dict[str, Any]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT review_batch_id, source_id, evidence_role, content_sha256,
               document_edition, page_ref
        FROM review_batch_sources
        ORDER BY review_batch_id, evidence_role, source_id
        """,
    ):
        review_batch_source_refs.setdefault(row.pop("review_batch_id"), []).append(row)
    for batch in review_batches:
        batch["sources"] = review_batch_source_refs.get(batch["id"], [])
    shop_input_batches = rows_as_dicts(
        connection,
        """
        SELECT id, input_path, input_sha256, recorded_by, recorded_at,
               capture_method, source_id, row_count
        FROM shop_input_batches ORDER BY recorded_at, input_path
        """,
    )
    claim_source_refs: dict[str, list[dict[str, str]]] = {}
    for row in rows_as_dicts(
        connection,
        """
        SELECT claim_id, source_id, evidence_role
        FROM compatibility_claim_sources
        ORDER BY claim_id, evidence_role, source_id
        """,
    ):
        claim_source_refs.setdefault(row.pop("claim_id"), []).append(row)

    relationships = rows_as_dicts(
        connection,
        """
        SELECT id, subject_tool_id, relationship, object_kind, object_tool_id,
               object_value, evidence_status, review_status, confidence, source_id,
               evidence_kind, source_page_ref, source_raw_text, notes, generated_by, suppressed
        FROM compatibility_claims
        ORDER BY subject_tool_id, relationship, object_tool_id, object_value, id
        """,
    )
    for relationship in relationships:
        relationship["suppressed"] = bool(relationship["suppressed"])
        relationship["source_refs"] = claim_source_refs.get(relationship["id"], [])

    component_counts = dict(
        connection.execute(
            "SELECT component_type, COUNT(*) FROM tools GROUP BY component_type ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    manufacturer_counts = dict(
        connection.execute(
            """
            SELECT m.name, COUNT(*)
            FROM tools t JOIN manufacturers m ON m.id = t.manufacturer_id
            GROUP BY m.id ORDER BY COUNT(*) DESC, m.name
            """
        ).fetchall()
    )
    evidence_counts = dict(
        connection.execute(
            "SELECT evidence_status, COUNT(*) FROM tools GROUP BY evidence_status ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    suppressed_machine_claims = connection.execute(
        "SELECT COUNT(*) FROM compatibility_claims WHERE relationship='compatible_with_machine' AND suppressed=1"
    ).fetchone()[0]
    material_counts = dict(
        connection.execute(
            """
            SELECT iso_group, COUNT(*) FROM tool_material_recommendations
            WHERE is_current=1 AND verification_status IN (
              'catalog_verified', 'manufacturer_verified', 'shop_verified'
            )
            GROUP BY iso_group ORDER BY iso_group
            """
        ).fetchall()
    )
    connection.close()

    deployment_digest = hashlib.sha256(db_path.read_bytes())
    deployment_root = ROOT.parent / "docs" / "v3"
    deployment_inputs = [
        Path(__file__).resolve(),
        deployment_root / "index.html",
        deployment_root / "app.css",
        deployment_root / "app.js",
        deployment_root / "manifest.webmanifest",
        deployment_root / "sw.js",
        deployment_root / "toolbase-card.png",
    ]
    for deployment_input in deployment_inputs:
        if deployment_input.is_file():
            deployment_digest.update(deployment_input.name.encode("utf-8"))
            deployment_digest.update(deployment_input.read_bytes())
    build_hash = deployment_digest.hexdigest()[:16]
    projection = {
        "meta": {
            "schema_version": build_report["schema_version"],
            "seed_manifest_sha256": build_report["seed_manifest_sha256"],
            "build_hash": build_hash,
            "counts": build_report["counts"],
            "quality": {
                "suppressed_direct_machine_claims": suppressed_machine_claims,
                "note": "Compatibility is evidence with status, not a guarantee of physical fit.",
            },
        },
        "stats": {
            "components": component_counts,
            "manufacturers": manufacturer_counts,
            "evidence": evidence_counts,
            "materials": material_counts,
        },
        "tools": tools,
        "sources": sources,
        "review_batches": review_batches,
        "shop_input_batches": shop_input_batches,
        "relationships": relationships,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    temp = json_out.with_suffix(json_out.suffix + ".tmp")
    temp.write_text(
        json.dumps(projection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temp, json_out)

    index_tools: list[dict[str, Any]] = []
    for tool in tools:
        material_groups = sorted({item["iso_group"] for item in tool["materials"]})
        operations = sorted({item["operation_type"] for item in tool["cutting_data"]})
        grade_codes = sorted({item["code"] for item in tool["grade_options"] if item.get("code")})
        geometry = tool.get("geometry_display") or {}
        fact_terms = [
            f"{fact['key']} {fact['value']}"
            for fact in tool["facts"]
            if fact["key"] in {
                "ansi_catalog_id", "iso_catalog_id", "iso_id", "iso_designation",
                "insert_type", "cutting_direction", "material_groups", "grade",
                "grade_material", "grade_coating", "geometry", "chipbreaker",
                "shank_height_mm", "shank_width_mm", "shank_diameter_mm",
            }
        ]
        search_text = " ".join(
            str(value)
            for value in (
                tool["part_number"], *tool["aliases"], tool["manufacturer"],
                tool["component_type"], tool["family"], tool["tool_type"],
                tool["description"], tool["size"], tool["geometry"], tool["insert_seat"],
                tool["iso_designation"], tool["grade"], tool["shape"], tool["chipbreaker"],
                *(tool["tags"] or []), *material_groups, *operations, *grade_codes, *fact_terms,
            )
            if value
        ).casefold()
        index_tools.append(
            {
                "id": tool["id"],
                "part_number": tool["part_number"],
                "normalized_part_number": tool["normalized_part_number"],
                "aliases": tool["aliases"],
                "manufacturer": tool["manufacturer"],
                "component_type": tool["component_type"],
                "family": tool["family"],
                "tool_type": tool["tool_type"],
                "description": tool["description"],
                "size": tool["size"],
                "grade": tool["grade"],
                "grade_codes": grade_codes,
                "chipbreaker": tool["chipbreaker"],
                "geometry": tool["geometry"],
                "geometry_shape": geometry.get("shape_name"),
                "corner_radius_mm": corner_radius_mm_from_geometry(geometry),
                "material_groups": material_groups,
                "operation_types": operations,
                "verification_status": tool["verification_status"],
                "review_status": tool["review_status"],
                "quarantine_reason": tool["quarantine_reason"],
                "has_cutting_data": bool(tool["cutting_data"]),
                "source_count": len(set(tool["source_ids"])),
                "search_text": search_text,
            }
        )

    index_projection = {
        "meta": projection["meta"],
        "stats": projection["stats"],
        "tools": index_tools,
    }
    details_projection = {
        "meta": projection["meta"],
        "tools_by_id": {tool["id"]: tool for tool in tools},
        "sources_by_id": {source["id"]: source for source in sources},
        "review_batches": review_batches,
        "shop_input_batches": shop_input_batches,
        "relationships": relationships,
    }
    index_path = json_out.with_name("catalog-index.json")
    details_path = json_out.with_name("catalog-details.json")
    meta_path = json_out.with_name("build-meta.json")
    for output_path, payload in (
        (index_path, index_projection),
        (details_path, details_projection),
        (meta_path, {"schema_version": build_report["schema_version"], "build_hash": build_hash}),
    ):
        output_temp = output_path.with_suffix(output_path.suffix + ".tmp")
        output_temp.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(output_temp, output_path)
    return {
        "path": str(json_out),
        "bytes": json_out.stat().st_size,
        "index_path": str(index_path),
        "index_bytes": index_path.stat().st_size,
        "details_path": str(details_path),
        "details_bytes": details_path.stat().st_size,
        "build_hash": build_hash,
        "tools": len(tools),
        "sources": len(sources),
        "relationships": len(relationships),
    }


def main() -> None:
    from build_review_queue import build_queue

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--db-out", type=Path, default=ROOT / "build" / "toolbase.sqlite")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=ROOT.parent / "docs" / "v3" / "data" / "catalog.json",
    )
    parser.add_argument(
        "--published-db-out",
        type=Path,
        default=ROOT.parent / "docs" / "v3" / "data" / "toolbase.sqlite",
    )
    parser.add_argument(
        "--review-queue-out",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    report = build_database(args.data_dir.resolve(), args.db_out.resolve())
    web = build_web_projection(args.db_out.resolve(), args.json_out.resolve(), report)
    review_queue_path = (
        args.review_queue_out.resolve()
        if args.review_queue_out
        else args.db_out.resolve().parent / "ecas20-review-queue.json"
    )
    review_queue = build_queue(args.db_out.resolve(), review_queue_path)
    args.published_db_out.resolve().parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.db_out.resolve(), args.published_db_out.resolve())
    report["web_projection"] = web
    report["review_queue"] = {
        "path": str(review_queue_path),
        **review_queue,
    }
    report["published_database"] = {
        "path": str(args.published_db_out.resolve()),
        "bytes": args.published_db_out.resolve().stat().st_size,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
