# migrate_db.ps1 - Ensure holders and inserts tables in db.sqlite

$dbPath = "db.sqlite"

# Create holders table if not exists
sqlite3 $dbPath @"
CREATE TABLE IF NOT EXISTS holders (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    shank_size TEXT,
    clamp_type TEXT,
    orientation TEXT,
    internal_external TEXT
);
"@

# Create inserts table if not exists
sqlite3 $dbPath @"
CREATE TABLE IF NOT EXISTS inserts (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    material TEXT,
    geometry TEXT,
    compatible_holders TEXT,
    internal_external TEXT
);
"@

Write-Output "Migration complete. Tables ensured."
