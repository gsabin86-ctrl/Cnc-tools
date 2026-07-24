# CNC Toolbase

CNC Toolbase is a source-aware reference for Swiss CNC inserts, holders, modules, shanks, adapters, specifications, work-material recommendations, compatibility evidence, and cutting data.

## Repository Layout

The repository has four deliberate parts:

| Path | Purpose |
|---|---|
| `toolbase/` | Owner-approved data seed, canonical schema, provenance records, build scripts, audits, and tests. |
| `docs/` | GitHub Pages deployment only: redirect, domain file, and the current `/v3` application. |
| `catalogs/` | Local manufacturer-document library. PDFs are intentionally not tracked by normal Git; schema maps are tracked. |
| `legacy/` | Preserved v1/v2 databases, experiments, scripts, and historical planning documents. Nothing here is canonical. |

Start here:

- `toolbase/docs/ARCHITECTURE.md` - current source-of-truth and directory rules.
- `toolbase/README.md` - build, source, and audit commands.
- `docs/v3/index.html` - active catalog interface.

The site root redirects to `docs/v3/`. The previous hosted page and all earlier database workflows are preserved under `legacy/`.

## Data Flow

```text
owner-approved JSONL seed + manufacturer-source manifest + approved imports + shop inputs
                                   |
                                   v
                       deterministic v3 build
                                   |
                   +---------------+---------------+
                   |                               |
                   v                               v
           canonical SQLite               search/detail JSON
                   |                               |
                   +---------------+---------------+
                                   v
                         audits and GitHub Pages
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

## Data Rules

- Existing canonical records are owner-approved.
- Missing is better than invented.
- Manufacturer catalog and website provenance stays attached to the published record.
- Approval is separate from citation precision; a broad catalog range can later be refined to an exact page without invalidating the record.
- Compatibility follows `station -> holder -> insert` or `station -> shank -> module -> insert`.
- Work-material recommendations, not manufacturer grades, are the primary public organization for inserts.
- Internal workflow states remain available for maintenance but are not public-facing badges.
- Unit conversions and RPM/feed-rate calculations are display-only.
