# Iscar — Schema Map
_Read this before extracting any Iscar catalog data. Maps Iscar conventions to the canonical `tools` table schema._

---

## Naming Conventions

### Insert Part Numbers
Iscar uses ISO-based naming with their own grade suffix.

**Format:** `[ISO_shape_size_RE]-[GRADE]`
Examples:
- `CCMT 09T304-IC807` — CCMT insert, 9.53mm IC, r0.4mm, grade IC807
- `DCMT 11T304-IC907` — DCMT insert, 11mm IC, r0.4mm, grade IC907

Use the full string including grade as `json_id`: `CCMT 09T304-IC807`

### Swiss Holder Part Numbers
Pattern: `[style]-[shank_height][shank_width][shank_length]-[insert_size]S`

Examples:
- `SCACR-1010K-09S` — SCAC style, 10x10mm shank, K-length, 09 insert size, Swiss
- `SDJCR-0808K-07S` — SDJC style, 8x8mm shank, K-length, 07 insert size, Swiss
- `SVJCR-1212K-11S` — SVJC style, 12x12mm shank, K-length, 11 insert size, Swiss
- `DGTR 16B-2D25SH` — DGT right-hand, 16mm body, 2mm blade, 25mm parting diameter, Swiss

The trailing `S` denotes Swiss-type holder.

---

## Grade Codes

| Grade | Type | Application |
|-------|------|-------------|
| `IC807` | PVD TiAlN carbide | Stainless steel, finishing |
| `IC907` | PVD TiAlN carbide | Steel, medium-finishing |
| `IC08` | CVD carbide | Stainless, light interrupted |
| `IC20` | Cermet | Fine finishing, steels |
| `IC328` | PVD carbide | General steel turning |
| `IC9007` | PVD nano-layer | Stainless + steel |
| `IC9015` | PVD nano-layer | Stainless, difficult materials |

Grade goes in the **`grade`** field.

---

## Insert Shapes (Iscar Swiss catalog)

| Code | Included Angle | Tolerance | Notes |
|------|---------------|-----------|-------|
| `CCMT` | 80° diamond | M (molded) | Most common Swiss insert |
| `DCMT` | 55° diamond | M (molded) | Profiling |
| `VCMT` | 35° diamond | M (molded) | Profiling, tight spaces |
| `CCGT` | 80° diamond | G (ground) | Finishing |
| `DCGT` | 55° diamond | G (ground) | Finishing/profiling |

Shape goes in the **`shape`** field.

---

## Holder Styles → Insert Compatibility

| Holder Style | Insert Seat | Notes |
|---|---|---|
| `SCAC` | CCMT/CCGT | 80° diamond, S-clamp |
| `SDJC` | DCMT/DCGT | 55° diamond, screw clamp |
| `SVJC` | VCMT/VCGT | 35° diamond, screw clamp |
| `DGT` / `DGL` | DGN/DGR/DGL grooving | Iscar grooving blade system |

---

## Field-by-Field Mapping

| Schema Field | Iscar Source | Notes |
|---|---|---|
| `json_id` | Full part number incl. grade | e.g. `CCMT 09T304-IC807` |
| `manufacturer` | `"Iscar"` | Always |
| `component_type` | `"insert"` or `"holder"` | |
| `category` | `"Turning Inserts"` / `"Swiss Turning Holders"` / `"Grooving Holders"` | |
| `type` | `"Iscar [SHAPE] Insert"` or `"Iscar Swiss [style] Holder"` | |
| `shape` | ISO shape code | e.g. `"CCMT"` |
| `chipbreaker` | `null` for standard Iscar Swiss inserts | Iscar Swiss catalog doesn't use chipbreaker suffixes |
| `grade` | Grade code | e.g. `"IC807"` |
| `geometry` | `"positive"` for all Swiss catalog inserts | |
| `size` | ISO size code | e.g. `"CCMT 09T304"` |
| `insert_seat` | For holders only | e.g. `"CCMT 09T3"` |
| `mounts_to` | `"ECAS20_GANG_BLOCK"` for 16mm square shank holders | Verify shank size |
| `sources` | `["Iscar Miniature Parts Catalog, p.XXX"]` | Include page |

---

## Spec Fields (Swiss inserts)
```json
{
  "iso_designation": "CCMT 09T304",
  "insert_shape": "CCMT",
  "included_angle": "80 deg",
  "inscribed_circle_D": "9.53 mm",
  "thickness_S": "3.97 mm",
  "corner_radius_RE": "0.4 mm",
  "cutting_direction": "Neutral",
  "tolerance_class": "M"
}
```

### Spec Fields (Swiss holders)
```json
{
  "shank_height": "10 mm",
  "shank_width": "10 mm",
  "overall_length": "100 mm",
  "cutting_direction": "Right Hand",
  "measurement_type": "Metric"
}
```

---

## Tagging Guide

Always include:
- `"Iscar"`, `"Swiss-type"`
- Shape: `"CCMT"`, `"DCMT"` etc.
- Grade: `"IC807"`, `"IC907"` etc.
- Holder style if applicable: `"SCAC"`, `"SDJC"`, `"SVJC"`
- Operation: `"turning"`, `"grooving"`, `"profiling"` etc.
- Hand if not neutral: `"right-hand"`, `"left-hand"`

---

## Anchor Example (verified, in DB)

```json
{
  "json_id": "SCACR-1010K-09S",
  "component_type": "holder",
  "manufacturer": "Iscar",
  "type": "Iscar Swiss SCAC Turning Holder",
  "shape": null,
  "chipbreaker": null,
  "grade": null,
  "insert_seat": "CCMT 09T3 / CCGT 09T3",
  "mounts_to": "ECAS20_GANG_BLOCK",
  "specs": {
    "shank_height": "10 mm",
    "shank_width": "10 mm",
    "cutting_direction": "Right Hand"
  },
  "sources": ["Iscar Miniature Parts Catalog, p.XXX"],
  "tags": ["holder","Swiss-type","SCAC","CCMT","Iscar","right-hand","10mm-shank"]
}
```

---

## Common Mistakes to Avoid

- ❌ Don't omit the grade from `json_id` — `CCMT 09T304-IC807` not just `CCMT 09T304`
- ❌ Don't set `mounts_to` on 8mm shank holders without confirming ECAS20 compatibility
- ❌ Don't add chipbreaker codes that aren't in the catalog — leave null if not specified
- ✅ Left-hand holders (SCACL, SDJCL, SVJCL) are separate entries from right-hand
- ✅ Each grade variant is a separate DB entry
- ✅ `insert_seat` should list both ground (CCGT) and molded (CCMT) variants when both fit
