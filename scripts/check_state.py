import os
import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite'))
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== DB State ===")
c.execute("SELECT COUNT(*) as n FROM tools")
print(f"Total: {c.fetchone()['n']}")

print("\nBy type + manufacturer:")
c.execute("SELECT component_type, manufacturer, COUNT(*) as n FROM tools GROUP BY component_type, manufacturer ORDER BY component_type, manufacturer")
for r in c.fetchall():
    mfr = r['manufacturer'] if r['manufacturer'] else '(none)'
    print(f"  {r['component_type']:<12} {mfr:<20} {r['n']}")

print("\nPending work hints:")
c.execute("SELECT json_id, component_type, insert_seat FROM tools WHERE component_type IN ('holder','module') AND insert_seat IS NULL")
rows = c.fetchall()
print(f"  Holders/modules with no insert_seat: {len(rows)}")
for r in rows:
    print(f"    {r['component_type']:<10} {r['json_id']}")

conn.close()

