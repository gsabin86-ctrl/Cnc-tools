#!/usr/bin/env python3
"""Build the deterministic Star ECAS-20 source-review queue from the canonical DB."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MACHINE_ID = "ECAS20_GANG_BLOCK"


def rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, params)
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, record)) for record in cursor.fetchall()]


def build_queue(db_path: Path, output_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    tools = {
        row["id"]: row
        for row in rows(
            connection,
            """
            SELECT t.id, t.part_number, m.name AS manufacturer, t.component_type,
                   t.description, t.geometry, t.insert_seat, t.iso_designation,
                   t.grade, t.chipbreaker, t.evidence_status
            FROM tools t JOIN manufacturers m ON m.id=t.manufacturer_id
            ORDER BY t.id
            """,
        )
    }
    stations = rows(
        connection,
        """
        SELECT t.id, CAST(f.value_number AS INTEGER) AS station_number,
               size_fact.value_number AS size_mm, shape_fact.value_text AS shape
        FROM tools t
        JOIN facts f ON f.tool_id=t.id AND f.fact_key='station_number'
        LEFT JOIN facts size_fact ON size_fact.tool_id=t.id AND size_fact.fact_key='accepted_shank_size_mm'
        LEFT JOIN facts shape_fact ON shape_fact.tool_id=t.id AND shape_fact.fact_key='accepted_shank_shape'
        WHERE t.component_type='station' AND t.id LIKE ?
        ORDER BY station_number
        """,
        (f"{MACHINE_ID}_STATION_%",),
    )
    station_ids = {station["id"] for station in stations}
    fit_claims = rows(
        connection,
        """
        SELECT id, subject_tool_id, relationship, object_tool_id, evidence_status,
               review_status, source_id, source_raw_text, notes
        FROM compatibility_claims
        WHERE subject_tool_id IN ({}) AND relationship IN ('accepts_holder','accepts_shank')
          AND review_status='accepted' AND suppressed=0
        ORDER BY subject_tool_id, relationship, object_tool_id
        """.format(",".join("?" for _ in station_ids)),
        tuple(sorted(station_ids)),
    ) if station_ids else []

    stations_for_root: dict[str, list[int]] = defaultdict(list)
    station_number_by_id = {station["id"]: station["station_number"] for station in stations}
    fit_claim_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in fit_claims:
        root_id = claim["object_tool_id"]
        stations_for_root[root_id].append(station_number_by_id[claim["subject_tool_id"]])
        fit_claim_by_pair[(claim["subject_tool_id"], root_id)] = claim

    all_claims = rows(
        connection,
        """
        SELECT id, subject_tool_id, relationship, object_kind, object_tool_id,
               object_value, evidence_status, review_status, confidence, source_id,
               source_page_ref, source_raw_text, notes, suppressed
        FROM compatibility_claims
        WHERE suppressed=0
        ORDER BY subject_tool_id, relationship, object_tool_id, object_value, id
        """,
    )
    children: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for claim in all_claims:
        subject = claim["subject_tool_id"]
        target = claim["object_tool_id"]
        if claim["relationship"] == "mounts_to" and target and subject in tools:
            children[target].append((subject, claim))
        elif claim["relationship"] in {"accepts_module", "accepts_insert", "adapts_to"} and target:
            children[subject].append((target, claim))

    fact_counts = dict(
        connection.execute("SELECT tool_id, COUNT(*) FROM facts GROUP BY tool_id").fetchall()
    )
    source_counts = dict(
        connection.execute("SELECT tool_id, COUNT(DISTINCT source_id) FROM tool_sources GROUP BY tool_id").fetchall()
    )
    material_counts = dict(
        connection.execute("SELECT tool_id, COUNT(*) FROM tool_material_recommendations GROUP BY tool_id").fetchall()
    )
    cutting_counts = dict(
        connection.execute("SELECT tool_id, COUNT(*) FROM usable_cutting_data GROUP BY tool_id").fetchall()
    )

    queue_items: list[dict[str, Any]] = []
    visited_paths: set[tuple[str, str, str]] = set()
    for root_id in sorted(stations_for_root):
        work = deque([(root_id, [root_id], None, 0)])
        seen_depth: dict[str, int] = {root_id: 0}
        while work:
            tool_id, path, incoming_claim, depth = work.popleft()
            tool = tools[tool_id]
            key = (root_id, tool_id, incoming_claim["id"] if incoming_claim else "station-fit")
            if key in visited_paths:
                continue
            visited_paths.add(key)
            missing = []
            if source_counts.get(tool_id, 0) == 0:
                missing.append("manufacturer source")
            if fact_counts.get(tool_id, 0) == 0:
                missing.append("specifications")
            if not tool.get("geometry") and not tool.get("iso_designation"):
                missing.append("geometry")
            if tool["component_type"] == "insert" and material_counts.get(tool_id, 0) == 0:
                missing.append("work material")
            if tool["component_type"] == "insert" and cutting_counts.get(tool_id, 0) == 0:
                missing.append("speeds and feeds")
            review_status = incoming_claim["review_status"] if incoming_claim else "accepted"
            queue_items.append(
                {
                    "priority": 10 + depth * 10,
                    "station_numbers": sorted(set(stations_for_root[root_id])),
                    "path": path,
                    "tool_id": tool_id,
                    "part_number": tool["part_number"],
                    "manufacturer": tool["manufacturer"],
                    "component_type": tool["component_type"],
                    "relationship_claim_id": incoming_claim["id"] if incoming_claim else None,
                    "relationship": incoming_claim["relationship"] if incoming_claim else "station interface fit",
                    "review_status": review_status,
                    "evidence_status": incoming_claim["evidence_status"] if incoming_claim else "shop_verified",
                    "source_count": source_counts.get(tool_id, 0),
                    "fact_count": fact_counts.get(tool_id, 0),
                    "material_profile_count": material_counts.get(tool_id, 0),
                    "verified_cutting_profile_count": cutting_counts.get(tool_id, 0),
                    "missing": missing,
                    "next_action": (
                        "Audit the relationship and exact interface against the manufacturer source."
                        if incoming_claim and review_status == "needs_review"
                        else "Fill only the missing fields from an exact manufacturer source."
                    ),
                }
            )
            if depth >= 2:
                continue
            for child_id, claim in children.get(tool_id, []):
                if child_id not in tools or child_id in path:
                    continue
                next_depth = depth + 1
                if seen_depth.get(child_id, 99) < next_depth:
                    continue
                seen_depth[child_id] = next_depth
                work.append((child_id, [*path, child_id], claim, next_depth))

    queue_items.sort(
        key=lambda item: (
            item["priority"],
            0 if item["review_status"] == "needs_review" else 1,
            -len(item["missing"]),
            item["manufacturer"].casefold(),
            item["part_number"].casefold(),
        )
    )
    payload = {
        "schema_version": 1,
        "machine_tool_id": MACHINE_ID,
        "purpose": "Shop-first manufacturer review queue; this file does not approve compatibility or cutting data.",
        "rules": [
            "Machine station to holder/shank fits are accepted only from the recorded shop interface rule plus source-backed dimensions.",
            "Shank to module and holder/module to insert links remain needs_review until exact manufacturer evidence is recorded.",
            "Missing speeds and feeds remain missing; no values are inferred from neighboring tools.",
        ],
        "counts": {
            "stations": len(stations),
            "station_fit_claims": len(fit_claims),
            "unique_tools": len({item["tool_id"] for item in queue_items}),
            "items": len(queue_items),
            "needs_review": sum(item["review_status"] == "needs_review" for item in queue_items),
        },
        "items": queue_items,
    }
    connection.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)
    return payload["counts"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "build" / "toolbase.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "ecas20-review-queue.json")
    args = parser.parse_args()
    print(json.dumps(build_queue(args.db.resolve(), args.out.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
