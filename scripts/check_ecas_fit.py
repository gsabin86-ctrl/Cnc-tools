import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=== Direct mounts to ECAS20_GANG_BLOCK ===")
cur.execute("SELECT json_id, component_type, size FROM tools WHERE mounts_to='ECAS20_GANG_BLOCK'")
for row in cur.fetchall():
    print(f"  [{row[1]}] {row[0]} | size={row[2]}")

print()
print("=== Holders through bushing adapters ===")
cur.execute("SELECT json_id, component_type, size, mounts_to FROM tools WHERE mounts_to LIKE 'BUSHING%'")
for row in cur.fetchall():
    print(f"  [{row[1]}] {row[0]} | size={row[2]} | via {row[3]}")

conn.close()
