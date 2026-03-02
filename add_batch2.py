import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

inserts = [
    {
        'json_id': 'CCMT09T308LF KC730',
        'category': 'Turning Inserts',
        'type': 'CCMT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. 80 degree rhomboid, tolerance M, 0.8mm corner radius. KC730 Beyond Drive grade.',
        'specs': json.dumps({
            'iso_id': 'CCMT09T308LF',
            'ansi_id': 'CCMT3252LF',
            'material_number': '7093840',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '9.672 mm',
            'thickness': '3.969 mm',
            'corner_radius': '0.8 mm',
            'hole_size': '4.4 mm',
            'insert_angle': '80 degrees',
            'tolerance': 'M',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '09T3',
        'geometry': 'LF - Light finishing. 80 degree rhomboid with 0.8mm corner radius for general finishing operations.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SCLCR0920']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.ccmt-lf.7093840.html',
            'https://www.kennametal.com/us/en/products/fam.ccmt-lf.100001904.html'
        ]),
        'price_range': '$22.81 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'CCMT', 'KC730', 'steel', 'stainless', 'cast-iron', 'non-ferrous', 'high-temp', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'CCGT09T308LF KC730',
        'category': 'Turning Inserts',
        'type': 'CCGT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, and high-temp alloys. 80 degree rhomboid positive, tight tolerance G, 0.8mm corner radius. KC730 Beyond Drive grade.',
        'specs': json.dumps({
            'iso_id': 'CCGT09T308LF',
            'ansi_id': 'CCGT3252LF',
            'material_number': '1161887',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '9.672 mm',
            'thickness': '3.97 mm',
            'corner_radius': '0.8 mm',
            'hole_size': '4.4 mm',
            'insert_angle': '80 degrees',
            'tolerance': 'G',
            'chipbreaker': 'LF',
            'chipbreaker_sides': '1 - one-side',
            'grade': 'KC730',
            'material': 'Carbide'
        }),
        'size': '09T3',
        'geometry': 'LF - Light finishing. 80 degree rhomboid positive rake with 0.8mm corner radius. Tight G tolerance for precision finishing.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SCLCR0920']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.positive-inserts-ccgt-lf.1161887.html',
            'https://www.kennametal.com/us/en/products/fam.positive-inserts-ccgt-lf.100001908.html'
        ]),
        'price_range': '$25.57 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'CCGT', 'KC730', 'steel', 'stainless', 'high-temp', 'positive', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'VBGT160408LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBGT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel, stainless, cast iron, non-ferrous, and high-temp alloys. 35 degree rhomboid positive, tight tolerance G, 0.8mm corner radius. KC730 Beyond Drive grade. 1604 size for KM16SVJBR1630 cutting unit.',
        'specs': json.dumps({
            'iso_id': 'VBGT160408LF',
            'ansi_id': 'VBGT332LF',
            'material_number': '7093223',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '16.606 mm',
            'thickness': '4.76 mm',
            'corner_radius': '0.8 mm',
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
        'geometry': 'LF - Light finishing. 35 degree rhomboid positive rake with 0.8mm corner radius. 1604 size variant for larger SVJB cutting units.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1630']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.positive-inserts-vbgt-lf.7093223.html',
            'https://www.kennametal.com/us/en/products/fam.positive-inserts-vbgt-lf.100002953.html'
        ]),
        'price_range': '$31.53 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBGT', 'KC730', 'steel', 'stainless', 'cast-iron', 'high-temp', 'positive', 'KM-micro']),
        'condition': 'New'
    },
    {
        'json_id': 'VBMT160408LF KC730',
        'category': 'Turning Inserts',
        'type': 'VBMT Screw-On Turning Insert',
        'manufacturer': 'Kennametal',
        'description': 'Light finishing geometry for steel and stainless steel. 35 degree rhomboid, tolerance M, 0.8mm corner radius. KC730 Beyond Drive grade. 1604 size for KM16SVJBR1630 cutting unit.',
        'specs': json.dumps({
            'iso_id': 'VBMT160408LF',
            'ansi_id': 'VBMT332LF',
            'material_number': '1161975',
            'ic_size': '9.525 mm',
            'cutting_edge_length': '16.606 mm',
            'thickness': '4.763 mm',
            'corner_radius': '0.8 mm',
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
        'geometry': 'LF - Light finishing. 35 degree rhomboid with 0.8mm corner radius. Tolerance M. 1604 size variant for larger SVJB cutting units.',
        'compatible_machines': json.dumps(['CNC lathes with KM Micro quick-change tooling']),
        'compatible_holders': json.dumps(['KM16SVJBR1630']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'https://www.kennametal.com/us/en/products/p.vbmt-lf.1161975.html',
            'https://www.kennametal.com/us/en/products/fam.vbmt-lf.100002955.html'
        ]),
        'price_range': '$35.68 (list price)',
        'tags': json.dumps(['turning', 'finishing', 'VBMT', 'KC730', 'steel', 'stainless', 'positive', 'KM-micro']),
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
