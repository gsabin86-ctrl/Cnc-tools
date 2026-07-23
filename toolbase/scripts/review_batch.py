#!/usr/bin/env python3
"""Validate, scaffold, and compile auditable tool review batches.

Proposal schema 2 is deliberately review-only.  The public database build reads
only compiled packets in ``toolbase/data/reviewed_imports``; this script refuses
to compile a packet until every proposal row has a terminal human decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from copy import deepcopy
from html.parser import HTMLParser
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "docs" / "v3" / "data" / "toolbase.sqlite"
ALLOWED_DECISIONS = {
    "pending",
    "approved",
    "approved_with_corrections",
    "rejected",
    "quarantined",
}
TERMINAL_DECISIONS = ALLOWED_DECISIONS - {"pending"}
VERIFICATION_BY_SOURCE = {
    "manufacturer_catalog": "catalog_verified",
    "manufacturer_product_page": "manufacturer_verified",
    "manufacturer_technical_guide": "manufacturer_verified",
}
SUPPORTED_ARTIFACT_FORMATS = frozenset(
    {"pdf", "json", "structured_json", "html", "structured_html"}
)
# Exact proposal/ledger hashes for schema-2 reviews released before artifact_format
# became mandatory. Proposal validation can recognize the proposal hash alone, but
# corrected_proposed payloads receive legacy handling only when both immutable
# files match. New or changed ledgers therefore use the current rules.
LEGACY_SCHEMA_2_REVIEW_PAIRS = frozenset(
    {
        (
            "be70c619ef8e892a47ebc3f93176f8cf79ee7c7878e8c3ae18e94eb766f1fc3d",
            "f90a8e29e0f30d937e1aa49bcdcdd60d571900cdbaf20a6e396949af265b450d",
        ),
        (
            "364ca89cf0ba7de6401d4c3356bd78d52efce1efaf6f73425d5885faa20c2350",
            "1ce2af52a15d38443b370c77045bc41d6e4ee1d032b5c4574be670451c50113f",
        ),
        (
            "ce80b6d73cff47071779083a71a491c65f423f85c0e9914995be0c74222c1d67",
            "383d051a2d3751f026396f42b78875d20384785e99ed1e6c09974d7bb80d4933",
        ),
        (
            "ddbcdc7490bfd94cea6321fd0d4cd820ea1577644bbc8c4d37d85f65266abb4f",
            "58d5a22975dea1b062422b73a12f41aedb733659c88c596fb150cff7f789c2e7",
        ),
        (
            "0d07f13577b952f6fc51428addec5adb91cfa13a3b07af628f0ec39a52c3bde9",
            "57572858be1b2ecf4a82cabd2b80d3acd154fb8eed91a8000646eb4e1945c95b",
        ),
        (
            "129a169e47ce86c0e94122c0612b12155b2aeffeed80d52d72e906b62634baf6",
            "54e639596b620834e98951bfbe070fbd94249d8c1d39ebc6dbd695464c82bd9e",
        ),
        (
            "b967bb4e30de896c7e88a2913f5fee539557ecbfcf7af138e2d4a54c0a0d795a",
            "a1f31dd238b9315a761f2d5c0d135e49c36ad0bd276e8f747f2dd7a84dd987e3",
        ),
        (
            "7e6db66fafc6fd4fd459f3dbcdbcba7772fc4ab632a45ab9d8c407f24e2c4d4c",
            "865025bf865eaba84b4cfb17c8d7ab361934093840860dba1a491e71fc0509a7",
        ),
    }
)
LEGACY_SCHEMA_2_PROPOSAL_HASHES = frozenset(
    proposal_sha256 for proposal_sha256, _ in LEGACY_SCHEMA_2_REVIEW_PAIRS
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(serialized.encode("utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_local_artifact_format(
    path: Path,
    artifact_format: str,
    context: str,
) -> list[str]:
    if artifact_format in {"json", "structured_json"}:
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return [
                f"{context}: declared {artifact_format} but local source is not valid JSON"
            ]
        return []

    with path.open("rb") as stream:
        signature = stream.read(8192)
    if artifact_format == "pdf":
        if not signature.startswith(b"%PDF-"):
            return [f"{context}: declared pdf but local source has no PDF signature"]
        return []

    if artifact_format in {"html", "structured_html"}:
        if signature.startswith(b"%PDF-"):
            return [
                f"{context}: declared {artifact_format} but local source has a PDF signature"
            ]
        decoded = signature.decode("utf-8", errors="replace").casefold()
        if "<!doctype html" not in decoded and "<html" not in decoded:
            return [
                f"{context}: declared {artifact_format} but local source is not recognizable HTML"
            ]
    return []


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for encoded_token in pointer.split("/")[1:]:
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(pointer)
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                raise KeyError(pointer)
            index = int(token)
            if index >= len(current):
                raise KeyError(pointer)
            current = current[index]
        else:
            raise KeyError(pointer)
    return current


def json_contains(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and json_contains(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(json_contains(candidate, item) for candidate in actual)
            for item in expected
        )
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def strict_json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def validate_json_value_claims(
    item: dict[str, Any],
    group: str,
    item_context: str,
    evidence: dict[str, Any],
    default_source_id: str,
    json_documents: dict[str, Any],
) -> list[str]:
    claims = evidence.get("value_claims")
    errors: list[str] = []
    if not isinstance(claims, dict):
        if claims is not None:
            errors.append(f"{item_context}: value_claims must be an object")
        claims = {}

    excluded_fields = {
        "tool_updates": {"evidence"},
        "facts": {"fact_key", "original_key", "evidence"},
        "grade_options": {"option_kind", "is_primary", "evidence"},
        "material_recommendations": {"notes", "evidence"},
        "cutting_profiles": {"notes", "evidence"},
    }[group]
    required_fields = {
        field
        for field, value in item.items()
        if field not in excluded_fields and value is not None
    }
    for field in sorted(required_fields - set(claims)):
        errors.append(f"{item_context}: missing value claim for {field}")

    for field, claim in claims.items():
        claim_context = f"{item_context}: value claim for {field}"
        if field not in item:
            errors.append(f"{claim_context} names a missing proposed field")
            continue
        if not isinstance(claim, dict):
            errors.append(f"{claim_context} must be an object")
            continue
        claim_source_id = claim.get("source_id") or default_source_id
        source_document = json_documents.get(claim_source_id)
        if source_document is None:
            errors.append(f"{claim_context} source is not a verified JSON artifact")
            continue

        selectors = [
            key for key in ("source_pointer", "source_values", "source_absence")
            if key in claim
        ]
        if len(selectors) != 1:
            errors.append(f"{claim_context} must use exactly one source selector")
            continue
        selector = selectors[0]

        if selector == "source_pointer":
            pointer = claim.get("source_pointer")
            try:
                actual = resolve_json_pointer(source_document, pointer)
            except KeyError:
                errors.append(f"{claim_context} cannot resolve JSON pointer {pointer!r}")
                continue
            if not strict_json_equal(actual, item[field]):
                errors.append(f"{claim_context} does not match proposed value")
            continue

        normalization = claim.get("normalization")
        if not isinstance(normalization, str) or not normalization.strip():
            errors.append(f"{claim_context} requires a normalization rationale")
        if "normalized_value" not in claim:
            errors.append(f"{claim_context} requires normalized_value")
        elif not strict_json_equal(claim["normalized_value"], item[field]):
            errors.append(f"{claim_context} normalized_value does not match proposed value")

        if selector == "source_values":
            source_values = claim.get("source_values")
            if not isinstance(source_values, dict) or not source_values:
                errors.append(f"{claim_context} source_values must be a nonempty object")
                continue
            for pointer, expected in source_values.items():
                try:
                    actual = resolve_json_pointer(source_document, pointer)
                except KeyError:
                    errors.append(f"{claim_context} cannot resolve JSON pointer {pointer!r}")
                    continue
                if not strict_json_equal(actual, expected):
                    errors.append(f"{claim_context} source value at {pointer} does not match artifact")
        else:
            source_absence = claim.get("source_absence")
            if not isinstance(source_absence, list) or not source_absence:
                errors.append(f"{claim_context} source_absence must be a nonempty list")
                continue
            for pointer in source_absence:
                try:
                    resolve_json_pointer(source_document, pointer)
                except KeyError:
                    continue
                errors.append(f"{claim_context} expected JSON pointer {pointer!r} to be absent")

    return errors


class HtmlFragmentTextExtractor(HTMLParser):
    VOID_ELEMENTS = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    )

    def __init__(self, target_id: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.found = target_id is None
        self.active_depth = 1 if target_id is None else 0
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        is_void = tag.casefold() in self.VOID_ELEMENTS
        if self.active_depth:
            if not is_void:
                self.active_depth += 1
            return
        if dict(attrs).get("id") == self.target_id:
            self.found = True
            if not is_void:
                self.active_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.active_depth and dict(attrs).get("id") == self.target_id:
            self.found = True

    def handle_endtag(self, tag: str) -> None:
        if self.target_id is not None and self.active_depth:
            self.active_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.active_depth:
            self.text.append(data)


def extract_html_text(html_text: str, target_id: str | None = None) -> tuple[bool, str]:
    parser = HtmlFragmentTextExtractor(target_id)
    parser.feed(html_text)
    parser.close()
    return parser.found, " ".join(" ".join(parser.text).split())


def validate_structured_assertions(
    proposed: dict[str, Any],
    context: str,
    source_by_id: dict[str, dict[str, Any]],
    json_documents: dict[str, Any],
    html_documents: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    tool_updates = proposed.get("tool_updates")
    if isinstance(tool_updates, dict) and tool_updates:
        groups.append(("tool_updates", [tool_updates]))
    groups.extend(
        (group, proposed.get(group) or [])
        for group in ("facts", "grade_options", "material_recommendations", "cutting_profiles")
    )
    for group, items in groups:
        for item_index, item in enumerate(items, 1):
            item_context = (
                f"{context} tool_updates"
                if group == "tool_updates"
                else f"{context} {group}[{item_index}]"
            )
            evidence = evidence_for(item)
            source_id = evidence.get("source_id") or item.get("source_id")
            source = source_by_id.get(source_id) or {}
            artifact_format = source.get("artifact_format")
            locator = evidence.get("source_page_ref")
            raw_excerpt = evidence.get("source_raw_text")

            if artifact_format in {"json", "structured_json"} and source_id in json_documents:
                try:
                    located = resolve_json_pointer(json_documents[source_id], locator)
                except KeyError:
                    errors.append(
                        f"{item_context}: JSON pointer does not resolve: {locator}"
                    )
                    continue
                try:
                    excerpt = json.loads(raw_excerpt)
                except (TypeError, json.JSONDecodeError):
                    errors.append(f"{item_context}: source_raw_text must be valid JSON")
                    continue
                if not json_contains(located, excerpt):
                    errors.append(
                        f"{item_context}: source_raw_text is not contained at JSON pointer {locator}"
                    )
                errors.extend(
                    validate_json_value_claims(
                        item, group, item_context, evidence, source_id, json_documents
                    )
                )

            if artifact_format in {"html", "structured_html"} and source_id in html_documents:
                html_text = html_documents[source_id]
                if not isinstance(locator, str) or not locator.startswith("#") or len(locator) == 1:
                    errors.append(
                        f"{item_context}: HTML locator must be a nonempty id fragment"
                    )
                    continue
                element_id = locator[1:]
                fragment_found, fragment_text = extract_html_text(html_text, element_id)
                if not fragment_found:
                    errors.append(f"{item_context}: HTML id locator does not resolve: {locator}")
                    continue
                normalized_html = " ".join(html_text.split())
                normalized_excerpt = " ".join(str(raw_excerpt or "").split())
                if not normalized_excerpt or normalized_excerpt not in normalized_html:
                    errors.append(
                        f"{item_context}: source_raw_text is not contained in the HTML snapshot"
                    )
                    continue
                _, excerpt_text = extract_html_text(str(raw_excerpt))
                if not excerpt_text or excerpt_text not in fragment_text:
                    errors.append(
                        f"{item_context}: source_raw_text is not contained in HTML fragment {locator}"
                    )
    return errors


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def evidence_for(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("evidence")
    return value if isinstance(value, dict) else {}


def compiled_source_page_ref(evidence: dict[str, Any]) -> str | None:
    page = evidence.get("pdf_page")
    if page is not None:
        return f"PDF page {page}"
    return evidence.get("source_page_ref")


def validate_proposed_payload(
    proposed: Any,
    context: str,
    source_by_id: dict[str, dict[str, Any]],
    *,
    allow_legacy_artifact_format: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(proposed, dict):
        return [f"{context}: proposed object is required"]

    assertion_groups = (
        "facts",
        "grade_options",
        "material_recommendations",
        "cutting_profiles",
    )
    if not any(proposed.get(group) for group in assertion_groups):
        errors.append(f"{context}: no auditable assertions were proposed")
    validation_groups: list[tuple[str, list[dict[str, Any]]]] = [
        (group, proposed.get(group) or []) for group in assertion_groups
    ]
    tool_updates = proposed.get("tool_updates")
    if (
        not allow_legacy_artifact_format
        and isinstance(tool_updates, dict)
        and tool_updates
    ):
        validation_groups.append(("tool_updates", [tool_updates]))
    for group, items in validation_groups:
        for item_index, item in enumerate(items, 1):
            item_context = (
                f"{context} tool_updates"
                if group == "tool_updates"
                else f"{context} {group}[{item_index}]"
            )
            if group == "grade_options" and "manufacturer_material_number" in item:
                material_number = item.get("manufacturer_material_number")
                if not isinstance(material_number, str) or not material_number.strip():
                    errors.append(
                        f"{item_context}: manufacturer_material_number must be a nonempty string"
                    )
            evidence = evidence_for(item)
            source_id = evidence.get("source_id") or item.get("source_id")
            if source_id not in source_by_id:
                errors.append(f"{item_context}: evidence source is missing from proposal")
                continue
            page = evidence.get("pdf_page")
            page_ref = evidence.get("source_page_ref")
            source = source_by_id[source_id]
            if source.get("local_path"):
                artifact_format = source.get("artifact_format")
                has_page_ref = isinstance(page_ref, str) and bool(page_ref.strip())
                if not artifact_format and not allow_legacy_artifact_format:
                    errors.append(f"{item_context}: local source requires artifact_format")
                    continue
                if artifact_format and artifact_format not in SUPPORTED_ARTIFACT_FORMATS:
                    errors.append(
                        f"{item_context}: unsupported artifact_format {artifact_format!r}"
                    )
                    continue
                if artifact_format == "pdf":
                    page_count = source.get("page_count")
                    if page_ref is not None or page is None:
                        errors.append(
                            f"{item_context}: PDF source requires pdf_page and forbids source_page_ref"
                        )
                    elif not isinstance(page, int) or isinstance(page, bool):
                        errors.append(f"{item_context}: pdf_page must be an integer")
                    elif (
                        not isinstance(page_count, int)
                        or isinstance(page_count, bool)
                        or page_count < 1
                        or not 1 <= page <= page_count
                    ):
                        errors.append(f"{item_context}: pdf_page is outside the source")
                elif artifact_format:
                    if page is not None:
                        errors.append(f"{item_context}: structured source must not use pdf_page")
                    if not has_page_ref:
                        errors.append(f"{item_context}: structured source requires source_page_ref")
                else:
                    has_page = page is not None
                    if has_page and has_page_ref:
                        errors.append(f"{item_context}: use either pdf_page or source_page_ref, not both")
                    elif not has_page and not has_page_ref:
                        errors.append(
                            f"{item_context}: pdf_page or source_page_ref is required for a catalog assertion"
                        )
                    elif has_page:
                        if not isinstance(page, int) or isinstance(page, bool):
                            errors.append(f"{item_context}: pdf_page must be an integer")
                        elif not 1 <= page <= int(source.get("page_count") or 0):
                            errors.append(f"{item_context}: pdf_page is outside the source")
            if not evidence.get("source_table_ref"):
                errors.append(f"{item_context}: source_table_ref is required")
            if not evidence.get("source_raw_text"):
                errors.append(f"{item_context}: source_raw_text is required")

    for profile_index, profile in enumerate(proposed.get("cutting_profiles") or [], 1):
        context_profile = f"{context} cutting_profiles[{profile_index}]"
        for key in (
            "source_part_number",
            "source_grade",
            "source_geometry",
            "source_chipbreaker",
            "source_material_label",
            "iso_material_group",
            "operation_type",
            "cut_condition",
        ):
            if not profile.get(key):
                errors.append(f"{context_profile}: missing {key}")
        for prefix in ("surface_speed", "feed", "depth_of_cut"):
            minimum = profile.get(f"{prefix}_min")
            maximum = profile.get(f"{prefix}_max")
            unit = profile.get(f"{prefix}_unit")
            if minimum is None and maximum is None:
                continue
            if minimum is not None and not isinstance(minimum, (int, float)):
                errors.append(f"{context_profile}: {prefix} minimum must be numeric when stated")
            if maximum is not None and not isinstance(maximum, (int, float)):
                errors.append(f"{context_profile}: {prefix} maximum must be numeric when stated")
            if (
                isinstance(minimum, (int, float))
                and isinstance(maximum, (int, float))
                and minimum > maximum
            ):
                errors.append(f"{context_profile}: {prefix} minimum exceeds maximum")
            if not unit:
                errors.append(f"{context_profile}: {prefix}_unit is required")

        speed_start = profile.get("surface_speed_start")
        speed_min = profile.get("surface_speed_min")
        speed_max = profile.get("surface_speed_max")
        if speed_start is not None and not (
            isinstance(speed_min, (int, float))
            and isinstance(speed_max, (int, float))
            and speed_min <= speed_start <= speed_max
        ):
            errors.append(f"{context_profile}: surface speed start is outside the range")
    return errors


def validate_proposal(proposal_path: Path, database_path: Path) -> tuple[dict[str, Any], list[str]]:
    proposal = read_json(proposal_path)
    allow_legacy_artifact_format = (
        file_sha256(proposal_path) in LEGACY_SCHEMA_2_PROPOSAL_HASHES
    )
    errors: list[str] = []
    if proposal.get("schema_version") != 2:
        errors.append("proposal: schema_version must be 2")
    if proposal.get("status") != "source_extracted":
        errors.append("proposal: status must remain source_extracted")
    if proposal.get("import_allowed") is not False:
        errors.append("proposal: import_allowed must be false")
    for key in ("proposal_id", "title", "created_at"):
        if not proposal.get(key):
            errors.append(f"proposal: missing {key}")

    sources = proposal.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("proposal: sources must contain at least one source")
        sources = []
    source_by_id: dict[str, dict[str, Any]] = {}
    json_documents: dict[str, Any] = {}
    html_documents: dict[str, str] = {}
    for index, source in enumerate(sources, 1):
        context = f"source {index}"
        source_id = source.get("source_id")
        if not source_id:
            errors.append(f"{context}: missing source_id")
            continue
        if source_id in source_by_id:
            errors.append(f"{context}: duplicate source_id {source_id}")
        source_by_id[source_id] = source
        for key in ("manufacturer", "title", "source_type", "content_sha256"):
            if not source.get(key):
                errors.append(f"{context}: missing {key}")
        local = repo_path(source.get("local_path"))
        if local:
            if not local.is_file():
                errors.append(f"{context}: local source is missing: {display_path(local)}")
            else:
                actual_hash = file_sha256(local)
                if source.get("content_sha256") != actual_hash:
                    errors.append(f"{context}: SHA-256 does not match local source")
                artifact_format = source.get("artifact_format")
                if not artifact_format:
                    if not allow_legacy_artifact_format:
                        errors.append(f"{context}: local source requires artifact_format")
                elif artifact_format not in SUPPORTED_ARTIFACT_FORMATS:
                    errors.append(
                        f"{context}: unsupported artifact_format {artifact_format!r}"
                    )
                else:
                    artifact_errors = validate_local_artifact_format(
                        local, artifact_format, context
                    )
                    errors.extend(artifact_errors)
                    if not artifact_errors and artifact_format in {
                        "json",
                        "structured_json",
                    }:
                        json_documents[source_id] = json.loads(
                            local.read_text(encoding="utf-8-sig")
                        )
                    elif not artifact_errors and artifact_format in {
                        "html",
                        "structured_html",
                    }:
                        html_documents[source_id] = local.read_text(
                            encoding="utf-8", errors="replace"
                        )
        elif not source.get("url"):
            errors.append(f"{context}: a local_path or url is required")
        elif not allow_legacy_artifact_format:
            errors.append(
                f"{context}: new schema-2 source requires local_path for byte verification"
            )

    rows = proposal.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 25:
        errors.append("proposal: rows must contain 1 through 25 tools")
        rows = []
    row_ids: set[str] = set()
    tool_ids: set[str] = set()
    connection = sqlite3.connect(database_path)
    try:
        for index, row in enumerate(rows, 1):
            context = f"row {index}"
            row_id = row.get("proposal_row_id")
            lookup = row.get("tool_lookup") or {}
            tool_id = lookup.get("tool_id")
            if not row_id:
                errors.append(f"{context}: missing proposal_row_id")
            elif row_id in row_ids:
                errors.append(f"{context}: duplicate proposal_row_id {row_id}")
            row_ids.add(row_id)
            if not tool_id:
                errors.append(f"{context}: missing tool_lookup.tool_id")
                continue
            if tool_id in tool_ids:
                errors.append(f"{context}: duplicate tool id {tool_id}")
            tool_ids.add(tool_id)
            db_row = connection.execute(
                """
                SELECT t.id, m.name, t.component_type
                FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
                WHERE t.id=?
                """,
                (tool_id,),
            ).fetchone()
            if not db_row:
                errors.append(f"{context}: database tool does not exist: {tool_id}")
                continue
            if lookup.get("manufacturer") and lookup["manufacturer"] != db_row[1]:
                errors.append(f"{context}: manufacturer does not match database")
            if lookup.get("component_type") and lookup["component_type"] != db_row[2]:
                errors.append(f"{context}: component_type does not match database")

            proposed = row.get("proposed")
            errors.extend(
                validate_proposed_payload(
                    proposed,
                    context,
                    source_by_id,
                    allow_legacy_artifact_format=allow_legacy_artifact_format,
                )
            )
            if isinstance(proposed, dict) and not allow_legacy_artifact_format:
                errors.extend(
                    validate_structured_assertions(
                        proposed,
                        context,
                        source_by_id,
                        json_documents,
                        html_documents,
                    )
                )
    finally:
        connection.close()
    return proposal, errors


def _same_json_value(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int equality shortcut."""
    return json.dumps(
        left, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) == json.dumps(right, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_correction_contract(
    original: dict[str, Any], corrected: dict[str, Any], context: str
) -> list[str]:
    """Keep correction structure fixed while claims authorize mutable values.

    ``approved_with_corrections`` may change source-claimed values, but it must not
    add, remove, or rename publication paths. Fields deliberately excluded from
    value-claim coverage are immutable here. A structural correction requires a
    revised proposal and a new human review instead of a fail-open ledger edit.
    """
    errors: list[str] = []
    if set(original) != set(corrected):
        errors.append(f"{context}: corrected payload top-level fields differ from proposal")

    for field in (
        "aliases",
        "tags",
        "replace_fact_keys",
        "reject_grade_codes",
        "replace_material_recommendations",
    ):
        if not _same_json_value(original.get(field), corrected.get(field)):
            errors.append(f"{context}: immutable field {field} differs from proposal")

    original_updates = original.get("tool_updates")
    corrected_updates = corrected.get("tool_updates")
    if isinstance(original_updates, dict) and isinstance(corrected_updates, dict):
        original_fields = set(original_updates) - {"evidence"}
        corrected_fields = set(corrected_updates) - {"evidence"}
        if original_fields != corrected_fields:
            errors.append(f"{context}: tool_updates fields differ from proposal")
        original_value_fields = {
            field for field in original_fields if original_updates[field] is not None
        }
        corrected_value_fields = {
            field for field in corrected_fields if corrected_updates[field] is not None
        }
        if original_value_fields != corrected_value_fields:
            errors.append(
                f"{context}: tool_updates null/non-null fields differ from proposal"
            )
    elif type(original_updates) is not type(corrected_updates):
        errors.append(f"{context}: tool_updates structure differs from proposal")

    immutable_item_fields = {
        "facts": ("fact_key", "original_key"),
        "grade_options": ("option_kind", "is_primary"),
        "material_recommendations": ("notes",),
        "cutting_profiles": ("notes",),
    }
    for group, immutable_fields in immutable_item_fields.items():
        original_items = original.get(group)
        corrected_items = corrected.get(group)
        if not isinstance(original_items, list) or not isinstance(corrected_items, list):
            if type(original_items) is not type(corrected_items):
                errors.append(f"{context}: {group} structure differs from proposal")
            continue
        if len(original_items) != len(corrected_items):
            errors.append(f"{context}: {group} length differs from proposal")
            continue
        for item_index, (original_item, corrected_item) in enumerate(
            zip(original_items, corrected_items), 1
        ):
            item_context = f"{context} {group}[{item_index}]"
            if not isinstance(original_item, dict) or not isinstance(corrected_item, dict):
                if type(original_item) is not type(corrected_item):
                    errors.append(f"{item_context}: structure differs from proposal")
                continue
            original_fields = set(original_item) - {"evidence"}
            corrected_fields = set(corrected_item) - {"evidence"}
            if original_fields != corrected_fields:
                errors.append(f"{item_context}: fields differ from proposal")
            original_value_fields = {
                field for field in original_fields if original_item[field] is not None
            }
            corrected_value_fields = {
                field for field in corrected_fields if corrected_item[field] is not None
            }
            if original_value_fields != corrected_value_fields:
                errors.append(
                    f"{item_context}: null/non-null fields differ from proposal"
                )
            for field in immutable_fields:
                if not _same_json_value(
                    original_item.get(field), corrected_item.get(field)
                ):
                    errors.append(
                        f"{item_context}: immutable field {field} differs from proposal"
                    )
    return errors


def validate_ledger(
    proposal_path: Path,
    proposal: dict[str, Any],
    ledger_path: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not ledger_path.is_file():
        return None, [f"ledger: file not found: {display_path(ledger_path)}"]
    proposal_sha256 = file_sha256(proposal_path)
    ledger_sha256 = file_sha256(ledger_path)
    allow_legacy_artifact_format = (
        proposal_sha256,
        ledger_sha256,
    ) in LEGACY_SCHEMA_2_REVIEW_PAIRS
    ledger = read_json(ledger_path)
    if ledger.get("schema_version") != 2:
        errors.append("ledger: schema_version must be 2")
    if ledger.get("proposal_id") != proposal.get("proposal_id"):
        errors.append("ledger: proposal_id does not match")
    if ledger.get("proposal_sha256") != file_sha256(proposal_path):
        errors.append("ledger: proposal SHA-256 does not match")
    decisions = ledger.get("decisions")
    if not isinstance(decisions, list):
        errors.append("ledger: decisions must be a list")
        decisions = []
    expected_rows = {row["proposal_row_id"]: row for row in proposal.get("rows") or []}
    source_by_id = {source["source_id"]: source for source in proposal.get("sources") or []}
    json_documents: dict[str, Any] = {}
    html_documents: dict[str, str] = {}
    if not allow_legacy_artifact_format:
        for source_id, source in source_by_id.items():
            local = repo_path(source.get("local_path"))
            if not local or not local.is_file():
                continue
            artifact_format = source.get("artifact_format")
            if artifact_format in {"json", "structured_json"}:
                try:
                    json_documents[source_id] = json.loads(
                        local.read_text(encoding="utf-8-sig")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            elif artifact_format in {"html", "structured_html"}:
                html_documents[source_id] = local.read_text(
                    encoding="utf-8", errors="replace"
                )
    seen: set[str] = set()
    for index, decision in enumerate(decisions, 1):
        context = f"ledger decision {index}"
        row_id = decision.get("proposal_row_id")
        if row_id not in expected_rows:
            errors.append(f"{context}: unknown proposal row {row_id!r}")
            continue
        if row_id in seen:
            errors.append(f"{context}: duplicate decision for {row_id}")
        seen.add(row_id)
        expected_tool = (expected_rows[row_id].get("tool_lookup") or {}).get("tool_id")
        if decision.get("tool_id") != expected_tool:
            errors.append(f"{context}: tool_id does not match proposal")
        if decision.get("decision") not in ALLOWED_DECISIONS:
            errors.append(f"{context}: invalid decision {decision.get('decision')!r}")
        if decision.get("decision") in TERMINAL_DECISIONS:
            for key in ("reviewer", "decided_at"):
                if not decision.get(key):
                    errors.append(f"{context}: terminal decision requires {key}")
        if decision.get("decision") == "approved_with_corrections":
            corrected = decision.get("corrected_proposed")
            if not isinstance(corrected, dict):
                errors.append(f"{context}: corrected_proposed is required")
            else:
                errors.extend(
                    validate_proposed_payload(
                        corrected,
                        f"{context} corrected_proposed",
                        source_by_id,
                        allow_legacy_artifact_format=allow_legacy_artifact_format,
                    )
                )
                if not allow_legacy_artifact_format:
                    original_proposed = expected_rows[row_id].get("proposed")
                    if isinstance(original_proposed, dict):
                        errors.extend(
                            validate_correction_contract(
                                original_proposed,
                                corrected,
                                f"{context} corrected_proposed",
                            )
                        )
                    errors.extend(
                        validate_structured_assertions(
                            corrected,
                            f"{context} corrected_proposed",
                            source_by_id,
                            json_documents,
                            html_documents,
                        )
                    )
        if decision.get("decision") in {"rejected", "quarantined"} and not decision.get("notes"):
            errors.append(f"{context}: rejection/quarantine reason is required")
    missing = sorted(set(expected_rows) - seen)
    if missing:
        errors.append(f"ledger: missing decisions for {', '.join(missing)}")
    complete = len(decisions) == len(expected_rows) and all(
        decision.get("decision") in TERMINAL_DECISIONS for decision in decisions
    )
    if ledger.get("status") == "complete" and not complete:
        errors.append("ledger: status cannot be complete while decisions are pending")
    if ledger.get("import_allowed") is True and not complete:
        errors.append("ledger: import_allowed cannot be true while decisions are pending")
    if complete and (ledger.get("status") != "complete" or ledger.get("import_allowed") is not True):
        errors.append("ledger: terminal decisions require status complete and import_allowed true")
    return ledger, errors


def assertion_evidence(
    item: dict[str, Any], source_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], str, str]:
    evidence = evidence_for(item)
    source_id = evidence.get("source_id") or item.get("source_id")
    source = source_by_id[source_id]
    verification = VERIFICATION_BY_SOURCE.get(source.get("source_type"), "source_extracted")
    evidence_status = (
        "manufacturer_claim" if verification == "manufacturer_verified" else "catalog_claim"
    )
    return evidence, verification, evidence_status


def compile_row(
    row: dict[str, Any],
    decision: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    proposed = deepcopy(
        decision.get("corrected_proposed")
        if decision["decision"] == "approved_with_corrections"
        else row["proposed"]
    )
    tool_id = row["tool_lookup"]["tool_id"]
    reviewer = decision["reviewer"]
    reviewed_at = decision["decided_at"]
    tool_updates = proposed.get("tool_updates") or {}
    tool_update_evidence = evidence_for(tool_updates)
    source_ids = {
        (evidence_for(item).get("source_id") or item.get("source_id"))
        for group in (
            "facts",
            "grade_options",
            "material_recommendations",
            "cutting_profiles",
        )
        for item in proposed.get(group) or []
        if evidence_for(item).get("source_id") or item.get("source_id")
    }
    if tool_update_evidence.get("source_id"):
        source_ids.add(tool_update_evidence["source_id"])
    compiled: dict[str, Any] = {
        "proposal_row_id": row["proposal_row_id"],
        "tool_id": tool_id,
        "decision": decision["decision"],
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "tool_updates": {
            "description": tool_updates.get("description"),
            "geometry": tool_updates.get("geometry") or row.get("current_summary", {}).get("geometry") or "unknown",
            "lifecycle_status": tool_updates.get("lifecycle_status") or "unknown",
            "evidence_status": "catalog_source",
            "grade": tool_updates.get("grade"),
            "grade_reviewed": "grade" in tool_updates,
            "chipbreaker": tool_updates.get("chipbreaker"),
            "chipbreaker_reviewed": "chipbreaker" in tool_updates,
        },
        "aliases": proposed.get("aliases") or [],
        "source_ids": sorted(source_ids),
        "tags": proposed.get("tags") or [],
        "replace_fact_keys": proposed.get("replace_fact_keys")
        or sorted({item["fact_key"] for item in proposed.get("facts") or []}),
        "facts": [],
        "grade_options": [],
        "reject_grade_codes": proposed.get("reject_grade_codes") or [],
        "replace_material_recommendations": bool(proposed.get("replace_material_recommendations")),
        "material_recommendations": [],
        "cutting_profiles": [],
    }
    if tool_update_evidence:
        compiled["tool_updates"].update(
            {
                "source_id": tool_update_evidence.get("source_id"),
                "source_page_ref": compiled_source_page_ref(tool_update_evidence),
                "source_table_ref": tool_update_evidence.get("source_table_ref"),
                "source_raw_text": tool_update_evidence.get("source_raw_text"),
                "extraction_method": tool_update_evidence.get("extraction_method")
                or "manual",
            }
        )
        if tool_update_evidence.get("value_claims") is not None:
            compiled["tool_updates"]["value_claims"] = tool_update_evidence[
                "value_claims"
            ]

    for item in proposed.get("facts") or []:
        evidence, verification, evidence_status = assertion_evidence(item, source_by_id)
        fact = {key: value for key, value in item.items() if key != "evidence"}
        fact.update(
            {
                "id": stable_id("fact", tool_id, item["fact_key"], item.get("value_text"), item.get("value_number"), reviewed_at),
                "original_key": item.get("original_key") or f"reviewed_{item['fact_key']}",
                "evidence_status": evidence_status,
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_ids": evidence.get("source_ids") or [evidence["source_id"]],
                "source_page_ref": compiled_source_page_ref(evidence),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
            }
        )
        if evidence.get("value_claims") is not None:
            fact["value_claims"] = evidence["value_claims"]
        compiled["facts"].append(fact)

    for item in proposed.get("grade_options") or []:
        evidence, verification, _ = assertion_evidence(item, source_by_id)
        option = {key: value for key, value in item.items() if key != "evidence"}
        option.update(
            {
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_page_ref": compiled_source_page_ref(evidence),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
            }
        )
        if evidence.get("value_claims") is not None:
            option["value_claims"] = evidence["value_claims"]
        compiled["grade_options"].append(option)

    for item in proposed.get("material_recommendations") or []:
        evidence, verification, evidence_status = assertion_evidence(item, source_by_id)
        recommendation = {key: value for key, value in item.items() if key != "evidence"}
        recommendation.update(
            {
                "id": stable_id("material", tool_id, item.get("grade_code"), item["iso_group"], item.get("material_subgroup"), reviewed_at),
                "evidence_status": evidence_status,
                "verification_status": verification,
                "source_id": evidence["source_id"],
                "source_ids": evidence.get("source_ids") or [evidence["source_id"]],
                "source_page_ref": compiled_source_page_ref(evidence),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
            }
        )
        if evidence.get("value_claims") is not None:
            recommendation["value_claims"] = evidence["value_claims"]
        compiled["material_recommendations"].append(recommendation)

    for item in proposed.get("cutting_profiles") or []:
        evidence, verification, _ = assertion_evidence(item, source_by_id)
        profile = {key: value for key, value in item.items() if key != "evidence"}
        profile.update(
            {
                "id": stable_id("cutting-profile", tool_id, item.get("source_grade"), item.get("material_subgroup"), item.get("cut_condition"), reviewed_at),
                "source_id": evidence["source_id"],
                "source_page_ref": compiled_source_page_ref(evidence),
                "source_table_ref": evidence.get("source_table_ref"),
                "source_raw_text": evidence.get("source_raw_text"),
                "extraction_method": evidence.get("extraction_method") or "manual",
                "verification_status": verification,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "notes": decision.get("notes"),
                "coolant_condition": item.get("coolant_condition") or "unknown",
            }
        )
        if evidence.get("value_claims") is not None:
            profile["value_claims"] = evidence["value_claims"]
        profile["evidence_sources"] = evidence.get("sources") or [
            {
                "source_id": evidence["source_id"],
                "evidence_role": role,
                "source_page_ref": profile["source_page_ref"],
                "source_table_ref": profile["source_table_ref"],
                "source_raw_text": profile["source_raw_text"],
                "extraction_method": profile["extraction_method"],
            }
            for role in ("identity", "geometry_parameters", "cutting_speed")
        ]
        compiled["cutting_profiles"].append(profile)
    return compiled


def scaffold(proposal_path: Path, output_path: Path) -> None:
    proposal = read_json(proposal_path)
    payload = {
        "schema_version": 2,
        "review_id": f"{proposal['proposal_id']}-review",
        "proposal_id": proposal["proposal_id"],
        "proposal_path": display_path(proposal_path),
        "proposal_sha256": file_sha256(proposal_path),
        "review_started_at": str(date.today()),
        "status": "pending",
        "review_completed_at": None,
        "import_allowed": False,
        "decisions": [
            {
                "proposal_row_id": row["proposal_row_id"],
                "tool_id": row["tool_lookup"]["tool_id"],
                "decision": "pending",
                "reviewer": None,
                "decided_at": None,
                "capture_method": "local_review_screen",
                "notes": None,
            }
            for row in proposal.get("rows") or []
        ],
    }
    write_json(output_path, payload)


def compile_packet(
    proposal_path: Path,
    proposal: dict[str, Any],
    ledger_path: Path,
    ledger: dict[str, Any],
    output_path: Path,
) -> None:
    decision_by_row = {item["proposal_row_id"]: item for item in ledger["decisions"]}
    source_by_id = {item["source_id"]: item for item in proposal["sources"]}
    primary_source = next(
        (item for item in proposal["sources"] if item.get("batch_role") == "primary_catalog"),
        proposal["sources"][0],
    )
    approved_rows: list[dict[str, Any]] = []
    quarantined_rows: list[dict[str, Any]] = []
    for row in proposal["rows"]:
        decision = decision_by_row[row["proposal_row_id"]]
        if decision["decision"] in {"approved", "approved_with_corrections"}:
            approved_rows.append(compile_row(row, decision, source_by_id))
        else:
            quarantined_rows.append(
                {
                    "proposal_row_id": row["proposal_row_id"],
                    "tool_id": row["tool_lookup"]["tool_id"],
                    "decision": decision["decision"],
                    "reason": decision["notes"],
                    "reviewer": decision["reviewer"],
                    "reviewed_at": decision["decided_at"],
                }
            )
    reviewed_at = ledger.get("review_completed_at") or max(
        item["decided_at"] for item in ledger["decisions"]
    )
    packet_sources = []
    review_sources = []
    for source in proposal["sources"]:
        packet_sources.append(
            {
                "id": source["source_id"],
                "source_type": source["source_type"],
                "title": source["title"],
                "url": source.get("url"),
                "local_path": source.get("local_path"),
                "page_ref": source.get("page_ref"),
                "manufacturer": source.get("manufacturer"),
                "raw_reference": source.get("raw_reference")
                or f"{source.get('local_path') or source.get('url')} | SHA-256 {source['content_sha256']}",
                "content_sha256": source.get("content_sha256"),
                "document_edition": source.get("document_edition"),
                "notes": source.get("edition_evidence") or source.get("notes"),
            }
        )
        review_sources.append(
            {
                "source_id": source["source_id"],
                "evidence_role": source.get("batch_role") or "supporting_source",
                "content_sha256": source.get("content_sha256"),
                "document_edition": source.get("document_edition"),
                "page_ref": source.get("page_ref"),
            }
        )
    packet = {
        "schema_version": 2,
        "import_id": stable_id("review-batch", proposal["proposal_id"], file_sha256(ledger_path)),
        "proposal_id": proposal["proposal_id"],
        "proposal_path": display_path(proposal_path),
        "proposal_sha256": file_sha256(proposal_path),
        "review_ledger_path": display_path(ledger_path),
        "review_ledger_sha256": file_sha256(ledger_path),
        "catalog_sha256": primary_source["content_sha256"],
        "catalog_source_id": primary_source["source_id"],
        "reviewed_at": reviewed_at,
        "row_count": len(approved_rows) + len(quarantined_rows),
        "sources": packet_sources,
        "review_sources": review_sources,
        "rows": approved_rows,
        "quarantined_rows": quarantined_rows,
    }
    write_json(output_path, packet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scaffold_parser = subparsers.add_parser("scaffold-ledger")
    scaffold_parser.add_argument("--proposal", type=Path, required=True)
    scaffold_parser.add_argument("--out", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--proposal", type=Path, required=True)
    validate_parser.add_argument("--ledger", type=Path)
    validate_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--proposal", type=Path, required=True)
    compile_parser.add_argument("--ledger", type=Path, required=True)
    compile_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    compile_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    proposal_path = args.proposal.resolve()
    if args.command == "scaffold-ledger":
        scaffold(proposal_path, args.out.resolve())
        print(json.dumps({"status": "created", "ledger": display_path(args.out)}, indent=2))
        return 0

    proposal, errors = validate_proposal(proposal_path, args.db.resolve())
    ledger = None
    if args.ledger:
        ledger, ledger_errors = validate_ledger(proposal_path, proposal, args.ledger.resolve())
        errors.extend(ledger_errors)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, indent=2), file=sys.stderr)
        return 1
    if args.command == "compile":
        if not ledger or ledger.get("status") != "complete" or ledger.get("import_allowed") is not True:
            print("ledger does not authorize import", file=sys.stderr)
            return 1
        compile_packet(proposal_path, proposal, args.ledger.resolve(), ledger, args.out.resolve())
        print(json.dumps({"status": "compiled", "packet": display_path(args.out)}, indent=2))
    else:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "proposal": display_path(proposal_path),
                    "rows": len(proposal.get("rows") or []),
                    "ledger": display_path(args.ledger) if args.ledger else None,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
