"""Run after any DB change to keep data.json in sync with the viewer."""
import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()
data = {}
for table in ['holders', 'inserts']:
    c.execute(f'SELECT * FROM {table}')
    rows = []
    for row in c.fetchall():
        r = dict(row)
        for k in ['specs','compatible_machines','compatible_holders','compatible_inserts','sources','tags','applications']:
            if k in r and r[k]:
                try: r[k] = json.loads(r[k])
                except: pass
        rows.append(r)
    data[table] = rows
conn.close()
with open(OUT, 'w') as f:
    json.dump(data, f, indent=2)
total = sum(len(v) for v in data.values())
print(f"Exported {total} records to data.json ({len(data['holders'])} holders, {len(data['inserts'])} inserts)")
