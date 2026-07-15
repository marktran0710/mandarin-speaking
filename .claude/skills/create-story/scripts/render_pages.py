"""Render a page range from the 時代華語 1 (Modern Chinese 1) source PDF to PNG images.

Usage:
    python render_pages.py START END OUT_DIR [--dpi 150]

START/END are 1-indexed, inclusive page numbers as printed in references/lesson-index.md.
Renders one PNG per page named page_<n>.png into OUT_DIR (created if missing).
The source PDF has no text layer (scanned book) -- rendering to image and reading
the image is the only way to see its content.
"""
import sys
import os
import fitz

PDF_PATH = r"D:\hautran\Chinese\book refer\時代華語 1 課程.pdf"


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    out_dir = sys.argv[3]
    dpi = 150
    if "--dpi" in sys.argv:
        dpi = int(sys.argv[sys.argv.index("--dpi") + 1])

    if not os.path.exists(PDF_PATH):
        print(f"Source PDF not found at {PDF_PATH}. If it moved, update PDF_PATH in this script "
              f"and the path noted in references/lesson-index.md.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(PDF_PATH)
    start = max(1, start)
    end = min(doc.page_count, end)
    for i in range(start - 1, end):
        pix = doc[i].get_pixmap(dpi=dpi)
        out_path = os.path.join(out_dir, f"page_{i + 1}.png")
        pix.save(out_path)
        print("saved", out_path)


if __name__ == "__main__":
    main()
