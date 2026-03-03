import urllib.request, os, time

base_url = "https://www.iscar.com/Catalogs/Publication/Catalogs_Mm/english_1/Miniature_Parts/Miniature%20Parts_Catalog_flipview_part1/files/page/{}.jpg?2025-12-24081709"
out_dir = "C:/Users/gsabi/.openclaw/workspace/cnc-tool-database/catalog_images_part1"
os.makedirs(out_dir, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

for page in range(1, 31):
    url = base_url.format(page)
    out_path = os.path.join(out_dir, f"page_{page:03d}.jpg")
    if os.path.exists(out_path):
        print(f"Page {page}: already exists")
        continue
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            with open(out_path, 'wb') as f:
                f.write(data)
            print(f"Page {page}: {len(data)} bytes")
    except Exception as e:
        print(f"Page {page}: FAILED - {e}")
    time.sleep(0.3)
