import json, os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
PROPOSALS_PATH = os.path.join(DATA_DIR, 'proposals.json')

SOURCE = "Sandvik Latest cutting tools 26-1.pdf p.425"

entries = [
    # --- METRIC ---
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM12-N1012",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 10mm square shank, QSM12 machine-side connection. Mounts standard 10mm square shank into QS Micro quick-change system. For Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_mm": 10,
                "shank_width_mm": 10,
                "qs_size": "QSM12",
                "oal_mm": 80.0,
                "overall_width_mm": 16.0,
                "overall_height_mm": 12.0,
                "min_overhang_mm": 12.0,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square"
            }),
            "size": "10mm sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "10mm", "quick-change"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM12-N1212",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 12mm square shank, QSM12 machine-side connection. Mounts standard 12mm square shank into QS Micro quick-change system. For Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_mm": 12,
                "shank_width_mm": 12,
                "qs_size": "QSM12",
                "oal_mm": 80.0,
                "overall_width_mm": 16.0,
                "overall_height_mm": 12.0,
                "min_overhang_mm": 12.0,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square"
            }),
            "size": "12mm sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "12mm", "quick-change"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM16-N1616",
            "component_type": "shank",
            "mounts_to": "ECAS20_GANG_BLOCK",
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 16mm square shank, QSM16 machine-side connection. Mounts into ECAS20 gang block 16mm square station; provides QS Micro quick-change interface on cutting side for CoroTurn SL heads.",
            "specs": json.dumps({
                "shank_height_mm": 16,
                "shank_width_mm": 16,
                "qs_size": "QSM16",
                "oal_mm": 80.0,
                "overall_width_mm": 18.0,
                "overall_height_mm": 16.0,
                "min_overhang_mm": 12.0,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square"
            }),
            "size": "16mm sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "16mm", "quick-change", "ECAS20"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM16-N2020",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 20mm square shank, QSM16 machine-side connection. Mounts standard 20mm square shank into QS Micro quick-change system. For Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_mm": 20,
                "shank_width_mm": 20,
                "qs_size": "QSM16",
                "oal_mm": 80.0,
                "overall_width_mm": 20.0,
                "overall_height_mm": 20.0,
                "min_overhang_mm": 10.0,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square"
            }),
            "size": "20mm sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "20mm", "quick-change"]),
            "condition": "New"
        }
    },
    # --- IMPERIAL ---
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM12-N0608",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 3/8\" (0.375\") square shank, QSM12 machine-side connection. Imperial variant for Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_in": 0.375,
                "shank_height_mm": 9.525,
                "qs_size": "QSM12",
                "oal_in": 3.150,
                "overall_width_in": 0.630,
                "overall_height_in": 0.472,
                "min_overhang_in": 0.472,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square",
                "measurement_type": "Imperial"
            }),
            "size": "3/8\" sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "imperial", "3/8", "quick-change"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM12-N08",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 1/2\" (0.500\") square shank, QSM12 machine-side connection. Imperial variant for Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_in": 0.500,
                "shank_height_mm": 12.7,
                "qs_size": "QSM12",
                "oal_in": 3.150,
                "overall_width_in": 0.644,
                "overall_height_in": 0.500,
                "min_overhang_in": 0.472,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square",
                "measurement_type": "Imperial"
            }),
            "size": "1/2\" sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "imperial", "1/2", "quick-change"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM16-N10",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 5/8\" (0.625\") square shank, QSM16 machine-side connection. Imperial variant for Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_in": 0.625,
                "shank_height_mm": 15.875,
                "qs_size": "QSM16",
                "oal_in": 3.150,
                "overall_width_in": 0.706,
                "overall_height_in": 0.625,
                "min_overhang_in": 0.472,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square",
                "measurement_type": "Imperial"
            }),
            "size": "5/8\" sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "imperial", "5/8", "quick-change"]),
            "condition": "New"
        }
    },
    {
        "action": "insert",
        "table": "tools",
        "status": "proposed",
        "fields": {
            "json_id": "QSM16-N12",
            "component_type": "shank",
            "mounts_to": None,
            "category": "Shank Adaptors",
            "type": "QS Micro Shank Adaptor",
            "manufacturer": "Sandvik Coromant",
            "description": "QS Micro shank adaptor, 3/4\" (0.750\") square shank, QSM16 machine-side connection. Imperial variant for Swiss-type lathes.",
            "specs": json.dumps({
                "shank_height_in": 0.750,
                "shank_height_mm": 19.05,
                "qs_size": "QSM16",
                "oal_in": 3.150,
                "overall_width_in": 0.787,
                "overall_height_in": 0.750,
                "min_overhang_in": 0.394,
                "connection_thread": "M6",
                "coolant_pressure_bar": 150,
                "machine_side_connection": "QS Micro (CNSC=3)",
                "cutting_side_connection": "CoroTurn SL (CXSC=1)",
                "shank_type": "square",
                "measurement_type": "Imperial"
            }),
            "size": "3/4\" sq",
            "insert_seat": None,
            "compatible_inserts": None,
            "sources": json.dumps([SOURCE]),
            "price_range": None,
            "tags": json.dumps(["sandvik", "QS micro", "shank adaptor", "swiss", "imperial", "3/4", "quick-change"]),
            "condition": "New"
        }
    },
]

# Load existing proposals or start fresh
if os.path.exists(PROPOSALS_PATH):
    with open(PROPOSALS_PATH, 'r', encoding='utf-8') as f:
        existing = json.load(f)
else:
    existing = []

existing.extend(entries)

with open(PROPOSALS_PATH, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print(f"Added {len(entries)} proposals to {PROPOSALS_PATH}")
for e in entries:
    mt = e['fields']['mounts_to'] or 'NULL (pending verification)'
    print(f"  {e['fields']['json_id']:20s}  {e['fields']['size']:10s}  mounts_to={mt}")
