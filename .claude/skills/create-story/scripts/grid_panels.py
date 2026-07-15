"""Crop a generated comic-grid image into its individual panels and overlay a
coordinate grid on each, so bubble positions can be read off by eye before
writing an overlay_captions.py config.

Usage:
    python grid_panels.py IMAGE_PATH ROWS COLS OUT_DIR [--step 20] [--scale 2]

Panels are numbered 1..ROWS*COLS in reading order (left-to-right,
top-to-bottom), matching the "Panel N" numbering used in the skill's image
prompts. Saves panel{N}.png (plain crop) and panel{N}_grid.png (upscaled,
with red vertical / blue horizontal gridlines labeled every --step pixels,
in the plain crop's own coordinate space) into OUT_DIR.
"""
import sys
import os
from PIL import Image, ImageDraw


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    image_path = sys.argv[1]
    rows = int(sys.argv[2])
    cols = int(sys.argv[3])
    out_dir = sys.argv[4]
    step = 20
    if "--step" in sys.argv:
        step = int(sys.argv[sys.argv.index("--step") + 1])
    scale = 2
    if "--scale" in sys.argv:
        scale = int(sys.argv[sys.argv.index("--scale") + 1])

    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    pw, ph = w // cols, h // rows

    n = 1
    for row in range(rows):
        for col in range(cols):
            x0 = col * pw
            y0 = row * ph
            x1 = (col + 1) * pw if col < cols - 1 else w
            y1 = (row + 1) * ph if row < rows - 1 else h
            panel = im.crop((x0, y0, x1, y1))
            panel.save(os.path.join(out_dir, f"panel{n}.png"))

            pw_l, ph_l = panel.size
            big = panel.resize((pw_l * scale, ph_l * scale), Image.LANCZOS)
            draw = ImageDraw.Draw(big)
            for gx in range(0, pw_l, step):
                draw.line([(gx * scale, 0), (gx * scale, ph_l * scale)], fill=(255, 0, 0), width=1)
                draw.text((gx * scale + 2, 2), str(gx), fill=(255, 0, 0))
            for gy in range(0, ph_l, step):
                draw.line([(0, gy * scale), (pw_l * scale, gy * scale)], fill=(0, 120, 255), width=1)
                draw.text((2, gy * scale + 2), str(gy), fill=(0, 120, 255))
            big.save(os.path.join(out_dir, f"panel{n}_grid.png"))
            print(f"panel {n}: box=({x0},{y0})-({x1},{y1}) size={panel.size}")
            n += 1


if __name__ == "__main__":
    main()
