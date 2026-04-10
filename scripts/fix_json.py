import json

with open('proposals.json', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the last complete entry (ends with },"status":"proposed"})
last_good = content.rfind('},"status":"proposed"}')
if last_good == -1:
    print("Could not find marker")
else:
    trimmed = content[:last_good + len('},"status":"proposed"}')]
    
    # Build the final entry as a dict and serialize cleanly
    final = {
        "action": "insert",
        "table": "tools",
        "fields": {
            "json_id": "R108.PG20.02",
            "component_type": "insert",
            "mounts_to": None,
            "category": "Threading Inserts",
            "type": "Horn System 108 PG Threading Insert",
            "manufacturer": "PH Horn",
            "description": "Horn System 108 PG threading insert (80 deg profile), right-hand, 20 TPI, min bore 8mm.",
            "specs": "{\"thread_standard\":\"PG\",\"thread_angle\":\"80 deg\",\"tpi\":\"20\",\"E\":\"1.9 mm\",\"f\":\"4.8 mm\",\"d\":\"6 mm\",\"s\":\"3.6 mm\",\"min_bore_dmin\":\"8 mm\",\"cutting_direction\":\"Right\"}",
            "size": "108",
            "shape": "Threading",
            "chipbreaker": "N/A",
            "grade": "EG55, TN35",
            "compatible_machines": "[\"CNC lathes\"]",
            "compatible_inserts": "[\"N/A\"]",
            "sources": "[\"PH Horn Supermini-Mini Catalog, System 108 Insert Page 238\"]",
            "tags": "[\"threading\",\"PG\",\"80deg\",\"right-hand\",\"20TPI\",\"Horn\",\"System-108\"]",
            "condition": "New"
        },
        "status": "proposed"
    }
    
    complete = trimmed + ',\n  ' + json.dumps(final) + '\n]'
    
    # Validate
    data = json.loads(complete)
    print(f"Valid JSON: {len(data)} entries")
    
    with open('proposals.json', 'w', encoding='utf-8') as f:
        f.write(complete)
    print("Written.")
