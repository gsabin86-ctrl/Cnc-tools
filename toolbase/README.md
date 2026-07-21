# CNC Toolbase v3

This directory is the clean, data-first rebuild of the CNC tooling project. It preserves the existing tooling records while removing the web app, Firebase, reviews, and commerce concerns from the database model.

## What Is Canonical

The reviewable seed files under `toolbase/data` are the preserved starting point:

- `tools.jsonl`: all 1,212 legacy tool records, one tool per line.
- `legacy_relationships.jsonl`: all 677 legacy or inferred relationship candidates.
- `catalog_claims.jsonl`: 17 source-backed Sandvik compatibility claims that only existed in v2.
- `reviewed_imports/*.json`: deterministic build inputs compiled from completed, authorized review ledgers.
- `source_documents.json`: deduplicated local manufacturer catalogs with edition evidence, page count, local audit path, and SHA-256 content hash.
- `shop_inputs/*.json`: direct shop confirmations, including machine-station interfaces, with recorder, date, raw statement, and a stored build hash.
- `manifest.json`: row counts and SHA-256 hashes of the two source databases used for the export.

The old databases remain untouched. The v3 SQLite file and website data are generated artifacts, not hand-edited sources.

## Build Products

Running the build creates:

- `toolbase/build/toolbase.sqlite`: local canonical build.
- `toolbase/build/ecas20-review-queue.json`: deterministic shop-first review queue.
- `docs/v3/data/toolbase.sqlite`: downloadable published database.
- `docs/v3/data/catalog-index.json`: compact search-first website projection.
- `docs/v3/data/catalog-details.json`: full tool, evidence, and relationship bundle loaded on demand.
- `docs/v3/data/catalog.json`: complete compatibility projection retained for downstream consumers.

The website reads static JSON rather than loading SQLite and WebAssembly in the browser. It has no Firebase or other runtime dependency. A service worker caches the viewer and both active data bundles for offline use.

## Commands

Run these from the repository root.

```powershell
python toolbase/scripts/build.py
python toolbase/scripts/audit.py toolbase/build/toolbase.sqlite
python toolbase/scripts/validate_cutting_proposal.py
python toolbase/scripts/import_reviewed_proposal.py --check
python toolbase/scripts/review_batch.py validate `
  --proposal toolbase/proposals/kennametal-topswiss-identity-batch-01.json `
  --ledger toolbase/reviews/kennametal-topswiss-identity-batch-01.decisions.json
python toolbase/scripts/serve_review.py
python -m unittest discover -s toolbase/tests -v
python -m http.server 8000 --directory docs
```

Then open `http://127.0.0.1:8000/`; the hosted root now redirects to v3.

Use the extraction command only when deliberately taking a new snapshot from the legacy databases:

```powershell
python toolbase/scripts/extract_seed.py `
  --legacy-db docs/db.sqlite `
  --v2-db docs/db_v2.sqlite `
  --out toolbase/data
```

Routine data work should flow through reviewed proposal/import files. Do not edit any SQLite file by hand.

The first completed review is the 12-row Kennametal TopSwiss cutting-data pilot. The next packet, `kennametal-topswiss-identity-batch-01.json`, contains 25 exact catalog-row matches and is intentionally pending. Run `serve_review.py` and open `http://127.0.0.1:8765/` to compare the current record, proposal, and rendered manufacturer page on a phone or desktop. Decisions stay in browser storage until the ledger is exported.

Schema-2 proposals are immutable and non-importable by themselves. `review_batch.py compile` requires a complete hash-bound ledger. Approved rows compile into a reviewed import; rejected or quarantined rows compile only into quarantine state. Pending rows make compilation fail. Do not place a compiled file under `data/reviewed_imports` until the batch has actually been reviewed.

For a future review, keep this order:

1. Extract a proposal without changing its source-derived fields.
2. Record one human decision for every row in a separate review ledger.
3. Record approved, approved-with-corrections, rejected, or quarantined for every row.
4. Set `status=complete` and `import_allowed=true` only after no decision remains pending.
5. Compile, rebuild, audit, and test. Never edit the compiled import or SQLite output by hand.

## Accuracy Contract

- Missing data is valid; invented data is not.
- Material recommendations are promoted only from exact human-reviewed manufacturer evidence. Legacy structured claims are retained in a separate audit-only section and do not power filters.
- A grade is a manufacturer entity. Tool/grade options retain the full order number, availability, source page/table, extraction method, reviewer, and review batch.
- Compatibility records are claims with evidence and review status, not guaranteed fit.
- Physical compatibility flows from the machine station outward: `station -> holder -> insert` or `station -> shank -> module -> insert`. Adapters appear only when physically required.
- The ECAS-20 shop rule assigns holders and modular shanks only by an exact, source-backed machine-side shape and nominal-size match. Descriptions, names, sizes, and tags alone do not create station fit.
- Facts and material recommendations separate source presence from verification and can retain page, table, raw excerpt, extraction method, review batch, reviewer, and review date. Compatibility lineage roles distinguish direct proof from legacy row context and derivation inputs.
- Direct insert-to-machine shortcuts are retained for audit history but suppressed from valid compatibility paths.
- Speeds and feeds require an exact tool/grade/geometry, work material, operation, source range (including the manufacturer's start value when supplied), source unit, and review status.
- Only `catalog_verified` or `manufacturer_verified` cutting profiles may appear as usable recommendations. Shop observations may be retained elsewhere, but are not manufacturer recommendations.

See [the first-principles review](../docs/FIRST_PRINCIPLES_REVIEW.md) for the diagnosis and roadmap.
