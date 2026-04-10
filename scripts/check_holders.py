import os
import sqlite3, json
conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite'))
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("""
    SELECT json_id, component_type, manufacturer, compatible_inserts, specs
    FROM tools
    WHERE component_type IN ('holder','module')
    AND insert_seat IS NULL
    ORDER BY component_type, json_id
""")
for r in c.fetchall():
    ci = r['compatible_inserts']
    sp = r['specs']
    print(f"\n{r['component_type'].upper()} {r['json_id']}")
    if ci:
        print(f"  compatible_inserts: {ci}")
    if sp:
        try:
            d = json.loads(sp)
            for k,v in d.items():
                print(f"  specs.{k}: {v}")
        except:
            print(f"  specs: {sp}")
conn.close()

