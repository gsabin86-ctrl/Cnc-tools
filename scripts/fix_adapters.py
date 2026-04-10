import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. Remove the wrong square-shank bushing adapters from tools table
cur.execute("DELETE FROM tools WHERE component_type='adapter' AND json_id LIKE 'BUSHING_16SQ%'")
print(f"Removed {cur.rowcount} square bushing adapter tool nodes")

# 2. Remove from adapters table too
cur.execute("DELETE FROM adapters WHERE json_id LIKE 'BUSHING_16SQ%'")
print(f"Removed {cur.rowcount} square bushing adapter records")

# 3. Unlink square shank Iscar holders - they don't fit ECAS20 at all
square_holders = [
    'SCACR-0808K-06S','SCACR-1010K-06S','SCACR-1010K-09S','SCACR-1212K-09S',
    'SDJCR-0808K-07S','SDJCR-1010M-07S','SDJCR-1010K-11S','SDJCR-1212K-07S',
    'SDJCR-1212M-11S','SVJCR-0808K-11S','SVJCR-1010K-11S','SVJCR-1212K-11S',
]
for h in square_holders:
    cur.execute("UPDATE tools SET mounts_to=NULL WHERE json_id=?", (h,))
    print(f"  Unlinked: {h}")

# 4. Add correct bushing adapters: 22mm ROUND pocket -> smaller round shanks
adapters = [
    {
        'json_id': 'BUSHING_22RND_TO_8RND',
        'description': 'Reducing bushing adapter - 22mm round pocket to 8mm round shank. REQUIRED to mount 8mm round shank holders in ECAS20 stations 16-19.',
        'from_type': 'round', 'from_size_mm': 22,
        'to_type': 'round',   'to_size_mm': 8,
        'fits_machines': json.dumps(['STAR_ECAS20']),
        'specs': json.dumps({'pocket_size_mm': 22, 'shank_size_mm': 8, 'shank_type': 'round', 'required': True}),
        'sources': json.dumps([]),
        'tags': json.dumps(['bushing', 'adapter', 'reducing', 'round', '8mm', '22mm', 'required'])
    },
    {
        'json_id': 'BUSHING_22RND_TO_10RND',
        'description': 'Reducing bushing adapter - 22mm round pocket to 10mm round shank. REQUIRED to mount 10mm round shank holders in ECAS20 stations 16-19.',
        'from_type': 'round', 'from_size_mm': 22,
        'to_type': 'round',   'to_size_mm': 10,
        'fits_machines': json.dumps(['STAR_ECAS20']),
        'specs': json.dumps({'pocket_size_mm': 22, 'shank_size_mm': 10, 'shank_type': 'round', 'required': True}),
        'sources': json.dumps([]),
        'tags': json.dumps(['bushing', 'adapter', 'reducing', 'round', '10mm', '22mm', 'required'])
    },
    {
        'json_id': 'BUSHING_22RND_TO_12RND',
        'description': 'Reducing bushing adapter - 22mm round pocket to 12mm round shank. REQUIRED to mount 12mm round shank holders in ECAS20 stations 16-19.',
        'from_type': 'round', 'from_size_mm': 22,
        'to_type': 'round',   'to_size_mm': 12,
        'fits_machines': json.dumps(['STAR_ECAS20']),
        'specs': json.dumps({'pocket_size_mm': 22, 'shank_size_mm': 12, 'shank_type': 'round', 'required': True}),
        'sources': json.dumps([]),
        'tags': json.dumps(['bushing', 'adapter', 'reducing', 'round', '12mm', '22mm', 'required'])
    },
]

for a in adapters:
    cur.execute("""
        INSERT OR REPLACE INTO adapters
        (json_id, description, from_type, from_size_mm, to_type, to_size_mm, fits_machines, specs, sources, tags)
        VALUES (:json_id, :description, :from_type, :from_size_mm, :to_type, :to_size_mm,
                :fits_machines, :specs, :sources, :tags)
    """, a)
    # Also add as tool nodes so they appear in the viewer chain
    cur.execute("""
        INSERT OR REPLACE INTO tools
        (json_id, component_type, mounts_to, category, type, manufacturer, description, specs, size, tags)
        VALUES (?, 'adapter', 'ECAS20_GANG_BLOCK', 'Bushing Adapters', 'Reducing Bushing', 'Generic', ?, ?, ?, ?)
    """, (a['json_id'], a['description'], a['specs'], f"22->{ a['to_size_mm']}mm rnd", a['tags']))
    print(f"Added: {a['json_id']}")

conn.commit()

# 5. Verify
print("\n=== Direct mounts to ECAS20_GANG_BLOCK ===")
cur.execute("SELECT json_id, component_type, size FROM tools WHERE mounts_to='ECAS20_GANG_BLOCK'")
for row in cur.fetchall():
    print(f"  [{row[1]}] {row[0]} | size={row[2]}")

print("\n=== Tools with mounts_to=NULL (unlinked, not machine/root nodes) ===")
cur.execute("SELECT json_id, component_type, size FROM tools WHERE mounts_to IS NULL AND component_type NOT IN ('machine','insert') LIMIT 20")
for row in cur.fetchall():
    print(f"  [{row[1]}] {row[0]} | size={row[2]}")

conn.close()
