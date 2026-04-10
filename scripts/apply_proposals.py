import os
"""
CNC Tool Database - Apply Proposals
Reads proposals.json and applies insert or update actions to the tools table.

Usage:
  python scripts/apply_proposals.py           # dry run
  python scripts/apply_proposals.py --apply   # execute
"""

import sqlite3, json, sys
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
PROPOSALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'proposals.json')
DRY_RUN = '--apply' not in sys.argv

proposals = json.loads(Path(PROPOSALS_PATH).read_text(encoding='utf-8'))
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

errors = []
plan = []

for p in proposals:
    action = p.get('action', 'insert')
    jid = p.get('json_id')

    if action == 'update':
        c.execute("SELECT id FROM tools WHERE json_id = ?", (jid,))
        row = c.fetchone()
        if not row:
            errors.append(f"UPDATE FAILED: {jid} not found in tools table")
            continue
        fields = p.get('fields', {})
        if not fields:
            errors.append(f"UPDATE SKIPPED: {jid} has no fields to update")
            continue
        set_clause = ', '.join([f"{k} = ?" for k in fields])
        vals = list(fields.values()) + [jid]
        plan.append(('update', jid, set_clause, vals, p.get('source', '')))

    elif action == 'insert':
        fields = p.get('fields', {})
        # json_id can live at top level OR inside fields
        if not jid and fields:
            jid = fields.get('json_id')
        c.execute("SELECT id FROM tools WHERE json_id = ?", (jid,))
        if c.fetchone():
            # Already applied — silently skip, clean from proposals on commit
            continue
        plan.append(('insert', jid, p))

print(f"{'DRY RUN - ' if DRY_RUN else ''}Proposals: {len(proposals)} | Planned: {len(plan)} | Errors: {len(errors)}")
print()

for item in plan:
    if item[0] == 'update':
        _, jid, set_clause, vals, source = item
        print(f"  UPDATE {jid}")
        fields_dict = {k: v for k, v in zip([s.split(' =')[0] for s in set_clause.split(', ')], vals[:-1])}
        for k, v in fields_dict.items():
            print(f"    {k}: {v[:80]}{'...' if len(str(v)) > 80 else ''}")
        print(f"    source: {source}")
    elif item[0] == 'insert':
        _, jid, p = item
        ct = p.get('fields', p).get('component_type', '?')
        print(f"  INSERT {jid} ({ct})")

if errors:
    print()
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")

if DRY_RUN:
    print()
    print("Dry run complete. Pass --apply to execute.")
    conn.close()
    sys.exit(0 if not errors else 1)

if errors:
    print("Aborting due to errors.")
    conn.close()
    sys.exit(1)

# Execute
for item in plan:
    if item[0] == 'update':
        _, jid, set_clause, vals, source = item
        c.execute(f"UPDATE tools SET {set_clause} WHERE json_id = ?", vals)
        print(f"  Applied UPDATE: {jid}")
    elif item[0] == 'insert':
        _, jid, p = item
        # Support fields dict or flat top-level keys
        data = p.get('fields', p)
        cols = ['json_id','component_type','mounts_to','category','type','manufacturer',
                'description','specs','size','geometry','insert_seat','iso_designation',
                'compatible_machines','compatible_inserts','sources','price_range',
                'tags','condition','grade','shape','chipbreaker']
        vals = [data.get(col) for col in cols]
        placeholders = ','.join(['?' for _ in cols])
        c.execute(f"INSERT INTO tools ({','.join(cols)}) VALUES ({placeholders})", vals)
        print(f"  Applied INSERT: {jid}")

conn.commit()
conn.close()

# Clean already-applied entries from proposals.json
applied_ids = {item[1] for item in plan if item[0] == 'insert'}
remaining = [p for p in proposals if p.get('fields', p).get('json_id') not in applied_ids]
Path(PROPOSALS_PATH).write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding='utf-8')

print()
print(f"Done. {len(plan)} change(s) applied.")

