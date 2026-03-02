import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

inserts = [
    {
        'json_id': 'VBGT110301LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBGT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. Positive rake, tight tolerance G, 0.1mm corner radius for ultra-fine finishing. KC730 Beyond Drive grade.',
        'specs': json.dumps({
            'iso_id': 'VBGT110301LF',
            'ansi_id': 'VBGT220LF',
            'material_number': '1161876',
            'ic_size': '6.35 mm',
            'cutting_edge_length': '11.0 mm',
            'thickness': '3.18 mm',
            'corner_radius': '0.1 mm',
            'hole_size': '2.9 mm',
            'insert_angle': '35 degrees',
            'clearance_angle': '5 degrees',
            'tolerance': 'G',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '1103',
        'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake insert with 0.1mm corner radius for sharp, low-force cutting action.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1120', 'KM16SVJBR1630']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/fam.positive-inserts-vbgt-lf.100002953.html',
            'https://www.toolsunited.com/App/EN/Article/ArticleDetailsPage/97248493081207822'
        ]),
        'price_range': '$31.55 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBGT', 'KC730', 'steel', 'stainless', 'cast-iron', 'high-temp', 'positive', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'VBMT110304LF K313',
        'category': 'Turning Inserts',
        'type': 'VBMT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. Positive rake, tolerance M, 0.4mm corner radius. K313 hard fine-grain WC/Co grade for non-ferrous and high-temp applications.',
        'specs': json.dumps({
            'iso_id': 'VBMT110304LF',
            'ansi_id': 'VBMT221LF',
            'material_number': '1162230',
            'ic_size': '6.35 mm',
            'cutting_edge_length': '11.071 mm',
            'thickness': '3.18 mm',
            'corner_radius': '0.4 mm',
            'hole_size': '2.8 mm',
            'insert_angle': '35 degrees',
            'clearance_angle': '5 degrees',
            'tolerance': 'M',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'K313',
            'material': 'Carbide'
        }),
        'size': '1103',
        'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake insert with 0.4mm corner radius. Tolerance M for general turning applications.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1120']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.vbmt-lf.7093813.html',
            'https://toolsunited.com/EN/Article/Details/24696400130906387'
        ]),
        'price_range': '$26.56 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBMT', 'K313', 'steel', 'stainless', 'cast-iron', 'non-ferrous', 'high-temp', 'positive', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'VBGT160401LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBGT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. Positive rake, tight tolerance G, 0.1mm corner radius. KC730 Beyond Drive grade. 1604 size for KM16SVJBR1630 cutting unit.',
        'specs': json.dumps({
            'iso_id': 'VBGT160401LF',
            'ansi_id': 'VBGT3302LF',
            'material_number': '7093182',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '16.606 mm',
            'thickness': '4.76 mm',
            'corner_radius': '0.1 mm',
            'hole_size': '4.4 mm',
            'insert_angle': '35 degrees',
            'clearance_angle': '5 degrees',
            'tolerance': 'G',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '1604',
        'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake insert with 0.1mm corner radius. 1604 size variant for larger SVJB cutting units.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1630']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.positive-inserts-vbgt-lf.7093182.html',
            'https://www.kennametal.com/us/en/products/fam.positive-inserts-vbgt-lf.100002953.html'
        ]),
        'price_range': '$31.53 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBGT', 'KC730', 'steel', 'stainless', 'cast-iron', 'high-temp', 'positive', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'VBMT160404LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBMT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. Positive rake, tolerance M, 0.4mm corner radius. KC730 Beyond Drive grade. 1604 size for KM16SVJBR1630 cutting unit.',
        'specs': json.dumps({
            'iso_id': 'VBMT160404LF',
            'ansi_id': 'VBMT331LF',
            'material_number': '7093814',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '16.606 mm',
            'thickness': '4.76 mm',
            'corner_radius': '0.4 mm',
            'hole_size': '4.4 mm',
            'insert_angle': '35 degrees',
            'clearance_angle': '5 degrees',
            'tolerance': 'M',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '1604',
        'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake insert with 0.4mm corner radius. Tolerance M. 1604 size variant for larger SVJB cutting units.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1630']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.vbmt-lf.7093814.html',
            'https://www.kennametal.com/us/en/products/fam.vbmt-lf.100002955.html'
        ]),
        'price_range': '$27.51 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBMT', 'KC730', 'steel', 'stainless', 'cast-iron', 'non-ferrous', 'high-temp', 'positive', 'KM-micro']),
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
