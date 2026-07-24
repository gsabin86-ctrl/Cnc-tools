import json, os, sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db.sqlite')
PROPOSALS_PATH = os.path.join(DATA_DIR, 'proposals.json')

with open(PROPOSALS_PATH, 'r', encoding='utf-8') as f:
    proposals = json.load(f)

conn = sqlite3.connect(DB)
cur = conn.cursor()

kept, removed = [], []
for p in proposals:
    jid = p.get('fields', {}).get('json_id') or p.get('json_id')
    action = p.get('action', 'insert')
    if action == 'insert' and jid:
        cur.execute("SELECT 1 FROM tools WHERE json_id=?", (jid,))
        if cur.fetchone():
            removed.append(jid)
            continue
    kept.append(p)

conn.close()

with open(PROPOSALS_PATH, 'w', encoding='utf-8') as f:
    json.dump(kept, f, indent=2, ensure_ascii=False)

print(f"Removed {len(removed)} already-applied entries:")
for r in removed: print(f"  {r}")
print(f"Kept {len(kept)} pending proposals")
