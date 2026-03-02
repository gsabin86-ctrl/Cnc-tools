import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite")
conn = sqlite3.connect(DB)
c = conn.cursor()

inserts = [
    {
        "json_id": "CCMT09T304UF KC730",
        "category": "Turning Inserts",
        "type": "CCMT Screw-On Turning Insert",
        "manufacturer": "Kennametal",
        "description": "Ultra-fine finishing geometry for steel, stainless, and high-temp alloys. Beyond Drive grade KC730.",
        "specs": json.dumps({"ic_size":"9.525 mm","cutting_edge_length":"9.672 mm","thickness":"3.969 mm","corner_radius":"0.4 mm","hole_size":"4.4 mm","iso_id":"CCMT09T304UF","ansi_id":"CCMT3251UF"}),
        "size": "09T3",
        "geometry": "UF - Ultra-fine finishing. Positive rake, sharp edge for light cutting action.",
        "compatible_machines": json.dumps(["CNC lathes with KM Micro tooling"]),
        "compatible_holders": json.dumps(["KM16SCLCR0920"]),
        "compatible_inserts": json.dumps(["N/A"]),
        "sources": json.dumps(["https://www.kennametal.com/us/en/products/p.ccmt09t304uf-kc730.1161831.html"]),
        "price_range": "$29.28 (list price)",
        "tags": json.dumps(["turning","finishing","CCMT","KC730","steel","stainless","high-temp"]),
        "condition": "New"
    },
    {
        "json_id": "CCGT09T304LF KC730",
        "category": "Turning Inserts",
        "type": "CCGT Screw-On Turning Insert",
        "manufacturer": "Kennametal",
        "description": "Light finishing geometry for steel, stainless, and high-temp alloys. Positive insert with sharp cutting action. KC730 grade.",
        "specs": json.dumps({"ic_size":"9.525 mm","cutting_edge_length":"9.672 mm","thickness":"3.969 mm","corner_radius":"0.4 mm","hole_size":"4.4 mm","iso_id":"CCGT09T304LF","ansi_id":"CCGT3251LF"}),
        "size": "09T3",
        "geometry": "LF - Light finishing. Positive rake geometry for reduced cutting forces and fine surface finish.",
        "compatible_machines": json.dumps(["CNC lathes with KM Micro tooling"]),
        "compatible_holders": json.dumps(["KM16SCLCR0920"]),
        "compatible_inserts": json.dumps(["N/A"]),
        "sources": json.dumps(["https://www.kennametal.com/us/en/products/p.ccgt09t304lf-kc730.1161886.html"]),
        "price_range": "$30.43 (list price)",
        "tags": json.dumps(["turning","finishing","CCGT","KC730","steel","stainless","high-temp","positive"]),
        "condition": "New"
    }
]

for entry in inserts:
    cols = ", ".join(entry.keys())
    placeholders = ", ".join(["?" for _ in entry])
    c.execute(f"INSERT OR IGNORE INTO inserts ({cols}) VALUES ({placeholders})", list(entry.values()))
    print(f"Added: {entry['json_id']}")

conn.commit()
print(f"Total inserts: {c.execute('SELECT COUNT(*) FROM inserts').fetchone()[0]}")
conn.close()
