# CNC Toolbase: First-Principles Review

## Executive Summary

The tooling data is recoverable and valuable. The project is not suffering from SQLite corruption; it is suffering from several generations of experiments sharing one repository and from a data model that confuses a tool record, a sourced fact, a compatibility claim, and a published website.

The local checkout is the same repository as `https://github.com/gsabin86-ctrl/Cnc-tools.git`. The live branch is `master`. The local `codex-repo-hygiene` branch contains eight additional cleanup/data-model commits, plus uncommitted changes to `docs/index.html` and `docs/db.sqlite`.

The v3 rebuild lives at `docs/v3/`. On 2026-07-21 the previous hosted page was copied byte-for-byte to `archive/database-cleanup/legacy-hosted-index-2026-07-21.html`, and the root page was replaced with a local redirect to v3. The legacy SQLite files are not used by the new runtime.

## What Is Actually Here

| Asset | Confirmed state | Decision |
|---|---:|---|
| Legacy production tools | 1,212 valid rows | Preserve every row in reviewable JSONL. |
| Shop-confirmed machine stations | 10 | Publish as typed station records with direct shop-note lineage. |
| Inserts | 1,088 | Useful catalog seed, but overrepresented. |
| Holders | 63 | High-priority verification/expansion area. |
| Modules | 44 | High-priority compatibility area. |
| Shanks | 10 | High-priority machine-stack area. |
| Adapters | 3 | Keep, but require shop-note evidence and typed interfaces. |
| Sources | 176 normalized references | Retain; improve URL/file/page locators. |
| Imported and reviewed facts | 12,017 | Retain original keys and values; normalize conservatively. |
| Fact/source lineage links | 12,288 | Retain the row sources behind every sourced imported fact. |
| Compatibility candidates | 694 | Keep as claims; none should silently become guaranteed fit. |
| Compatibility lineage links | 1,200 | Distinguish direct proof, record context, and derivation inputs. |
| Explicit material recommendations | 344 across 203 tools | Publish with evidence labels. Do not infer from tags. |
| Verified cutting profiles | 12 | Publish the completed TopSwiss pilot with its source page, table, and reviewer. |
| Catalog registry | 48 catalogs; 39 not started, 8 mapped, 1 partially extracted | Extract selectively by value, not wholesale. |

Both original SQLite files and the v3 build pass integrity and foreign-key checks.

## Confirmed Problems

### 1. The current application contains unrelated product ideas

Firebase authentication, reviews, replies, favorites, commerce tables, inventory, and listings obscure the core job. They add latency and failure modes without improving the tooling reference.

Decision: v3 contains tools, facts, sources, materials, interfaces, compatibility claims, and cutting data only.

### 2. The browser is coupled directly to a binary database

The current page downloads `db.sqlite`, downloads a SQLite WebAssembly runtime from a CDN, executes a query, then contains all application code and styling in one very large HTML file.

Decision: SQLite is still the queryable database, while a deterministic build emits a static JSON projection for GitHub Pages. The v3 page has no runtime dependency or Firebase initialization.

### 3. “Normalized v2” copied inconsistencies instead of resolving them

The legacy `specs` objects contain 221 distinct keys, including casing and naming variants. The old migration placed nearly all of them into a generic fact table and extracted the first number from any string, which caused prose such as compatibility notes to acquire misleading numeric values.

Decision: v3 preserves the original key, applies only a small explicit alias map, and parses a numeric fact only when the entire source value is numeric. Ranges and prose remain text until a category-specific importer understands them.

### 4. Compatibility shortcuts violate the physical model

There are 172 direct `compatible_with_machine` claims: 160 start at inserts and 12 start at holders. An insert does not physically fit a machine station; it must be reached through the actual holder stack.

Decision: these records remain in the audit trail but are suppressed. Valid fit starts at the machine station and follows one of these typed paths:

```text
machine station → holder → insert
machine station → shank → module → insert
```

An adapter or bushing is inserted only where the physical station-to-tool connection requires it.

### 5. Source presence was being confused with verification

A catalog title or manufacturer URL is useful provenance, but its mere presence does not prove that every imported field was checked.

Decision: v3 separates evidence type from review status. “Catalog source” means traceable to a catalog reference, not human-verified truth. Facts and material recommendations carry their own review metadata; compatibility and cutting data carry their own review state.

### 6. The schema and built v2 database drifted apart

The checked-in v2 schema includes cutting-data tables, while `docs/db_v2.sqlite` does not. Its metadata still reports schema version 2.2.0.

Decision: the v3 database is rebuilt from source every time, audited, and tested for deterministic output. A stale binary can no longer define the schema by accident.

## Product Definition

The useful product has four jobs:

1. Find a tool quickly by part number, manufacturer, component, grade, shape, chipbreaker, material, or catalog fact.
2. Show typed specs and the original imported facts without pretending every field is verified.
3. Show recommended work materials only when an explicit source field supports the recommendation.
4. Show speeds, feeds, and DOC only when the exact tool context and source have been reviewed.

Compatibility is a fifth job, but it remains a candidate/evidence system until the physical interfaces and shop fit are documented.

## Cutting-Data Rules

The existing `CUTTING_DATA_PLAN.md` is directionally correct and remains the basis of the v3 table.

One cutting profile represents one exact combination of:

- tool part number;
- grade and geometry/chipbreaker context;
- ISO work-material group and subgroup;
- operation and cut condition;
- coolant condition when supplied;
- surface-speed minimum, manufacturer start, and maximum in source units when supplied;
- feed range in source units;
- depth-of-cut range in source units;
- manufacturer source and page/table reference;
- extraction and review status.

The UI may use only profiles marked `catalog_verified` or `manufacturer_verified`. Proposed, extracted, shop-observed, ambiguous, and rejected rows remain review data rather than manufacturer recommendations.

The two pilot parts named in the old guide—Sandvik DNMG 432-PM 4425 and DCGT 3(2.5)1-UM 1205—are not present in the current 1,212-row seed. The first pilot should instead use 10–25 real database records from one manufacturer/family whose exact grade and source chart are locally available.

The first completed review covers 12 exact-match Kennametal TopSwiss inserts. The extracted proposal remains immutable and non-importable by itself; the separate decision ledger records 12 human decisions, 9 of them with corrections, and explicitly authorizes import. A deterministic compiler emits the reviewed build input, and the v3 build verifies both file hashes before publishing 12 `catalog_verified` profiles. Each profile preserves Kennametal's MIN/START/MAX speed values, source units, product and parameter pages, exact ANSI/ISO catalog numbers, grade, geometry, reviewer, and the accepted page-18 source ambiguity.

## Recommended Sequence

### Phase 1 — Stable foundation (implemented in v3)

- Preserve all current tools and unique v2 claims in JSONL.
- Build a minimal SQLite schema deterministically.
- Publish a dependency-free JSON projection.
- Audit data loss, foreign keys, aliases, sources, compatibility shortcuts, materials, and cutting-data coverage.
- Keep the current root page unchanged while v3 is reviewed.

### Phase 2 — Identity and spec cleanup

- Prioritize holders, modules, shanks, and adapters before importing hundreds more inserts.
- Review one manufacturer/family at a time.
- Establish category-specific field dictionaries and units.
- Convert placeholders such as “not specified” to missing values.
- Attach exact catalog file and page to reviewed facts.

### Phase 3 — Work-material coverage

- Preserve the 191 tools with explicit ISO material groups.
- Extract explicit material recommendations for the remaining high-use inserts.
- Keep material group, grade, chipbreaker, and operation together.
- Never promote free-form tags into source-backed recommendations.

### Phase 4 — Speeds and feeds

- Select one 10–25 tool pilot from an actual catalog family in the seed.
- Extract into a proposal file; do not write SQLite directly.
- Validate part/grade/geometry/material/operation/ranges/units/source.
- Review against the actual page or table.
- Publish only approved rows and show source units exactly as printed.
- Add display-only metric/imperial conversion after the source data is trustworthy.

### Phase 5 — Physical compatibility

- Define round-shank, square-shank, modular, adapter input/output, and station interfaces.
- Capture size, shape, handedness/orientation, pocket depth, coolant alignment, and clearance when relevant.
- Replace direct machine shortcuts with traversable paths.
- Mark physical machine fit `shop_verified` only after confirmation.

### Phase 6 — Promote and publish

- Review `docs/v3/` locally and on the deployed GitHub Pages origin.
- The root promotion and byte-for-byte legacy archive are complete.
- Commit the source seed, schema, scripts, tests, website, and generated published data.
- Merge or rebase the eight cleanup commits onto the chosen publishing branch.
- Push to the GitHub Pages source branch and smoke-test `cnctoolbase.com`.

## Current v3 Audit Baseline

```text
tools:                         1,222 (1,212 legacy + 10 shop-confirmed stations)
manufacturers:                     9
sources:                         177
tool/source links:              1,290
facts:                         12,057
fact/source lineage links:     12,328
material recommendations:        344 (203 tools)
material/source links:            344
interfaces:                       893
compatibility claims:             736
compatibility/source links:      1,289
review batches:                     1
shop-input batches:                 1
reviewed tool tags:               164
verified cutting profiles:         12
database integrity:                 ok
foreign-key issues:                  0
```

Known work remains visible rather than hidden: three legacy tools have no source, four source records lack a usable locator, 694 legacy compatibility claims need review, and material/cutting-data coverage is incomplete. The ten ECAS-20 station-to-machine records and 32 exact-interface station-fit records are accepted and shop-verified. The 16 mm square stations each accept the four currently source-established 16x16 tools (`DGTR 16B-2D25SH`, `KM16NCM10400`, `KM16RCM1616100HPC`, and `QSM16-N1616`); the 22 mm round stations each accept `B105.0022.02` and `B110.0022.02`. The 16 mm round `B110.0016.02` is deliberately excluded from the square stations.
