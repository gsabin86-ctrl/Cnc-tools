# CNC Toolbase

CNC Toolbase is a source-aware reference for Swiss CNC inserts, holders, modules, shanks, adapters, specifications, work-material recommendations, compatibility evidence, and reviewed cutting data.

## Current Project

The clean system has two deliberate parts:

| Path | Purpose |
|---|---|
| `toolbase/` | Reviewable data seed, canonical schema, review queue, build scripts, audits, and tests. |
| `docs/v3/` | Mobile-first offline GitHub Pages application and generated publish data. |

Start here:

- `docs/FIRST_PRINCIPLES_REVIEW.md` — diagnosis, decisions, accuracy rules, and roadmap.
- `toolbase/README.md` — build, review, and audit commands.
- `docs/v3/index.html` — the active catalog interface.

The site root now redirects to `docs/v3/`. The previous hosted page is preserved byte-for-byte at `archive/database-cleanup/legacy-hosted-index-2026-07-21.html`; older databases and helpers remain legacy/history and are not the canonical workflow.

## Data Flow

```text
reviewable JSONL seed + approved review ledgers + shop inputs
                              ↓
             deterministic reviewed import + build
                              ↓
    canonical SQLite + search/detail JSON + review queue
                              ↓
                    audits, tests, GitHub Pages
```

SQLite and published JSON files are generated outputs. Do not hand-edit them.

## Quick Start

From the repository root:

```powershell
python toolbase/scripts/build.py
python toolbase/scripts/audit.py toolbase/build/toolbase.sqlite
python -m unittest discover -s toolbase/tests -v
python -m http.server 8000 --directory docs
```

Open `http://127.0.0.1:8000/`.

## Accuracy Rules

- Missing is better than invented.
- Every published fact retains source lineage; a located source is not the same as a reviewed fact.
- Legacy row context is traceable but is not direct proof.
- Compatibility is a reviewed claim, not an automatic guarantee of fit.
- Valid machine fit follows `station → holder → insert` or `station → shank → module → insert`; direct insert-to-machine shortcuts are invalid.
- Material tags are not promoted into recommendations without explicit source data.
- Speeds and feeds appear only after exact tool, grade, geometry, material, operation, ranges, units, and source have been reviewed.
- Only manufacturer/catalog-reviewed cutting profiles are exposed as usable recommendations. Unit conversions and RPM/feed-rate calculations are display-only.
