import re

path = 'C:/Users/gsabi/.openclaw/workspace/cnc-tool-database/iscar_miniature_catalog_part1.mhtml'
with open(path, 'rb') as f:
    raw = f.read()

boundary = b'------MultipartBoundary--efzyImdJxKg9i6U1Kxgenv3GuDSdNhNZy9yaEay8Gd----'
parts = raw.split(boundary)

html_part = parts[1].decode('utf-8', errors='ignore')

# Find JS config block
for keyword in ['bookConfig', 'flipConfig', 'totalPage', 'numPage', 'pageList', 'pageurl', 'large/', 'medium/', 'small/']:
    idx = html_part.find(keyword)
    if idx >= 0:
        print(f"\n=== '{keyword}' at {idx} ===")
        print(html_part[idx:idx+300])
