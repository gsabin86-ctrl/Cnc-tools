"""
insert_sandvik_gap.py — Fill missing Sandvik CoroTurn 107 inserts (metric).

Source: sandvik_coroturn107_inserts.pdf
  Page 10: SCMT (S-style, square)       — PM chipbreaker
  Page 11: TCGT (T-style, light finish) — K chipbreaker
           TCMX (T-style, wiper)        — WF chipbreaker
  Page 12: TCMT (T-style, medium)       — PM, UM, MR, UR chipbreakers

All data read directly from catalog tables. Imperial-only sizes excluded.
"""

import sqlite3, json

DB = "docs/db.sqlite"
SOURCE = "Sandvik CoroTurn 107 Inserts catalog (sandvik_coroturn107_inserts.pdf)"

CHIPBREAKER_INFO = {
    "PM": ("Medium — general steel/stainless/cast iron",   ["P","M","K"],   "Medium"),
    "UM": ("Medium universal — steel/stainless/cast iron/superalloy", ["P","M","K","S"], "Medium"),
    "K":  ("Light finishing — cast iron and non-ferrous",  ["K"],           "Finishing"),
    "WF": ("Wiper finishing — high surface quality",       ["P","M","K"],   "Finishing"),
    "MR": ("Medium roughing — steel/stainless",            ["P","M"],       "Medium"),
    "UR": ("Universal roughing — steel/stainless/cast iron",["P","M","K"],  "Medium"),
}

SHAPE_INFO = {
    "SCMT": ("S (90° Square)",  7, "M"),
    "TCGT": ("T (60° Triangle)", 7, "G"),
    "TCMX": ("T (60° Triangle)", 7, "X"),
    "TCMT": ("T (60° Triangle)", 7, "M"),
}

# All data sourced from catalog pages (metric rows only)
# Fields: json_id, ssc, le_mm, s_mm, re_mm, ic_mm, bn_mm, d1_mm, chipbreaker
INSERTS = [
    # Page 10 — SCMT, PM, P+M+K
    ("SCMT-09-T3-04-PM", "09",  9.1, 3.97, 0.4,  9.52, None, 4.40, "PM"),
    ("SCMT-09-T3-08-PM", "09",  8.7, 3.97, 0.8,  9.52, None, 4.40, "PM"),
    ("SCMT-12-04-04-PM", "12", 12.3, 4.76, 0.4, 12.70, None, 5.50, "PM"),
    ("SCMT-12-04-08-PM", "12", 11.9, 4.76, 0.8, 12.70, None, 5.50, "PM"),

    # Page 11 — TCGT, K (light finishing, cast iron/non-ferrous)
    ("TCGT-09-02-02L-K", "09",  9.2, 2.38, 0.2,  5.56, 2.50, None, "K"),
    ("TCGT-09-02-04L-K", "09",  9.0, 2.38, 0.4,  5.56, 2.50, None, "K"),
    ("TCGT-11-02-02L-K", "11", 10.5, 2.38, 0.2,  6.35, 2.80, None, "K"),
    ("TCGT-11-02-04L-K", "11", 10.3, 2.38, 0.4,  6.35, 2.80, None, "K"),

    # Page 11 — TCMX, WF (wiper finishing)
    ("TCMX-09-02-04-WF", "09",  9.0, 2.38, 0.4,  5.56, 0.07, 2.50, "WF"),
    ("TCMX-11-03-04-WF", "11", 10.3, 3.17, 0.4,  6.35, 0.07, 2.80, "WF"),
    ("TCMX-11-03-08-WF", "11",  9.9, 3.17, 0.8,  6.35, 0.07, 2.80, "WF"),
    ("TCMX-16-T3-08-WF", "16", 15.7, 3.97, 0.8,  9.52, 0.10, 4.40, "WF"),

    # Page 12 — TCMT, PM (medium, P+M+K+S)
    ("TCMT-09-02-04-PM", "09",  9.0, 2.38, 0.4,  5.56, None, 2.50, "PM"),
    ("TCMT-09-02-08-PM", "09",  8.6, 2.38, 0.8,  5.56, None, 2.50, "PM"),
    ("TCMT-11-03-04-PM", "11", 10.3, 3.17, 0.4,  6.35, None, 2.80, "PM"),
    ("TCMT-11-03-08-PM", "11",  9.9, 3.17, 0.8,  6.35, None, 2.80, "PM"),
    ("TCMT-16-T3-04-PM", "16", 16.1, 3.97, 0.4,  9.52, None, 4.40, "PM"),
    ("TCMT-16-T3-08-PM", "16", 15.7, 3.97, 0.8,  9.52, None, 4.40, "PM"),

    # Page 12 — TCMT, UM (medium universal, P+M+K+S)
    ("TCMT-09-02-04-UM", "09",  9.0, 2.38, 0.4,  5.56, None, 2.50, "UM"),
    ("TCMT-09-02-08-UM", "09",  8.6, 2.38, 0.8,  5.56, None, 2.50, "UM"),
    ("TCMT-11-02-04-UM", "11", 10.3, 2.38, 0.4,  6.35, None, 2.80, "UM"),
    ("TCMT-11-02-08-UM", "11",  9.9, 2.38, 0.8,  6.35, None, 2.80, "UM"),

    # Page 12 — TCMT, MR (medium roughing, P+M)
    ("TCMT-16-T3-08-MR", "16", 15.7, 3.97, 0.8,  9.52, 0.10, 4.40, "MR"),

    # Page 12 — TCMT, UR (universal roughing, P+M+K)
    ("TCMT-11-02-08-UR", "11",  9.9, 2.38, 0.8,  6.35, None, 2.80, "UR"),
]


def build_rows():
    rows = []
    for (json_id, ssc, le, s, re, ic, bn, d1, cb) in INSERTS:
        shape_prefix = json_id[:4]
        shape_str, clearance, tolerance = SHAPE_INFO[shape_prefix]
        cb_desc, mats, cut_type = CHIPBREAKER_INFO[cb]

        specs = {
            "ssc": ssc,
            "le_mm": le,
            "s_mm": s,
            "re_mm": re,
            "ic_mm": ic,
            "material_groups": mats,
        }
        if bn is not None:
            specs["bn_mm"] = bn
        if d1 is not None:
            specs["d1_mm"] = d1

        desc = ("Sandvik %s insert %s, chipbreaker %s, grade 1625. "
                "%s. IC %.2f mm, RE %.1f mm." % (
                    shape_prefix, json_id, cb, cb_desc, ic, re))

        tags = ["sandvik", "swiss", "CoroTurn 107", shape_prefix, "turning",
                cut_type.lower()] + [m.lower() for m in mats]

        rows.append({
            "json_id":            json_id,
            "component_type":     "insert",
            "category":           "CoroTurn 107 Inserts",
            "type":               "CoroTurn 107 turning insert \u2013 %s" % cut_type,
            "manufacturer":       "Sandvik Coromant",
            "description":        desc,
            "specs":              json.dumps(specs),
            "size":               ssc,
            "geometry":           None,
            "compatible_machines": None,
            "compatible_inserts": None,
            "sources":            json.dumps([SOURCE]),
            "tags":               json.dumps(tags),
            "condition":          "New",
            "grade":              "1625",
            "shape":              shape_str,
            "chipbreaker":        cb_desc,
            "iso_designation":    json_id.replace("-", " ").rsplit(" ", 1)[0],
        })
    return rows


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
    rows = build_rows()
    print("Built %d records:" % len(rows))
    for r in rows:
        print("  %s  [%s]  IC=%.2f  RE=%.1f" % (
            r["json_id"], r["grade"],
            json.loads(r["specs"])["ic_mm"],
            json.loads(r["specs"])["re_mm"]))

    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db(rows)
        print("\nInserted %d new, skipped %d duplicates" % (inserted, skipped))
    else:
        print("\nRun with --insert to write to database")
