import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

inserts = [
    {
        'json_id': 'VBMT110308LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBMT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel and stainless steel. 35 degree rhomboid, tolerance M, 0.8mm corner radius. KC730 Beyond Drive grade. Completes the 1103 corner radius range for SVJBR1120.',
        'specs': json.dumps({
            'iso_id': 'VBMT110308LF',
            'ansi_id': 'VBMT222LF',
            'material_number': '1161972',
            'ic_size': '6.35 mm',
            'cutting_edge_length': '11.071 mm',
            'thickness': '3.18 mm',
            'corner_radius': '0.8 mm',
            'hole_size': '2.9 mm',
            'insert_angle': '35 degrees',
            'clearance_angle': '5 degrees',
            'tolerance': 'M',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '1103',
        'geometry': 'LF - Light finishing. 35 degree rhomboid with 0.8mm corner radius. Tolerance M. Largest corner radius available in 1103 size.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1120']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.vbmt-lf.1161972.html',
            'https://www.kennametal.com/us/en/products/fam.vbmt-lf.100002955.html'
        ]),
        'price_range': '$34.43 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBMT', 'KC730', 'steel', 'stainless', 'KM-micro']),
        'condition': 'New'
    }
]

for ins in inserts:
    c.execute('''INSERT INTO inserts (json_id, category, type, manufacturer, description, specs, size, geometry,
        compatible_machines, compatible_holders, compatible_inserts, sources, price_range, tags, condition)
        VALUES (:json_id, :category, :type, :manufacturer, :description, :specs, :size, :geometry,
        :compatible_machines, :compatible_holders, :compatible_inserts, :sources, :price_range, :tags, :condition)''', ins)
    print(f'Added: {ins["json_id"]}')

conn.commit()
conn.close()
print('Done.')
