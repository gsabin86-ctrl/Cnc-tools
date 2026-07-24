# CNC Tool Database Workflow

**Owner:** Greg Sabin
**Last updated:** 2026-05-18
**Status:** Active project workflow

This repo is being cleaned up around one goal: CNC tooling data should be referenceable, auditable, accurate, and true. Missing data is allowed. Invented data is not.

## Current Database Roles

| File | Role | Notes |
|------|------|-------|
| `docs/db.sqlite` | Current production UI database | Served by `docs/server.js` and fetched by `docs/index.html`. Keep stable until the UI migrates. |
| `docs/db_v2.sqlite` | Normalized future database | Generated from `docs/db.sqlite`; better source/spec/compatibility structure. |
| root `db.sqlite` | Archived legacy copy | Older 629-row database. It is not used by the current app. |

See `docs/DATABASES.md` for the detailed database inventory.

## Data Entry Rule

Do not hand-edit SQLite files.

New catalog data should move through this shape:

```text
manufacturer source -> structured proposal -> audit -> Greg approval -> scripted apply -> verification
```

That applies to tooling records, compatibility records, and cutting-data records.

## Safety Rules

| Rule | Detail |
|------|--------|
| No invented data | Every real field must trace to a manufacturer page, catalog page, machine manual, or explicitly labeled shop note. |
| Missing stays missing | Unknown data should stay `null`, blank, or `needs_review`; do not fill with typical values. |
| No silent DB writes | Any database-changing script should make a backup or require an explicit `--apply` mode. |
| Review before apply | Present small reviewable batches before changing production data. |
| Machine fit needs physical verification | Catalog specs are not enough for machine station fit. Shank shape, station size, pocket depth, orientation, coolant ports, and real shop fit matter. |
| Shape matters | Round shank and square shank compatibility must be modeled as different physical interfaces. |
| Cutting data is safety-critical | Speeds, feeds, and DOC ranges must have auditable source rows and verification status before the calculator treats them as usable. |

## Current Database State

Last checked: 2026-05-18.

| Database | Count | Notes |
|----------|-------|-------|
| `docs/db.sqlite` | 1,212 `tools` rows | Current UI database. |
| `docs/db_v2.sqlite` | 1,212 `catalog_tools` rows | Normalized target with sources, specs, and compatibility edges. |
| archived root `db.sqlite` | 629 `tools` rows | Stale legacy copy retained only for audit/history. |

## Maintained Scripts

Use scripts under `docs/scripts` for the current project:

| Script | Purpose |
|--------|---------|
| `docs/scripts/audit-database.js` | Audit current and v2 databases. |
| `docs/scripts/migrate-v2.js` | Rebuild normalized v2 database from current production DB. |
| `docs/scripts/clean-db.js` | Controlled cleanup of current production DB. |
| `docs/scripts/verify-tools.js` | Verify selected tool records. |
| `docs/scripts/build-compatibility-edges.js` | Generate compatibility edges for review. |

Older root-level Python scripts are historical helpers unless refreshed and documented for the current `docs/db.sqlite` workflow.

## Near-Term Cleanup Path

1. Keep `docs/db.sqlite` stable while the current UI depends on it.
2. Use `docs/db_v2.sqlite` as the professional target model.
3. Add a cutting-data schema and proposal format before importing any speeds/feeds.
4. Migrate UI reads from the flat `tools` table toward the normalized v2 tables.
5. Remove or archive stale root-level data/scripts once replacements exist in `docs/scripts`.
