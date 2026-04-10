import json, os

OUT_DIR = 'training_pairs'

types_to_preview = [
    'spec_to_description',
    'insert_to_application',
    'full_context',
    'holder_to_inserts',
]

for ptype in types_to_preview:
    path = os.path.join(OUT_DIR, f'pairs_{ptype}.jsonl')
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    if not lines:
        continue
    pair = json.loads(lines[0])
    print(f"\n{'='*70}")
    print(f"TYPE: {ptype}  (source: {pair.get('source','?')})")
    print(f"{'='*70}")
    print("INPUT:")
    print(pair['input'][:600])
    print("\nOUTPUT:")
    print(pair['output'][:400])
    print()
