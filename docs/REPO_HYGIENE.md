# Repository Hygiene

This repo contains both source files and large/generated local artifacts. The goal is to keep the app, scripts, schema, and documentation trackable while keeping scratch output out of Git.

## Track

- App source:
  - `docs/index.html`
  - `docs/server.js`
  - `docs/start-viewer.bat`
  - `docs/package.json`
  - `docs/package-lock.json`
- Database scripts:
  - `docs/scripts/*.js`
- Data model docs:
  - `docs/db/*.sql`
  - `docs/db/*.md`
  - `docs/DATABASES.md`
  - `docs/PROFESSIONALIZATION_PLAN.md`
- Published database while the current UI depends on it:
  - `docs/db.sqlite`
- Future database model while the v2 migration is under review:
  - `docs/db_v2.sqlite`

## Ignore

- Dependency installs:
  - `node_modules/`
  - `docs/node_modules/`
- Local scratch:
  - `.claude/`
  - `_page_view/`
  - `temps/`
- Generated logs and backups:
  - `*.log`
  - `docs/*.backup-*`
  - `docs/server.*.log`
- Incomplete browser downloads:
  - `*.crdownload`
- Generated pet/image run output:
  - `docs/dragoon-pet-run/`
- Large catalog PDFs and extracted catalog artifacts.
- Archived stale databases:
  - `archive/database-cleanup/`

## Current Cleanup Rule

Do not delete generated files during hygiene passes unless explicitly requested. Ignore them first, then archive or remove them only after the canonical workflow is clear.
