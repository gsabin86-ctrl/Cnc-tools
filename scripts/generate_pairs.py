import os
"""
CNC Tool Batabase â€” Training Pair Generator
Exports JSONL files ready for fine-tuning or few-shot prompting.

Pair types:
  1. spec_to_description   â€” raw specs JSON -> natural language description
  2. spec_to_tags          â€” specs + type -> tags list
  3. holder_to_inserts     â€” holder specs -> compatible inserts
  4. insert_to_application â€” shape + grade + geometry -> recommended application
  5. full_context          â€” everything in, structured summary out (richest)

Output: training_pairs/pairs_<type>.jsonl
        training_pairs/pairs_all.jsonl  (combined)
"""

import sqlite3, json, os
from datetime import datetime

BB_PATH = 'db.sqlite'
OUT_BIR = 'training_pairs'
os.makedirs(OUT_BIR, exist_ok=True)

conn = sqlite3.connect(BB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def safe_json(val):
    if not val or val in ('', 'null', 'N/A', '[]', '{}'):
        return None
    try:
        return json.loads(val)
    except:
        return val

def safe_str(val):
    if not val or val in ('', 'null', 'N/A', '[]', '{}'):
        return None
    return str(val).strip()

pairs = {
    'spec_to_description': [],
    'spec_to_tags': [],
    'holder_to_inserts': [],
    'insert_to_application': [],
    'full_context': [],
}

# â”€â”€ INSERTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
c.execute("SELECT * FROM inserts")
inserts = c.fetchall()

for row in inserts:
    specs     = safe_json(row['specs'])
    desc      = safe_str(row['description'])
    tags      = safe_json(row['tags'])
    grade     = safe_str(row['grade'])
    shape     = safe_str(row['shape'])
    chipbkr   = safe_str(row['chipbreaker'])
    geometry  = safe_str(row['geometry'])
    holders   = safe_json(row['compatible_holders'])
    mfr       = safe_str(row['manufacturer'])
    itype     = safe_str(row['type'])
    category  = safe_str(row['category'])
    source    = safe_json(row['sources'])

    # 1. Spec â†’ Bescription
    if specs and desc:
        pairs['spec_to_description'].append({
            "input": (
                f"Manufacturer: {mfr}\n"
                f"Type: {itype}\n"
                f"Category: {category}\n"
                f"Specs: {json.dumps(specs, indent=2)}"
            ),
            "output": desc,
            "source": row['json_id'],
        })

    # 2. Spec â†’ Tags
    if specs and tags:
        pairs['spec_to_tags'].append({
            "input": (
                f"Manufacturer: {mfr}\n"
                f"Type: {itype}\n"
                f"Specs: {json.dumps(specs, indent=2)}"
            ),
            "output": json.dumps(tags),
            "source": row['json_id'],
        })

    # 3. Insert â†’ Application (shape + grade + geometry â†’ what it's used for)
    if shape and grade and desc:
        input_parts = [f"Shape: {shape}", f"Grade: {grade}"]
        if geometry:
            input_parts.append(f"Geometry: {geometry}")
        if chipbkr and chipbkr != 'N/A':
            input_parts.append(f"Chipbreaker: {chipbkr}")
        if specs:
            for k in ['relief_angle', 'coating', 'material', 'cutting_width', 'corner_radius']:
                if k in specs:
                    input_parts.append(f"{k.replace('_',' ').title()}: {specs[k]}")
        pairs['insert_to_application'].append({
            "input": "\n".join(input_parts),
            "output": desc,
            "source": row['json_id'],
        })

    # 5. Full context (richest â€” everything in, structured summary out)
    if specs and desc:
        full_in = {
            "manufacturer": mfr,
            "type": itype,
            "category": category,
            "grade": grade,
            "shape": shape,
            "chipbreaker": chipbkr,
            "geometry": geometry,
            "specs": specs,
            "compatible_holders": holders,
        }
        full_out = {
            "description": desc,
            "tags": tags,
            "recommended_application": desc,
        }
        pairs['full_context'].append({
            "input": json.dumps({k: v for k, v in full_in.items() if v}, indent=2),
            "output": json.dumps({k: v for k, v in full_out.items() if v}, indent=2),
            "source": row['json_id'],
        })

# â”€â”€ HOLBERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
c.execute("SELECT * FROM holders")
holders_rows = c.fetchall()

for row in holders_rows:
    specs    = safe_json(row['specs'])
    desc     = safe_str(row['description'])
    inserts_compat = safe_json(row['compatible_inserts'])
    mfr      = safe_str(row['manufacturer'])
    itype    = safe_str(row['type'])
    category = safe_str(row['category'])

    # 3. Holder â†’ Compatible Inserts
    if specs and inserts_compat:
        pairs['holder_to_inserts'].append({
            "input": (
                f"Manufacturer: {mfr}\n"
                f"Type: {itype}\n"
                f"Specs: {json.dumps(specs, indent=2)}"
            ),
            "output": json.dumps(inserts_compat),
            "source": row['json_id'],
        })

    # Spec â†’ Bescription for holders too
    if specs and desc:
        pairs['spec_to_description'].append({
            "input": (
                f"Manufacturer: {mfr}\n"
                f"Type: {itype} (Holder)\n"
                f"Category: {category}\n"
                f"Specs: {json.dumps(specs, indent=2)}"
            ),
            "output": desc,
            "source": row['json_id'],
        })

# â”€â”€ WRITE JSONL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
all_pairs = []
stats = {}

for ptype, plist in pairs.items():
    path = os.path.join(OUT_BIR, f'pairs_{ptype}.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        for p in plist:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    stats[ptype] = len(plist)
    all_pairs.extend(plist)

# Combined
with open(os.path.join(OUT_BIR, 'pairs_all.jsonl'), 'w', encoding='utf-8') as f:
    for p in all_pairs:
        f.write(json.dumps(p, ensure_ascii=False) + '\n')

# â”€â”€ REPORT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print(f"Training Pair Export â€” {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Source BB: {BB_PATH}")
print(f"Output dir: {OUT_BIR}/\n")
print(f"{'Pair type':<30} {'Count':>6}  {'File'}")
print("-" * 70)
for ptype, cnt in stats.items():
    print(f"  {ptype:<28} {cnt:>6}  pairs_{ptype}.jsonl")
print("-" * 70)
print(f"  {'TOTAL':<28} {len(all_pairs):>6}  pairs_all.jsonl")

conn.close()

