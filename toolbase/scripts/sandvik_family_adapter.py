#!/usr/bin/env python3
"""Capture and transform exact Sandvik Coromant insert families.

The adapter discovers manufacturer-listed candidates, fetches each exact material-ID
response, identity-gates family membership, and writes one immutable structured
snapshot. It never writes SQLite or public website artifacts directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUTOCOMPLETE_URL = "https://www.sandvik.coromant.com/api/productsearch/getautocompleteitems"
PRODUCT_URL = "https://www.sandvik.coromant.com/api/productsearch/product"
USER_AGENT = "CNC-Toolbase-Sandvik-family-adapter/1.0"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def collapse_order_code(value: object) -> str:
    return " ".join(str(value or "").split())


def normalized_order_code(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", collapse_order_code(value).upper())


def json_pointer_escape(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def autocomplete_request_url(query: str, limit: int) -> str:
    return AUTOCOMPLETE_URL + "?" + urllib.parse.urlencode(
        {
            "query": query,
            "queryContext": "CoromantGB",
            "autocompleteType": "coromantproductsearch",
            "itemsToReturn": limit,
        }
    )


def product_request_url(material_id: str) -> str:
    return PRODUCT_URL + "?" + urllib.parse.urlencode(
        {
            "id": material_id,
            "unitOfMeasurement": "Metric",
            "language": "en-gb",
            "country": "gb",
        }
    )


def fetch_json_bytes(url: str, attempts: int = 4) -> tuple[bytes, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.casefold():
                raise ValueError(f"expected JSON from {url}, received {content_type!r}")
            return raw, json.loads(raw)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def candidate_identity(candidate: dict[str, Any]) -> tuple[str, str]:
    return str(candidate.get("ID") or "").strip(), normalized_order_code(candidate.get("Title"))


def family_membership_errors(candidate: dict[str, Any], response: dict[str, Any]) -> list[str]:
    product = response.get("product") if isinstance(response, dict) else None
    if not isinstance(product, dict):
        return ["response.product is missing"]
    candidate_id, candidate_order = candidate_identity(candidate)
    checks = [
        (str(product.get("MaterialID") or ""), candidate_id, "material ID"),
        (normalized_order_code(product.get("ORDCODE")), candidate_order, "order code"),
        (str(product.get("PRODFAM") or ""), "CoroTurn 107", "product family"),
        (str(product.get("InsertDesignation") or ""), "DCGT", "insert designation"),
        (str(product.get("GTCId") or ""), "INSI", "generic taxonomy"),
    ]
    return [f"{label} mismatch: {actual!r} != {expected!r}" for actual, expected, label in checks if actual != expected]


def discover(query: str, limits: tuple[int, int] = (1000, 2000)) -> dict[str, Any]:
    captures = []
    for limit in limits:
        url = autocomplete_request_url(query, limit)
        raw, payload = fetch_json_bytes(url)
        if not isinstance(payload, list):
            raise ValueError(f"autocomplete response for limit {limit} is not a list")
        captures.append(
            {
                "url": url,
                "requested_limit": limit,
                "response_sha256": sha256_bytes(raw),
                "items": payload,
            }
        )
    identity_sets = [
        sorted(candidate_identity(item) for item in capture["items"] if isinstance(item, dict))
        for capture in captures
    ]
    if identity_sets[0] != identity_sets[1]:
        raise ValueError("expanded autocomplete requests returned different candidate identities")
    if len(identity_sets[0]) >= min(limits):
        raise ValueError("candidate count reached an autocomplete limit; family completeness is unresolved")
    ids = [identity[0] for identity in identity_sets[0]]
    orders = [identity[1] for identity in identity_sets[0]]
    if any(not item for item in ids):
        raise ValueError("autocomplete candidates contain missing material IDs")
    if any(not item for item in orders) or len(orders) != len(set(orders)):
        raise ValueError("autocomplete candidates contain missing or duplicate order codes")
    return {
        "query": query,
        "verification": {
            "same_candidate_identities": True,
            "candidate_count_below_both_limits": True,
            "suggestion_count": len(ids),
            "candidate_material_id_count": len(set(ids)),
        },
        "captures": captures,
    }


def capture_family(query: str, workers: int = 6) -> dict[str, Any]:
    discovery = discover(query)
    candidates = discovery["captures"][-1]["items"]
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        by_id.setdefault(str(item["ID"]), []).append(item)
    fetched: dict[str, dict[str, Any]] = {}

    def fetch_one(material_id: str) -> tuple[str, dict[str, Any]]:
        url = product_request_url(material_id)
        raw, response = fetch_json_bytes(url)
        if not isinstance(response, dict):
            raise ValueError(f"product response {material_id} is not an object")
        return material_id, {
            "api_url": url,
            "response_sha256": sha256_bytes(raw),
            "autocomplete": next(
                (item for item in by_id[material_id] if str(item.get("ItemType") or "").casefold() == "iso"),
                by_id[material_id][0],
            ),
            "autocomplete_aliases": by_id[material_id],
            "response": response,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_one, material_id): material_id for material_id in sorted(by_id)}
        for future in as_completed(futures):
            material_id, record = future.result()
            fetched[material_id] = record

    included: list[str] = []
    excluded: dict[str, list[str]] = {}
    for material_id in sorted(fetched, key=lambda item: (int(item) if item.isdigit() else item)):
        errors = family_membership_errors(fetched[material_id]["autocomplete"], fetched[material_id]["response"])
        if errors:
            excluded[material_id] = errors
        else:
            included.append(material_id)

    size_tokens = sorted(
        {
            collapse_order_code(fetched[material_id]["response"]["product"].get("ORDCODE")).split()[1]
            for material_id in included
        }
    )
    size_cross_checks: dict[str, Any] = {}
    reconciled_ids: set[str] = set()
    for size_token in size_tokens:
        size_query = f"DCGT {size_token}"
        size_discovery = discover(size_query)
        exact_ids = sorted(
            {
                str(item.get("ID") or "")
                for item in size_discovery["captures"][-1]["items"]
                if str(item.get("ItemType") or "").casefold() == "iso"
                and re.match(r"^DCGT(?:\s|\d)", collapse_order_code(item.get("Title")).upper())
            }
        )
        expected_ids = sorted(
            material_id
            for material_id in included
            if collapse_order_code(fetched[material_id]["response"]["product"].get("ORDCODE")).split()[1]
            == size_token
        )
        if exact_ids != expected_ids:
            raise ValueError(
                f"size-query reconciliation failed for {size_query}: {len(exact_ids)} != {len(expected_ids)}"
            )
        reconciled_ids.update(exact_ids)
        size_cross_checks[size_token] = {
            "query": size_query,
            "exact_dcgt_material_ids": exact_ids,
            "discovery": size_discovery,
        }
    if reconciled_ids != set(included):
        raise ValueError("size-query union does not equal the product-gated family inventory")

    return {
        "schema_version": 1,
        "adapter": "sandvik-coromant-productsearch-v1",
        "snapshot_id": f"sandvik-coroturn107-dcgt-family-{datetime.now(timezone.utc).date().isoformat()}",
        "manufacturer": "Sandvik Coromant",
        "retrieved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": {
            "seed_query": query,
            "required_product_family": "CoroTurn 107",
            "required_insert_designation": "DCGT",
            "required_gtc_id": "INSI",
            "membership_rule": "Exact material ID and order code agree between autocomplete and product response; product.PRODFAM=CoroTurn 107; product.InsertDesignation=DCGT; product.GTCId=INSI.",
        },
        "discovery": discovery,
        "size_query_cross_checks": size_cross_checks,
        "size_query_union_matches_included_family": True,
        "included_material_ids": included,
        "excluded_candidates": excluded,
        "products": {material_id: fetched[material_id] for material_id in sorted(fetched)},
    }


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    included = snapshot.get("included_material_ids") or []
    products = snapshot.get("products") or {}
    counters: dict[str, dict[str, int]] = {
        "lifecycle_codes": {},
        "availability": {},
        "chipbreakers": {},
        "grades": {},
        "sizes": {},
    }
    material_groups: set[str] = set()
    cutting_profiles = 0
    with_replacements = 0
    for material_id in included:
        product = products[material_id]["response"]["product"]
        for target, key in (
            ("lifecycle_codes", "LCS"),
            ("availability", "TIBPAvailability"),
            ("chipbreakers", "CBMD"),
            ("grades", "GRADE"),
            ("sizes", "InsertSizeCode"),
        ):
            value = str(product.get(key) or "source_not_stated")
            counters[target][value] = counters[target].get(value, 0) + 1
        material_groups.update(str(value) for value in product.get("TMC1ISO") or [])
        if product.get("ReplacementProductId"):
            with_replacements += 1
        for operation in product.get("CuttingOperations") or []:
            cutting_profiles += len(operation.get("materials") or [])
    return {
        "suggestion_count": snapshot["discovery"]["verification"]["suggestion_count"],
        "candidate_material_id_count": snapshot["discovery"]["verification"]["candidate_material_id_count"],
        "included_count": len(included),
        "excluded_count": len(snapshot.get("excluded_candidates") or {}),
        "products_with_replacements": with_replacements,
        "cutting_profile_rows": cutting_profiles,
        "material_groups": sorted(material_groups),
        **{key: dict(sorted(value.items())) for key, value in counters.items()},
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="discover and fetch an exact Sandvik family")
    capture.add_argument("--query", default="DCGT")
    capture.add_argument("--workers", type=int, default=6)
    capture.add_argument("--snapshot-out", type=Path, required=True)
    summary = subparsers.add_parser("summarize", help="summarize a captured family snapshot")
    summary.add_argument("--snapshot", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "capture":
        snapshot = capture_family(args.query, workers=args.workers)
        write_json(args.snapshot_out, snapshot)
        print(json.dumps({"snapshot": str(args.snapshot_out), **summarize(snapshot)}, indent=2))
        return 0
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    print(json.dumps(summarize(snapshot), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
