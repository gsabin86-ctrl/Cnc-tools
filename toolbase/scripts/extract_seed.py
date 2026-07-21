#!/usr/bin/env python3
"""Export the irreplaceable legacy tooling data into reviewable JSONL files.

This is a one-way preservation step. It never modifies either source database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable


JSON_COLUMNS = {
    "specs": {},
    "compatible_machines": [],
    "compatible_inserts": [],
    "sources": [],
    "tags": [],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_json_columns(record: dict[str, Any]) -> dict[str, Any]:
    for key, fallback in JSON_COLUMNS.items():
        raw = record.get(key)
        if raw is None or str(raw).strip() == "":
            record[key] = fallback.copy() if isinstance(fallback, (dict, list)) else fallback
            continue
        record[key] = json.loads(raw)
    return record


def read_rows(path: Path, sql: str) -> list[dict[str, Any]]:
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql)]


def atomic_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            count += 1
    os.replace(temp, path)
    return count


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def export(legacy_db: Path, v2_db: Path, out_dir: Path) -> dict[str, Any]:
    tools = read_rows(legacy_db, "SELECT * FROM tools ORDER BY json_id")
    for row in tools:
        row.pop("id", None)
        decode_json_columns(row)

    relationships = read_rows(
        legacy_db,
        "SELECT * FROM compatibility_edges ORDER BY edge_key",
    )
    for row in relationships:
        row.pop("id", None)

    claim_sql = """
        SELECT
          c.claim_key, c.subject_public_id, c.subject_part_number,
          c.subject_component_type, c.relationship, c.object_kind,
          c.object_public_id, c.object_value, c.object_component_type,
          c.source_page_ref, c.source_catalog_page_ref, c.source_table_ref,
          c.source_field_ref, c.source_raw_text, c.catalog_id, c.batch_name,
          c.extraction_method, c.verification_status, c.reviewer,
          c.reviewed_at, c.confidence, c.notes,
          s.source_key, s.source_type, s.title AS source_title,
          s.url AS source_url, s.file_name AS source_file_name,
          s.page_ref AS structured_source_page_ref, s.notes AS source_notes
        FROM compatibility_claims c
        LEFT JOIN sources s ON s.id = c.source_id
        ORDER BY c.claim_key
    """
    claims = read_rows(v2_db, claim_sql)

    counts = {
        "tools": atomic_jsonl(out_dir / "tools.jsonl", tools),
        "legacy_relationships": atomic_jsonl(
            out_dir / "legacy_relationships.jsonl", relationships
        ),
        "catalog_claims": atomic_jsonl(out_dir / "catalog_claims.jsonl", claims),
    }
    manifest = {
        "format_version": 1,
        "source_databases": {
            "legacy": {"file": legacy_db.name, "sha256": sha256_file(legacy_db)},
            "v2": {"file": v2_db.name, "sha256": sha256_file(v2_db)},
        },
        "counts": counts,
    }
    atomic_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-db", type=Path, required=True)
    parser.add_argument("--v2-db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest = export(args.legacy_db.resolve(), args.v2_db.resolve(), args.out.resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
