import os
import sqlite3

db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite'))
cur = db.cursor()

cur.execute("SELECT COUNT(*) FROM tools WHERE manufacturer='PH Horn'")
print('PH Horn total:', cur.fetchone()[0])

cur.execute("SELECT json_id, type FROM tools WHERE manufacturer='PH Horn' AND component_type='holder' ORDER BY json_id")
print('\nHorn holders in DB:')
for r in cur.fetchall():
    print(' ', r[0], '|', r[1])

cur.execute("SELECT DISTINCT json_id FROM tools WHERE manufacturer='PH Horn' AND component_type='insert' ORDER BY json_id LIMIT 20")
print('\nSample Horn inserts (first 20):')
for r in cur.fetchall():
    print(' ', r[0])

db.close()

