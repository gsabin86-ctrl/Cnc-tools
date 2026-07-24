# Toolbase v1/v2 Preservation

This directory contains the database and web-viewer generations superseded by the canonical `toolbase/` pipeline and the `docs/v3/` static viewer.

- `databases/` preserves the 1,212-row flat database and its normalized v2 migration.
- `db-schema/` preserves the v2 schema and design notes.
- `node-runtime/` preserves the older SQLite-in-browser/server scripts and package metadata.
- `notes/` preserves superseded architecture, cleanup, and professionalization documents.
- `preserved-hosted/` preserves the former hosted page byte-for-byte.

These files are migration history, not production inputs. The only supported extraction use is the explicit legacy snapshot command documented in `toolbase/README.md`.
