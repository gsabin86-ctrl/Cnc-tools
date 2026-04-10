# Kennametal — Schema Map
_Read this before extracting any Kennametal catalog data. Maps Kennametal conventions to the canonical `tools` table schema._

---

## Naming Conventions

### TopSwiss Insert Part Numbers
Kennametal uses **dual naming** — ANSI and ISO. Both go in `specs`. Use ISO as `json_id`.

**ANSI format:** `[shape][size_ansi][chipbreaker]`
Example: `CCGT21502MRPPS`
- `CCGT` — shape
- `215` — IC size in 32nds of inch (21 = 6.35mm, 32 = 9.53mm)
- `02` / `05` / `1` — corner radius code (02=0.1mm, 05=0.2mm, 1=0.4mm, 2=0.8mm)
- `MR` — metric, right-hand (or `ML` = left)
- `PPS` — chipbreaker code

**ISO format:** `[shape][IC_mm][thickness][corner_radius][hand][chipbreaker]`
Example: `CCGT060201MRPPS`
- `CCGT` — shape
- `06` — IC in mm (06=6.35mm, 09=9.53mm)
- `02` — thickness code
- `01` — corner radius in 0.1mm steps (01=0.1, 02=0.2, 04=0.4, 08=0.8)
- `MR` — metric right (ML = left)
- `PPS` — chipbreaker

**Use ISO as `json_id`.** Store ANSI in `specs.ansi_catalog_id`.

### KM16 Module/Shank Part Numbers
Pattern: `KM16[function][size]`
- `KM16NCM10400` — KM16 neutral clamping module
- `KM16NSR220` — KM16 neutral square right, 2mm groove
- `KM16SDJCR1120` — KM16, S-clamp, D-shape insert, J-rake, C-clearance, right-hand, 11mm IC, 20mm length

---

## Grade Codes → Schema Field Mapping

| Kennametal Grade | Type | Application |
|-----------------|------|-------------|
| `KCP20S` | PVD-coated carbide | Finishing/medium, steels + stainless |
| `KCM25S` | CVD-coated carbide | Medium, stainless priority |
| `KCS25S` | PVD-coated carbide | Difficult materials, stainless/exotics |
| `KN10S` | Cermet | Fine finishing, steels + non-ferrous |
| `KTP25S` | PVD-coated carbide | General purpose Swiss-type, all ops |

Grade goes in the **`grade`** field. These are Swiss-specific grades (S suffix = Swiss optimized).

---

## Chipbreaker Codes

| Code | Name | Use |
|------|------|-----|
| `PPS` | Positive Polished Swiss | General finishing, sharp edge |
| `LFS` | Low Feed Swiss | Light finishing, very low feed |
| `FFS` | Fine Finishing Swiss | Fine finishing, stainless |
| `MWS` | Medium Wiper Swiss | High-feed medium finishing |
| `MPS` | Medium Polish Swiss | Medium finishing |
| `FWS` | Fine Wiper Swiss | High-feed fine finishing |
| `FPS` | Fine Polish Swiss | Superior surface finish |

Chipbreaker goes in the **`chipbreaker`** field AND in the `json_id` (it's part of the ISO part number).

---

## Insert Shapes

| Code | Included Angle | Notes |
|------|---------------|-------|
| `CCGT` | 80° diamond | Positive, ground, Swiss finishing |
| `CCET` | 80° diamond | Positive, ground, eccentric relief, left or right hand |
| `CCMT` | 80° diamond | Positive, molded |
| `DCGT` | 55° diamond | Positive, ground, profiling |
| `DCET` | 55° diamond | Positive, ground, eccentric |
| `DCMT` | 55° diamond | Positive, molded |
| `VBMT` | 35° diamond | Positive, molded, used in KM16 modules |
| `VBGT` | 35° diamond | Positive, ground |
| `SCMT` | 90° square | Positive, molded |
| `TCMT` | 60° triangle | Positive, molded |

Shape goes in the **`shape`** field verbatim (e.g. `"CCGT"`).

---

## Tolerance Classes

| Code | Meaning |
|------|---------|
| `G` | Ground, tight tolerance (CCGT, DCGT) |
| `E` | Eccentric relief ground (CCET, DCET) |
| `M` | Molded (CCMT, DCMT, VBMT) |

Store in `specs.tolerance_class`.

---

## Hand Codes in Part Numbers

| Code | Meaning |
|------|---------|
| `MR` / (no suffix on some) | Neutral or right-hand |
| `ML` | Left-hand |
| `R` (in CCET/DCET) | Right-hand |
| `L` (in CCET/DCET) | Left-hand |

Store in `specs.cutting_direction` as `"Right"`, `"Left"`, or `"Neutral"`.

---

## Standard IC Sizes (TopSwiss)

| ANSI code | IC mm | Thickness mm |
|-----------|-------|-------------|
| `21x` | 6.35 | 2.38 |
| `32x` / `09T` | 9.53 | 3.97 |

---

## Field-by-Field Mapping

| Schema Field | Kennametal Source | Notes |
|---|---|---|
| `json_id` | ISO catalog ID | e.g. `CCGT060201MRPPS` |
| `manufacturer` | `"Kennametal"` | Always |
| `component_type` | `"insert"` or `"holder"` or `"module"` | |
| `category` | `"Turning Inserts"` | For TopSwiss inserts |
| `type` | `"Kennametal TopSwiss [SHAPE] Insert"` | e.g. `"Kennametal TopSwiss CCGT Insert"` |
| `shape` | ISO shape code | e.g. `"CCGT"` |
| `chipbreaker` | Chipbreaker suffix | e.g. `"PPS"` |
| `grade` | Grade code | e.g. `"KCP20S"` |
| `geometry` | `"positive"` / `"positive wiper"` / `"positive fine-polish"` etc. | Derived from chipbreaker |
| `size` | `"[ISO] / [ANSI]"` | e.g. `"CCGT060201 / CCGT21502"` |
| `specs` | JSON — see below | |
| `sources` | `["Kennametal TopSwiss Inserts Catalog MetricInch, p.X"]` | Include page |
| `tags` | Array | See tagging guide |

---

## Spec Fields (TopSwiss inserts)
```json
{
  "iso_catalog_id": "CCGT060201MRPPS",
  "ansi_catalog_id": "CCGT21502MRPPS",
  "insert_shape": "CCGT",
  "included_angle": "80 deg",
  "inscribed_circle_D": "6.35 mm",
  "thickness_S": "2.38 mm",
  "corner_radius_RE": "0.1 mm",
  "cutting_length_L10": "6.45 mm",
  "chipbreaker": "PPS",
  "geometry": "positive",
  "tolerance_class": "G",
  "cutting_direction": "Neutral"
}
```

---

## Spec Fields (KM16 modules)
```json
{
  "system_size_machine_side": "KM16",
  "f_dimension": "10 mm",
  "cutting_height": "8 mm",
  "tool_length": "20 mm",
  "clamping_type": "S-Clamping (Right Hand)",
  "torque": "10-11 Newton Meters"
}
```

---

## Tagging Guide

Always include:
- `"Kennametal"`, `"TopSwiss"`, `"Swiss-type"`
- Shape: `"CCGT"`, `"DCGT"`, `"CCMT"` etc.
- Grade: `"KCP20S"`, `"KN10S"` etc.
- Chipbreaker: `"PPS"`, `"LFS"` etc.
- Operation: `"finishing"`, `"fine-finishing"`, `"profiling"`, `"wiper"` etc.
- Hand if not neutral: `"right-hand"`, `"left-hand"`
- Material hint if grade-specific: `"stainless"`, `"non-ferrous"`, `"cermet"`

---

## Anchor Example (verified, in DB)

```json
{
  "json_id": "CCGT060201MRPPS",
  "component_type": "insert",
  "manufacturer": "Kennametal",
  "type": "Kennametal TopSwiss CCGT Insert",
  "shape": "CCGT",
  "chipbreaker": "PPS",
  "grade": "KCP20S",
  "geometry": "positive",
  "size": "CCGT060201 / CCGT21502",
  "specs": {
    "iso_catalog_id": "CCGT060201MRPPS",
    "ansi_catalog_id": "CCGT21502MRPPS",
    "insert_shape": "CCGT",
    "included_angle": "80 deg",
    "inscribed_circle_D": "6.35 mm",
    "thickness_S": "2.38 mm",
    "corner_radius_RE": "0.1 mm",
    "cutting_length_L10": "6.45 mm",
    "chipbreaker": "PPS",
    "geometry": "positive",
    "tolerance_class": "G",
    "cutting_direction": "Neutral"
  },
  "sources": ["Kennametal TopSwiss Inserts Catalog MetricInch, p.3"],
  "tags": ["turning","CCGT","Swiss-type","finishing","KCP20S","Kennametal","TopSwiss","positive"]
}
```

---

## Common Mistakes to Avoid

- ❌ Don't use ANSI as `json_id` — always use ISO
- ❌ Don't omit `ansi_catalog_id` from specs — both names matter for searchability
- ❌ Don't confuse tolerance class (G/E/M) with grade (KCP20S etc.)
- ❌ Don't set `chipbreaker = "N/A"` for Kennametal — they always have chipbreaker codes
- ✅ One DB entry per grade — if an insert ships in 3 grades, that's 3 entries
- ✅ Always store cutting_direction in specs even if Neutral
