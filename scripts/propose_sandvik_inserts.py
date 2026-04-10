import json, os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
PROPOSALS_PATH = os.path.join(DATA_DIR, 'proposals.json')
SRC_107 = "Sandvik Latest cutting tools 26-1.pdf p.29-40"
SRC_C2  = "Sandvik Latest cutting tools 26-1.pdf p.76-96"

def ins(json_id, shape, iso_desig, chipbreaker, grade, category, app, specs, tags, source):
    return {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": json_id,
            "component_type": "insert",
            "mounts_to": None,
            "category": category,
            "type": app,
            "manufacturer": "Sandvik Coromant",
            "description": f"Sandvik {shape} insert {json_id}, chipbreaker {chipbreaker}, grade {grade}.",
            "specs": json.dumps(specs),
            "size": specs.get("ssc") or specs.get("width_code"),
            "insert_seat": None,
            "iso_designation": iso_desig,
            "compatible_inserts": None,
            "sources": json.dumps([source]),
            "price_range": None,
            "grade": grade,
            "shape": shape,
            "chipbreaker": chipbreaker,
            "tags": json.dumps(["sandvik", "swiss"] + tags),
            "condition": "New"
        }
    }

entries = []

# ============================================================
# SECTION 1: CoroTurn 107 — CCMT inserts (metric only)
# ============================================================
ccmt_data = [
    # (ordering_code, ssc, le_mm, s_mm, re_mm, ic_mm, bn_mm, chipbreaker, grade, app)
    ("CCMT 09 T3 04-PF", "09", 9.3,  3.97, 0.4, 9.52, None, "PF", "1625", "Finishing"),
    ("CCMT 09 T3 08-PF", "09", 8.9,  3.97, 0.8, 9.52, None, "PF", "1625", "Finishing"),
    ("CCMT 12 04 04-PF", "12", 12.5, 4.76, 0.4, 12.70,None, "PF", "1625", "Finishing"),
    ("CCMT 09 T3 04-UF", "09", 9.3,  3.97, 0.4, 9.52, None, "UF", "1625", "Finishing"),
    ("CCMT 06 02 04-WF", "06", 6.0,  2.38, 0.4, 6.35, 0.10, "WF", "1625", "Finishing"),
    ("CCMT 06 02 08-WF", "06", 5.6,  2.38, 0.8, 6.35, 0.10, "WF", "1625", "Finishing"),
    ("CCMT 09 T3 04-WF", "09", 9.3,  3.97, 0.4, 9.52, 0.10, "WF", "1625", "Finishing"),
    ("CCMT 09 T3 08-WF", "09", 8.9,  3.97, 0.8, 9.52, 0.10, "WF", "1625", "Finishing"),
    ("CCMT 06 02 04-PM", "06", 6.0,  2.38, 0.4, 6.35, None, "PM", "1625", "Medium"),
    ("CCMT 06 02 08-PM", "06", 5.6,  2.38, 0.8, 6.35, None, "PM", "1625", "Medium"),
    ("CCMT 09 T3 04-PM", "09", 9.3,  3.97, 0.4, 9.52, None, "PM", "1625", "Medium"),
    ("CCMT 09 T3 08-PM", "09", 8.9,  3.97, 0.8, 9.52, None, "PM", "1625", "Medium"),
    ("CCMT 12 04 08-PM", "12", 12.1, 4.76, 0.8, 12.70,None, "PM", "1625", "Medium"),
    ("CCMT 06 02 04-UM", "06", 6.0,  2.38, 0.4, 6.35, None, "UM", "1625", "Medium"),
    ("CCMT 09 T3 04-UM", "09", 9.3,  3.97, 0.4, 9.52, None, "UM", "1625", "Medium"),
    ("CCMT 09 T3 08-UM", "09", 8.9,  3.97, 0.8, 9.52, None, "UM", "1625", "Medium"),
    ("CCMT 09 T3 04-WM", "09", 9.3,  3.97, 0.4, 9.52, 0.12, "WM", "1625", "Medium"),
    ("CCMT 09 T3 08-WM", "09", 8.9,  3.97, 0.8, 9.52, 0.14, "WM", "1625", "Medium"),
]
for code, ssc, le, s, re, ic, bn, cb, grade, app in ccmt_data:
    # json_id: strip spaces and replace with dashes for consistency
    jid = code.replace(" ", "-")
    spec = {"ssc": ssc, "le_mm": le, "s_mm": s, "re_mm": re, "ic_mm": ic, "material_groups": ["P","M","K"]}
    if bn: spec["bn_mm"] = bn
    entries.append(ins(jid, "CCMT", code, cb, grade,
        "CoroTurn 107 Inserts", f"CoroTurn 107 turning insert — {app}",
        spec, ["CoroTurn 107", "CCMT", "turning", app.lower()], SRC_107))

# ============================================================
# SECTION 2: CoroTurn 107 — DCMT inserts (metric only)
# ============================================================
dcmt_data = [
    ("DCMT 11 T3 04-PF", "11", 11.2, 3.97, 0.4,  9.52, "PF", "1625", "Finishing"),
    ("DCMT 11 T3 08-PF", "11", 10.8, 3.97, 0.8,  9.52, "PF", "1625", "Finishing"),
    ("DCMT 11 T3 04-UF", "11", 11.2, 3.97, 0.4,  9.52, "UF", "1625", "Finishing"),
    ("DCMT 07 02 04-PM", "07", 7.4,  2.38, 0.4,  6.35, "PM", "1625", "Medium"),
    ("DCMT 07 02 08-PM", "07", 7.0,  2.38, 0.8,  6.35, "PM", "1625", "Medium"),
    ("DCMT 11 T3 04-PM", "11", 11.2, 3.97, 0.4,  9.52, "PM", "1625", "Medium"),
    ("DCMT 11 T3 08-PM", "11", 10.8, 3.97, 0.8,  9.52, "PM", "1625", "Medium"),
    ("DCMT 11 T3 12-PM", "11", 10.4, 3.97, 1.2,  9.52, "PM", "1625", "Medium"),
    ("DCMT 07 02 04-UM", "07", 7.4,  2.38, 0.4,  6.35, "UM", "1625", "Medium"),
    ("DCMT 11 T3 04-UM", "11", 11.2, 3.97, 0.4,  9.52, "UM", "1625", "Medium"),
    ("DCMT 11 T3 08-UM", "11", 10.8, 3.97, 0.8,  9.52, "UM", "1625", "Medium"),
]
for code, ssc, le, s, re, ic, cb, grade, app in dcmt_data:
    jid = code.replace(" ", "-")
    spec = {"ssc": ssc, "le_mm": le, "s_mm": s, "re_mm": re, "ic_mm": ic, "material_groups": ["P","M","K"]}
    entries.append(ins(jid, "DCMT", code, cb, grade,
        "CoroTurn 107 Inserts", f"CoroTurn 107 turning insert — {app}",
        spec, ["CoroTurn 107", "DCMT", "turning", app.lower()], SRC_107))

# ============================================================
# SECTION 3: CoroCut 2 — Parting inserts (E/F/G)
# ============================================================
# (json_id, width_code, cw_mm, chipbreaker, hand, psir_deg, an_deg, grades_summary)
corocut2_parting = [
    # RH CF
    ("C2I-F2R-0250-0501-CF", "F", 2.50, "CF", "R", 5.0, 7.0, ["P1225","P1135","P1145","M1225","M1135","M1145","K1225","K1135","N1225","N1135","S1145"]),
    ("C2I-G2R-0300-0501-CF", "G", 3.00, "CF", "R", 5.0, 7.0, ["P1225","P1135","P1145","M1225","M1135","M1145","K1225","K1135","N1225","N1135","S1145"]),
    # RH CR
    ("C2I-F2R-0250-0503-CR", "F", 2.50, "CR", "R", 5.0, 7.0, ["P1225","P1135","M1225","M1135","K1225","K1135","N1225","S1135"]),
    ("C2I-G2R-0300-0503-CR", "G", 3.00, "CR", "R", 5.0, 7.0, ["P1225","P1135","P1145","M1225","M1135","M1145","K1225","K1135","N1225","N1135","S1145"]),
    # RH CS
    ("C2I-E2R-0200-1001-CS", "E", 2.00, "CS", "R", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-E2R-0200-1501-CS", "E", 2.00, "CS", "R", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-F2R-0250-1001-CS", "F", 2.50, "CS", "R", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-F2R-0250-1501-CS", "F", 2.50, "CS", "R", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-G2R-0300-1001-CS", "G", 3.00, "CS", "R", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-G2R-0300-1501-CS", "G", 3.00, "CS", "R", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    # LH CF
    ("C2I-F2L-0250-0501-CF", "F", 2.50, "CF", "L", 5.0, 7.0, ["P1225","M1135","K1225","K1135","N1225","S1135"]),
    ("C2I-G2L-0300-0501-CF", "G", 3.00, "CF", "L", 5.0, 7.0, ["P1225","P1135","P1145","M1225","M1135","M1145","K1225","K1135","N1225","N1135","S1145"]),
    # LH CR
    ("C2I-F2L-0250-0503-CR", "F", 2.50, "CR", "L", 5.0, 7.0, ["P1225","P1135","M1225","M1135","K1225","K1135","N1225","S1135"]),
    ("C2I-G2L-0300-0503-CR", "G", 3.00, "CR", "L", 5.0, 7.0, ["P1225","P1135","M1225","M1135","K1225","K1135","N1225","N1135","S1135"]),
    # LH CS
    ("C2I-E2L-0200-1001-CS", "E", 2.00, "CS", "L", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-E2L-0200-1501-CS", "E", 2.00, "CS", "L", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-F2L-0250-1001-CS", "F", 2.50, "CS", "L", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-F2L-0250-1501-CS", "F", 2.50, "CS", "L", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-G2L-0300-1001-CS", "G", 3.00, "CS", "L", 10.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    ("C2I-G2L-0300-1501-CS", "G", 3.00, "CS", "L", 15.0, 5.0, ["P1225","M1225","K1225","N1225","S1225"]),
    # Neutral CF
    ("C2I-F2N-0250-0001-CF", "F", 2.50, "CF", "N", None, 7.0, ["P1225","P1135","P1145","P5015","P4425","M1225","M1135","M1145","M5015","K1225","K1135","K4425","N1205","N1225","S1135","S1145"]),
    ("C2I-G2N-0300-0001-CF", "G", 3.00, "CF", "N", None, 7.0, ["P1225","P1135","P1145","P5015","P4425","M1205","M1225","M1135","M1145","M5015","K1225","K1135","K4425","N1205","N1225","N1135","S1225","S1135","S1145"]),
    # Neutral CM
    ("C2I-E2N-0200-0002-CM", "E", 2.00, "CM", "N", None, 7.0, ["M1205","N1205","S1205"]),
    ("C2I-F2N-0250-0002-CM", "F", 2.50, "CM", "N", None, 7.0, ["M1205","N1205","S1205"]),
    ("C2I-G2N-0300-0002-CM", "G", 3.00, "CM", "N", None, 7.0, ["M1205","N1205","S1205"]),
    # Neutral CO
    ("C2I-E2N-0200-0001-CO", "E", 2.00, "CO", "N", None, 7.0, ["P1225","P1135","P1145","P1205","M1225","M1135","M1145","K1225","K1135","N1205","N1225","S1225","S1135","S1145"]),
    ("C2I-F2N-0250-0001-CO", "F", 2.50, "CO", "N", None, 7.0, ["P1225","P1135","P1145","P1205","M1225","M1135","M1145","K1225","K1135","N1205","N1225","S1225","S1135","S1145"]),
    ("C2I-G2N-0300-0001-CO", "G", 3.00, "CO", "N", None, 7.0, ["P1225","P1135","P1145","P1205","M1225","M1135","M1145","K1225","K1135","N1205","N1225","S1225","S1135","S1145"]),
    # Neutral CR
    ("C2I-F2N-0250-0003-CR", "F", 2.50, "CR", "N", None, 7.0, ["P1225","P1135","P3115","P1145","P4425","M1205","M1225","M1135","M1145","K1225","K1135","K3115","K4425","N1205","N1225","S1225","S1135","S1145"]),
    ("C2I-G2N-0300-0003-CR", "G", 3.00, "CR", "N", None, 7.0, ["P1225","P1135","P3115","P1145","P4425","M1205","M1225","M1135","M1145","K1225","K1135","K3115","K4425","N1205","N1225","S1225","S1135","S1145"]),
]
for code, wc, cw, cb, hand, psir, an, grades in corocut2_parting:
    spec = {"width_code": wc, "cutting_width_mm": cw, "hand": hand, "clearance_angle_deg": an,
            "grades_available": grades}
    if psir is not None: spec["psir_deg"] = psir
    hand_label = {"R": "right-hand", "L": "left-hand", "N": "neutral"}[hand]
    entries.append(ins(code, "CoroCut 2", code, cb, grades[0] if grades else "1225",
        "CoroCut 2 Inserts", f"CoroCut 2 parting insert — {hand_label} — {cb}",
        spec, ["CoroCut 2", "parting", hand_label, f"width-{wc}", f"{cw}mm"], SRC_C2))

# ============================================================
# SECTION 4: CoroCut 2 — Grooving inserts (E/F/G)
# ============================================================
corocut2_grooving = [
    # GF finishing
    ("C2I-E2N-0185-0001-GF", "E", 1.85, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-E2N-0200-0002-GF", "E", 2.00, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-E2N-0200-0004-GF", "E", 2.00, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-E2N-0224-0002-GF", "E", 2.24, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-F2N-0239-0002-GF", "F", 2.39, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-F2N-0239-0004-GF", "F", 2.39, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-F2N-0246-0003-GF", "F", 2.46, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-F2N-0279-0003-GF", "F", 2.79, "GF", 1.0,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0300-0002-GF", "G", 3.00, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0300-0004-GF", "G", 3.00, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0300-0008-GF", "G", 3.00, "GF", 1.5,  ["P1225","M1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0318-0002-GF", "G", 3.18, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0318-0004-GF", "G", 3.18, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0318-0008-GF", "G", 3.18, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    ("C2I-G2N-0361-0003-GF", "G", 3.61, "GF", 1.5,  ["P1225","M1205","K1225","N1205","S1225"]),
    # GL medium
    ("C2I-E2N-0200-0003-GL", "E", 2.00, "GL", None, ["P1225","P1135","P3115","P4425","M1225","M1135","K1225","K1135","K3115","K4425","N1225","S1225","S1135"]),
    ("C2I-F2N-0250-0003-GL", "F", 2.50, "GL", None, ["P1225","P1135","P3115","P4425","M1225","M1135","K1225","K1135","K3115","K4425","N1225","S1225","S1135"]),
    ("C2I-G2N-0300-0003-GL", "G", 3.00, "GL", None, ["P1225","P1135","P3115","P4425","M1225","M1135","K1225","K1135","K3115","K4425","N1225","S1225","S1135"]),
    # GM medium
    ("C2I-E2N-0200-0002-GM", "E", 2.00, "GM", None, ["P1225","P1135","P3115","P1145","P4425","M1225","M1135","M1145","K1225","K1135","K3115","N1225","S1225","S1135","S1145"]),
    ("C2I-E2N-0239-0002-GM", "E", 2.39, "GM", None, ["P1225","P1135","M1225","M1135","K1225","K1135","N1225","S1225","S1135"]),
    ("C2I-G2N-0300-0003-GM", "G", 3.00, "GM", None, ["P1225","P1135","P3115","P1145","P4425","M1225","M1135","M1145","K1225","K1135","K3115","N1225","S1225","S1135","S1145"]),
    ("C2I-G2N-0318-0003-GM", "G", 3.18, "GM", None, ["P1225","P1135","P3115","P1145","P4425","M1225","M1135","M1145","K1225","K1135","K3115","N1225","S1225","S1135","S1145"]),
]
for code, wc, cw, cb, apmx, grades in corocut2_grooving:
    spec = {"width_code": wc, "cutting_width_mm": cw, "hand": "neutral", "grades_available": grades}
    if apmx: spec["apmx_mm"] = apmx
    entries.append(ins(code, "CoroCut 2", code, cb, grades[0] if grades else "1225",
        "CoroCut 2 Inserts", f"CoroCut 2 grooving insert — neutral — {cb}",
        spec, ["CoroCut 2", "grooving", "neutral", f"width-{wc}", f"{cw}mm"], SRC_C2))

# ============================================================
# SECTION 5: CoroCut 2 — Turning (TF/TM) & Profiling (RO)
# ============================================================
corocut2_other = [
    ("C2I-G2N-0300-0003-TF", "G", 3.00, "TF", "turning",  1.8,  None, ["M1205","N1205","S1205"]),
    ("C2I-G2N-0300-0004-TM", "G", 3.00, "TM", "turning",  None, None, ["P1225","P1135","P3115","M1145","M5015","M4425","M1205","K1225","K1135","K1145","K5015","N1225","N1135","N3115","S1225","S1135","S1145","S1205"]),
    ("C2I-E2N-0200-RO",      "E", 2.00, "RO", "profiling", 0.8,  1.0, ["P1225","P1135","M1205","M1225","M1135","K1225","K1135","K1205","N1225","N1205","S1225","S1135"]),
    ("C2I-E2N-0239-RO",      "E", 2.39, "RO", "profiling", 1.0,  1.2, ["P1225","P1135","M1225","M1135","K1225","K1135","N1225","S1225","S1135"]),
    ("C2I-F2N-0300-RO",      "F", 3.00, "RO", "profiling", 1.3,  1.5, ["P1225","P1135","P1205","M1225","M1135","K1225","K1135","K1205","N1225","N1205","S1225","S1135"]),
    ("C2I-F2N-0318-RO",      "F", 3.18, "RO", "profiling", 1.4,  1.6, ["P1225","P1135","M1205","M1225","M1135","K1225","K1135","N1205","S1225","S1135"]),
]
for code, wc, cw, cb, app, apmx, re, grades in corocut2_other:
    spec = {"width_code": wc, "cutting_width_mm": cw, "hand": "neutral", "grades_available": grades}
    if apmx: spec["apmx_mm"] = apmx
    if re:   spec["re_mm"] = re
    entries.append(ins(code, "CoroCut 2", code, cb, grades[0] if grades else "1225",
        "CoroCut 2 Inserts", f"CoroCut 2 {app} insert — neutral — {cb}",
        spec, ["CoroCut 2", app, "neutral", f"width-{wc}"], SRC_C2))

# ============================================================
# Save
# ============================================================
if os.path.exists(PROPOSALS_PATH):
    with open(PROPOSALS_PATH, 'r', encoding='utf-8') as f:
        existing = json.load(f)
else:
    existing = []

existing.extend(entries)

with open(PROPOSALS_PATH, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

from collections import Counter
print(f"Added {len(entries)} proposals")
print(f"\nBreakdown:")
c = Counter()
for e in entries:
    c[e['fields']['type']] += 1
for k, v in sorted(c.items()):
    print(f"  {v:3d}  {k}")
print(f"\nTotal in proposals.json: {len(existing)}")
