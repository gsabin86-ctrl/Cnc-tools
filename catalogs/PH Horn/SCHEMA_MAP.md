# PH Horn — Schema Map
_Read this before extracting any Horn catalog data. Maps Horn conventions to the canonical `tools` table schema._

---

## Naming Conventions

### Insert Part Numbers
Horn uses proprietary part numbers — not ISO. Pattern:

| Prefix | Meaning |
|--------|---------|
| `R105.xxxx` | Right-hand, System 105 |
| `L105.xxxx` | Left-hand, System 105 |
| `RA105.xxxx` | Right-hand alternate geometry, System 105 |
| `R108.xxxx` | Right-hand, System 108 |
| `A110.xxxx` | System 110 face grooving |
| `R110.xxxx` | Right-hand, System 110 |
| `R106.xxxx` | Right-hand, System 106 |
| `L106.xxxx` | Left-hand, System 106 |

General pattern: `[hand][system].[geometry].[size].[variant]`

### Holder Part Numbers
Pattern: `[hand]B[system].[shank_mm].[variant]`

| Example | Meaning |
|---------|---------|
| `B105.0022.02` | System 105, 22mm shank, variant 02 (neutral/standard) |
| `RB106.0012.01` | Right-hand, System 106, 12mm shank, variant 01 |
| `LB106.0012.01` | Left-hand, System 106, 12mm shank, variant 01 |
| `B108.0006.01A` | System 108, 6mm shank, variant 01A (internal coolant) |
| `B111.0012.2.00` | System 111, 12mm shank, 2= (variant) |

Shank diameter is the 4-digit middle field in mm (e.g. `0012` = 12mm, `0022` = 22mm).

---

## Grade Codes → Schema Field Mapping

Horn grades go in the **`grade`** field, NOT chipbreaker.

| Horn Grade | Meaning | Use |
|------------|---------|-----|
| `53GE` | Universal carbide | General machining, most materials |
| `53HT` | Hard turning carbide | Hardened steels, interrupted cuts |
| `52IT` | Internal turning carbide | Bore work, internal operations |
| `TH35` | PVD-coated carbide | Stainless, titanium |
| `EG35` | Carbide, fine grain | Non-ferrous, aluminium |
| `IG35` | Cermet | Fine finishing steels |

**`chipbreaker` field:** Set to `"N/A"` for all Horn inserts — Horn geometry is integral to the insert form, not a separate chipbreaker feature.

---

## System Reference

| System | Primary Use | Min Bore / OD | Shank Sizes |
|--------|------------|---------------|-------------|
| 105 | Supermini grooving/boring | Ø ≥ 5mm | 16mm, 22mm |
| 106 | Small grooving/boring/chamfer | Ø ≥ 6mm | 12mm |
| 107 | Grooving/boring/chamfer/thread | Ø ≥ 7mm | 12mm |
| 108 | Circlip (DIN 471/472), grooving, boring | Ø ≥ 8mm | 6, 8, 12mm |
| 109 | Mini grooving/boring | Ø ≥ 6mm | 16mm |
| 10P | Medium grooving/boring/undercut | Ø ≥ 9mm | 12mm |
| 110 | Small boring/grooving/face grooving | Ø ≥ 6mm | 16, 20, 22, 25mm |
| 111 | Circlip grooving (DIN 471/472) | Ø ≥ 11mm | 8, 12mm |

---

## Field-by-Field Mapping

| Schema Field | Horn Source | Notes |
|---|---|---|
| `json_id` | Horn part number verbatim | e.g. `R105.0150.7.6` |
| `manufacturer` | `"PH Horn"` | Always |
| `component_type` | `"insert"` or `"holder"` | |
| `category` | `"Grooving Inserts"` / `"Boring Inserts"` / `"Threading Inserts"` / `"Circlip Grooving Inserts"` / `"Turning Holders"` | Pick most specific |
| `type` | `"PH Horn System [N] [operation] Insert"` | e.g. `"PH Horn System 108 Circlip Grooving Insert"` |
| `shape` | `null` | Horn inserts have no ISO shape code |
| `chipbreaker` | `"N/A"` | Always for Horn inserts |
| `grade` | Grade code from catalog | e.g. `"53GE"` |
| `geometry` | Brief description | e.g. `"full-radius grooving"`, `"boring"`, `"60° threading"` |
| `size` | Primary dimension string | e.g. `"groove width 1.5mm"` or `"r0.2mm"` |
| `specs` | JSON object | See spec fields below |
| `insert_seat` | `null` for inserts | Only on holders |
| `mounts_to` | `null` for inserts | Only on holders/modules |
| `sources` | `["PH Horn Supermini-Mini Catalog, p.XXX"]` | Include page number |
| `tags` | Array of relevant terms | See tagging guide below |

---

## Spec Fields by Operation Type

### Grooving inserts
```json
{
  "system": "108",
  "operation": "grooving",
  "groove_width_mm": 1.5,
  "cutting_depth_max_mm": 3.0,
  "corner_radius_RE": 0.2,
  "min_bore_diameter_mm": 8.0,
  "hand": "Right"
}
```

### Boring inserts
```json
{
  "system": "110",
  "operation": "boring",
  "corner_radius_RE": 0.2,
  "min_bore_diameter_mm": 6.0,
  "hand": "Right"
}
```

### Circlip grooving inserts
```json
{
  "system": "108",
  "operation": "circlip grooving",
  "din_standard": "DIN 471",
  "groove_width_mm": 0.94,
  "shaft_diameter_range_mm": "8-9",
  "hand": "Right"
}
```

### Threading inserts
```json
{
  "system": "108",
  "operation": "threading",
  "thread_angle_deg": 60,
  "pitch_mm": 1.0,
  "min_bore_diameter_mm": 8.0,
  "hand": "Right"
}
```

### Holders
```json
{
  "system": "106",
  "shank_shape": "square",
  "shank_size_mm": 12,
  "hand": "Right",
  "coolant": "standard"
}
```

---

## Tagging Guide

Always include:
- `"PH Horn"`, `"Horn"`, `"Swiss-type"`
- System number: `"System 105"`, `"System 108"` etc.
- Operation: `"grooving"`, `"boring"`, `"threading"`, `"circlip"`, `"chamfering"`, `"undercut"`, `"face grooving"`
- Hand: `"right-hand"` or `"left-hand"` (omit for neutral)
- Grade name: `"53GE"`, `"53HT"`, etc.
- DIN standard if applicable: `"DIN 471"`, `"DIN 472"`

---

## Anchor Examples (verified, in DB)

### Holder
```json
{
  "json_id": "B105.0022.02",
  "component_type": "holder",
  "manufacturer": "PH Horn",
  "type": "PH Horn System 105 Toolholder",
  "shape": null,
  "chipbreaker": null,
  "grade": null,
  "insert_seat": "HWS 105225",
  "mounts_to": "ECAS20_GANG_BLOCK",
  "specs": {"system":"105","shank_shape":"round","shank_size_mm":22,"hand":"Neutral","coolant":"standard"}
}
```

### Grooving insert
```json
{
  "json_id": "R108.PG08.02",
  "component_type": "insert",
  "manufacturer": "PH Horn",
  "type": "PH Horn System 108 Circlip Grooving Insert",
  "shape": null,
  "chipbreaker": "N/A",
  "grade": "53GE",
  "specs": {"system":"108","operation":"circlip grooving","din_standard":"DIN 471","groove_width_mm":0.74,"shaft_diameter_range_mm":"8-9","hand":"Right"}
}
```

---

## Common Mistakes to Avoid

- ❌ Don't put grade codes in `chipbreaker` field — they go in `grade`
- ❌ Don't invent ISO shape codes for Horn inserts — `shape` is null
- ❌ Don't omit the catalog page number from `sources`
- ❌ Don't use `"N/A"` for `grade` on graded inserts — only holders/ungraded items
- ✅ Always set `chipbreaker = "N/A"` for Horn inserts
- ✅ Always include system number in both `type` and `tags`
- ✅ `mounts_to` on inserts is always `null`
