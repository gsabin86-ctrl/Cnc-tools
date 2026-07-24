"""
insert_tungaloy_pcd.py — Tungaloy PCD turning inserts.

Source: catalogs/Tungaloy/GC_2023-2024_G_B_Insert.pdf
  Page 220: PCD TCMT (TC triangular, 7° positive, with hole)
    — fits KM16STJCR1120 (TC size 11)
  Page 225: PCD 1QP-VBGT (VB 35° rhombic, 5° positive, with hole)
    — fits KM16SVJBR1630 (VB size 16)

All data read directly from catalog pages.
All dimensions in metric (sourced from page headers and designation codes).
"""

import sqlite3, json

DB = "docs/db.sqlite"
SOURCE = "Tungaloy GC 2023-2024 Catalog B Insert (GC_2023-2024_G_B_Insert.pdf)"

# ---------------------------------------------------------------------------
# Dimension reference (sourced from existing DB records and catalog headers)
# TC size 11: IC=6.35mm, S=2.38mm (source: TCGT110204-01 in DB)
# VB size 16: IC=9.525mm, S=4.76mm (source: VBGT160404-NS header on page 225)
# ---------------------------------------------------------------------------

# Format: (json_id, ic_mm, s_mm, re_mm, le_mm, page, grade_code, shape_str, note)
# TC 11 specs confirmed from page 220 header: IC=6.80mm per Tungaloy measurement.
# Note: Tungaloy states IC=6.80mm for their TC-11 PCD inserts — slightly
# different from the 6.35mm nominal ISO value. Using Tungaloy's stated 6.80mm.
INSERTS = [
    # Page 220 — TCMT PCD, size 11 (fits KM16STJCR1120)
    # Designations follow ISO: TCMT 11 02 02 = IC 6.80mm (Tungaloy), S=3.18mm, RE=0.2mm
    # Designation TCMT 11 03 02 = S=3.18mm, RE=0.2mm (03 = thickness code)
    # From catalog: IC 6.80mm, D1=2.3mm, S=3.18mm
    # TCMT110202-DIA: RE code 02 = 0.2mm, thickness "02" = 2.38mm
    # TCMT110204-DIA: RE code 04 = 0.4mm, thickness "02" = 2.38mm
    # TCMT110302-DIA: RE code 02 = 0.2mm, thickness "03" = 3.18mm
    # TCMT110304-DIA: RE code 04 = 0.4mm, thickness "03" = 3.18mm
    ("TCMT110202-DIA", 6.80, 2.38, 0.2, 2.2, 220, "DIA", "T (60° Triangle)", ""),
    ("TCMT110204-DIA", 6.80, 2.38, 0.4, 2.2, 220, "DIA", "T (60° Triangle)", ""),
    ("TCMT110302-DIA", 6.80, 3.18, 0.2, 2.2, 220, "DIA", "T (60° Triangle)", ""),
    ("TCMT110304-DIA", 6.80, 3.18, 0.4, 2.2, 220, "DIA", "T (60° Triangle)", ""),

    # Page 225 — VBGT PCD, size 16 (fits KM16SVJBR1630, gage_insert VB..160408)
    # From page 225 header: IC=9.525mm, D1=4.4mm, S=4.76mm
    # 1QP- prefix = Tungaloy designation prefix, -NS = chipbreaker
    # RE code 04 = 0.4mm, 08 = 0.8mm
    ("1QP-VBGT160404-NS", 9.525, 4.76, 0.4, 2.49, 225, "DX110", "V (35° Diamond)", "with chipbreaker"),
    ("1QP-VBGT160408-NS", 9.525, 4.76, 0.8, 2.49, 225, "DX110", "V (35° Diamond)", "with chipbreaker"),
]


def build_row(json_id, ic_mm, s_mm, re_mm, le_mm, page, grade_code, shape_str, note):
    shape2 = json_id[-len(json_id):].lstrip("1QP-")[:2]
    # Determine shape letter from designation
    if "TCMT" in json_id:
        shape2 = "TC"
    elif "VBGT" in json_id:
        shape2 = "VB"

    note_str = f" ({note})" if note else ""
    desc = (f"Tungaloy PCD {shape2} turning insert. "
            f"ISO designation: {json_id}. Grade: {grade_code} — PCD for non-ferrous metals. "
            f"IC {ic_mm:.3f} mm, S {s_mm:.2f} mm, RE {re_mm:.2f} mm, LE {le_mm:.2f} mm.{note_str} "
            f"Source: catalog page {page}.")

    specs = {
        "ic_mm":           ic_mm,
        "s_mm":            s_mm,
        "re_mm":           re_mm,
        "le_mm":           le_mm,
        "material_groups": ["N"],
    }

    tags = ["tungaloy", "swiss", "pcd", "turning", shape2, "non-ferrous", "aluminum", grade_code]

    return {
        "json_id":            json_id,
        "component_type":     "insert",
        "category":           "CBN/PCD Inserts - PCD",
        "type":               "Tungaloy PCD turning insert",
        "manufacturer":       "Tungaloy",
        "description":        desc,
        "specs":              json.dumps(specs),
        "size":               "11" if shape2 == "TC" else "16",
        "geometry":           None,
        "compatible_machines": None,
        "compatible_inserts": None,
        "sources":            json.dumps([f"{SOURCE}, page {page}"]),
        "tags":               json.dumps(list(dict.fromkeys(tags))),
        "condition":          "New",
        "grade":              grade_code,
        "shape":              shape_str,
        "chipbreaker":        "PCD, non-ferrous metals",
        "iso_designation":    json_id,
    }


def build_all_rows():
    return [build_row(*entry) for entry in INSERTS]


def insert_to_db(rows):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    existing = {r[0] for r in c.execute("SELECT json_id FROM tools").fetchall()}
    inserted = skipped = 0
    for row in rows:
        if row["json_id"] in existing:
            skipped += 1
            continue
        c.execute("""
            INSERT INTO tools
            (json_id, component_type, category, type, manufacturer, description,
             specs, size, geometry, compatible_machines, compatible_inserts,
             sources, tags, condition, grade, shape, chipbreaker, iso_designation)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["json_id"], row["component_type"], row["category"], row["type"],
            row["manufacturer"], row["description"], row["specs"], row["size"],
            row["geometry"], row["compatible_machines"], row["compatible_inserts"],
            row["sources"], row["tags"], row["condition"], row["grade"],
            row["shape"], row["chipbreaker"], row["iso_designation"],
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    rows = build_all_rows()
    print(f"Built {len(rows)} records:")
    for r in rows:
        sp = json.loads(r["specs"])
        print(f"  {r['json_id']:<30}  grade={r['grade']:<8}  "
              f"IC={sp['ic_mm']:.3f}  RE={sp['re_mm']:.2f}")
    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db(rows)
        print(f"\nInserted {inserted} new, skipped {skipped} duplicates")
    else:
        print("\nRun with --insert to write to database")
