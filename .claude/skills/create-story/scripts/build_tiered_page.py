"""Build one tiered page: the SAME artwork captioned three times, stacked.

The story is one plot told at three reading levels, so the illustration
should be one drawing read at three reading levels too. Asking an image
model for three versions gives three different drawings — the cast drifts,
the palette shifts, and the learner is looking at a new picture instead of
the same moment in richer words. So the art is generated once, and this
script writes each tier's captions onto a copy of that one file and stacks
the copies into a single page:

    +---- EASY ----+     <- same pixels
    | P1 | P2 | P3 |
    +--- MEDIUM ---+     <- same pixels, different captions
    | P1 | P2 | P3 |
    +---- HARD ----+     <- same pixels, different captions
    | P1 | P2 | P3 |

Usage:
    python build_tiered_page.py IMAGE CONFIG OUT_PATH [options]

    --font PATH        Traditional-Chinese-capable .ttf/.ttc
    --parts-dir DIR    also save the three single-tier pages separately
    --max-bytes N      shrink to fit a size budget (default 1500000)

CONFIG shape:
{
  "rows": 3, "cols": 2,
  "title": "《我的房間》My Room",          // optional banner at the top
  "boxes": {"2": [45, 35, 235, 115]},      // optional, see "Two caption modes"
  "tiers": {
    "easy":   {"1": "中明：你好。", "2": "..."},
    "medium": {"1": "中明：你好，好久不見。", "2": "..."},
    "hard":   {"1": "中明：好久不見，你最近怎麼樣？", "2": "..."}
  }
}

Panel keys are 1-indexed in reading order (top-left = 1), matching "Panel N"
in the image prompt. A panel with no text in a tier simply gets no caption
in that tier's block.

Two caption modes, per panel:
  * strip  (default) — the caption goes in a band under its panel. Needs no
    measuring and cannot garble, so this is the reliable path: generate the
    art text-free, run this, done.
  * bubble — when "boxes" holds an entry for that panel, the text is drawn
    inside that box instead (a blank speech bubble the image model drew).
    Measure boxes once with grid_panels.py; all three tiers reuse them,
    because all three tiers are the same picture.

Newlines inside a caption are kept, so "中文\npinyin" renders as two lines.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from overlay_captions import find_font, wrap_and_fit, wrap_text  # noqa: E402

TIER_ORDER = ["easy", "medium", "hard"]
TIER_LABELS = {
    "easy": "EASY  簡單",
    "medium": "MEDIUM  普通",
    "hard": "HARD  進階",
}
# A quiet colour per tier: enough to tell the blocks apart when scrolling,
# not so much that it fights the artwork.
TIER_CHIPS = {
    "easy": (108, 158, 118),
    "medium": (206, 154, 74),
    "hard": (183, 104, 94),
}

INK = (40, 30, 25)
STRIP_BG = (255, 253, 249)
STRIP_RULE = (214, 206, 194)
HEADER_BG = (245, 242, 236)
LINE_SPACING = 1.32
STRIP_PAD_RATIO = 0.30  # of one line's height, top and bottom
MAX_STRIP_LINES = 3


def panel_bounds(width, height, rows, cols, index):
    """Pixel box of panel `index` (1-based, reading order).

    The last column and row absorb the rounding remainder, matching how
    grid_panels.py crops — otherwise a 1023px-wide 2-column image would drop
    a stripe of artwork.
    """
    pw, ph = width // cols, height // rows
    row, col = divmod(index - 1, cols)
    x0, y0 = col * pw, row * ph
    x1 = (col + 1) * pw if col < cols - 1 else width
    y1 = (row + 1) * ph if row < rows - 1 else height
    return x0, y0, x1, y1


def fit_strip(draw, text, box_w, font_path, start_size, min_size=11):
    """Largest font size that keeps a caption within MAX_STRIP_LINES."""
    font = ImageFont.truetype(font_path, start_size)
    lines = wrap_text(draw, text, box_w, font)
    for size in range(start_size, min_size - 1, -1):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, box_w, font)
        if len(lines) <= MAX_STRIP_LINES:
            break
    line_h = font.getbbox("測")[3] - font.getbbox("測")[1]
    return font, lines, line_h


def render_tier(base, rows, cols, texts, boxes, font_path):
    """One tier's page: the base artwork plus that tier's captions."""
    width, height = base.size
    measure = ImageDraw.Draw(base.copy())
    panel_w = width // cols
    start_size = max(13, int(panel_w * 0.052))

    # Measure every strip first — a row is only as tall as its longest caption,
    # and rows are sized independently so a chatty row doesn't pad the others.
    strip_plans = {}
    strip_heights = [0] * rows
    for index in range(1, rows * cols + 1):
        key = str(index)
        if key not in texts or key in boxes:
            continue
        x0, _, x1, _ = panel_bounds(width, height, rows, cols, index)
        inner_w = (x1 - x0) * 0.92
        font, lines, line_h = fit_strip(measure, texts[key], inner_w, font_path, start_size)
        pad = int(line_h * STRIP_PAD_RATIO)
        needed = int(len(lines) * line_h * LINE_SPACING) + 2 * pad
        strip_plans[index] = (font, lines, line_h, pad)
        row = (index - 1) // cols
        strip_heights[row] = max(strip_heights[row], needed)

    page = Image.new("RGB", (width, height + sum(strip_heights)), STRIP_BG)
    draw = ImageDraw.Draw(page)

    # Paste each row of artwork, then the caption band that belongs under it.
    y_cursor = 0
    for row in range(rows):
        _, ry0, _, ry1 = panel_bounds(width, height, rows, cols, row * cols + 1)
        row_img = base.crop((0, ry0, width, ry1))
        page.paste(row_img, (0, y_cursor))
        y_cursor += ry1 - ry0

        band_h = strip_heights[row]
        if band_h:
            draw.line([(0, y_cursor), (width, y_cursor)], fill=STRIP_RULE, width=1)
            for col in range(cols):
                index = row * cols + col + 1
                if index not in strip_plans:
                    continue
                x0, _, x1, _ = panel_bounds(width, height, rows, cols, index)
                font, lines, line_h, pad = strip_plans[index]
                total_h = len(lines) * line_h * LINE_SPACING
                text_y = y_cursor + (band_h - total_h) / 2
                for i, line in enumerate(lines):
                    line_w = draw.textlength(line, font=font)
                    draw.text(
                        (x0 + ((x1 - x0) - line_w) / 2, text_y + i * line_h * LINE_SPACING),
                        line,
                        font=font,
                        fill=INK,
                    )
                if col < cols - 1:
                    draw.line(
                        [(x1, y_cursor + pad), (x1, y_cursor + band_h - pad)],
                        fill=STRIP_RULE,
                        width=1,
                    )
            y_cursor += band_h

    # Bubble-mode panels are drawn straight onto the artwork, in the box the
    # image model left blank. Offsets shift down by the strips already added
    # above that panel's row.
    for index in range(1, rows * cols + 1):
        key = str(index)
        if key not in texts or key not in boxes:
            continue
        x0, y0, _, _ = panel_bounds(width, height, rows, cols, index)
        row = (index - 1) // cols
        y_offset = y0 + sum(strip_heights[:row])
        lx0, ly0, lx1, ly1 = boxes[key]
        box_w, box_h = lx1 - lx0, ly1 - ly0
        font, lines, line_h = wrap_and_fit(draw, texts[key], box_w, box_h, font_path)
        total_h = line_h * len(lines) * LINE_SPACING
        start_y = y_offset + ly0 + (box_h - total_h) / 2
        for i, line in enumerate(lines):
            line_w = draw.textlength(line, font=font)
            draw.text(
                (x0 + lx0 + (box_w - line_w) / 2, start_y + i * line_h * LINE_SPACING),
                line,
                font=font,
                fill=INK,
            )

    return page


def draw_band(width, label, chip, font_path, height):
    """The separator between two tiers.

    Labels are off by default: the sections are already ordered simplest to
    hardest, and a page with no Latin text on it matches what the image
    prompt asks for. Pass "labels": true (or a {tier: text} dict) to name
    them.
    """
    band = Image.new("RGB", (width, height), HEADER_BG)
    draw = ImageDraw.Draw(band)
    if label is None:
        draw.line([(0, height // 2), (width, height // 2)], fill=STRIP_RULE, width=1)
        return band
    draw.rectangle([0, 0, max(6, width // 160), height], fill=chip)
    font = ImageFont.truetype(font_path, max(14, int(height * 0.46)))
    bbox = font.getbbox(label)
    draw.text(
        (width // 40 + 8, (height - (bbox[3] - bbox[1])) / 2 - bbox[1]),
        label,
        font=font,
        fill=INK,
    )
    return band


def save_within_budget(page, out_path, max_bytes):
    """Save, falling back to JPEG if the PNG blows the size budget.

    The skill targets pages under ~1.5 MB so they stay pasteable and quick to
    load on a classroom connection; three stacked blocks is three times the
    pixels, so this matters more here than for a single grid.
    """
    stem, ext = os.path.splitext(out_path)
    if ext.lower() in (".jpg", ".jpeg"):
        for quality in (90, 85, 80, 74, 68, 60):
            page.save(out_path, quality=quality, optimize=True)
            if not max_bytes or os.path.getsize(out_path) <= max_bytes:
                return out_path
        return out_path

    page.save(out_path, optimize=True)
    if not max_bytes or os.path.getsize(out_path) <= max_bytes:
        return out_path

    jpg_path = stem + ".jpg"
    for quality in (90, 85, 80, 74, 68, 60):
        page.save(jpg_path, quality=quality, optimize=True)
        if os.path.getsize(jpg_path) <= max_bytes:
            break
    print(
        f"  PNG was {os.path.getsize(out_path)} bytes (over {max_bytes}); "
        f"wrote {jpg_path} instead"
    )
    os.remove(out_path)
    return jpg_path


def build(image_path, config, out_path, font_path, parts_dir=None, max_bytes=1_500_000):
    base = Image.open(image_path).convert("RGB")
    rows, cols = config["rows"], config["cols"]
    boxes = {str(k): v for k, v in config.get("boxes", {}).items()}
    tiers = config["tiers"]
    present = [tier for tier in TIER_ORDER if tier in tiers] + [
        tier for tier in tiers if tier not in TIER_ORDER
    ]

    width = base.size[0]
    label_config = config.get("labels", False)
    show_labels = label_config is not False
    labels = {**TIER_LABELS, **(label_config if isinstance(label_config, dict) else {})}
    band_h = max(34, int(width * 0.045)) if show_labels else max(10, int(width * 0.014))

    blocks = []
    for tier in present:
        texts = {str(k): v for k, v in tiers[tier].items()}
        tier_page = render_tier(base, rows, cols, texts, boxes, font_path)
        if parts_dir:
            os.makedirs(parts_dir, exist_ok=True)
            part_path = os.path.join(parts_dir, f"{tier}.png")
            tier_page.save(part_path)
            print(f"  {tier}: {part_path}")
        blocks.append(
            (
                draw_band(
                    width,
                    labels.get(tier, tier.upper()) if show_labels else None,
                    TIER_CHIPS.get(tier, INK),
                    font_path,
                    band_h,
                ),
                tier_page,
            )
        )

    title = config.get("title")
    title_h = int(band_h * 1.15) if title else 0
    total_h = title_h + sum(band.size[1] + body.size[1] for band, body in blocks)
    page = Image.new("RGB", (width, total_h), STRIP_BG)

    y = 0
    if title:
        draw = ImageDraw.Draw(page)
        font = ImageFont.truetype(font_path, max(16, int(title_h * 0.5)))
        bbox = font.getbbox(title)
        draw.text(
            ((width - (bbox[2] - bbox[0])) / 2, (title_h - (bbox[3] - bbox[1])) / 2 - bbox[1]),
            title,
            font=font,
            fill=INK,
        )
        y += title_h
    for band, body in blocks:
        page.paste(band, (0, y))
        y += band.size[1]
        page.paste(body, (0, y))
        y += body.size[1]

    final_path = save_within_budget(page, out_path, max_bytes)
    print(f"saved {final_path} ({page.size[0]}x{page.size[1]}, {len(blocks)} tiers)")
    return final_path


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    image_path, config_path, out_path = sys.argv[1:4]

    def flag(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

    font_path = flag("--font") or find_font()
    parts_dir = flag("--parts-dir")
    max_bytes = int(flag("--max-bytes", "1500000"))

    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)

    build(image_path, config, out_path, font_path, parts_dir, max_bytes)


if __name__ == "__main__":
    main()
