# Sandvik Registry Review

Date: 2026-05-22

This review classifies the local Sandvik catalog files enough to choose safe extraction batches. It does not add tool rows or cutting-data rows.

## Reviewed Catalogs

| Catalog ID | File | Classification |
|------------|------|----------------|
| `sandvik-latest-cutting-tools-26-1` | `catalogs/Sandvik/Latest cutting tools 26-1.pdf` | Broad current catalog: turning, grooving, threading, milling, drilling, boring, holders/adapters. |
| `sandvik-original` | `catalogs/Sandvik/original.pdf` | Sliding-head/small-parts brochure; useful for Swiss-machine tooling categories. |
| `sandvik-sandvik-corocut2-inserts` | `catalogs/Sandvik/sandvik_corocut2_inserts.pdf` | Grooving/parting inserts. |
| `sandvik-sandvik-coroturn107-inserts` | `catalogs/Sandvik/sandvik_coroturn107_inserts.pdf` | Turning inserts. |
| `sandvik-sandvik-p401-450` | `catalogs/Sandvik/sandvik_p401-450.pdf` | Holding tools/adaptors, CoroTurn SL/CoroBore interface sections. |
| `sandvik-sandvik-p423-430` | `catalogs/Sandvik/sandvik_p423-430.pdf` | Smaller holding tool/adaptor extract. |
| `sandvik-sandvik-qs-modules` | `catalogs/Sandvik/sandvik_qs_modules.pdf` | QS Micro cutting heads/shanks, insert compatibility fields, shank/mounting dimensions. |
| `sandvik-sandvik-toc` | `catalogs/Sandvik/sandvik_toc.pdf` | Navigation/table-of-contents only. |

## Pilot Insert Findings

Pilot target inserts:

- `DNMG 432-PM 4425`
- `DCGT 3(2.5)1-UM 1205`

Local PDF findings:

- `DNMG 432-PM` appears in `Latest cutting tools 26-1.pdf` on PDF page 21 as a T-Max P D-style 55 degree insert geometry row.
- That local row appears under current grade columns, not the `GC4425` pilot grade.
- `DCGT 3(2.5)1-UM 1205` was not found as an exact local PDF hit during this review.
- The current v2 database has many Sandvik records, but not exact pilot rows for `DNMG 432-PM 4425` or `DCGT 3(2.5)1-UM 1205` as catalog tools.

## Implication

The cutting-data pilot should not start by applying cutting-data rows directly.

Safe order:

1. Verify or add exact Sandvik pilot catalog tool records.
2. Locate manufacturer source pages or older manufacturer catalog pages for the exact grade/designation combinations.
3. Extract cutting-data proposal rows only after exact source matches exist.
4. Validate and review before apply.

## Compatibility Notes

Sandvik compatibility extraction should be split by relationship type:

- Insert sections: insert geometry, ISO/ANSI designation, grade, chipbreaker, and material suitability.
- QS Micro sections: module/cutting-head to insert compatibility using `MIID` and insert style fields.
- Shank/adaptor sections: `mounts_to` and `adapts_to` physical interfaces, including shank size, connection code, and coolant pressure.

Machine/station compatibility still requires Greg/shop verification later.
