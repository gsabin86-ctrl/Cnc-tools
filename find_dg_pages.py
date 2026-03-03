import re

path = 'C:/Users/gsabi/.openclaw/workspace/cnc-tool-database/iscar_miniature_catalog_part1.mhtml'
with open(path, 'rb') as f:
    raw = f.read()

boundary = b'------MultipartBoundary--efzyImdJxKg9i6U1Kxgenv3GuDSdNhNZy9yaEay8Gd----'
parts = raw.split(boundary)

html = parts[1].decode('utf-8', errors='ignore')

# Look for any mention of DGN, DGR, DGL, DGTR, Do-Grip in the HTML
for term in ['DGN', 'DGR', 'DGL', 'DGTR', 'Do-Grip', 'DoGrip', 'GROOVE', 'groove']:
    idx = html.find(term)
    if idx >= 0:
        print(f"\n=== '{term}' at {idx} ===")
        print(html[max(0,idx-100):idx+200])

# Also look for any page bookmarks/anchors
anchors = re.findall(r'anchor[^"]{0,50}|bookmark[^"]{0,50}|data-page="(\d+)"', html)
print(f"\nData-page attributes found: {set(anchors[:20])}")

# Look for total page count
m = re.search(r'(\d{3,4})\s*pages?', html, re.IGNORECASE)
if m:
    print(f"\nPage count mention: {m.group(0)}")
