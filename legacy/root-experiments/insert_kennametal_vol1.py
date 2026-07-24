import pdfplumber, re, sqlite3, json

CATALOG_PATH = "catalogs/Kennametal/Master Catalog 2018 Vol. 1 Turning Tools English Inch.pdf"

# Pages with relevant insert types
INSERT_PAGES = list(range(210, 216)) + list(range(246, 252)) + list(range(278, 292)) + list(range(302, 312))

TARGET_PREFIXES = [
    "CCMT060202","CCMT060204","CCMT060208",
    "CCGT060201","CCGT060202","CCGT060204",
    "CCMT09T302","CCMT09T304","CCMT09T308",
    "CCGT09T301","CCGT09T302","CCGT09T304",
    "DCMT070202","DCMT070204","DCMT070208",
    "DCGT070201","DCGT070202","DCGT070204","DCGT070208",
    "DCMT11T302","DCMT11T304","DCMT11T308","DCMT11T312",
    "DCGT11T301","DCGT11T302","DCGT11T304","DCGT11T308",
    "TCMT110202","TCMT110204","TCMT110208",
    "TCMT110304","TCMT110308","TCMT110312",
    "TCMT16T302","TCMT16T304","TCMT16T308","TCMT16T312",
    "TCGT110202","TCGT110204","TCGT110208",
    "TCGT16T302","TCGT16T304","TCGT16T308",
    "VBMT110302","VBMT110304","VBMT110308",
    "VBMT160402","VBMT160404","VBMT160408","VBMT160412",
    "VBGT110302","VBGT110304","VBGT110308",
    "VBGT160402","VBGT160404","VBGT160408",
]

PREFIX_ISO = {
    "CCMT060202": ("CCMT 06 02 02","C (80\u00b0 Rhombic)",6.35,2.38,0.2,7,"M"),
    "CCMT060204": ("CCMT 06 02 04","C (80\u00b0 Rhombic)",6.35,2.38,0.4,7,"M"),
    "CCMT060208": ("CCMT 06 02 08","C (80\u00b0 Rhombic)",6.35,2.38,0.8,7,"M"),
    "CCGT060201": ("CCGT 06 02 01","C (80\u00b0 Rhombic)",6.35,2.38,0.1,7,"G"),
    "CCGT060202": ("CCGT 06 02 02","C (80\u00b0 Rhombic)",6.35,2.38,0.2,7,"G"),
    "CCGT060204": ("CCGT 06 02 04","C (80\u00b0 Rhombic)",6.35,2.38,0.4,7,"G"),
    "CCMT09T302": ("CCMT 09T3 02","C (80\u00b0 Rhombic)",9.525,3.97,0.2,7,"M"),
    "CCMT09T304": ("CCMT 09T3 04","C (80\u00b0 Rhombic)",9.525,3.97,0.4,7,"M"),
    "CCMT09T308": ("CCMT 09T3 08","C (80\u00b0 Rhombic)",9.525,3.97,0.8,7,"M"),
    "CCGT09T301": ("CCGT 09T3 01","C (80\u00b0 Rhombic)",9.525,3.97,0.1,7,"G"),
    "CCGT09T302": ("CCGT 09T3 02","C (80\u00b0 Rhombic)",9.525,3.97,0.2,7,"G"),
    "CCGT09T304": ("CCGT 09T3 04","C (80\u00b0 Rhombic)",9.525,3.97,0.4,7,"G"),
    "DCMT070202": ("DCMT 07 02 02","D (55\u00b0 Rhombic)",6.35,2.38,0.2,7,"M"),
    "DCMT070204": ("DCMT 07 02 04","D (55\u00b0 Rhombic)",6.35,2.38,0.4,7,"M"),
    "DCMT070208": ("DCMT 07 02 08","D (55\u00b0 Rhombic)",6.35,2.38,0.8,7,"M"),
    "DCGT070201": ("DCGT 07 02 01","D (55\u00b0 Rhombic)",6.35,2.38,0.1,7,"G"),
    "DCGT070202": ("DCGT 07 02 02","D (55\u00b0 Rhombic)",6.35,2.38,0.2,7,"G"),
    "DCGT070204": ("DCGT 07 02 04","D (55\u00b0 Rhombic)",6.35,2.38,0.4,7,"G"),
    "DCGT070208": ("DCGT 07 02 08","D (55\u00b0 Rhombic)",6.35,2.38,0.8,7,"G"),
    "DCMT11T302": ("DCMT 11T3 02","D (55\u00b0 Rhombic)",9.525,3.97,0.2,7,"M"),
    "DCMT11T304": ("DCMT 11T3 04","D (55\u00b0 Rhombic)",9.525,3.97,0.4,7,"M"),
    "DCMT11T308": ("DCMT 11T3 08","D (55\u00b0 Rhombic)",9.525,3.97,0.8,7,"M"),
    "DCMT11T312": ("DCMT 11T3 12","D (55\u00b0 Rhombic)",9.525,3.97,1.2,7,"M"),
    "DCGT11T301": ("DCGT 11T3 01","D (55\u00b0 Rhombic)",9.525,3.97,0.1,7,"G"),
    "DCGT11T302": ("DCGT 11T3 02","D (55\u00b0 Rhombic)",9.525,3.97,0.2,7,"G"),
    "DCGT11T304": ("DCGT 11T3 04","D (55\u00b0 Rhombic)",9.525,3.97,0.4,7,"G"),
    "DCGT11T308": ("DCGT 11T3 08","D (55\u00b0 Rhombic)",9.525,3.97,0.8,7,"G"),
    "TCMT110202": ("TCMT 11 02 02","T (60\u00b0 Triangle)",6.35,2.38,0.2,7,"M"),
    "TCMT110204": ("TCMT 11 02 04","T (60\u00b0 Triangle)",6.35,2.38,0.4,7,"M"),
    "TCMT110208": ("TCMT 11 02 08","T (60\u00b0 Triangle)",6.35,2.38,0.8,7,"M"),
    "TCMT110304": ("TCMT 11 03 04","T (60\u00b0 Triangle)",6.35,3.18,0.4,7,"M"),
    "TCMT110308": ("TCMT 11 03 08","T (60\u00b0 Triangle)",6.35,3.18,0.8,7,"M"),
    "TCMT110312": ("TCMT 11 03 12","T (60\u00b0 Triangle)",6.35,3.18,1.2,7,"M"),
    "TCGT110202": ("TCGT 11 02 02","T (60\u00b0 Triangle)",6.35,2.38,0.2,7,"G"),
    "TCGT110204": ("TCGT 11 02 04","T (60\u00b0 Triangle)",6.35,2.38,0.4,7,"G"),
    "TCGT110208": ("TCGT 11 02 08","T (60\u00b0 Triangle)",6.35,2.38,0.8,7,"G"),
    "TCGT16T302": ("TCGT 16T3 02","T (60\u00b0 Triangle)",9.525,3.97,0.2,7,"G"),
    "TCGT16T304": ("TCGT 16T3 04","T (60\u00b0 Triangle)",9.525,3.97,0.4,7,"G"),
    "TCGT16T308": ("TCGT 16T3 08","T (60\u00b0 Triangle)",9.525,3.97,0.8,7,"G"),
    "TCMT16T302": ("TCMT 16T3 02","T (60\u00b0 Triangle)",9.525,3.97,0.2,7,"M"),
    "TCMT16T304": ("TCMT 16T3 04","T (60\u00b0 Triangle)",9.525,3.97,0.4,7,"M"),
    "TCMT16T308": ("TCMT 16T3 08","T (60\u00b0 Triangle)",9.525,3.97,0.8,7,"M"),
    "TCMT16T312": ("TCMT 16T3 12","T (60\u00b0 Triangle)",9.525,3.97,1.2,7,"M"),
    "VBMT110302": ("VBMT 11 03 02","V (35\u00b0) VBMT positive",6.35,3.18,0.2,5,"M"),
    "VBMT110304": ("VBMT 11 03 04","V (35\u00b0) VBMT positive",6.35,3.18,0.4,5,"M"),
    "VBMT110308": ("VBMT 11 03 08","V (35\u00b0) VBMT positive",6.35,3.18,0.8,5,"M"),
    "VBMT160402": ("VBMT 16 04 02","V (35\u00b0) VBMT positive",9.525,4.76,0.2,5,"M"),
    "VBMT160404": ("VBMT 16 04 04","V (35\u00b0) VBMT positive",9.525,4.76,0.4,5,"M"),
    "VBMT160408": ("VBMT 16 04 08","V (35\u00b0) VBMT positive",9.525,4.76,0.8,5,"M"),
    "VBMT160412": ("VBMT 16 04 12","V (35\u00b0) VBMT positive",9.525,4.76,1.2,5,"M"),
    "VBGT110302": ("VBGT 11 03 02","V (35\u00b0) VBGT positive",6.35,3.18,0.2,5,"G"),
    "VBGT110304": ("VBGT 11 03 04","V (35\u00b0) VBGT positive",6.35,3.18,0.4,5,"G"),
    "VBGT110308": ("VBGT 11 03 08","V (35\u00b0) VBGT positive",6.35,3.18,0.8,5,"G"),
    "VBGT160402": ("VBGT 16 04 02","V (35\u00b0) VBGT positive",9.525,4.76,0.2,5,"G"),
    "VBGT160404": ("VBGT 16 04 04","V (35\u00b0) VBGT positive",9.525,4.76,0.4,5,"G"),
    "VBGT160408": ("VBGT 16 04 08","V (35\u00b0) VBGT positive",9.525,4.76,0.8,5,"G"),
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
    "DCGT070208": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCMT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCMT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCMT11T308": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCMT11T312": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCGT11T301": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120"],
    "DCGT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCGT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCGT11T308": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "TCMT110202": ["KM16STJCR1120"],
    "TCMT110204": ["KM16STJCR1120"],
    "TCMT110208": ["KM16STJCR1120"],
    "TCMT110304": ["KM16STJCR1120"],
    "TCMT110308": ["KM16STJCR1120"],
    "TCMT110312": ["KM16STJCR1120"],
    "TCGT110202": ["KM16STJCR1120"],
    "TCGT110204": ["KM16STJCR1120"],
    "TCGT110208": ["KM16STJCR1120"],
    "TCGT16T302": ["KM16STGCR1620","KM16STJCR1620"],
    "TCGT16T304": ["KM16STGCR1620","KM16STJCR1620"],
    "TCGT16T308": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T302": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T304": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T308": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T312": ["KM16STGCR1620","KM16STJCR1620"],
    "VBMT110302": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT110304": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT110308": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT160402": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBMT160404": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBMT160408": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBMT160412": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBGT110302": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBGT110304": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBGT110308": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBGT160402": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBGT160404": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBGT160408": ["KM16SVJBR1630","KM16SVGBR1630"],
}

CB_INFO = {
    "UF":  ("Ultra Fine - precision finishing, ultra-sharp edge",
            ["steel","stainless","non-ferrous","superalloy"], ["finishing","turning"],
            "KC730, KC5025, KC5010"),
    "LF":  ("Light Finishing - light cutting action, excellent surface finish",
            ["steel","stainless","cast iron","non-ferrous"], ["finishing","turning"],
            "KC730, KC5025, KC5010, K313"),
    "FP":  ("Finishing Positive - finishing to medium cutting",
            ["steel","stainless","cast iron"], ["finishing","turning"],
            "KC5010, KC5025, KC730"),
    "FW":  ("Finishing Wiper - wiper geometry for high surface quality",
            ["steel","stainless"], ["finishing","turning"],
            "KC5010, KC5025"),
    "HP":  ("High Performance - medium to semi-rough cutting",
            ["stainless","superalloy","non-ferrous"], ["medium","turning"],
            "KC5025, KC5510, KC9225"),
    "MW":  ("Medium Wiper - medium cutting with wiper for better surface finish",
            ["steel","stainless","cast iron"], ["medium","turning"],
            "KC5010, KC5025, KC730"),
    "MP":  ("Medium Positive - medium cutting, wide range",
            ["steel","stainless","cast iron"], ["medium","turning"],
            "KC5010, KC5025, KC730"),
    "MF":  ("Medium Finishing - medium to finishing operations",
            ["steel","stainless","cast iron"], ["semi-finishing","turning"],
            "KC5010, KC5025, KC730"),
    "11":  ("Standard - general-purpose carbide geometry",
            ["steel","stainless"], ["turning"],
            "KC9225, KC9315"),
}

def get_cb(suffix):
    if suffix in CB_INFO:
        return CB_INFO[suffix]
    return (suffix + " chipbreaker", ["steel","stainless"], ["turning"], "see catalog")

def normalize_mm(s):
    """Convert comma-decimal to float."""
    return float(s.replace(",", "."))

def extract_all():
    results = {}
    with pdfplumber.open(CATALOG_PATH) as pdf:
        for pg_num in INSERT_PAGES:
            if pg_num > len(pdf.pages):
                continue
            text = pdf.pages[pg_num-1].extract_text() or ""
            for line in text.split("\n"):
                tokens = line.split()
                if len(tokens) < 6:
                    continue
                # First token should be ISO part number
                tok = tokens[0]
                matched_prefix = None
                for pfx in TARGET_PREFIXES:
                    if tok.startswith(pfx):
                        matched_prefix = pfx
                        break
                if not matched_prefix or tok in results:
                    continue
                # Parse: ISO ANSI D_mm D_in L_mm L_in R_mm R_in [grades...]
                try:
                    IC = normalize_mm(tokens[2])
                    if abs(IC - 9.53) < 0.01:
                        IC = 9.525
                    R_tok = tokens[6].replace(",",".")
                    R = float(R_tok) if R_tok.replace(".","").isdigit() else PREFIX_ISO.get(matched_prefix, (None,None,None,None,None))[4]
                except (IndexError, ValueError):
                    R = None
                    IC = None

                iso_data = PREFIX_ISO.get(matched_prefix)
                if iso_data:
                    IC = iso_data[2]
                    S  = iso_data[3]
                    R  = R or iso_data[4]
                else:
                    S = None

                results[tok] = {"prefix": matched_prefix, "IC": IC, "RE": R, "S": S}

    return results

def build_records(results):
    rows = []
    for part, data in sorted(results.items()):
        prefix = data["prefix"]
        iso_data = PREFIX_ISO.get(prefix)
        if not iso_data:
            continue

        iso_str, shape, IC, S, RE, relief, tolerance = iso_data
        holders = SEAT_HOLDERS.get(prefix, [])

        # Extract chipbreaker from part number
        suffix = part[len(prefix):]
        cb_desc, materials, ops, grades = get_cb(suffix)

        shape_name = prefix[:4]

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

        tags = list(materials) + list(ops) + ["Kennametal", shape_name]
        if "finishing" in ops:
            tags.append("finishing")

        desc = ("Kennametal %s positive turning insert, %s chipbreaker. "
                "%s. Corner radius %.1f mm, IC %.3f mm. Grades: %s." % (
                    iso_str, suffix, cb_desc, RE, IC, grades))

        compat_machines = []
        if holders:
            compat_machines.append("Compatible via holders: " + ", ".join(holders))
        compat_machines.append("CNC turning lathes")

        rows.append({
            "json_id": part,
            "component_type": "insert",
            "category": "Turning Inserts",
            "type": "%s Positive Carbide Insert" % shape_name,
            "manufacturer": "Kennametal",
            "description": desc,
            "specs": json.dumps(specs),
            "size": prefix[4:],
            "geometry": "%s positive, %d-deg clearance, %s chipbreaker" % (iso_str, relief, suffix),
            "compatible_machines": json.dumps(compat_machines),
            "compatible_inserts": json.dumps(["N/A (this is the insert)"]),
            "sources": json.dumps(["Kennametal Master Catalog 2018 Vol. 1 Turning Tools"]),
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
    print("Extracted %d inserts from Vol.1" % len(results))
    rows = build_records(results)
    print("Built %d DB records" % len(rows))

    # Sample
    for p in ["CCMT060204UF","DCMT11T304LF","TCMT16T304MP","VBMT110304FP"]:
        if p in results:
            r = results[p]
            print("  %s: IC=%.3f RE=%.2f S=%.3f" % (p, r["IC"] or 0, r["RE"] or 0, r["S"] or 0))

    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db("docs/db.sqlite", rows)
        print("Inserted %d new, skipped %d duplicates" % (inserted, skipped))
    else:
        print("Run with --insert to write to database")
