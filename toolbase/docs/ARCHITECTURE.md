# Repository Architecture

## Source of Truth

`toolbase/data/` is the canonical, owner-approved tooling seed. The build combines it with structured approved imports, manufacturer-source metadata, and shop inputs to create the canonical SQLite database and website projections.

Published SQLite and JSON files are build products. Do not hand-edit them.

## Directory Roles

| Path | Role |
|---|---|
| `toolbase/data/` | Canonical tooling rows, relationships, source documents, approved imports, and shop inputs. |
| `toolbase/schema.sql` | Canonical SQLite schema. |
| `toolbase/scripts/` | Build, audit, extraction, source-manifest, and proposal tools. |
| `toolbase/catalogs/` | Catalog registry, schema, and registry example. |
| `toolbase/proposals/` | Structured proposed additions and compatibility extracts. |
| `toolbase/reviews/` | Owner decision ledgers. |
| `catalogs/` | Local manufacturer documents. PDFs are excluded from normal Git; tracked schema maps describe extraction structure. |
| `docs/v3/` | Current dependency-free, mobile-first viewer and generated publish data. |
| `docs/index.html` | Redirect to the current viewer. |
| `docs/CNAME` | Hosted domain configuration. |
| `legacy/` | Preserved earlier databases, scripts, training experiments, and superseded plans. |

## Approval and Provenance

Existing canonical records are owner-approved. Approval is separate from provenance:

- approval determines whether a record belongs in the database;
- provenance identifies the manufacturer catalog or website supporting it;
- citation precision records the exact page, table, URL, edition, or file hash when available.

Internal workflow states can remain in SQLite for maintenance, but they are not public-facing labels.

## Build Flow

```text
toolbase/data + approved imports + source manifest + shop inputs
                              |
                              v
                  toolbase/scripts/build.py
                              |
                +-------------+-------------+
                |                           |
                v                           v
     canonical SQLite                 static web JSON
 docs/v3/data/toolbase.sqlite   docs/v3/data/catalog-*.json
```

The viewer loads `catalog-index.json` for search and `catalog-details.json` for a selected tool. `catalog.json` is a redundant compatibility projection retained only for downstream consumers and may be removed in a later generated-artifact pass.

## Manufacturer Documents

Catalog metadata and hashes are tracked, but manufacturer PDFs are currently ignored by Git. A fresh clone therefore contains the data and provenance records but not every local audit PDF. If the source library is published later, use a deliberate large-file strategy such as Git LFS or release assets rather than ordinary Git blobs.
