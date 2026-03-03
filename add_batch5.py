import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()

inserts = [
    {
        'json_id': 'DGN 2002J IC908',
        'category': 'Groove/Turn & Parting Off',
        'type': 'Parting Off Indexable Insert',
        'manufacturer': 'Iscar',
        'description': 'Double-sided J-chipformer parting and grooving insert for soft materials, tubes, small diameters, and thin-walled parts at low-to-medium feeds. 2.0mm cutting width, IC908 grade.',
        'specs': json.dumps({
            'cutting_width': '2.00 mm',
            'cutting_width_tolerance': '+/- 0.020 mm',
            'corner_radius': '0.20 mm',
            'corner_radius_tolerance': '+/- 0.020 mm',
            'cutting_depth_max': '18.00 mm',
            'insert_length': '19.88 mm',
            'chipformer': 'J',
            'grade': 'IC908',
            'coating': 'TiAlN (PVD)',
            'cutting_direction': 'Neutral',
            'min_grooving_feed': '0.04 mm/rev',
            'max_grooving_feed': '0.12 mm/rev',
            'measurement_type': 'Metric'
        }),
        'size': '2002J',
        'geometry': 'J-type chipformer with positive configuration for soft materials and parting of tubes and thin-walled parts. Double-ended design.',
        'compatible_machines': json.dumps(['CNC lathes', 'Swiss automatic machines']),
        'compatible_holders': json.dumps(['DGTR/L-B-D-SH series (e.g., DGTR 16B-2D25SH)']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'Iscar Miniature Parts Catalog Part 1, page 508',
            'https://www.iscar.com/Catalogs/Publication/Catalogs_Mm/english_1/Miniature_Parts/Miniature%20Parts_Catalog_flipview_part1/index.html'
        ]),
        'price_range': '$10 - $15 per insert (estimated)',
        'tags': json.dumps(['parting', 'grooving', 'external', 'neutral', 'metric', 'carbide', 'IC908', 'J-chipformer', 'soft-materials', 'thin-wall']),
        'condition': 'New'
    },
    {
        'json_id': 'DGN 1502J IC908',
        'category': 'Groove/Turn & Parting Off',
        'type': 'Parting Off Indexable Insert',
        'manufacturer': 'Iscar',
        'description': 'Double-sided J-chipformer parting and grooving insert for soft materials, tubes, small diameters, and thin-walled parts. 1.5mm cutting width for narrow parting operations. IC908 grade.',
        'specs': json.dumps({
            'cutting_width': '1.50 mm',
            'cutting_width_tolerance': '+/- 0.030 mm',
            'corner_radius': '0.16 mm',
            'corner_radius_tolerance': '+/- 0.020 mm',
            'cutting_depth_max': '18.00 mm',
            'insert_length': '20.90 mm',
            'chipformer': 'J',
            'grade': 'IC908',
            'coating': 'TiAlN (PVD)',
            'cutting_direction': 'Neutral',
            'min_grooving_feed': '0.03 mm/rev',
            'max_grooving_feed': '0.12 mm/rev',
            'measurement_type': 'Metric'
        }),
        'size': '1502J',
        'geometry': 'J-type chipformer with positive configuration for narrow parting and grooving. Double-ended design.',
        'compatible_machines': json.dumps(['CNC lathes', 'Swiss automatic machines']),
        'compatible_holders': json.dumps(['DGTR/L-B-D-SH series (e.g., DGTR 16B-2D25SH)']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'Iscar Miniature Parts Catalog Part 1, page 508',
            'https://www.iscar.com/Catalogs/Publication/Catalogs_Mm/english_1/Miniature_Parts/Miniature%20Parts_Catalog_flipview_part1/index.html'
        ]),
        'price_range': '$10 - $15 per insert (estimated)',
        'tags': json.dumps(['parting', 'grooving', 'external', 'neutral', 'metric', 'carbide', 'IC908', 'J-chipformer', 'narrow', 'thin-wall']),
        'condition': 'New'
    },
    {
        'json_id': 'DGR 2202C-6D IC908',
        'category': 'Groove/Turn & Parting Off',
        'type': 'Parting Off Indexable Insert',
        'manufacturer': 'Iscar',
        'description': 'Double-sided right-hand C-chipformer parting insert for hard materials and tough applications. 2.2mm cutting width, 6 degree rake angle, IC908 grade.',
        'specs': json.dumps({
            'cutting_width': '2.20 mm',
            'corner_radius': '0.20 mm',
            'cutting_depth_max': '18.00 mm',
            'insert_length': '20.80 mm',
            'chipformer': 'C',
            'rake_angle': '6 degrees (right side)',
            'grade': 'IC908',
            'coating': 'TiAlN (PVD)',
            'cutting_direction': 'Right Hand',
            'min_grooving_feed': '0.04 mm/rev',
            'max_grooving_feed': '0.12 mm/rev',
            'measurement_type': 'Metric'
        }),
        'size': '2202C',
        'geometry': 'C-type chipformer for hard materials and tough applications. Right-hand (R) designation with 6 degree positive side rake. Double-ended design.',
        'compatible_machines': json.dumps(['CNC lathes', 'Swiss automatic machines']),
        'compatible_holders': json.dumps(['DGTR/L-B-D-SH series (e.g., DGTR 16B-2D25SH)']),
        'compatible_inserts': json.dumps(['N/A']),
        'sources': json.dumps([
            'Iscar Miniature Parts Catalog Part 1, page 506',
            'https://www.iscar.com/Catalogs/Publication/Catalogs_Mm/english_1/Miniature_Parts/Miniature%20Parts_Catalog_flipview_part1/index.html'
        ]),
        'price_range': '$10 - $15 per insert (estimated)',
        'tags': json.dumps(['parting', 'grooving', 'external', 'right-hand', 'metric', 'carbide', 'IC908', 'C-chipformer', 'hard-materials']),
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
