import sqlite3

db_path = 'db.sqlite'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create holders table if not exists
cursor.execute('''
CREATE TABLE IF NOT EXISTS holders (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    shank_size TEXT,
    clamp_type TEXT,
    orientation TEXT,
    internal_external TEXT
)
''')

# Create inserts table if not exists
cursor.execute('''
CREATE TABLE IF NOT EXISTS inserts (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    material TEXT,
    geometry TEXT,
    compatible_holders TEXT,
    internal_external TEXT
)
''')

conn.commit()
conn.close()

print("Migration complete. Tables ensured.")
