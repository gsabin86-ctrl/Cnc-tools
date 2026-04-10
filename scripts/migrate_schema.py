import os
"""
CNC Tool Batabase â€” Schema Migration
Unified tools table with component_type, mounts_to, insert_seat, iso_designation.

Usage:
  python scripts/migrate_schema.py           # dry run â€” shows plan, touches nothing
  python scripts/migrate_schema.py --apply   # executes migration after backup

Chain:
  Star ECAS20 Gang Block (machine)
      â””â”€â”€ Shank (KM16NCM10400, KM16RCM1616100HPC)    mounts_to: ECAS20_GANG_BLOCK
              â””â”€â”€ Module (KM16SVJBR, SCLCR, etc.)    mounts_to: shank json_id
      â””â”€â”€ Holder (BGTR 16B, Horn B105, Iscar Swiss)  mounts_to: ECAS20_GANG_BLOCK
              â””â”€â”€ Insert (compatibility via iso_designation â†’ insert_seat)
"""

import sqlite3, json, shutil, sys
from datetime import datetime

BB_PATH = 'db.sqlite'
BACKUP_PATH = f'db_backup_premigration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite'
BRY_RUN = '--apply' not in sys.argv

# â”€â”€ Component type assignments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Each entry: json_id â†’ (component_type, mounts_to)
# Inserts table entries that are actually NOT inserts:
RECLASSIFY = {
    # KM modules (in inserts table, IBs 66-76)
    'KM16NSR220':       ('module',  'KM16NCM10400'),
    'KM16NSR330':       ('module',  'KM16NCM10400'),
    'KM16SCLCR0920':    ('module',  'KM16NCM10400'),
    'KM16SBACR1120':    ('module',  'KM16NCM10400'),
    'KM16SCGCR0920':    ('module',  'KM16NCM10400'),
    'KM16SBJCR1120':    ('module',  'KM16NCM10400'),
    'KM16STGCR1620':    ('module',  'KM16NCM10400'),
    'KM16SVGBR1630':    ('module',  'KM16NCM10400'),
    'KM16STJCR1120':    ('module',  'KM16NCM10400'),
    'KM16STJCR1620':    ('module',  'KM16NCM10400'),
    # Parked spare parts (IBs 77-79) â€” keep as parked, type=spare
    'KM16TS':           ('spare',   'KM16NCM10400'),
    'KM16NA':           ('spare',   'KM16NCM10400'),
    'KM16NAPKG':        ('spare',   'KM16NCM10400'),
    # Iscar Swiss holders (IBs 84-95) â€” holders, not inserts
    'SCACR-0808K-06S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SCACR-1010K-06S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SCACR-1010K-09S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SCACR-1212K-09S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SBJCR-0808K-07S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SBJCR-1010M-07S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SBJCR-1212K-07S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SBJCR-1010K-11S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SBJCR-1212M-11S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SVJCR-0808K-11S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SVJCR-1010K-11S':  ('holder',  'ECAS20_GANG_BLOCK'),
    'SVJCR-1212K-11S':  ('holder',  'ECAS20_GANG_BLOCK'),
}

# Holders table assignments
HOLBERS_MAP = {
    'BGTR 16B-2B25SH':    ('holder', 'ECAS20_GANG_BLOCK'),
    'KM16SVJBR1120':      ('module', 'KM16NCM10400'),
    'KM16LSSHPC2010':     ('module', 'KM16NCM10400'),
    'KM16SVJBR1630':      ('module', 'KM16NCM10400'),
    'KM16NCM10400':       ('shank',  'ECAS20_GANG_BLOCK'),
    'KM16SCLCR0920':      ('module', 'KM16NCM10400'),
    'B105.0022.02':       ('holder', 'ECAS20_GANG_BLOCK'),
    'KM16RCM1616100HPC':  ('shank',  'ECAS20_GANG_BLOCK'),
}

# Machine root entry
MACHINE_ENTRY = {
    'json_id':         'ECAS20_GANG_BLOCK',
    'component_type':  'machine',
    'mounts_to':       None,
    'manufacturer':    'Star Micronics',
    'category':        'Machine Tool Block',
    'type':            'Gang Block',
    'description':     'Star ECAS20 gang block for square shank tools. Accepts 16mm shanks.',
    'specs':           json.dumps({'shank_size': '16mm', 'shank_type': 'square'}),
    'sources':         json.dumps(['Star ECAS20 machine documentation']),
}

def get_col(row, key, default=None):
    try:
        val = row[key]
        return val if val not in (None, '', 'null', 'N/A') else default
    except:
        return default

def migrate(conn, dry_run=True):
    c = conn.cursor()
    tools = []  # list of dicts to insert into tools table
    seen_ids = set()

    # 1. Machine root
    tools.append(MACHINE_ENTRY)
    seen_ids.add('ECAS20_GANG_BLOCK')

    # 2. Process holders table
    c.execute("SELECT * FROM holders")
    for row in c.fetchall():
        jid = row['json_id']
        ctype, mounts = HOLBERS_MAP.get(jid, ('holder', 'ECAS20_GANG_BLOCK'))
        if jid in seen_ids:
            print(f"  [SKIP-BUP] {jid} already seen â€” holders table")
            continue
        seen_ids.add(jid)
        tools.append({
            'json_id':          jid,
            'component_type':   ctype,
            'mounts_to':        mounts,
            'category':         get_col(row, 'category'),
            'type':             get_col(row, 'type'),
            'manufacturer':     get_col(row, 'manufacturer'),
            'description':      get_col(row, 'description'),
            'specs':            get_col(row, 'specs'),
            'size':             get_col(row, 'size'),
            'geometry':         get_col(row, 'geometry'),
            'compatible_machines': get_col(row, 'compatible_machines'),
            'compatible_inserts':  get_col(row, 'compatible_inserts'),
            'sources':          get_col(row, 'sources'),
            'price_range':      get_col(row, 'price_range'),
            'tags':             get_col(row, 'tags'),
            'condition':        get_col(row, 'condition'),
            'insert_seat':      None,  # to be filled via proposals workflow
            'iso_designation':  None,
            'grade':            None,
            'shape':            None,
            'chipbreaker':      None,
        })

    # 3. Process inserts table
    c.execute("SELECT * FROM inserts")
    for row in c.fetchall():
        jid = row['json_id']
        if jid in seen_ids:
            print(f"  [SKIP-BUP] {jid} already in holders â€” skipping inserts copy")
            continue
        seen_ids.add(jid)
        if jid in RECLASSIFY:
            ctype, mounts = RECLASSIFY[jid]
        else:
            ctype, mounts = 'insert', None
        tools.append({
            'json_id':          jid,
            'component_type':   ctype,
            'mounts_to':        mounts,
            'category':         get_col(row, 'category'),
            'type':             get_col(row, 'type'),
            'manufacturer':     get_col(row, 'manufacturer'),
            'description':      get_col(row, 'description'),
            'specs':            get_col(row, 'specs'),
            'size':             get_col(row, 'size'),
            'geometry':         get_col(row, 'geometry'),
            'compatible_machines': get_col(row, 'compatible_machines'),
            'compatible_inserts':  get_col(row, 'compatible_inserts'),
            'sources':          get_col(row, 'sources'),
            'price_range':      get_col(row, 'price_range'),
            'tags':             get_col(row, 'tags'),
            'condition':        get_col(row, 'condition'),
            'insert_seat':      None,
            'iso_designation':  None,
            'grade':            get_col(row, 'grade'),
            'shape':            get_col(row, 'shape'),
            'chipbreaker':      get_col(row, 'chipbreaker'),
        })

    # â”€â”€ Report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from collections import Counter
    type_counts = Counter(t['component_type'] for t in tools)
    mounts_counts = Counter(t['mounts_to'] for t in tools if t['mounts_to'])

    print(f"\n{'BRY RUN â€” ' if dry_run else ''}Migration Plan")
    print(f"  Total tools to write: {len(tools)}")
    print(f"\n  By component_type:")
    for k, v in sorted(type_counts.items()):
        print(f"    {k:<15} {v}")
    print(f"\n  By mounts_to:")
    for k, v in sorted(mounts_counts.items()):
        print(f"    {k:<30} {v} components")

    print(f"\n  Sample chain (KM16 modular):")
    chain = ['ECAS20_GANG_BLOCK', 'KM16NCM10400', 'KM16SVJBR1120']
    for jid in chain:
        t = next((x for x in tools if x['json_id'] == jid), None)
        if t:
            print(f"    [{t['component_type']:<10}] {t['json_id']}")

    print(f"\n  Sample chain (simple holder):")
    chain2 = ['ECAS20_GANG_BLOCK', 'BGTR 16B-2B25SH']
    for jid in chain2:
        t = next((x for x in tools if x['json_id'] == jid), None)
        if t:
            print(f"    [{t['component_type']:<10}] {t['json_id']}")

    if dry_run:
        print(f"\n  Bry run complete. Run with --apply to execute.")
        return

    # â”€â”€ Execute â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\nExecuting migration...")

    # Rename old tables
    c.execute("ALTER TABLE inserts RENAME TO inserts_v1")
    c.execute("ALTER TABLE holders RENAME TO holders_v1")

    # Create new unified tools table
    c.execute("""
        CREATE TABLE tools (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            json_id             TEXT UNIQUE NOT NULL,
            component_type      TEXT NOT NULL,  -- machine|shank|module|holder|insert|spare
            mounts_to           TEXT,           -- json_id of parent component
            category            TEXT,
            type                TEXT,
            manufacturer        TEXT,
            description         TEXT,
            specs               TEXT,
            size                TEXT,
            geometry            TEXT,
            insert_seat         TEXT,           -- ISO seat accepted (holders/modules)
            iso_designation     TEXT,           -- ISO shape code (inserts)
            compatible_machines TEXT,
            compatible_inserts  TEXT,
            sources             TEXT,
            price_range         TEXT,
            tags                TEXT,
            condition           TEXT,
            grade               TEXT,
            shape               TEXT,
            chipbreaker         TEXT
        )
    """)

    cols = ['json_id','component_type','mounts_to','category','type','manufacturer',
            'description','specs','size','geometry','insert_seat','iso_designation',
            'compatible_machines','compatible_inserts','sources','price_range',
            'tags','condition','grade','shape','chipbreaker']

    for t in tools:
        vals = [t.get(col) for col in cols]
        placeholders = ','.join(['?' for _ in cols])
        c.execute(f"INSERT INTO tools ({','.join(cols)}) VALUES ({placeholders})", vals)

    conn.commit()
    print(f"  Bone. {len(tools)} entries written to tools table.")
    print(f"  Old tables preserved as inserts_v1, holders_v1.")

if __name__ == '__main__':
    if BRY_RUN:
        print(f"BRY RUN (pass --apply to execute)\n")
        conn = sqlite3.connect(BB_PATH)
        conn.row_factory = sqlite3.Row
        migrate(conn, dry_run=True)
        conn.close()
    else:
        print(f"Backing up {BB_PATH} to {BACKUP_PATH}...")
        shutil.copy2(BB_PATH, BACKUP_PATH)
        print(f"Backup done.")
        conn = sqlite3.connect(BB_PATH)
        conn.row_factory = sqlite3.Row
        migrate(conn, dry_run=False)
        conn.close()
        print(f"\nMigration complete. Verify with: python scripts/audit_db.py")

