import os
import sqlite3, json

conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite'))
conn.row_factory = sqlite3.Row
c = conn.cursor()

# All holders
c.execute("SELECT id, json_id, category, type, manufacturer, description, compatible_holders, compatible_inserts FROM holders")
rows = c.fetchall()
print(f"Holders table: {len(rows)} entries\n")
for r in rows:
    print(f"  [{r['id']}] {r['json_id']}")
    print(f"       Category: {r['category']}")
    print(f"       Type:     {r['type']}")
    print(f"       Mfr:      {r['manufacturer']}")
    print(f"       compatible_holders: {r['compatible_holders']}")
    print(f"       compatible_inserts: {str(r['compatible_inserts'])[:120]}")
    print()

# Also check inserts table for anything that looks like a shank or module
print("\n--- Inserts table entries that might be shanks/modules ---")
c.execute("SELECT id, json_id, category, type, manufacturer, description FROM inserts WHERE category LIKE '%KM%' OR type LIKE '%KM%' OR json_id LIKE '%KM16%' OR category LIKE '%Holder%' OR category LIKE '%holder%'")
rows2 = c.fetchall()
for r in rows2:
    print(f"  [{r['id']}] {r['json_id']}  |  {r['category']}  |  {r['type']}")

conn.close()

