# Compatibility Model

The compatibility model is a tree/graph of physical fit, not just a list of matching inserts.

The goal is to answer questions like:

- Which inserts fit this holder?
- Which holder/module accepts this insert?
- Does this holder fit a machine station directly?
- Is a bushing or adapter needed between the tool and the station?
- Is the connection round shank, square shank, modular, or another interface?

## Core Chain Examples

### Direct Round-Shank Tooling

When the holder shank and machine station match, no bushing is needed.

```text
insert -> holder -> machine station
```

Example:

```text
insert -> 22 mm round holder -> 22 mm round station
```

### Round-Shank Tooling With Bushing

When the holder shank is smaller than the machine station, a bushing/adaptor is part of the compatibility path.

```text
insert -> holder -> bushing -> machine station
```

Example:

```text
insert -> 8 mm round holder -> 8 mm to 22 mm round bushing -> 22 mm round station
```

### Modular / Square-Shank Tooling

For modular tooling, the path may include an insert, module, shank adapter, and gang block connection.

```text
insert -> module -> shank adapter -> gang block / machine station
```

Example:

```text
insert -> KM Micro module -> square shank adapter -> square gang block station
```

## Critical Fit Attributes

Compatibility must distinguish physical interface type. Diameter alone is not enough.

Important attributes include:

- Shank shape: round vs square.
- Shank size: for example 8 mm, 10 mm, 12 mm, 16 mm, 22 mm.
- Station shape: round bore, square gang slot, modular receiver, or other.
- Station size.
- Orientation/handedness where relevant.
- Coolant alignment where relevant.
- Pocket depth and clearance where relevant.

Square-shank and round-shank tooling are not interchangeable just because a nominal size looks similar.

## Adapter Rows

Generic bushing rows are valid compatibility nodes when they represent a real shop adapter.

They should not be deleted just because they are generic. They do, however, need evidence:

- `source_type = shop_note` when based on an actual shop adapter.
- clear size/shape fields such as `from_shape`, `from_size_mm`, `to_shape`, and `to_size_mm`.
- compatibility edges such as holder-to-bushing and bushing-to-station.

## Verification Rule

Catalog fit and physical machine fit are different claims.

- Catalog data can support insert-to-holder or module-to-shank compatibility.
- Machine-station fit should be marked `shop_verified` only after physical verification.
- Inferred size/seat matches should remain `inferred` until checked.
