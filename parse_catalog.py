import re, os

path = 'C:/Users/gsabi/.openclaw/workspace/cnc-tool-database/iscar_miniature_catalog_part1.mhtml'
with open(path, 'rb') as f:
    raw = f.read()

boundary = b'------MultipartBoundary--efzyImdJxKg9i6U1Kxgenv3GuDSdNhNZy9yaEay8Gd----'
parts = raw.split(boundary)

html_part = parts[1].decode('utf-8', errors='ignore')

# Look for page image URLs
urls = re.findall(r'https?://[^\s"\'<>]+\.(jpg|png|pdf)', html_part, re.IGNORECASE)
print('Image URLs found:')
for u in urls[:20]:
    print(u)

# Look for JS config with page list
idx = html_part.find('files/')
if idx > 0:
    print('\nSample around "files/":')
    print(html_part[idx-50:idx+200])

# Find any "pages" array or similar
m = re.search(r'(numPages|totalPages|pageCount)[^;]{0,100}', html_part)
if m:
    print('\nPage count config:', m.group(0))
