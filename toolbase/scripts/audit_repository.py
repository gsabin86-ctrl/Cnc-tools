#!/usr/bin/env python3
"""Read-only integrity audit for repository layout, data bindings, and sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
TOOLBASE = REPO / "toolbase"
DATA = TOOLBASE / "data"

REQUIRED_PATHS = (
    REPO / "README.md",
    TOOLBASE / "README.md",
    TOOLBASE / "schema.sql",
    TOOLBASE / "scripts" / "build.py",
    TOOLBASE / "data" / "tools.jsonl",
    TOOLBASE / "data" / "legacy_relationships.jsonl",
    TOOLBASE / "data" / "source_documents.json",
    REPO / "docs" / "v3" / "index.html",
    REPO / "docs" / "v3" / "app.js",
    REPO / "docs" / "v3" / "data" / "catalog-index.json",
    REPO / "docs" / "v3" / "data" / "catalog-details.json",
    REPO / "docs" / "v3" / "data" / "toolbase.sqlite",
    REPO / "legacy" / "README.md",
    REPO / "legacy" / "v1-v2" / "databases" / "db.sqlite",
    REPO / "legacy" / "v1-v2" / "databases" / "db_v2.sqlite",
)

ALLOWED_DATABASES = {
    "docs/v3/data/toolbase.sqlite",
    "toolbase/build/toolbase.sqlite",
    "legacy/v1-v2/databases/db.sqlite",
    "legacy/v1-v2/databases/db_v2.sqlite",
}

STALE_REFERENCES = (
    "docs/catalog-registry.json",
    "docs/catalog-registry.schema.json",
    "docs/db.sqlite",
    "docs/db_v2.sqlite",
    "docs/scripts/",
    "data/tools.json",
)

TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".sql"}


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def audit(require_source_library: bool = False) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    missing_required = [relative(path) for path in REQUIRED_PATHS if not path.exists()]
    if missing_required:
        errors.append(
            issue(
                "missing_required_paths",
                "Required active or preserved paths are missing.",
                paths=missing_required,
            )
        )

    manifest = load_json(DATA / "manifest.json")
    jsonl_paths = {
        "tools": DATA / "tools.jsonl",
        "legacy_relationships": DATA / "legacy_relationships.jsonl",
        "catalog_claims": DATA / "catalog_claims.jsonl",
    }
    canonical_counts: dict[str, int] = {}
    for name, path in jsonl_paths.items():
        canonical_counts[name] = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        expected = manifest["counts"].get(name)
        if canonical_counts[name] != expected:
            errors.append(
                issue(
                    "canonical_row_count",
                    "Canonical JSONL row count does not match the extraction manifest.",
                    dataset=name,
                    expected=expected,
                    actual=canonical_counts[name],
                )
            )

    legacy_dir = REPO / "legacy" / "v1-v2" / "databases"
    legacy_hashes: dict[str, str] = {}
    for source_name, metadata in manifest["source_databases"].items():
        path = legacy_dir / metadata["file"]
        if not path.is_file():
            continue
        actual_hash = sha256(path)
        legacy_hashes[source_name] = actual_hash
        if actual_hash != metadata["sha256"]:
            errors.append(
                issue(
                    "legacy_database_hash",
                    "Preserved source database does not match the extraction manifest.",
                    database=relative(path),
                    expected=metadata["sha256"],
                    actual=actual_hash,
                )
            )

    source_manifest = load_json(DATA / "source_documents.json")
    documents = source_manifest.get("documents", [])
    duplicate_fields: dict[str, list[str]] = {}
    for field in ("catalog_id", "source_id", "local_path"):
        seen: set[str] = set()
        duplicates: set[str] = set()
        for document in documents:
            value = document.get(field)
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        if duplicates:
            duplicate_fields[field] = sorted(duplicates)
    if duplicate_fields:
        errors.append(
            issue(
                "duplicate_source_documents",
                "Manufacturer source identifiers and paths must be unique.",
                duplicates=duplicate_fields,
            )
        )

    missing_sources: list[str] = []
    source_hash_mismatches: list[dict[str, str]] = []
    source_size_mismatches: list[dict[str, Any]] = []
    present_source_bytes = 0
    for document in documents:
        local_path = document.get("local_path")
        if not local_path:
            continue
        path = REPO / local_path
        if not path.is_file():
            missing_sources.append(local_path)
            continue
        present_source_bytes += path.stat().st_size
        expected_size = document.get("file_size_bytes")
        if expected_size is not None and path.stat().st_size != expected_size:
            source_size_mismatches.append(
                {"path": local_path, "expected": expected_size, "actual": path.stat().st_size}
            )
        expected_hash = document.get("content_sha256")
        if expected_hash:
            actual_hash = sha256(path)
            if actual_hash != expected_hash:
                source_hash_mismatches.append(
                    {"path": local_path, "expected": expected_hash, "actual": actual_hash}
                )
    if source_size_mismatches:
        errors.append(
            issue(
                "source_size_mismatch",
                "Manufacturer source file size differs from its manifest.",
                files=source_size_mismatches,
            )
        )
    if source_hash_mismatches:
        errors.append(
            issue(
                "source_hash_mismatch",
                "Manufacturer source file content differs from its manifest.",
                files=source_hash_mismatches,
            )
        )
    if missing_sources:
        target = errors if require_source_library else warnings
        target.append(
            issue(
                "source_library_incomplete",
                "Manufacturer files are not present locally; metadata and hashes remain available.",
                count=len(missing_sources),
                paths=sorted(missing_sources),
            )
        )

    import_bindings = 0
    for packet_path in sorted((DATA / "reviewed_imports").glob("*.json")):
        packet = load_json(packet_path)
        for path_key, hash_key in (
            ("proposal_path", "proposal_sha256"),
            ("review_ledger_path", "review_ledger_sha256"),
        ):
            bound_path_text = packet.get(path_key)
            expected_hash = packet.get(hash_key)
            if not bound_path_text or not expected_hash:
                errors.append(
                    issue(
                        "review_binding_missing",
                        "Approved import is missing a bound path or SHA-256.",
                        packet=relative(packet_path),
                        path_key=path_key,
                        hash_key=hash_key,
                    )
                )
                continue
            bound_path = REPO / bound_path_text
            if not bound_path.is_file():
                errors.append(
                    issue(
                        "review_binding_path",
                        "Approved import points to a missing proposal or review ledger.",
                        packet=relative(packet_path),
                        path=bound_path_text,
                    )
                )
                continue
            actual_hash = sha256(bound_path)
            import_bindings += 1
            if actual_hash != expected_hash:
                errors.append(
                    issue(
                        "review_binding_hash",
                        "Approved import hash binding is broken.",
                        packet=relative(packet_path),
                        path=bound_path_text,
                        expected=expected_hash,
                        actual=actual_hash,
                    )
                )

    unexpected_databases = sorted(
        relative(path)
        for path in REPO.rglob("*.sqlite")
        if relative(path) not in ALLOWED_DATABASES
    )
    if unexpected_databases:
        warnings.append(
            issue(
                "unexpected_databases",
                "SQLite files exist outside the canonical build, deployment, or preserved legacy locations.",
                paths=unexpected_databases,
            )
        )

    stale_hits: list[dict[str, Any]] = []
    scan_roots = (REPO / "README.md", TOOLBASE, REPO / "docs" / "v3")
    for scan_root in scan_roots:
        paths = [scan_root] if scan_root.is_file() else scan_root.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if "data" in path.relative_to(REPO).parts and path.suffix.lower() == ".json":
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                normalized = line.replace("\\", "/")
                for stale in STALE_REFERENCES:
                    if stale in normalized:
                        stale_hits.append(
                            {"path": relative(path), "line": line_number, "reference": stale}
                        )
    if stale_hits:
        errors.append(
            issue(
                "stale_active_references",
                "Maintained files still reference superseded repository paths.",
                hits=stale_hits,
            )
        )

    app_js = (REPO / "docs" / "v3" / "app.js").read_text(encoding="utf-8")
    viewer_contract = {
        "loads_index": "data/catalog-index.json" in app_js,
        "loads_details": "data/catalog-details.json" in app_js,
        "loads_full_projection": "data/catalog.json" in app_js,
    }
    if not viewer_contract["loads_index"] or not viewer_contract["loads_details"]:
        errors.append(
            issue(
                "viewer_data_contract",
                "The viewer must load the search index and on-demand detail projection.",
                contract=viewer_contract,
            )
        )
    full_projection = REPO / "docs" / "v3" / "data" / "catalog.json"
    if full_projection.exists() and not viewer_contract["loads_full_projection"]:
        warnings.append(
            issue(
                "redundant_full_projection",
                "catalog.json is generated and tracked but the viewer does not load it.",
                path=relative(full_projection),
                bytes=full_projection.stat().st_size,
            )
        )

    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status": status,
        "repository": str(REPO),
        "canonical_counts": canonical_counts,
        "source_documents": {
            "registered": len(documents),
            "present": len(documents) - len(missing_sources),
            "missing": len(missing_sources),
            "present_bytes": present_source_bytes,
        },
        "legacy_database_hashes": legacy_hashes,
        "approved_import_hash_bindings_checked": import_bindings,
        "viewer_contract": viewer_contract,
        "errors": errors,
        "warnings": warnings,
    }


def human(report: dict[str, Any]) -> str:
    sources = report["source_documents"]
    lines = [
        f"Repository: {report['repository']}",
        f"Status: {report['status']}",
        "Canonical rows: "
        + ", ".join(f"{name}={count}" for name, count in report["canonical_counts"].items()),
        f"Manufacturer sources: {sources['present']}/{sources['registered']} present locally",
        f"Approved import hash bindings checked: {report['approved_import_hash_bindings_checked']}",
    ]
    if report["errors"]:
        lines.append("Errors:")
        lines.extend(f"  - {item['code']}: {item['message']}" for item in report["errors"])
    if report["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"  - {item['code']}: {item['message']}" for item in report["warnings"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-source-library",
        action="store_true",
        help="Fail when any registered local manufacturer document is unavailable.",
    )
    args = parser.parse_args()
    report = audit(require_source_library=args.require_source_library)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else human(report))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
