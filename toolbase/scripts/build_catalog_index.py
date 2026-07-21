#!/usr/bin/env python3
"""Build a hash-addressed page-text index for one catalog in the source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "toolbase" / "data" / "source_documents.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "toolbase" / "build" / "catalog_indexes"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-id", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    source = next(
        (item for item in manifest.get("documents") or [] if item.get("catalog_id") == args.catalog_id),
        None,
    )
    if source is None:
        print(f"unknown catalog id: {args.catalog_id}", file=sys.stderr)
        return 1
    pdf_path = REPO_ROOT / source["local_path"]
    if not pdf_path.is_file():
        print(f"catalog file is missing: {pdf_path}", file=sys.stderr)
        return 1
    actual_hash = file_sha256(pdf_path)
    if actual_hash != source["content_sha256"]:
        print("catalog SHA-256 no longer matches the manifest", file=sys.stderr)
        return 1
    output_path = args.out_dir / f"{actual_hash}.json"
    if args.check:
        if not output_path.is_file():
            print(f"index is missing: {output_path}", file=sys.stderr)
            return 1
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        valid = (
            payload.get("content_sha256") == actual_hash
            and payload.get("catalog_id") == args.catalog_id
            and len(payload.get("pages") or []) == source["page_count"]
        )
        if not valid:
            print("catalog index is stale or incomplete", file=sys.stderr)
            return 1
        print(json.dumps({"status": "valid", "path": str(output_path), "pages": len(payload["pages"])}, indent=2))
        return 0

    reader = PdfReader(str(pdf_path))
    pages = []
    for page_number, page in enumerate(reader.pages, 1):
        raw_text = page.extract_text() or ""
        pages.append(
            {
                "pdf_page": page_number,
                "text": raw_text,
                "normalized_text": normalize_text(raw_text),
            }
        )
    payload = {
        "schema_version": 1,
        "catalog_id": source["catalog_id"],
        "source_id": source["source_id"],
        "content_sha256": actual_hash,
        "page_count": len(pages),
        "pages": pages,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "built", "path": str(output_path), "pages": len(pages)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
