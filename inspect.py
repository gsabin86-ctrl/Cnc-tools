import sqlite3, json

conn = sqlite3.connect('db.sqlite')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print('Tables:', tables)
for t in tables:
    c.execute(f'SELECT COUNT(*) FROM {t}')
    count = c.fetchone()[0]
    c.execute(f'PRAGMA table_info({t})')
    cols = [col[1] for col in c.fetchall()]
    print(f'\n[{t}] - {count} rows')
    print(f'  Columns: {cols}')
    c.execute(f'SELECT * FROM {t} LIMIT 3')
    rows = c.fetchall()
    for row in rows:
        print(f'  Sample: {row}')
conn.close()
