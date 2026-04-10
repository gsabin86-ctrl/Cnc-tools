import json, os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
PROPOSALS_PATH = os.path.join(DATA_DIR, 'proposals.json')

SOURCE = "Sandvik Latest cutting tools 26-1.pdf"

def mod(json_id, family, desc, insert_seat, mounts_to, specs, tags):
    return {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": json_id,
            "component_type": "module",
            "mounts_to": mounts_to,
            "category": "QS Micro Cutting Heads",
            "type": family,
            "manufacturer": "Sandvik Coromant",
            "description": desc,
            "specs": json.dumps(specs),
            "size": specs.get("ssc_mm", specs.get("ssc")),
            "insert_seat": insert_seat,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "swiss"] + tags),
            "condition": "New"
        }
    }

# Helper: mounts_to based on SSC (cutting side connection size = QSM12 or QSM16)
def mt(ssc):
    # SSC=1 means CXSC=1 = CoroTurn side, connects to QSM12 or QSM16
    # Use the ordering code prefix to determine which shank adaptor
    return None  # set per entry based on QSM prefix in ordering code

entries = []

# -----------------------------------------------------------------------
# 1. CoroTurn 107 — Y-axis general turning (DCMT) — p.63
# -----------------------------------------------------------------------
for code, ssc, lf, wf, hf, htb, lu, ohx, wb in [
    ("QSM12-SDJCR-11B-Y", 11, 21.0, 6.0, 6.0, 18, 13.0, 21.0, 16.0),
    ("QSM16-SDJCR-11B-Y", 11, 25.0, 8.0, 8.0, 18, 23.0, 25.0, 17.6),
]:
    shank = "QSM12-N1212" if code.startswith("QSM12") else "QSM16-N1616"
    entries.append(mod(
        code,
        "CoroTurn 107 QS Micro — Y-axis turning",
        f"CoroTurn 107 QS Micro cutting head for Y-axis general turning. Right-hand, DCMT insert, 93deg approach. Mounts on {shank[:-5]} shank adaptor.",
        "DCMT 11 T3 02",
        shank,
        {"ssc": ssc, "lf_mm": lf, "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "lu_mm": lu, "ohx_mm": ohx, "wb_mm": wb,
         "kapr_deg": 93.0, "rmpx_deg": 27.0, "psir_deg": -3.0,
         "coolant_pressure_bar": 150, "torque_nm": 3.0,
         "hand": "right", "y_axis": True},
        ["CoroTurn 107", "DCMT", "Y-axis", "turning", "right-hand"]
    ))

# -----------------------------------------------------------------------
# 2. CoroTurn 107 — Y-axis general turning (CCMT) — p.63
# -----------------------------------------------------------------------
ccmt_y = [
    ("QSM12-SCLCL-09C", 9,  21.0, 6.0, 6.0, 18, 21.0, 16.0, "CCMT 09 T3 04", 3.0, "left"),
    ("QSM12-SCLCR-06C", 6,  21.0, 6.0, 6.0, 18, 21.0, 16.0, "CCMT 06 02 04", 0.9, "right"),
    ("QSM12-SCLCR-09C", 9,  21.0, 6.0, 6.0, 18, 21.0, 16.0, "CCMT 09 T3 04", 3.0, "right"),
    ("QSM16-SCLCL-09C", 9,  21.0, 8.0, 8.0, 22, 21.0, 18.0, "CCMT 09 T3 04", 3.0, "left"),
    ("QSM16-SCLCR-09C", 9,  21.0, 8.0, 8.0, 22, 21.0, 18.0, "CCMT 09 T3 04", 3.0, "right"),
]
for code, ssc, lf, wf, hf, htb, ohx, wb, seat, tq, hand in ccmt_y:
    shank = "QSM12-N1212" if code.startswith("QSM12") else "QSM16-N1616"
    entries.append(mod(
        code,
        "CoroTurn 107 QS Micro — Y-axis turning",
        f"CoroTurn 107 QS Micro cutting head for Y-axis general turning. {hand.capitalize()}-hand, CCMT insert, 95deg approach. Mounts on {shank[:-5]} shank adaptor.",
        seat,
        shank,
        {"ssc": ssc, "lf_mm": lf, "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "ohx_mm": ohx, "wb_mm": wb,
         "kapr_deg": 95.0, "psir_deg": -5.0,
         "coolant_pressure_bar": 150, "torque_nm": tq,
         "hand": hand, "y_axis": True},
        ["CoroTurn 107", "CCMT", "Y-axis", "turning", f"{hand}-hand"]
    ))

# -----------------------------------------------------------------------
# 3. CoroTurn 107 — general turning (DCMT) — p.64
# -----------------------------------------------------------------------
dcmt_gen = [
    ("QSM12-SDJCL-07C", 7,  22.0, 6.0, 6.0, 18, 22.0, 16.0, "DCMT 07 02 04", 0.9, "left"),
    ("QSM12-SDJCL-11C", 11, 23.0, 6.0, 6.0, 18, 23.0, 16.0, "DCMT 11 T3 08", 3.0, "left"),
    ("QSM12-SDJCR-07C", 7,  22.0, 6.0, 6.0, 18, 22.0, 16.0, "DCMT 07 02 04", 0.9, "right"),
    ("QSM12-SDJCR-11C", 11, 23.0, 6.0, 6.0, 18, 23.0, 16.0, "DCMT 11 T3 08", 3.0, "right"),
    ("QSM16-SDJCL-11C", 11, 23.0, 8.0, 8.0, 23, 23.0, 18.0, "DCMT 11 T3 08", 3.0, "left"),
    ("QSM16-SDJCR-11C", 11, 23.0, 8.0, 8.0, 23, 23.0, 18.0, "DCMT 11 T3 08", 3.0, "right"),
]
for code, ssc, lf, wf, hf, htb, ohx, wb, seat, tq, hand in dcmt_gen:
    shank = "QSM12-N1212" if code.startswith("QSM12") else "QSM16-N1616"
    entries.append(mod(
        code,
        "CoroTurn 107 QS Micro — general turning",
        f"CoroTurn 107 QS Micro cutting head for general turning. {hand.capitalize()}-hand, DCMT insert, 93deg approach. Mounts on {shank[:-5]} shank adaptor.",
        seat,
        shank,
        {"ssc": ssc, "lf_mm": lf, "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "ohx_mm": ohx, "wb_mm": wb,
         "kapr_deg": 93.0, "rmpx_deg": 27.0, "psir_deg": -3.0,
         "coolant_pressure_bar": 150, "torque_nm": tq,
         "hand": hand, "y_axis": False},
        ["CoroTurn 107", "DCMT", "turning", f"{hand}-hand"]
    ))

# -----------------------------------------------------------------------
# 4. CoroTurn 107 — general turning (VCMT) — p.64
# -----------------------------------------------------------------------
vcmt_gen = [
    ("QSM12-SVJCL-11C", 11, 26.0, 6.0, 6.0, 18, 26.0, 16.0, "VCMT 11 03 04", 0.9, "left",  50.0),
    ("QSM12-SVJCR-11C", 11, 26.0, 6.0, 6.0, 18, 26.0, 16.0, "VCMT 11 03 04", 0.9, "right", 50.0),
    ("QSM16-SVJCL-11C", 11, 26.0, 8.0, 8.0, 22, 26.0, 18.0, "VCMT 11 03 04", 0.9, "left",   0.0),
    ("QSM16-SVJCR-11C", 11, 26.0, 8.0, 8.0, 22, 26.0, 18.0, "VCMT 11 03 04", 0.9, "right",  0.0),
]
for code, ssc, lf, wf, hf, htb, ohx, wb, seat, tq, hand, rmpx in vcmt_gen:
    shank = "QSM12-N1212" if code.startswith("QSM12") else "QSM16-N1616"
    entries.append(mod(
        code,
        "CoroTurn 107 QS Micro — general turning",
        f"CoroTurn 107 QS Micro cutting head for general turning. {hand.capitalize()}-hand, VCMT insert, 93deg approach. Mounts on {shank[:-5]} shank adaptor.",
        seat,
        shank,
        {"ssc": ssc, "lf_mm": lf, "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "ohx_mm": ohx, "wb_mm": wb,
         "kapr_deg": 93.0, "rmpx_deg": rmpx, "psir_deg": -3.0,
         "coolant_pressure_bar": 150, "torque_nm": tq,
         "hand": hand, "y_axis": False},
        ["CoroTurn 107", "VCMT", "turning", f"{hand}-hand"]
    ))

# -----------------------------------------------------------------------
# 5. CoroCut 2 — parting & grooving — p.103
# -----------------------------------------------------------------------
# Insert seat coding: E/F/G = CoroCut 2 blade width designation
corocut2 = [
    ("C2R-QSM12-LE15AD", "QSM12", "E", 15.0, 32.0, 16.0, 32.0, 6.0, 6.0, 24, 2.5, "left"),
    ("C2R-QSM12-LF15AD", "QSM12", "F", 15.0, 28.0, 16.0, 28.0, 6.0, 6.0, 24, 2.5, "left"),
    ("C2R-QSM12-RE15AD", "QSM12", "E", 15.0, 32.0, 16.0, 32.0, 6.0, 6.0, 24, 2.5, "right"),
    ("C2R-QSM12-RF15AD", "QSM12", "F", 15.0, 28.0, 16.0, 28.0, 6.0, 6.0, 24, 2.5, "right"),
    ("C2R-QSM16-LE17AD", "QSM16", "E", 17.0, 33.0, 18.0, 33.0, 8.0, 8.0, 26, 2.5, "left"),
    ("C2R-QSM16-LG17AD", "QSM16", "G", 17.0, 32.0, 18.0, 32.0, 8.0, 8.0, 26, 2.5, "left"),
    ("C2R-QSM16-RE17AD", "QSM16", "E", 17.0, 33.0, 18.0, 33.0, 8.0, 8.0, 26, 2.5, "right"),
    ("C2R-QSM16-RG17AD", "QSM16", "G", 17.0, 32.0, 18.0, 32.0, 8.0, 8.0, 26, 2.5, "right"),
]
for code, qs, blade, cdx, ohx, wb, lf, wf, hf, htb, tq, hand in corocut2:
    shank = f"{qs}-N1616" if qs == "QSM16" else f"{qs}-N1212"
    entries.append(mod(
        code,
        "CoroCut 2 QS Micro — parting & grooving",
        f"CoroCut 2 QS Micro cutting head for parting and grooving. {hand.capitalize()}-hand, blade width {blade}, CDX {cdx}mm, internal coolant. Mounts on {qs} shank adaptor.",
        f"CoroCut 2 blade width {blade}",
        shank,
        {"cdx_mm": cdx, "ohx_mm": ohx, "wb_mm": wb, "lf_mm": lf,
         "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "blade_width_code": blade, "internal_coolant": True,
         "torque_nm": tq, "hand": hand},
        ["CoroCut 2", "parting", "grooving", f"{hand}-hand", "internal coolant"]
    ))

# -----------------------------------------------------------------------
# 6. CoroCut XS — parting & grooving — p.116
# -----------------------------------------------------------------------
xs_pg = [
    ("QSM12-SMALL-3A", "QSM12", 8.5, 28.0, 28.0, 16.0, 28.0, 6.0, 6.0, 18, 1.2, "left"),
    ("QSM12-SMALR-3A", "QSM12", 8.5, 28.0, 28.0, 16.0, 28.0, 6.0, 6.0, 18, 1.2, "right"),
    ("QSM16-SMALL-3A", "QSM16", 8.5, 28.0, None, 18.0, 28.0, 8.0, 8.0, 21, 1.2, "left"),
    ("QSM16-SMALR-3A", "QSM16", 8.5, 28.0, None, 18.0, 28.0, 8.0, 8.0, 21, 1.2, "right"),
]
for code, qs, cdx, ohx, ohn, wb, lf, wf, hf, htb, tq, hand in xs_pg:
    shank = f"{qs}-N1616" if qs == "QSM16" else f"{qs}-N1212"
    specs = {"cdx_mm": cdx, "ohx_mm": ohx, "wb_mm": wb, "lf_mm": lf,
             "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
             "torque_nm": tq, "hand": hand, "screw_clamp": True}
    if ohn: specs["ohn_mm"] = ohn
    entries.append(mod(
        code,
        "CoroCut XS QS Micro — parting & grooving",
        f"CoroCut XS QS Micro cutting head for parting and grooving. {hand.capitalize()}-hand, CDX {cdx}mm, screw clamp design. Mounts on {qs} shank adaptor.",
        "CoroCut XS 3mm width",
        shank,
        specs,
        ["CoroCut XS", "parting", "grooving", f"{hand}-hand", "screw clamp"]
    ))

# -----------------------------------------------------------------------
# 7. CoroCut XS — Y-axis parting & grooving — p.117
# -----------------------------------------------------------------------
xs_y = [
    ("QSM12-SMALR-3B-Y", "QSM12", 8.5, 15.0, 20.0, 26.0, 20.0, 6.0, 6.0, 16, 150, 1.2),
    ("QSM16-SMALR-3B-Y", "QSM16", 8.5, 20.0, 25.0, 26.0, 25.0, 8.0, 8.0, 18, 150, 1.2),
]
for code, qs, cdx, lu, ohx, wb, lf, wf, hf, htb, cp, tq in xs_y:
    shank = f"{qs}-N1616" if qs == "QSM16" else f"{qs}-N1212"
    entries.append(mod(
        code,
        "CoroCut XS QS Micro — Y-axis parting & grooving",
        f"CoroCut XS QS Micro cutting head for Y-axis parting and grooving. Right-hand, CDX {cdx}mm. Mounts on {qs} shank adaptor.",
        "CoroCut XS 3mm width",
        shank,
        {"cdx_mm": cdx, "lu_mm": lu, "ohx_mm": ohx, "wb_mm": wb,
         "lf_mm": lf, "wf_mm": wf, "hf_mm": hf, "htb_mm": htb,
         "coolant_pressure_bar": cp, "torque_nm": tq,
         "hand": "right", "y_axis": True},
        ["CoroCut XS", "parting", "grooving", "Y-axis", "right-hand"]
    ))

# Load + append + save
if os.path.exists(PROPOSALS_PATH):
    with open(PROPOSALS_PATH, 'r', encoding='utf-8') as f:
        existing = json.load(f)
else:
    existing = []

existing.extend(entries)

with open(PROPOSALS_PATH, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print(f"Added {len(entries)} proposals")
print(f"\nSummary by family:")
from collections import Counter
c = Counter(e['fields']['type'] for e in entries)
for k,v in c.items():
    print(f"  {v:2d}  {k}")

print(f"\nSample mounts_to:")
for e in entries[:3]:
    print(f"  {e['fields']['json_id']:30s} -> {e['fields']['mounts_to']}")
