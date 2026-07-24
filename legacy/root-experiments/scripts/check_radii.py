import sqlite3, json, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT specs FROM tools WHERE component_type='insert'")
keys = {}
for (specs_raw,) in cur.fetchall():
    if not specs_raw: continue
    try:
        s = json.loads(specs_raw)
        for k in s.keys():
            if any(x in k.lower() for x in ['radius', 're', 'corner']):
                keys[k] = keys.get(k, 0) + 1
    except:
        pass
conn.close()
print("Corner radius keys found:")
for k, v in sorted(keys.items(), key=lambda x: -x[1]):
    print(f"  {v:4d}  {k}")
