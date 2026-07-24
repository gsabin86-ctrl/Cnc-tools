"""
db.py — Quick DB inspection utility for the CNC tool database.

Usage:
    python3 db.py summary              # counts by type and manufacturer
    python3 db.py inserts [mfr]        # list inserts, optionally filtered by manufacturer
    python3 db.py holders [mfr]        # list holders
    python3 db.py search <term>        # search json_id / name across all tools
    python3 db.py orphans              # inserts whose compatible_holders don't exist in DB
    python3 db.py missing-back         # holders with no compatible_inserts back-links
    python3 db.py seat <prefix>        # all inserts with json_id starting with prefix
    python3 db.py sql "<query>"        # raw SQL query
"""

import sys, sqlite3, json

DB = "docs/db.sqlite"

def conn():
    return sqlite3.connect(DB)

def summary():
    db = conn()
    print("=== By component_type ===")
    for row in db.execute("SELECT component_type, COUNT(*) n FROM tools GROUP BY component_type ORDER BY n DESC"):
        print(f"  {row[0]:<12} {row[1]}")
    print()
    print("=== Inserts by manufacturer ===")
    for row in db.execute("SELECT manufacturer, COUNT(*) n FROM tools WHERE component_type='insert' GROUP BY manufacturer ORDER BY n DESC"):
        print(f"  {row[0]:<20} {row[1]}")
    print()
    print("=== Holders by manufacturer ===")
    for row in db.execute("SELECT manufacturer, COUNT(*) n FROM tools WHERE component_type='holder' GROUP BY manufacturer ORDER BY n DESC"):
        print(f"  {row[0]:<20} {row[1]}")
    total = db.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
    print(f"\nTOTAL: {total}")

def list_tools(ctype, mfr=None):
    db = conn()
    q = "SELECT json_id, name, manufacturer FROM tools WHERE component_type=?"
    args = [ctype]
    if mfr:
        q += " AND LOWER(manufacturer) LIKE ?"
        args.append(f"%{mfr.lower()}%")
    q += " ORDER BY manufacturer, json_id"
    rows = db.execute(q, args).fetchall()
    for r in rows:
        print(f"  {r[2]:<20} {r[0]:<30} {r[1]}")
    print(f"\n{len(rows)} records")

def search(term):
    db = conn()
    rows = db.execute(
        "SELECT component_type, manufacturer, json_id, name FROM tools "
        "WHERE json_id LIKE ? OR name LIKE ? ORDER BY component_type, json_id",
        [f"%{term}%", f"%{term}%"]
    ).fetchall()
    for r in rows:
        print(f"  [{r[0]}] {r[1]:<18} {r[2]:<30} {r[3]}")
    print(f"\n{len(rows)} records")

def orphans():
    """Show inserts whose compatible_machines notes reference holders not yet in DB.

    Note: holder refs are currently stored as text in compatible_machines,
    e.g. 'Compatible via holders: KM16STJCR1120, ...'
    Phase 4 will migrate these to mounts_to as structured JSON.
    """
    db = conn()
    all_holder_ids = {r[0] for r in db.execute("SELECT json_id FROM tools WHERE component_type IN ('holder','module')")}
    rows = db.execute(
        "SELECT json_id, manufacturer, compatible_machines FROM tools "
        "WHERE component_type='insert' AND compatible_machines IS NOT NULL"
    ).fetchall()
    holder_in_db = 0
    holder_missing = 0
    missing_holders = set()
    for json_id, mfr, cm in rows:
        machines = json.loads(cm) if cm else []
        for entry in machines:
            if entry.startswith("Compatible via holders:"):
                ids = [h.strip() for h in entry.replace("Compatible via holders:", "").split(",")]
                for hid in ids:
                    if hid in all_holder_ids:
                        holder_in_db += 1
                    else:
                        holder_missing += 1
                        missing_holders.add(hid)
    print(f"Holder refs in inserts:  {holder_in_db + holder_missing}")
    print(f"  Already in DB:         {holder_in_db}")
    print(f"  Missing from DB:       {holder_missing}")
    print(f"\nMissing holder json_ids ({len(missing_holders)}):")
    for h in sorted(missing_holders):
        print(f"  {h}")

def missing_back():
    """Holders with no compatible_inserts links."""
    db = conn()
    rows = db.execute(
        "SELECT json_id, manufacturer, compatible_inserts FROM tools WHERE component_type='holder'"
    ).fetchall()
    print("Holders with no back-linked inserts:")
    empty = 0
    for json_id, mfr, ci in rows:
        inserts = json.loads(ci) if ci else []
        if not inserts:
            print(f"  {mfr:<20} {json_id}")
            empty += 1
    print(f"\n{empty} holders without insert back-links (out of {len(rows)} holders)")

def seat(prefix):
    db = conn()
    rows = db.execute(
        "SELECT json_id, manufacturer, name FROM tools WHERE component_type='insert' AND json_id LIKE ? ORDER BY json_id",
        [f"{prefix}%"]
    ).fetchall()
    for r in rows:
        print(f"  {r[1]:<20} {r[0]:<35} {r[2]}")
    print(f"\n{len(rows)} inserts matching '{prefix}*'")

def raw_sql(query):
    db = conn()
    rows = db.execute(query).fetchall()
    for r in rows:
        print("  " + " | ".join(str(x) for x in r))
    print(f"\n{len(rows)} rows")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "summary":
        summary()
    elif cmd == "inserts":
        list_tools("insert", sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "holders":
        list_tools("holder", sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "search":
        search(sys.argv[2])
    elif cmd == "orphans":
        orphans()
    elif cmd == "missing-back":
        missing_back()
    elif cmd == "seat":
        seat(sys.argv[2])
    elif cmd == "sql":
        raw_sql(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
