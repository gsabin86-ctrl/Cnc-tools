"""
view_page.py — Render a catalog PDF page as an image for visual inspection.

Usage:
    python3 view_page.py <catalog_alias> <page_number>
    python3 view_page.py <catalog_alias> <page_start>-<page_end>

Catalog aliases (add more as needed):
    kv1      Kennametal Vol.1 Turning
    kv2      Kennametal Vol.2 Rotating
    kts      Kennametal TopSwiss
    mex      Mitsubishi External Turning
    msm      Mitsubishi Small Tools
    mbr      Mitsubishi Boring
    mgr      Mitsubishi Grooving
    tbi      Tungaloy Insert Catalog B
    tce      Tungaloy External Holders C
    tci      Tungaloy Internal Holders D
    sv1      Sandvik Main (p401-450)
    svc      Sandvik CoroTurn107

Output: saves PNG to _page_view/ folder and opens it.
"""

import sys, os, fitz

CATALOGS = {
    "kv1": "catalogs/kennametal/Master Catalog 2018 Vol. 1 Turning Tools English Inch.pdf",
    "kv2": "catalogs/kennametal/Master Catalog 2018 Vol. 2 Rotating Tools English Inch.pdf",
    "kts": "catalogs/kennametal/TopSwiss Inserts MetricInch.pdf",
    "mex": "catalogs/Mitsubishi/catalog_c010a_external_turning_tools.pdf",
    "msm": "catalogs/Mitsubishi/catalog_c010a_small_tools.pdf",
    "mbr": "catalogs/Mitsubishi/catalog_c010a_boring.pdf",
    "mgr": "catalogs/Mitsubishi/catalog_c010a_grooving_cuttingoff.pdf",
    "tbi": "catalogs/Tungaloy/GC_2023-2024_G_B_Insert.pdf",
    "tce": "catalogs/Tungaloy/GC_2023-2024_G_C_ExternalToolholder.pdf",
    "tci": "catalogs/Tungaloy/GC_2023-2024_G_D_InternalToolholder.pdf",
    "sv1": "catalogs/Sandvik/sandvik_p401-450.pdf",
    "svc": "catalogs/Sandvik/sandvik_coroturn107_inserts.pdf",
    "mcb": "catalogs/Mitsubishi/catalog_c010a_cbn_pcd_inserts.pdf",
}

def render_page(pdf_path, page_num, dpi=150):
    """Render a single page to a PNG file, return path."""
    os.makedirs("_page_view", exist_ok=True)
    doc = fitz.open(pdf_path)
    total = len(doc)
    if page_num < 1 or page_num > total:
        print(f"Page {page_num} out of range (1-{total})")
        return None
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    out = f"_page_view/p{page_num:04d}.png"
    pix.save(out)
    doc.close()
    return out

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    alias = sys.argv[1].lower()
    if alias not in CATALOGS:
        print(f"Unknown alias '{alias}'. Known: {', '.join(CATALOGS)}")
        sys.exit(1)

    path = CATALOGS[alias]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    page_arg = sys.argv[2]
    if "-" in page_arg:
        start, end = map(int, page_arg.split("-"))
        pages = range(start, end + 1)
    else:
        pages = [int(page_arg)]

    saved = []
    for pg in pages:
        out = render_page(path, pg)
        if out:
            saved.append(out)
            print(f"Saved: {out}")

    # Open the first image with the default viewer
    if saved:
        os.startfile(os.path.abspath(saved[0]))
        if len(saved) > 1:
            print(f"Opened {saved[0]} — {len(saved)} files in _page_view/")
