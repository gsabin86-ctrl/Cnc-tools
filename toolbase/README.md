# CNC Toolbase v3

This directory is the canonical, data-first CNC tooling system. It preserves the owner-approved tooling records while keeping the web app, Firebase, and commerce concerns out of the database model.

## Canonical Inputs

The seed files under `toolbase/data` are the preserved starting point:

- `tools.jsonl`: all 1,212 legacy tool records, one tool per line.
- `legacy_relationships.jsonl`: all 677 legacy or inferred relationship candidates.
- `catalog_claims.jsonl`: 17 source-backed Sandvik compatibility claims that only existed in v2.
- `reviewed_imports/*.json`: deterministic structured imports compiled from completed owner decisions.
- `source_documents.json`: deduplicated manufacturer catalogs with edition evidence, page count, local audit path, and SHA-256 content hash.
- `shop_inputs/*.json`: direct shop confirmations, including machine-station interfaces.
- `manifest.json`: row counts and SHA-256 hashes of the two legacy source databases used for the original export.

Catalog registry files live under `toolbase/catalogs/`. Active domain documentation lives under `toolbase/docs/`. Proposal examples live under `toolbase/examples/`.

## Build Products

Running the build creates:

- `toolbase/build/toolbase.sqlite`: local canonical build.
- `toolbase/build/ecas20-review-queue.json`: deterministic shop-first review queue.
- `docs/v3/data/toolbase.sqlite`: downloadable published database.
- `docs/v3/data/catalog-index.json`: compact search-first website projection.
- `docs/v3/data/catalog-details.json`: full tool, evidence, and relationship bundle loaded on demand.
- `docs/v3/data/catalog.json`: complete compatibility projection retained for downstream consumers.

The website reads static JSON and has no Firebase or other runtime dependency.

## Commands

Run these from the repository root:

```powershell
python toolbase/scripts/build.py
python toolbase/scripts/audit.py toolbase/build/toolbase.sqlite
python toolbase/scripts/validate_cutting_proposal.py
python toolbase/scripts/import_reviewed_proposal.py --check
python -m unittest discover -s toolbase/tests -v
python -m http.server 8000 --directory docs
```

Use extraction only when deliberately reconstructing the canonical seed from the preserved legacy databases:

```powershell
python toolbase/scripts/extract_seed.py `
  --legacy-db legacy/v1-v2/databases/db.sqlite `
  --v2-db legacy/v1-v2/databases/db_v2.sqlite `
  --out toolbase/data
```

The 12-row Kennametal TopSwiss cutting-data pilot is an approved structured import. The 25-row `kennametal-topswiss-identity-batch-01.json` packet remains a separate unfinished proposal and is not imported.

## Data Contract

- Existing canonical records are owner-approved.
- Missing data is valid; invented data is not.
- Manufacturer source type, title, location, edition, and hash are stored independently from approval.
- Manufacturer grade stays available as a tool attribute, while recommended work material is the primary public organization.
- Compatibility records are evidence-backed relationships, not automatic guarantees of physical fit.
- Physical compatibility flows from the machine station outward: `station -> holder -> insert` or `station -> shank -> module -> insert`.
- Speeds and feeds retain the exact tool, grade, geometry, work material, operation, source ranges, and source units.
- Internal maintenance states are not shown as public review badges.

See [the architecture guide](docs/ARCHITECTURE.md) for the current source-of-truth and directory rules. Historical diagnoses and superseded workflows are under `legacy/`.
