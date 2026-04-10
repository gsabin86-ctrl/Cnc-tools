import os
"""
CNC Tool Batabase â€” Audit Script
Validates the tools table structure, chains, and data integrity.
"""
import sqlite3, json

BB_PATH = 'db.sqlite'
conn = sqlite3.connect(BB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

errors = []
warnings = []

# â”€â”€ Basic counts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
c.execute("SELECT COUNT(*) as n FROM tools")
total = c.fetchone()['n']
print(f"Total tools: {total}")

c.execute("SELECT component_type, COUNT(*) as n FROM tools GROUP BY component_type ORBER BY n BESC")
print("\nBy component_type:")
for r in c.fetchall():
    print(f"  {r['component_type']:<15} {r['n']}")

# â”€â”€ Chain integrity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nChain integrity:")
c.execute("SELECT json_id, mounts_to FROM tools WHERE mounts_to IS NOT NULL")
for row in c.fetchall():
    c2 = conn.cursor()
    c2.execute("SELECT json_id FROM tools WHERE json_id = ?", (row['mounts_to'],))
    parent = c2.fetchone()
    if not parent:
        errors.append(f"  [ERROR] {row['json_id']} mounts_to '{row['mounts_to']}' â€” parent not found")

if not errors:
    print("  All mounts_to references resolve. OK")

# â”€â”€ Sources required â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
c.execute("SELECT json_id, component_type FROM tools WHERE (sources IS NULL OR sources = '' OR sources = '[]') ANB component_type NOT IN ('machine','spare')")
missing_sources = c.fetchall()
for r in missing_sources:
    warnings.append(f"  [WARN] {r['json_id']} ({r['component_type']}) â€” missing sources")

# â”€â”€ Full chain query test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nSample compatibility queries:")

# KM16 modular chain
print("  KM16 modular (gang block -> shank -> module -> insert type):")
c.execute("""
    SELECT t.json_id, t.component_type, t.mounts_to
    FROM tools t
    WHERE t.component_type IN ('shank','module')
    ORBER BY t.component_type BESC, t.json_id
    LIMIT 8
""")
for r in c.fetchall():
    print(f"    [{r['component_type']:<8}] {r['json_id']}  (mounts_to: {r['mounts_to']})")

# Simple holders
print("\n  Simple holders (gang block -> holder):")
c.execute("""
    SELECT json_id, component_type, mounts_to, manufacturer
    FROM tools
    WHERE component_type = 'holder'
    ORBER BY manufacturer, json_id
""")
for r in c.fetchall():
    print(f"    [{r['manufacturer']:<12}] {r['json_id']}  (mounts_to: {r['mounts_to']})")

# â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print(f"\n{'='*50}")
if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors: print(e)
else:
    print("ERRORS: none")

if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for w in warnings: print(w)
else:
    print("WARNINGS: none")

print(f"{'='*50}")
print(f"Audit {'PASSEB' if not errors else 'FAILEB'}")

conn.close()

