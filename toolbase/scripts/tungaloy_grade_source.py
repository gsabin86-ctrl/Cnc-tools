"""Deterministic parsing and parity checks for Tungaloy grade-page sources.

This module has no proposal/build dependencies so both the importer and the review
trust boundary can execute the exact same manufacturer-HTML parser.
"""

from __future__ import annotations

import html
import re
from typing import Any


def _cell_text(value: str, *, break_separator: str = " ") -> str:
    value = re.sub(r"<br\s*/?>", break_separator, value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(html.unescape(value).split())


def _range(value: str) -> dict[str, float | None]:
    if value.strip() in {"-", "–"}:
        return {"min": None, "max": None}
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)", value.strip())
    if not match:
        raise ValueError(f"unsupported Tungaloy range cell {value!r}")
    return {"min": float(match.group(1)), "max": float(match.group(2))}


def parse_standard_conditions(html_text: str) -> dict[str, Any]:
    match = re.search(
        r"Standard cutting conditions.*?(<table>\s*<thead>.*?</table>)",
        html_text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Tungaloy Standard cutting conditions table is missing")
    table_html = match.group(1)
    bounds = [
        float(value)
        for value in re.findall(r"<th>RE &lt; (\d+(?:\.\d+)?)</th>", table_html)
    ]
    if bounds != [0.03, 0.1, 0.2, 0.4]:
        raise ValueError(f"unexpected Tungaloy strict feed bounds: {bounds!r}")
    body = re.search(r"<tbody>(.*?)</tbody>", table_html, flags=re.DOTALL)
    if not body:
        raise ValueError("Tungaloy Standard cutting conditions body is missing")

    conditions: dict[str, dict[str, Any]] = {}
    for row_html in re.findall(r"<tr>(.*?)</tr>", body.group(1), flags=re.DOTALL):
        iso = "P" if 'class="p' in row_html else "M" if 'class="m' in row_html else None
        if not iso:
            raise ValueError("unrecognized ISO row in Tungaloy conditions table")
        raw_cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.DOTALL)
        cells = [_cell_text(cell) for cell in raw_cells]
        if len(cells) == 10:
            material = _cell_text(raw_cells[1], break_separator=", ")
            chipbreaker, grade, speed_text, doc_text = cells[2:6]
            feed_texts = cells[6:10]
            conditions[iso] = {
                "iso_group": iso,
                "materials": material,
                "vc_m_min": _range(speed_text),
                "depth_of_cut_mm_by_chipbreaker": {},
                "feed_mm_rev_by_chipbreaker_and_strict_radius_band": {},
            }
        elif len(cells) == 8 and iso in conditions:
            chipbreaker, grade, speed_text, doc_text = cells[0:4]
            feed_texts = cells[4:8]
        else:
            raise ValueError(f"unexpected Tungaloy table row shape for ISO {iso}: {len(cells)}")
        if grade != "SH7025" or chipbreaker not in {"JP", "JS"}:
            raise ValueError(f"unexpected Tungaloy row identity: {chipbreaker!r} / {grade!r}")
        if _range(speed_text) != conditions[iso]["vc_m_min"]:
            raise ValueError(f"inconsistent cutting speed in ISO {iso} row")
        conditions[iso]["depth_of_cut_mm_by_chipbreaker"][chipbreaker] = _range(doc_text)
        conditions[iso]["feed_mm_rev_by_chipbreaker_and_strict_radius_band"][chipbreaker] = [
            {"max_corner_radius_exclusive_mm": bound, **_range(value)}
            for bound, value in zip(bounds, feed_texts, strict=True)
        ]
    if set(conditions) != {"P", "M"}:
        raise ValueError("Tungaloy table must contain exact P and M condition rows")
    return {"standard_cutting_conditions": conditions, "table_html": table_html}


def validate_snapshot_against_html(snapshot: dict[str, Any], html_text: str) -> dict[str, Any]:
    if snapshot.get("coolant_scope") != "application_examples_only_not_standard_conditions_table":
        raise ValueError("Tungaloy coolant wording must remain scoped to application examples")
    parsed = parse_standard_conditions(html_text)
    if parsed["standard_cutting_conditions"] != snapshot.get("standard_cutting_conditions"):
        raise ValueError("normalized standard conditions do not match hash-bound HTML")
    for value in (snapshot.get("application_verbatim") or {}).values():
        if value not in html_text:
            raise ValueError("normalized application range does not match hash-bound HTML")
    if snapshot.get("coolant") and f"Coolant: {snapshot['coolant']}" not in html_text:
        raise ValueError("normalized coolant wording does not match hash-bound HTML")
    return parsed
