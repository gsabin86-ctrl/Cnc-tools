import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite")
conn = sqlite3.connect(DB)
c = conn.cursor()

entry = {
    "json_id": "KM16SCLCR0920",
    "category": "Tool Holders & Adapters",
    "type": "SCLC 95° KM Micro Cutting Unit (OD Application)",
    "manufacturer": "Kennametal",
    "description": "S-Clamping 95° cutting unit for external turning OD applications in the KM Micro quick-change system. Right-hand, accepts CCMT/CCGT 09T3 series inserts.",
    "specs": json.dumps({
        "system_size_machine_side": "KM16",
        "f_dimension": "10 mm",
        "cutting_height": "8 mm",
        "tool_length": "20 mm",
        "gage_insert": "CC..09T308",
        "torque": "10-11 Newton Meters",
        "clamping_type": "S-Clamping (Right Hand)",
        "approach_angle": "95 degrees"
    }),
    "size": "KM16",
    "geometry": "95° approach angle for OD turning. S-clamping secures CCMT/CCGT inserts. Suitable for steel, stainless, cast iron, non-ferrous, high-temp alloys, and hardened materials.",
    "compatible_machines": json.dumps(["Lathes with KM Micro quick-change tooling"]),
    "compatible_holders": json.dumps(["KM16NCM10400", "KM16NCMSF1928", "CV40KM16TRA", "KM16NCM1616100"]),
    "compatible_inserts": json.dumps(["CCMT09T3 series", "CCGT09T3 series (KC730 grade)"]),
    "sources": json.dumps(["https://www.kennametal.com/us/en/products/p.sclc-95-km-micro-cutting-units-od-application.1831206.html"]),
    "price_range": "$229.25 (list price)",
    "tags": json.dumps(["turning", "OD", "95-degree", "KM-micro", "S-clamping", "right-hand", "CCMT", "CCGT"]),
    "condition": "New"
}

cols = ", ".join(entry.keys())
placeholders = ", ".join(["?" for _ in entry])
c.execute(f"INSERT OR IGNORE INTO holders ({cols}) VALUES ({placeholders})", list(entry.values()))
conn.commit()
print(f"Done. Holders: {c.execute('SELECT COUNT(*) FROM holders').fetchone()[0]}")
conn.close()
