import pdfplumber, re, sqlite3, json

# Known standard dimensions to guide double-decimal splitting
KNOWN_IC = [3.57, 4.37, 4.76, 5.56, 6.35, 9.525, 12.7]
KNOWN_S  = [1.39, 1.59, 1.79, 2.38, 3.175, 3.18, 3.97, 4.76]
ALL_KNOWN = set(KNOWN_IC + KNOWN_S + [1.9, 2.2, 2.3, 2.5, 2.7, 2.8, 4.4])

def closest_known(v, known):
    return min(known, key=lambda x: abs(x - v))

def split_double_decimal(s):
    """Split a string with 2 decimal points into two floats using known IC/S values."""
    dots = [i for i, c in enumerate(s) if c == "."]
    if len(dots) < 2:
        try:
            return [float(s)]
        except:
            return []
    # Try all possible split positions between the two dots
    d1, d2 = dots[0], dots[1]
    best = None
    for split in range(d1 + 1, d2 + 1):
        left_s = s[:split]
        right_s = s[split:]
        if not right_s or right_s[0].isdigit() is False:
            continue
        try:
            lv = float(left_s)
            rv = float(right_s)
            # Prefer split where lv is close to a known IC value
            lv_err = min(abs(lv - k) for k in KNOWN_IC)
            rv_err = min(abs(rv - k) for k in KNOWN_S)
            score = lv_err + rv_err
            if best is None or score < best[0]:
                best = (score, lv, rv)
        except:
            pass
    if best:
        return [best[1], best[2]]
    try:
        return [float(s)]
    except:
        return []

def parse_nums(rest):
    nums = []
    for tok in rest.split():
        if tok.startswith("?") or tok in ("\\", "-", "IC", "RE", "S", "D1"):
            continue
        tok = tok.lstrip("<")
        if not tok:
            continue
        if tok.count(".") >= 2:
            nums.extend(split_double_decimal(tok))
        else:
            try:
                nums.append(float(tok))
            except:
                pass
    return nums

TARGET_PREFIXES = [
    "CCMT060204","CCGT060204","CCMT09T304","CCGT09T304",
    "DCMT070204","DCGT070204",
    "DCMT11T302","DCMT11T304","DCMT11T308","DCMT11T312",
    "DCGT11T302","DCGT11T304","DCGT11T308",
    "VCMT110304","VCGT110304",
    "TCMT110204","TCGT110204",
    "TCMT16T302","TCMT16T304","TCMT16T308","TCMT16T312",
    "TCGT16T302","TCGT16T304","TCGT16T308",
    "VBMT110304","VBGT110304","VBMT160404","VBGT160404",
]

def matches_prefix(tok):
    for p in TARGET_PREFIXES:
        if tok.startswith(p):
            return p
    return None

# Chipbreaker info: (description, primary_materials, operations, primary_grades)
CB_INFO = {
    "PSF":  ("P Steel Fine - precision finishing, low cutting force",
             ["steel","stainless","non-ferrous"], ["finishing","turning"],
             "T9215, T9225, T6215, AH8005, AH8015, AH6225, AH725"),
    "PF":   ("P Fine - fine finishing, steel and stainless",
             ["steel","stainless","cast iron"], ["finishing","turning"],
             "T9215, T9225, T6215, AH6225, AH725"),
    "PS":   ("P Semi - general semi-finishing, wide grade range",
             ["steel","stainless","cast iron","non-ferrous"], ["semi-finishing","turning"],
             "T9215, T9225, T6215, T9235, AH8005, AH8015, AH6225, AH6235, AH725"),
    "PSS":  ("P Semi-Strong - heavy semi-finishing to semi-roughing",
             ["steel","stainless","cast iron"], ["semi-roughing","turning"],
             "T9215, T9225, T6215, T9235, AH8015, AH6225, AH6235"),
    "PM":   ("P Medium - general medium cutting on steel",
             ["steel","stainless","cast iron","non-ferrous"], ["medium","turning"],
             "T9215, T9225, T6215, T9235, AH8005, AH8015, AH6225, AH6235, AH725"),
    "TSF":  ("T Stainless Fine - precision finishing on stainless and titanium",
             ["stainless","titanium","superalloy"], ["finishing","turning"],
             "T6215, AH6225, AH6235"),
    "TM":   ("T Stainless Medium - medium cutting on stainless and titanium",
             ["stainless","titanium","superalloy"], ["medium","turning"],
             "T6215, AH6225, AH6235"),
    "CM":   ("Cast Iron Medium - optimized for cast iron and hardened steel",
             ["cast iron","hardened steel"], ["medium","turning"],
             "TH10, GH330"),
    "SS":   ("Super Smooth - stainless and superalloy finishing",
             ["stainless","superalloy"], ["finishing","turning"],
             "T9215, T9225, AH6225, AH6235"),
    "AL":   ("Aluminum - non-ferrous and aluminum finishing",
             ["aluminum","non-ferrous"], ["finishing","turning"],
             "J740, SH725 (uncoated)"),
    "23":   ("Cermet 23 - high-speed steel finishing with cermet",
             ["steel"], ["finishing","turning"],
             "NS9530, AT9530 (cermet)"),
    "24":   ("Cermet 24 - cermet grade for precision steel",
             ["steel"], ["finishing","turning"],
             "GT9530 (cermet)"),
    "01":   ("Standard - general-purpose coated cermet",
             ["steel","stainless","non-ferrous"], ["finishing","turning"],
             "SH7025, SH725"),
    "DIA":  ("Diamond - PCD for non-ferrous ultra-fine finishing",
             ["aluminum","non-ferrous","copper"], ["finishing","turning"],
             "PCD"),
    "SW":   ("Smooth Wave - smooth wave chipbreaker",
             ["steel","stainless"], ["finishing","turning"],
             "T9215, AH6225"),
    "J10":  ("J10 - Swiss-type precision finishing chipbreaker",
             ["steel","stainless","non-ferrous"], ["finishing","turning"],
             "5207HS=SH7025, 527HS=SH725, 047J=J740"),
    "JS":   ("JS - J-Series Swiss-type finishing chipbreaker",
             ["steel","stainless","non-ferrous"], ["finishing","turning"],
             "SH7025, SH725, J740, NS9530"),
    "JP":   ("JP - J-Series positive Swiss-type chipbreaker",
             ["steel","non-ferrous"], ["finishing","turning"],
             "SH7025, SH725"),
    "W15":  ("W15 - ultra-precision uncoated finishing",
             ["non-ferrous","stainless"], ["precision finishing","turning"],
             "GH330, J740 (uncoated)"),
    "W20":  ("W20 - ultra-precision uncoated finishing, 09T3 size",
             ["non-ferrous","stainless"], ["precision finishing","turning"],
             "GH330, J740 (uncoated)"),
    "W08":  ("W08 - ultra-precision uncoated finishing, miniature",
             ["non-ferrous","stainless"], ["precision finishing","turning"],
             "GH330, J740 (uncoated)"),
}

# Map insert prefix to ISO designation and shape info
PREFIX_TO_ISO = {
    "CCMT060204": {"iso": "CCMT 06 02 04", "shape": "C (80\u00b0 Rhombic)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "CCGT060204": {"iso": "CCGT 06 02 04", "shape": "C (80\u00b0 Rhombic)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "CCMT09T304": {"iso": "CCMT 09T3 04", "shape": "C (80\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "CCGT09T304": {"iso": "CCGT 09T3 04", "shape": "C (80\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "DCMT070204": {"iso": "DCMT 07 02 04", "shape": "D (55\u00b0 Rhombic)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "DCGT070204": {"iso": "DCGT 07 02 04", "shape": "D (55\u00b0 Rhombic)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "DCMT11T302": {"iso": "DCMT 11T3 02", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.2,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "DCMT11T304": {"iso": "DCMT 11T3 04", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "DCMT11T308": {"iso": "DCMT 11T3 08", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.8,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "DCMT11T312": {"iso": "DCMT 11T3 12", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 1.2,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "DCGT11T302": {"iso": "DCGT 11T3 02", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.2,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "DCGT11T304": {"iso": "DCGT 11T3 04", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "DCGT11T308": {"iso": "DCGT 11T3 08", "shape": "D (55\u00b0 Rhombic)", "ic": 9.525, "s": 3.97, "re": 0.8,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "VCMT110304": {"iso": "VCMT 11 03 04", "shape": "V (35\u00b0 Rhombic)", "ic": 6.35, "s": 3.18, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "VCGT110304": {"iso": "VCGT 11 03 04", "shape": "V (35\u00b0 Rhombic)", "ic": 6.35, "s": 3.18, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "TCMT110204": {"iso": "TCMT 11 02 04", "shape": "T (60\u00b0 Triangle)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "TCGT110204": {"iso": "TCGT 11 02 04", "shape": "T (60\u00b0 Triangle)", "ic": 6.35, "s": 2.38, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "TCMT16T302": {"iso": "TCMT 16T3 02", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.2,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "TCMT16T304": {"iso": "TCMT 16T3 04", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "TCMT16T308": {"iso": "TCMT 16T3 08", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.8,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "TCMT16T312": {"iso": "TCMT 16T3 12", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 1.2,
                   "relief": 7, "tolerance": "M", "holding": "T (through hole)"},
    "TCGT16T302": {"iso": "TCGT 16T3 02", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.2,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "TCGT16T304": {"iso": "TCGT 16T3 04", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.4,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "TCGT16T308": {"iso": "TCGT 16T3 08", "shape": "T (60\u00b0 Triangle)", "ic": 9.525, "s": 3.97, "re": 0.8,
                   "relief": 7, "tolerance": "G", "holding": "T (through hole)"},
    "VBMT110304": {"iso": "VBMT 11 03 04", "shape": "V (35\u00b0) VBMT positive",  "ic": 6.35, "s": 3.18, "re": 0.4,
                   "relief": 5, "tolerance": "M", "holding": "T (through hole)"},
    "VBGT110304": {"iso": "VBGT 11 03 04", "shape": "V (35\u00b0) VBGT positive", "ic": 6.35, "s": 3.18, "re": 0.4,
                   "relief": 5, "tolerance": "G", "holding": "T (through hole)"},
    "VBMT160404": {"iso": "VBMT 16 04 04", "shape": "V (35\u00b0) VBMT positive", "ic": 12.7, "s": 4.76, "re": 0.4,
                   "relief": 5, "tolerance": "M", "holding": "T (through hole)"},
    "VBGT160404": {"iso": "VBGT 16 04 04", "shape": "V (35\u00b0) VBGT positive", "ic": 12.7, "s": 4.76, "re": 0.4,
                   "relief": 5, "tolerance": "G", "holding": "T (through hole)"},
}

# Compatible holders per seat prefix (from DB query)
SEAT_HOLDERS = {
    "CCMT060204": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCGT060204": ["SCACR-0808K-06S","SCACR-1010K-06S","QSM12-SCLCR-06C"],
    "CCMT09T304": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "CCGT09T304": ["SCACR-1010K-09S","SCACR-1212K-09S","QSM12-SCLCL-09C","QSM12-SCLCR-09C","QSM16-SCLCL-09C","KM16SCLCR0920","KM16SCGCR0920"],
    "DCMT070204": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCGT070204": ["SDJCR-0808K-07S","SDJCR-1010M-07S","SDJCR-1212K-07S","QSM12-SDJCL-07C","QSM12-SDJCR-07C"],
    "DCMT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCMT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCMT11T308": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCMT11T312": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCGT11T302": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCR-11B-Y","QSM16-SDJCR-11B-Y"],
    "DCGT11T304": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "DCGT11T308": ["SDJCR-1010K-11S","SDJCR-1212M-11S","KM16SDACR1120","KM16SDJCR1120","QSM12-SDJCL-11C","QSM12-SDJCR-11C","QSM16-SDJCL-11C"],
    "VCMT110304": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "VCGT110304": ["SVJCR-0808K-11S","SVJCR-1010K-11S","SVJCR-1212K-11S","QSM12-SVJCL-11C","QSM12-SVJCR-11C","QSM16-SVJCL-11C"],
    "TCMT110204": ["KM16STJCR1120"],
    "TCGT110204": ["KM16STJCR1120"],
    "TCMT16T302": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T304": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T308": ["KM16STGCR1620","KM16STJCR1620"],
    "TCMT16T312": ["KM16STGCR1620","KM16STJCR1620"],
    "TCGT16T302": ["KM16STGCR1620","KM16STJCR1620"],
    "TCGT16T304": ["KM16STGCR1620","KM16STJCR1620"],
    "TCGT16T308": ["KM16STGCR1620","KM16STJCR1620"],
    "VBMT110304": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBGT110304": ["KM16SVJBR1120","KM16LSSHPC2010"],
    "VBMT160404": ["KM16SVJBR1630","KM16SVGBR1630"],
    "VBGT160404": ["KM16SVJBR1630","KM16SVGBR1630"],
}

def get_chipbreaker_key(part):
    """Extract chipbreaker suffix from part number."""
    # Part format: CCMT060204-PSF or CCMT060204FN-JS etc.
    idx = part.rfind("-")
    if idx >= 0:
        return part[idx+1:]
    # No dash - might be bare (e.g. CCGT09T304 with no chipbreaker)
    return ""

def get_cb_desc(cb_key):
    """Look up chipbreaker info, with fallback."""
    if cb_key in CB_INFO:
        return CB_INFO[cb_key]
    # Try prefix matching for compound codes like FN-JS, MF-JS
    for key in CB_INFO:
        if cb_key.endswith(key):
            return CB_INFO[key]
    return (cb_key + " chipbreaker", ["steel","stainless"], ["turning"], "See Tungaloy catalog")

def extract_all():
    results = {}
    with pdfplumber.open("catalogs/Tungaloy/GC_2023-2024_G_B_Insert.pdf") as pdf:
        target_pages = [18,112,113,114,115,116,117,118,122,123,124,126,127,
                        140,141,142,143,152,153,154,155,156,194,195,197,198,212,213,217,218]
        for pg_num in target_pages:
            text = pdf.pages[pg_num-1].extract_text() or ""
            for line in text.split("\n"):
                for tok in line.split():
                    m = matches_prefix(tok)
                    if m and tok not in results:
                        idx = line.find(tok)
                        rest = line[idx + len(tok):]
                        nums = parse_nums(rest)
                        if len(nums) >= 4:
                            RE, IC, S, D1 = nums[-4], nums[-3], nums[-2], nums[-1]
                        elif len(nums) == 3:
                            RE, IC, S, D1 = None, nums[-3], nums[-2], nums[-1]
                        else:
                            RE, IC, S, D1 = None, None, None, None
                        # Override with known standard values if available
                        iso = PREFIX_TO_ISO.get(m, {})
                        if iso:
                            IC = iso["ic"]
                            S = iso["s"]
                            if RE is None:
                                RE = iso["re"]
                        results[tok] = {"prefix": m, "RE": RE, "IC": IC, "S": S, "D1": D1}
    return results

SHAPE_MAP = {
    "C": "80 deg Diamond",
    "D": "55 deg Diamond",
    "V": "35 deg Diamond",
    "T": "Triangle",
    "VB": "35 deg Diamond (VBMT)",
}

def build_records(results):
    rows = []
    for part, data in sorted(results.items()):
        prefix = data["prefix"]
        iso_data = PREFIX_TO_ISO.get(prefix, {})
        if not iso_data:
            continue

        cb_key = get_chipbreaker_key(part)
        cb_desc, materials, ops, grades = get_cb_desc(cb_key)
        holders = SEAT_HOLDERS.get(prefix, [])

        iso_str = iso_data["iso"]
        shape_letter = prefix[:1] if prefix[:2] != "VB" else "VB"
        shape_full = SHAPE_MAP.get(shape_letter, prefix[:1])

        RE = data["RE"] or iso_data.get("re", 0.4)
        IC = data["IC"] or iso_data.get("ic")
        S  = data["S"]  or iso_data.get("s")
        D1 = data["D1"]

        specs = {
            "iso_id": part,
            "iso_designation": iso_str,
            "ic_mm": IC,
            "s_mm": S,
            "re_mm": RE,
            "clearance_angle_deg": iso_data.get("relief", 7),
            "tolerance": iso_data.get("tolerance", "M"),
            "holding": iso_data.get("holding", "T (through hole)"),
            "insert_type": "positive",
            "available_grades": grades,
        }
        if D1:
            specs["d1_mm"] = D1

        tags = list(materials) + list(ops) + ["Tungaloy"]
        shape_name = iso_str.split()[0]  # e.g. CCMT
        tags.append(shape_name)
        if "finishing" in ops:
            tags.append("finishing")
        if "medium" in ops or "semi-finishing" in ops:
            tags.append("medium cutting")

        desc = ("Tungaloy %s positive turning insert, %s chipbreaker. "
                "%s. Corner radius %.1f mm, IC %.3f mm. "
                "Available grades: %s." % (
                    iso_str, cb_key if cb_key else "standard",
                    cb_desc, RE, IC or 0, grades))

        compat_machines = []
        if holders:
            compat_machines = ["Compatible via holders: " + ", ".join(holders)]
        else:
            compat_machines = ["CNC turning - see compatible holders"]

        row = {
            "json_id": part,
            "component_type": "insert",
            "category": "Turning Inserts",
            "type": "%s Screw-On Turning Insert" % shape_name,
            "manufacturer": "Tungaloy",
            "description": desc,
            "specs": json.dumps(specs),
            "size": prefix[4:] if len(prefix) > 4 else prefix,
            "geometry": "%s positive, 7-deg clearance, %s chipbreaker" % (iso_str, cb_key or "standard"),
            "compatible_machines": json.dumps(compat_machines),
            "compatible_inserts": json.dumps(["N/A (this is the insert)"]),
            "sources": json.dumps(["Tungaloy General Catalog 2023-2024 Section B (Inserts)"]),
            "tags": json.dumps(tags),
            "condition": "New",
            "grade": grades.split(",")[0].strip() if grades else "multiple",
            "shape": shape_full,
            "chipbreaker": cb_desc,
            "iso_designation": iso_str,
        }
        rows.append(row)
    return rows


def insert_to_db(db_path, rows):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get existing json_ids to avoid duplicates
    existing = set(r[0] for r in c.execute("SELECT json_id FROM tools").fetchall())

    inserted = 0
    skipped = 0
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
    print("Extracted %d inserts from PDF" % len(results))

    rows = build_records(results)
    print("Built %d DB records" % len(rows))

    # Sample check
    for p in ["CCMT060204-PSF","CCMT09T304-PS","DCMT11T304-PSF","VCMT110304-TSF",
              "TCMT16T304-PM","VBMT160404-PSS","VBMT110304-CM"]:
        if p in results:
            r = results[p]
            print("  %s: RE=%.2f IC=%.3f S=%.3f D1=%s" % (
                p, r["RE"] or 0, r["IC"] or 0, r["S"] or 0, r["D1"]))

    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db("docs/db.sqlite", rows)
        print("Inserted %d new records, skipped %d duplicates" % (inserted, skipped))
    else:
        print("\nRun with --insert to write to database")
