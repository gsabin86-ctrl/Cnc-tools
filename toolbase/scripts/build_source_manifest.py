#!/usr/bin/env python3
"""Inventory local manufacturer catalogs without publishing the catalog files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / "toolbase" / "catalogs" / "registry.json"
DEFAULT_OUTPUT = REPO_ROOT / "toolbase" / "data" / "source_documents.json"
MANUFACTURER_ALIASES = {
    "Mitsubishi": "Mitsubishi Materials",
    "Sandvik": "Sandvik Coromant",
    "Horn": "PH Horn",
}
IN_SCOPE_MANUFACTURERS = {
    "Iscar",
    "Kennametal",
    "Mitsubishi Materials",
    "PH Horn",
    "Sandvik Coromant",
    "Tungaloy",
}
PATH_MANUFACTURER_OVERRIDES = {
    "catalogs/kennametal/Latest cutting tools 26-1.pdf": "Sandvik Coromant",
}


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_layer_summary(reader: PdfReader) -> dict[str, Any]:
    indices = sorted({0, min(2, len(reader.pages) - 1), len(reader.pages) // 2, len(reader.pages) - 1})
    samples: list[dict[str, int]] = []
    for index in indices:
        try:
            characters = len(reader.pages[index].extract_text() or "")
        except Exception:
            characters = -1
        samples.append({"pdf_page": index + 1, "characters": characters})
    usable = sum(max(sample["characters"], 0) for sample in samples) >= 400
    return {"status": "usable" if usable else "weak", "samples": samples}


def catalog_year(entry: dict[str, Any], path: Path) -> str | None:
    explicit = str(entry.get("catalog_year") or "").strip()
    if explicit:
        return explicit
    years = re.findall(r"\b(?:19|20)\d{2}\b", path.name)
    return "-".join(dict.fromkeys(years)) if years else None


def build_manifest(registry_path: Path, retrieved_at: str) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    documents: list[dict[str, Any]] = []
    for entry in registry.get("catalogs") or []:
        manufacturer = MANUFACTURER_ALIASES.get(entry.get("manufacturer"), entry.get("manufacturer"))
        relative = str(entry.get("file_path") or "").replace("\\", "/")
        manufacturer = PATH_MANUFACTURER_OVERRIDES.get(relative, manufacturer)
        if manufacturer not in IN_SCOPE_MANUFACTURERS or "/split_parts/" in f"/{relative}":
            continue
        path = (REPO_ROOT / relative).resolve()
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            continue
        content_hash = sha256(path)
        reader = PdfReader(path)
        year = catalog_year(entry, path)
        document = {
            "catalog_id": entry["catalog_id"],
            "source_id": stable_id("source", entry["catalog_id"]),
            "manufacturer": manufacturer,
            "title": entry.get("title") or path.stem,
            "source_type": entry.get("source_type") or "manufacturer_catalog",
            "local_path": path.relative_to(REPO_ROOT).as_posix(),
            "url": entry.get("official_url"),
            "content_sha256": content_hash,
            "file_size_bytes": path.stat().st_size,
            "page_count": len(reader.pages),
            "document_edition": year or "edition unknown",
            "edition_evidence": (
                f"Year {year} recorded from registry or filename."
                if year
                else "No edition text recorded; resolve during family review."
            ),
            "retrieved_at": retrieved_at,
            "text_layer": text_layer_summary(reader),
            "review_status": "needs_review",
            "duplicate_paths": [],
        }
        documents.append(document)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        grouped.setdefault(document["content_sha256"], []).append(document)
    deduplicated: list[dict[str, Any]] = []
    for variants in grouped.values():
        def preference(document: dict[str, Any]) -> tuple[int, int, str]:
            folder_token = {
                "Mitsubishi Materials": "mitsubishi",
                "PH Horn": "ph horn",
                "Sandvik Coromant": "sandvik",
            }.get(document["manufacturer"], document["manufacturer"].casefold())
            path = document["local_path"].casefold()
            return (int(folder_token in path), int(" (1).pdf" not in path), path)

        canonical = max(variants, key=preference)
        canonical["duplicate_paths"] = sorted(
            item["local_path"] for item in variants if item is not canonical
        )
        deduplicated.append(canonical)
    documents = sorted(
        deduplicated,
        key=lambda item: (item["manufacturer"].casefold(), item["title"].casefold(), item["local_path"]),
    )
    return {
        "schema_version": 1,
        "generated_at": retrieved_at,
        "scope": "Local official catalogs relevant to manufacturers already present in the 1,222-tool seed.",
        "documents": documents,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_manifest(args.registry.resolve(), args.retrieved_at)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = args.out.resolve()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"STALE: {output}")
        print(f"CURRENT: {output} ({len(payload['documents'])} documents)")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(output)
    print(f"WROTE: {output} ({len(payload['documents'])} documents)")


if __name__ == "__main__":
    main()
