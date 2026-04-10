import os
import sqlite3, json

conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite'))
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Total rows
c.execute("SELECT COUNT(*) as total FROM inserts")
total = c.fetchone()['total']
print(f"Total entries: {total}")

# By category
c.execute("SELECT category, COUNT(*) as cnt FROM inserts GROUP BY category ORDER BY cnt DESC")
print("\nBy category:")
for r in c.fetchall():
    print(f"  {r['category']:<30} {r['cnt']}")

# By manufacturer
c.execute("SELECT manufacturer, COUNT(*) as cnt FROM inserts GROUP BY manufacturer ORDER BY cnt DESC")
print("\nBy manufacturer:")
for r in c.fetchall():
    print(f"  {r['manufacturer']:<30} {r['cnt']}")

# Field coverage
fields = ['description', 'specs', 'size', 'geometry', 'compatible_machines',
          'compatible_holders', 'compatible_inserts', 'sources', 'price_range',
          'tags', 'condition', 'grade', 'shape', 'chipbreaker']

print(f"\nField coverage ({total} total rows):")
for field in fields:
    c.execute(f"SELECT COUNT(*) as cnt FROM inserts WHERE {field} IS NOT NULL AND {field} != '' AND {field} != 'null' AND {field} != '[]' AND {field} != 'N/A'")
    cnt = c.fetchone()['cnt']
    pct = (cnt / total * 100) if total > 0 else 0
    bar = '#' * int(pct / 5)
    print(f"  {field:<25} {cnt:>4}/{total}  ({pct:5.1f}%)  {bar}")

# Sample a few rows to see what a training pair could look like
print("\n--- Sample row (raw) ---")
c.execute("SELECT * FROM inserts WHERE specs IS NOT NULL AND geometry IS NOT NULL LIMIT 1")
row = c.fetchone()
if row:
    for k in row.keys():
        val = row[k]
        if val and val not in ('', 'null', '[]', 'N/A'):
            print(f"  {k}: {str(val)[:120]}")

conn.close()

