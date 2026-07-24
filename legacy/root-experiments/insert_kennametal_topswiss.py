import pdfplumber, re, sqlite3, json

TARGET_PREFIXES = [
    "CCMT060202","CCMT060204","CCMT060208",
    "CCGT060201","CCGT060202","CCGT060204",
    "CCMT09T302","CCMT09T304","CCMT09T308",
    "CCGT09T301","CCGT09T302","CCGT09T304",
    "DCMT070202","DCMT070204","DCMT070208",
    "DCGT070201","DCGT070202","DCGT070204",
    "DCMT11T302","DCMT11T304","DCMT11T308",
    "DCGT11T301","DCGT11T302","DCGT11T304",
    "TCMT110202","TCMT110204","TCMT110208",
    "TCMT16T304","TCMT16T308","TCMT16T312",
    "VBMT110302","VBMT110304","VBMT110308",
    "VBMT160402","VBMT160404","VBMT160408",
    "VCMT110302","VCMT110304","VCMT110308",
    "VCGT110301","VCGT110302","VCGT110304",
]

# Standard IC values (replace 9.53 with 9.525)
def normalize_ic(ic):
    if abs(ic - 9.53) < 0.01:
        return 9.525
    return ic

PREFIX_ISO = {
    "CCMT060202": ("CCMT 06 02 02", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.2, 7, "M"),
    "CCMT060204": ("CCMT 06 02 04", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.4, 7, "M"),
    "CCMT060208": ("CCMT 06 02 08", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.8, 7, "M"),
    "CCGT060201": ("CCGT 06 02 01", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.1, 7, "G"),
    "CCGT060202": ("CCGT 06 02 02", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.2, 7, "G"),
    "CCGT060204": ("CCGT 06 02 04", "C (80\u00b0 Rhombic)", 6.35, 2.38, 0.4, 7, "G"),
    "CCMT09T302": ("CCMT 09T3 02", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.2, 7, "M"),
    "CCMT09T304": ("CCMT 09T3 04", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.4, 7, "M"),
    "CCMT09T308": ("CCMT 09T3 08", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.8, 7, "M"),
    "CCGT09T301": ("CCGT 09T3 01", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.1, 7, "G"),
    "CCGT09T302": ("CCGT 09T3 02", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.2, 7, "G"),
    "CCGT09T304": ("CCGT 09T3 04", "C (80\u00b0 Rhombic)", 9.525, 3.97, 0.4, 7, "G"),
    "DCMT070202": ("DCMT 07 02 02", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.2, 7, "M"),
    "DCMT070204": ("DCMT 07 02 04", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.4, 7, "M"),
    "DCMT070208": ("DCMT 07 02 08", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.8, 7, "M"),
    "DCGT070201": ("DCGT 07 02 01", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.1, 7, "G"),
    "DCGT070202": ("DCGT 07 02 02", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.2, 7, "G"),
    "DCGT070204": ("DCGT 07 02 04", "D (55\u00b0 Rhombic)", 6.35, 2.38, 0.4, 7, "G"),
    "DCMT11T302": ("DCMT 11T3 02", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.2, 7, "M"),
    "DCMT11T304": ("DCMT 11T3 04", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.4, 7, "M"),
    "DCMT11T308": ("DCMT 11T3 08", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.8, 7, "M"),
    "DCGT11T301": ("DCGT 11T3 01", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.1, 7, "G"),
    "DCGT11T302": ("DCGT 11T3 02", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.2, 7, "G"),
    "DCGT11T304": ("DCGT 11T3 04", "D (55\u00b0 Rhombic)", 9.525, 3.97, 0.4, 7, "G"),
    "TCMT110202": ("TCMT 11 02 02", "T (60\u00b0 Triangle)", 6.35, 2.38, 0.2, 7, "M"),
    "TCMT110204": ("TCMT 11 02 04", "T (60\u00b0 Triangle)", 6.35, 2.38, 0.4, 7, "M"),
    "TCMT110208": ("TCMT 11 02 08", "T (60\u00b0 Triangle)", 6.35, 2.38, 0.8, 7, "M"),
    "TCMT16T304": ("TCMT 16T3 04", "T (60\u00b0 Triangle)", 9.525, 3.97, 0.4, 7, "M"),
    "TCMT16T308": ("TCMT 16T3 08", "T (60\u00b0 Triangle)", 9.525, 3.97, 0.8, 7, "M"),
    "TCMT16T312": ("TCMT 16T3 12", "T (60\u00b0 Triangle)", 9.525, 3.97, 1.2, 7, "M"),
    "VBMT110302": ("VBMT 11 03 02", "V (35\u00b0) VBMT positive", 6.35, 3.18, 0.2, 5, "M"),
    "VBMT110304": ("VBMT 11 03 04", "V (35\u00b0) VBMT positive", 6.35, 3.18, 0.4, 5, "M"),
    "VBMT110308": ("VBMT 11 03 08", "V (35\u00b0) VBMT positive", 6.35, 3.18, 0.8, 5, "M"),
    "VBMT160402": ("VBMT 16 04 02", "V (35\u00b0) VBMT positive", 9.525, 4.76, 0.2, 5, "M"),
    "VBMT160404": ("VBMT 16 04 04", "V (35\u00b0) VBMT positive", 9.525, 4.76, 0.4, 5, "M"),
    "VBMT160408": ("VBMT 16 04 08", "V (35\u00b0) VBMT positive", 9.525, 4.76, 0.8, 5, "M"),
    "VCMT110302": ("VCMT 11 03 02", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.2, 7, "M"),
    "VCMT110304": ("VCMT 11 03 04", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.4, 7, "M"),
    "VCMT110308": ("VCMT 11 03 08", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.8, 7, "M"),
    "VCGT110301": ("VCGT 11 03 01", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.1, 7, "G"),
    "VCGT110302": ("VCGT 11 03 02", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.2, 7, "G"),
    "VCGT110304": ("VCGT 11 03 04", "V (35\u00b0 Rhombic)", 6.35, 3.18, 0.4, 7, "G"),
}

SEAT_HOLDERS = {
    "CCMT060202": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCMT060204": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCMT060208": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCGT060201": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCGT060202": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCGT060204": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCMT09T302": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCMT09T304": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCMT09T308": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCGT09T301": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCGT09T302": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCGT09T304": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "DCMT070202": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCMT070204": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCMT070208": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCGT070201": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCGT070202": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCGT070204": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCMT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCMT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCMT11T308": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCGT11T301": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCGT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCGT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "TCMT110202": ["KM16STJCR1120"],
    "TCMT110204": ["KM16STJCR1120"],
    "TCMT110208": ["KM16STJCR1120"],
    "TCMT16T304": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T308": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T312": ["KM16STGCR1620","KM16STJCR1620"],
    "VBMT110302": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT110304": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT110308": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT160402": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBMT160404": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBMT160408": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VCMT110302": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCMT110304": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCMT110308": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCGT110301": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCGT110302": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCGT110304": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
}

CB_INFO = {
    "MPS":   ("TopSwiss Medium Positive Swiss - medium cutting on steel/stainless",
              ["steel","stainless","cast iron"], ["medium","turning"], "S52PTK"),
    "FPS":   ("TopSwiss Fine Positive Swiss - finishing on steel/stainless",
              ["steel","stainless","cast iron","non-ferrous"], ["finishing","turning"], "S52PTK"),
    "MWS":   ("TopSwiss Medium Wiper Swiss - wiper geometry for improved surface finish at higher feeds",
              ["steel","stainless"], ["medium","turning"], "S52PTK"),
    "FWS":   ("TopSwiss Fine Wiper Swiss - wiper geometry for high surface quality finishing",
              ["steel","stainless","cast iron"], ["finishing","turning"], "S52PTK"),
    "MRPPS": ("TopSwiss PPS Right-Hand - precision positive for steel/stainless/titanium",
              ["steel","stainless","titanium","superalloy"], ["finishing","turning"],
              "S02PCK, S52MCK, S52SCK"),
    "MLFS":  ("TopSwiss LFS - light finishing for stainless and superalloys",
              ["stainless","titanium","superalloy","non-ferrous"], ["finishing","turning"],
              "S02PCK, S52MCK, S52SCK"),
    "MFFS":  ("TopSwiss FFS - fine finishing for stainless and superalloys",
              ["stainless","titanium","superalloy"], ["finishing","turning"],
              "S52MCK, S52SCK"),
}

def get_cb(part, prefix):
    suffix = part[len(prefix):]
    for key in CB_INFO:
        if suffix == key:
            return key, CB_INFO[key]
    for key in CB_INFO:
        if suffix.endswith(key):
            return key, CB_INFO[key]
    return suffix, (suffix + " chipbreaker", ["steel"], ["turning"], "S52PTK")

def extract_all():
    results = {}
    with pdfplumber.open("catalogs/Kennametal/TopSwiss Inserts MetricInch.pdf") as pdf:
        for pg_num in range(1, len(pdf.pages)+1):
            text = pdf.pages[pg_num-1].extract_text() or ""
            for line in text.split("\n"):
                tokens = line.split()
                if len(tokens) < 6:
                    continue
                for i, tok in enumerate(tokens):
                    matched_prefix = None
                    for pfx in TARGET_PREFIXES:
                        if tok.startswith(pfx):
                            matched_prefix = pfx
                            break
                    if matched_prefix and tok not in results:
                        nums = []
                        for t2 in tokens[i+1:]:
                            t2 = t2.lstrip("<")
                            try:
                                nums.append(float(t2))
                            except:
                                pass
                        if len(nums) >= 8:
                            IC = normalize_ic(nums[0])
                            R  = nums[4]
                            D1 = nums[6]
                            S  = nums[8] if len(nums) > 8 else None
                            iso_data = PREFIX_ISO.get(matched_prefix)
                            if iso_data:
                                IC, S, R = iso_data[2], iso_data[3], iso_data[4]
                            results[tok] = {"prefix": matched_prefix, "IC": IC, "RE": R, "S": S, "D1": D1}
    return results

def build_records(results):
    rows = []
    for part, data in sorted(results.items()):
        prefix = data["prefix"]
        iso_data = PREFIX_ISO.get(prefix)
        if not iso_data:
            continue

        iso_str, shape, IC, S, RE, relief, tolerance = iso_data
        D1 = data.get("D1")
        holders = SEAT_HOLDERS.get(prefix, [])
        cb_key, (cb_desc, materials, ops, grades) = get_cb(part, prefix)

        shape_name = prefix[:4]  # e.g. CCMT or DCGT

        specs = {
            "iso_id": part,
            "iso_designation": iso_str,
            "ic_mm": IC,
            "s_mm": S,
            "re_mm": RE,
            "clearance_angle_deg": relief,
            "tolerance": tolerance,
            "holding": "T (through hole)",
            "insert_type": "positive",
            "available_grades": grades,
        }
        if D1:
            specs["d1_mm"] = D1

        tags = list(materials) + list(ops) + ["Kennametal", "TopSwiss", shape_name]
        if "finishing" in ops:
            tags.append("finishing")
        if "medium" in ops:
            tags.append("medium cutting")

        desc = ("Kennametal TopSwiss %s positive turning insert, %s chipbreaker. "
                "%s. Corner radius %.1f mm, IC %.3f mm. "
                "Grade(s): %s." % (iso_str, cb_key, cb_desc, RE, IC, grades))

        compat_machines = ["Swiss-type CNC lathes"]
        if holders:
            compat_machines.append("Compatible via holders: " + ", ".join(holders))

        rows.append({
            "json_id": part,
            "component_type": "insert",
            "category": "Turning Inserts",
            "type": "%s TopSwiss Positive Insert" % shape_name,
            "manufacturer": "Kennametal",
            "description": desc,
            "specs": json.dumps(specs),
            "size": prefix[4:] if len(prefix) > 4 else prefix,
            "geometry": "%s positive, %d-deg clearance, %s chipbreaker" % (iso_str, relief, cb_key),
            "compatible_machines": json.dumps(compat_machines),
            "compatible_inserts": json.dumps(["N/A (this is the insert)"]),
            "sources": json.dumps(["Kennametal TopSwiss Inserts Catalog (Metric/Inch)"]),
            "tags": json.dumps(tags),
            "condition": "New",
            "grade": grades.split(",")[0].strip(),
            "shape": shape,
            "chipbreaker": cb_desc,
            "iso_designation": iso_str,
        })
    return rows

def insert_to_db(db_path, rows):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    existing = set(r[0] for r in c.execute("SELECT json_id FROM tools").fetchall())
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
    results = extract_all()
    print("Extracted %d TopSwiss inserts from PDF" % len(results))
    rows = build_records(results)
    print("Built %d DB records" % len(rows))

    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db("docs/db.sqlite", rows)
        print("Inserted %d new, skipped %d duplicates" % (inserted, skipped))
    else:
        print("Run with --insert to write to database")
