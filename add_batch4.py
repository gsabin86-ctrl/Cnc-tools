import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

# Fix data error: VBGT110301LF should not list KM16SVJBR1630 (1103 size != 1604 size)
c.execute("SELECT id, compatible_holders FROM inserts WHERE json_id = 'VBGT110301LF KC730'")
row = c.fetchone()
if row:
    holders = json.loads(row[1])
    if 'KM16SVJBR1630' in holders:
        holders.remove('KM16SVJBR1630')
        c.execute("UPDATE inserts SET compatible_holders = ? WHERE id = ?", (json.dumps(holders), row[0]))
        print(f'Fixed: removed KM16SVJBR1630 from VBGT110301LF KC730 compatible_holders')

# Add VBGT110304LF KC730 - the 0.4mm CR positive gap in the 1103 series
insert = {
    'json_id': 'VBGT110304LF KC730',
    'category': 'Turning Inserts',
    'type': 'VBGT Screw-On Turning Insert',
    'manufacturer': 'Kennametal',
    'description': 'Light finishing geometry for steel, stainless, and high-temp alloys. 35 degree rhomboid positive, tight tolerance G, 0.4mm corner radius. KC730 Beyond Drive grade.',
    'specs': json.dumps({
        'iso_id': 'VBGT110304LF',
        'ansi_id': 'VBGT221LF',
        'material_number': '1161964',
        'ic_size': '6.35 mm',
        'cutting_edge_length': '11.071 mm',
        'thickness': '3.18 mm',
        'corner_radius': '0.4 mm',
        'hole_size': '2.8 mm',
        'insert_angle': '35 degrees',
        'clearance_angle': '5 degrees',
        'tolerance': 'G',
        'chipbreaker': 'LF',
        'chipbreaker_sides': '1 - one-side',
        'grade': 'KC730',
        'material': 'Carbide'
    }),
    'size': '1103',
    'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake with 0.4mm corner radius. Tight G tolerance for precision finishing.',
    'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
    'compatible_holders': json.dumps(['KM16SVJBR1120']),
    'compatible_inserts': json.dumps(['N/A']),
    'sources': json.dumps([
        'https://www.kennametal.com/us/en/products/p.positive-inserts-vbgt-lf.1161964.html',
        'https://www.kennametal.com/us/en/products/fam.positive-inserts-vbgt-lf.100002953.html'
    ]),
    'price_range': '$38.97 (list price)',
    'tags': json.dumps(['turning', 'finishing', 'VBGT', 'KC730', 'steel', 'stainless', 'high-temp', 'positive', 'KM-micro']),
    'condition': 'New'
}

c.execute('''INSERT INTO inserts (json_id, category, type, manufacturer, description, specs, size, geometry,
    compatible_machines, compatible_holders, compatible_inserts, sources, price_range, tags, condition)
    VALUES (:json_id, :category, :type, :manufacturer, :description, :specs, :size, :geometry,
    :compatible_machines, :compatible_holders, :compatible_inserts, :sources, :price_range, :tags, :condition)''', insert)
print(f'Added: {insert["json_id"]}')

conn.commit()
conn.close()
print('Done.')
