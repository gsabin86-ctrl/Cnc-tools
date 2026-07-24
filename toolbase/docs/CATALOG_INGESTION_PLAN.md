# Catalog Ingestion Plan

The catalog folder is the raw manufacturer library. The database should not absorb it all at once. Catalogs need to be mapped, categorized, extracted into proposals, reviewed, and only then applied.

The three priorities are:

- Compatibility: inserts to holders, holders to modules, modules to shanks, adapters/bushings to stations, and all critical interface details.
- Searchability: clean categories, component types, names, dimensions, grades, and source-backed specs.
- Auditability: every claim traces back to manufacturer catalog pages or manufacturer product pages.

## Catalog Registry First

Before extracting tools, each catalog gets a registry record.

Important fields:

| Field | Purpose |
|-------|---------|
| `catalog_id` | Stable ID for scripts and review notes. |
| `manufacturer` | Manufacturer or best-known source owner. |
| `title` | Human-readable catalog title. |
| `file_path` | Path to the local source file. |
| `source_type` | Usually `manufacturer_catalog`. |
| `catalog_year` | Year/version when known. |
| `machining_categories` | Turning, grooving, threading, boring, milling, drilling, Swiss tooling, etc. |
| `component_types` | Insert, holder, module, shank, adapter, bushing, spare, endmill, drill, reamer, etc. |
| `compatibility_targets` | Which fit relationships this catalog can prove. |
| `extraction_status` | `not_started`, `mapped`, `partially_extracted`, `extracted`, `reviewed`, or `retired`. |
| `review_status` | `needs_review`, `approved_scope`, `blocked`, or `not_relevant`. |

The registry is a map, not extracted tool data.

## Category And Component Type

Machining category and component type stay separate.

Examples:

| Machining category | Component type |
|-------------------|----------------|
| turning | insert |
| turning | holder |
| swiss_tooling | module |
| swiss_tooling | shank |
| grooving | insert |
| grooving | holder |
| threading | insert |
| threading | holder |
| milling | endmill |
| drilling | drill |

This matters because compatibility uses component type. An insert does not connect to the machine the same way a module or shank does.

## Compatibility Evidence

Catalog extraction should look for compatibility claims separately from basic specs.

Target relationships:

| Relationship | Meaning |
|--------------|---------|
| `accepts_insert` | Holder/module accepts an insert seat, insert family, or exact insert. |
| `mounts_to` | Tooling component mounts to another component. |
| `adapts_to` | Bushing/adapter changes one physical interface into another. |
| `compatible_with_machine` | Tooling is compatible with a specific machine/station after shop verification. |
| `replaces` | Manufacturer-supported replacement/supersession. |

Machine/station fit can wait until machine data is available. Catalog rows can still capture holder-seat, module-shank, and adapter-interface facts first.

Critical interface fields:

- insert seat / ISO designation
- holder pocket or insert family
- shank shape: round or square
- shank size
- module connection
- adapter/bushing input and output interface
- handedness/orientation
- coolant-through details when present
- screws, clamps, wedges, and spare part links when present

## Extraction Workflow

1. Draft or update catalog registry.
2. Greg reviews scope and priority.
3. Pick one catalog section and one component type.
4. Extract into proposal JSON only.
5. Validate proposal.
6. Review source pages/tables with Greg.
7. Apply with a script only after approval.
8. Audit database.

Recommended batch sizes:

- Cutting data: 10-25 insert/material/operation rows.
- Compatibility claims: 25-100 source-backed relationships.
- Basic catalog tools/specs: 25-100 rows, depending on table clarity.

Compatibility proposals should preserve the exact level of evidence from the source. If a catalog says a module accepts an insert seat such as `DCMT 11 T3 02`, record that as an insert-seat compatibility claim. Do not automatically promote it into every matching insert SKU until the database has a reviewed rule for that expansion.

## Agentic Task Boundaries

Agents can:

- map catalog files
- identify sections and tables
- extract candidate tool/spec/compatibility rows
- produce proposal JSON
- summarize gaps and ambiguity

Agents should not:

- hand-edit SQLite outside the reviewed apply scripts
- invent missing dimensions
- infer cutting data from similar tools
- mark machine compatibility without Greg/shop verification
- merge component types together for convenience

## Near-Term Sequence

1. Create and maintain `toolbase/catalogs/registry.json`.
2. Select one reviewed catalog section and one component type.
3. Extract source-backed compatibility or cutting-data proposal rows.
4. Validate and review the source pages/tables.
5. Apply only approved rows with `catalogs:compat:apply` or `cutting-data:apply`.
6. Audit database counts and source coverage.
