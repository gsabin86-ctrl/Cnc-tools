import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

insert = {
    "json_id": "DGL 2202C-6D IC908",
    "category": "Groove/Turn & Parting Off",
    "type": "Parting Off Indexable Insert",
    "manufacturer": "Iscar",
    "description": "Left-hand parting and grooving insert with C-type chipformer. Suited for external grooving and parting where left-hand lead angle is required. Double-sided design.",
    "specs": json.dumps({
        "cutting_width": "2.2 mm",
        "corner_radius": "0.20 mm",
        "overall_length": "20.80 mm",
        "cutting_depth_max": "18 mm",
        "lead_angle": "6°",
        "lead_angle_direction": "Left Hand",
        "chipformer": "C",
        "cutting_direction": "Left Hand",
        "coating": "TiAlN",
        "grade": "IC908",
        "max_grooving_feed": "0.12 mm/rev",
        "min_grooving_feed": "0.04 mm/rev",
        "measurement_type": "Metric"
    }),
    "size": "2202C",
    "geometry": "C-type chipformer with left-hand 6° lead angle. Double-sided DGLM design. Mirror image of DGR 2202C-6D.",
    "compatible_machines": json.dumps(["CNC lathes for external grooving and parting"]),
    "compatible_holders": json.dumps(["DGTR 16B-2D25SH"]),
    "compatible_inserts": json.dumps(["N/A (this is the insert)"]),
    "sources": json.dumps(["Iscar Miniature Parts Catalog Part 1, page 506"]),
    "price_range": "$10 - $15 per insert (estimated, pack of 10)",
    "tags": json.dumps(["parting", "grooving", "external", "left-hand", "metric", "carbide"]),
    "condition": "New"
}

c.execute("""
    INSERT INTO inserts (json_id, category, type, manufacturer, description, specs, size, geometry,
        compatible_machines, compatible_holders, compatible_inserts, sources, price_range, tags, condition)
    VALUES (:json_id, :category, :type, :manufacturer, :description, :specs, :size, :geometry,
        :compatible_machines, :compatible_holders, :compatible_inserts, :sources, :price_range, :tags, :condition)
""", insert)

conn.commit()
print(f"Added: {insert['json_id']} (id={c.lastrowid})")

# Verify
c.execute("SELECT COUNT(*) FROM inserts")
print(f"Total inserts: {c.fetchone()[0]}")
conn.close()
