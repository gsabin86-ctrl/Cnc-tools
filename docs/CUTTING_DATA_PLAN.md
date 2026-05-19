# Cutting Data Plan

Cutting data is safety-critical. CNCToolbase should only show speeds, feeds, and depth-of-cut ranges when the numbers are traceable to a real source and have a clear verification status.

## Goal

Give the Speeds panel a trustworthy data layer without pretending the database is more complete than it is.

The UI should be able to say one of two things:

- Verified cutting data exists for this insert/material/operation.
- No verified cutting data is attached yet.

## Data Model

Cutting data belongs in its own table, separate from the main tool row.

Proposed v2 table:

- `cutting_data_profiles`

Each row represents one auditable cutting recommendation range for a specific tool, material group, operation, and source.

Important fields:

| Field | Purpose |
|-------|---------|
| `tool_id` | The insert/tool the row applies to. |
| `source_id` | The source document/page/product URL for the numbers. |
| `source_part_number` | Exact part number as written in the source. |
| `source_grade` | Exact grade as written in the source. |
| `source_geometry` | Exact geometry/chipbreaker context from the source when present. |
| `iso_material_group` | ISO material group: P, M, K, N, S, H, O, or unknown. |
| `operation_type` | Turning, boring, grooving, parting, threading, drilling, milling, or unknown. |
| `surface_speed_min/max/unit` | Source speed range, stored in source units. |
| `feed_min/max/unit` | Source feed range, stored in source units. |
| `depth_of_cut_min/max/unit` | Source DOC range, stored in source units. |
| `source_page_ref` | Catalog page, PDF page, or product page section. |
| `source_table_ref` | Named source chart/table when available. |
| `verification_status` | Review state for whether the row can be used. |

The schema stores source units as published. Unit conversions should happen in display/calculator code so the original source numbers remain auditable.

## Verification Status

| Status | Meaning |
|--------|---------|
| `proposed` | Entered as a candidate row, not reviewed. |
| `source_extracted` | Extracted from a source but not yet checked against the source by a reviewer. |
| `needs_review` | Something is ambiguous or incomplete. |
| `catalog_verified` | Checked against a manufacturer catalog page/PDF. |
| `manufacturer_verified` | Checked against a manufacturer product page or primary manufacturer source. |
| `shop_verified` | Proven as a shop default or shop-tested override, not a manufacturer claim. |
| `rejected` | Do not use. |

The Speeds panel should only use rows with `catalog_verified`, `manufacturer_verified`, or `shop_verified`.

## Batch Workflow

1. Pick a small batch: one manufacturer, one insert family, or 10-25 insert/grade combinations.
2. Extract proposed rows into a review file.
3. Audit required fields and units.
4. Review source pages against the proposed rows.
5. Apply only approved rows with a script.
6. Re-run database audit.
7. Wire only verified rows into the UI.

## Rules

- Do not infer cutting data from a similar insert.
- Do not average distributor examples into manufacturer ranges.
- Do not mix metric and imperial without preserving the source unit.
- Do not use a row unless part number, grade, material group, operation, and units all match.
- Keep missing data honest.

## First Pilot

Use the two calculator inserts as a pilot only after the source pages are checked:

- Sandvik DNMG 432-PM 4425
- Sandvik DCGT 3(2.5)1-UM 1205

Until source verification is complete, those rows should remain `proposed` or `needs_review`, not calculator-ready.
