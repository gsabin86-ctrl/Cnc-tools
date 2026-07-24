import sqlite3, os
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT json_id, component_type FROM tools WHERE component_type='machine'")
print("Machine-type tools:")
for row in cur.fetchall():
    print(" ", row)
conn.close()
