"""Overlay Chinese caption text into the empty speech bubbles of a generated
comic-grid image (see references/image-prompt-template.md's blank-bubble
mode: the image prompt only ever asks for blank bubble shapes, never for
AI-rendered text, so the real text is added here afterward from the
Caption Script).

This captions ONE image at one reading level. For the usual case — the same
artwork captioned at all three tiers and stacked into one page — use
build_tiered_page.py instead; it wraps this logic and adds caption strips for
panels with no bubble.

Usage:
    python overlay_captions.py IMAGE_PATH CONFIG_JSON OUT_PATH [--font PATH]

CONFIG_JSON shape:
{
  "rows": 3, "cols": 2,
  "panels": {
    "2": {"box": [45, 35, 235, 115], "text": "你的書好多！"},
    "3": {"box": [195, 35, 318, 98], "text": "..."}
  }
}
- "rows"/"cols" must match the grid used in the image prompt.
- Panel keys are 1-indexed reading order (top-left=1), matching "Panel N"
  in the prompt. Omit panels with no bubble (narrator-only panels).
- "box" is [left, top, right, bottom] in that PANEL's own local pixel
  coordinates (i.e. before adding the panel's offset in the full image) --
  read these off the panelN_grid.png images from grid_panels.py. Keep the
  box comfortably inside the drawn bubble outline; text auto-shrinks to fit
  but a box that's too generous will still let text spill past the outline.

Font: defaults to the first Traditional-Chinese-capable font found among
common Windows install paths; pass --font to use a specific .ttf/.ttc.
"""
import sys
import os
import json
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msjhbd.ttc",   # Microsoft JhengHei Bold (Traditional)
    r"C:\Windows\Fonts\msjh.ttc",     # Microsoft JhengHei (Traditional)
    r"C:\Windows\Fonts\NotoSansTC-VF.ttf",
    r"C:\Windows\Fonts\mingliu.ttc",
]

LINE_SPACING = 1.5
PAD = 0.82  # shrink each box by this factor for margin from the drawn outline

# Chinese typesetting forbids these from starting a line (禁則). Breaking
# "整齊多了，快進來坐" after 了 would push the comma to the head of the next
# line, which reads as a typo to anyone literate in the script.
NO_LINE_START = "。，、；：？！）」』】〉》”’%…·"


def find_font():
    for path in DEFAULT_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise SystemExit(
        "No Traditional-Chinese-capable font found among default candidates; pass --font PATH."
    )


def wrap_text(draw, text, box_w, font):
    """Wrap to `box_w`, honouring explicit newlines and the 禁則 rule.

    Chinese has no spaces to break on, so wrapping is by character width. A
    line may run one character over rather than orphan a comma or full stop
    onto the next line.
    """
    sample = "測試字寬"
    avg_w = draw.textlength(sample, font=font) / len(sample)
    per_line = max(1, int(box_w / avg_w))
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            if len(current) + 1 > per_line and char not in NO_LINE_START:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    return lines


def wrap_and_fit(draw, text, box_w, box_h, font_path, max_size=22, min_size=8):
    box_w *= PAD
    box_h *= PAD
    font, lines, line_h = None, [text], 1
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, box_w, font)
        line_h = font.getbbox("測")[3] - font.getbbox("測")[1]
        total_h = line_h * len(lines) * LINE_SPACING
        max_line_w = max(draw.textlength(line, font=font) for line in lines)
        if total_h <= box_h and max_line_w <= box_w:
            return font, lines, line_h
    return font, lines, line_h


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    image_path = sys.argv[1]
    config_path = sys.argv[2]
    out_path = sys.argv[3]
    font_path = sys.argv[sys.argv.index("--font") + 1] if "--font" in sys.argv else find_font()

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    rows, cols = config["rows"], config["cols"]
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    pw, ph = w // cols, h // rows
    draw = ImageDraw.Draw(im)

    for panel_key, spec in config["panels"].items():
        n = int(panel_key)
        row, col = divmod(n - 1, cols)
        ox = col * pw
        oy = row * ph
        lx0, ly0, lx1, ly1 = spec["box"]
        box_w, box_h = lx1 - lx0, ly1 - ly0
        font, lines, line_h = wrap_and_fit(draw, spec["text"], box_w, box_h, font_path)
        total_h = line_h * len(lines) * LINE_SPACING
        start_y = oy + ly0 + (box_h - total_h) / 2
        for i, line in enumerate(lines):
            line_w = draw.textlength(line, font=font)
            x = ox + lx0 + (box_w - line_w) / 2
            y = start_y + i * line_h * LINE_SPACING
            draw.text((x, y), line, font=font, fill=(40, 30, 25))

    im.save(out_path)
    print("saved", out_path)


if __name__ == "__main__":
    main()
