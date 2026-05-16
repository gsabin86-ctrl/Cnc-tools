# Database Files

This project currently has more than one SQLite file because the data model has evolved. They are not automatically synchronized at runtime.

## Current Files

### `docs/db.sqlite`

Current published UI database.

- Used by `docs/server.js`.
- Fetched by `docs/index.html` as `db.sqlite`.
- Contains the current flat `tools` table used by the app.
- Current row count: 1,212 tools.

Treat this as the legacy production database until the UI is migrated to v2.

### `docs/db_v2.sqlite`

Normalized v2 database generated from `docs/db.sqlite`.

- Contains `catalog_tools`, `sources`, `tool_specs`, and `compatibility_edges`.
- Better matches the long-term goal of auditable tool facts and verified compatibility.
- Current row count: 1,212 catalog tools.
- Not yet used by the frontend.

Treat this as the preferred future canonical database shape.

### Root `db.sqlite`

Older root-level database.

- Contains fewer rows than `docs/db.sqlite`.
- Appears to be a previous working database from before the published `docs` database grew.
- Not served by the current `docs/server.js`.

Treat this as legacy/stale until proven otherwise.

## Intended Direction

The cleanup path is:

1. Keep `docs/db.sqlite` stable while the current UI depends on it.
2. Use `docs/db_v2.sqlite` as the target model for structured sources, specs, and compatibility.
3. Migrate the UI to read v2 tables directly.
4. After migration, archive or remove stale database files so only one canonical database remains in normal use.

## Important Rule

Do not manually copy data between SQLite files. Use documented migration or publish scripts so the source of truth remains clear.
