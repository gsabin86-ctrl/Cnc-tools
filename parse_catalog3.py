import re

path = 'C:/Users/gsabi/.openclaw/workspace/cnc-tool-database/iscar_miniature_catalog_part1.mhtml'
with open(path, 'rb') as f:
    raw = f.read()

boundary = b'------MultipartBoundary--efzyImdJxKg9i6U1Kxgenv3GuDSdNhNZy9yaEay8Gd----'
parts = raw.split(boundary)

# Part 1 is the main HTML - it's 890KB so rich with JS
html = parts[1].decode('utf-8', errors='ignore')

# Search for patterns that indicate page image loading
for pattern in ['pageUrl', 'pageImage', 'getPage', 'loadPage', '"page"', 'files/page', 'files/large', 'files/normal', 'normalSize', 'pageFile']:
    idx = html.find(pattern)
    if idx >= 0:
        print(f"\n=== '{pattern}' at {idx} ===")
        print(html[max(0,idx-50):idx+300])
        print()
