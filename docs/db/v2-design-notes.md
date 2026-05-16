# CNC Toolbase V2 Data Model

This schema is meant to turn the current Swiss tooling archive into a verifiable catalog and future commerce platform.

## Principles

- Catalog facts and sellable inventory are separate.
- Compatibility is stored as edge records, not loose arrays.
- Technical claims should carry source evidence.
- Category-specific specs live in category tables, while shared search/catalog fields live in `catalog_tools`.
- Customer behavior such as favorites and reviews attaches to catalog tools, not one-off inventory listings.

## Main Layers

- `catalog_tools`: shared product/catalog records for all tool categories.
- `swiss_tool_specs`: Swiss-specific fields migrated from the current database.
- `solid_carbide_specs`: placeholder for drills, endmills, reamers, threadmills, and similar round tools.
- `tool_specs`: flexible key/value specs for filtering and source-backed verification.
- `sources`, `tool_sources`, `tool_spec_sources`: provenance.
- `compatibility_edges`, `compatibility_edge_sources`: verifiable compatibility tree.
- `inventory_items`, `listings`, `orders`, `order_items`: commerce.
- `user_profiles`, `favorite_tools`, `tool_reviews`: customer-facing account features.

## Verification Status Meaning

- `unverified`: present in the database but not backed by a source.
- `imported`: imported from the old DB; source quality may vary.
- `catalog_claim`: backed by a catalog reference or local/text source.
- `manufacturer_verified`: backed by a manufacturer product page or manufacturer-hosted source.
- `shop_verified`: confirmed by real shop use or internal setup notes.
- `rejected`: kept for audit/history but known incorrect.

## Migration Notes

The migration script creates `db_v2.sqlite` from `db.sqlite` and refuses to overwrite an existing v2 database.

Run:

```bash
npm run db:v2
npm run db:v2:apply
```

Current Swiss tooling rows land in `swiss-tooling`, while `solid-carbide`, `endmills`, and `drills` are seeded for future sessions.
