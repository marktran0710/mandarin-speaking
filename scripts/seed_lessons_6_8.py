"""Seed Modern Chinese Book 1 Lessons 6-8 in teacher/public story mode.

Easy lines are transcribed from the supplied book PDF. Reading lines are split
into natural short units, so frame counts follow the actual speaking turns.
The generated storyboard sheets are cropped into one image per frame.
"""
from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8"
SPEECH_UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8-bubble"
FULL_UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8-full"
FULL_V2_UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8-full-v2"
FULL_V3_UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8-full-v3"
FULL_V3_FINAL_UPLOADS = ROOT / "backend" / "uploads" / "images" / "lesson-6-8-full-v3-final"
API = "http://127.0.0.1:8000/api/custom-stories"
GEN = Path(r"C:\Users\Administrator\.codex\generated_images\01a009d9-ed47-7fd3-a7ed-b26c2ee4aff9")

SHEETS = {
    "l6d1": (GEN / "exec-d2edf2fd-2678-42a5-a944-7d826273b764.png", 4, 3, 7),
    "l6d2": (GEN / "exec-a1488675-2e5a-4ffa-8a0a-20cff23e5b6e.png", 3, 2, 6),
    "l6r": (GEN / "exec-a9cfb54c-81f8-4b2c-8700-c55dec499d43.png", 4, 3, 11),
    "l7d1": (GEN / "exec-3b80291c-3a23-4585-a0dd-8edada11a3e5.png", 4, 2, 8),
    "l7d2": (GEN / "exec-5645a6de-3dba-4aed-94ef-6c1690f39afa.png", 4, 2, 7),
    "l7r": (GEN / "exec-e6230b66-028e-4a0e-9e59-8a7fec827344.png", 4, 3, 10),
    "l8d1": (GEN / "exec-cdfecba7-5500-47f0-8dc0-7a9a92173bf8.png", 5, 2, 9),
    "l8d2": (GEN / "exec-47035049-5ba7-4252-bf77-ae39b05abfbe.png", 5, 2, 9),
    "l8r": (GEN / "exec-90f9f69f-2216-41d5-8326-646039e59a95.png", 4, 4, 13),
}

LESSONS = {
    6: {
        "d1": ("對話一：週末去打網球吧！", [
            "國安：今天天氣不錯，海邊的風景也很漂亮，我想去游泳，你們想去嗎？",
            "友美：我不會游泳。宜文，你會游泳嗎？",
            "宜文：我會游泳，可是游得不太好。",
            "國安：我們去跑步，怎麼樣？",
            "友美：我不喜歡跑步，我跑步跑得很慢。",
            "宜文：打網球怎麼樣？中明說妳的網球打得很好，我們一起去打吧。",
            "友美：好啊。",
        ]),
        "d2": ("對話二：週末去打網球吧！", [
            "國安：聽說這部電影很有趣，我們晚上一起去看，好不好？",
            "中明：我覺得有一點兒累，我想回家休息。",
            "國安：你不要常常在家上網、看電腦、玩手機，應該去運動。明天我有空，我們可以一起去騎腳踏車。",
            "中明：可是我只想聽音樂、睡覺。",
            "國安：後天去呢？",
            "中明：這兩天天氣有點兒冷，我們週末去，好嗎？",
        ]),
        "r": ("短文：我的興趣", [
            "我有幾個好朋友。", "我們都喜歡學中文、聽音樂、唱歌。", "中明最愛唱歌。",
            "他的中文歌唱得很好。", "平常我們都有點兒忙。", "可是週末我們常一起去運動。",
            "宜文游泳游得不錯。", "國安的籃球打得很好。", "我喜歡打網球。",
            "有時候我們也一起去看運動比賽。", "有這幾個好朋友，我真高興！",
        ]),
    },
    7: {
        "d1": ("對話一：怎麼去天美飯店？", [
            "友美：元真，我們明天幾點去找你的韓國朋友？", "元真：我們下午四點要到天美飯店，她在那裡等我們。",
            "友美：我們要怎麼去？坐捷運還是坐公車？", "元真：聽說那家飯店不遠，我想我們可以從學校走路去。",
            "友美：可是我不知道怎麼走，你知道嗎？", "元真：我也不知道。我們可以先上網看地圖。",
            "友美：啊！上課了！我們先上課吧。", "元真：好。",
        ]),
        "d2": ("對話二：坐捷運去吧！", [
            "元真：友美，妳看，天美飯店在大學路。我現在知道怎麼走了。",
            "友美：啊！天美飯店在這裡！我知道這個地方，附近有郵局跟超級市場。",
            "元真：我想走路一定沒問題。", "友美：可是我覺得那裡有點兒遠，走路去太累了。",
            "元真：妳想怎麼去？", "友美：坐捷運又方便又舒服，我們可以坐捷運。", "元真：好，我們明天坐捷運去吧。",
        ]),
        "r": ("短文：從我家坐捷運很方便", [
            "我家附近有三條捷運線。", "一條紅的、一條綠的和一條藍的。", "我平常坐紅線去學校上課。",
            "週末也坐捷運去運動、看電影。", "朋友常來找我。", "他們都覺得坐捷運來我家，又快又方便。",
            "從我家到機場也不遠。", "開車去、坐捷運去都可以。", "機場附近的風景也很漂亮。", "我常常去看風景、看飛機。",
        ]),
    },
    8: {
        "d1": ("對話一：我想買新衣服", [
            "宜文：元真，妳的這條裙子真好看，我很喜歡。", "元真：謝謝，這是我去年的生日禮物。",
            "宜文：聽說這個牌子的東西很貴，可是很多人喜歡。", "元真：是啊，因為這個牌子很有名，衣服、褲子和裙子也都很好看，所以很多人買。",
            "宜文：妳知道去哪裡買這個牌子的衣服嗎？", "元真：知道，百貨公司都有，不難找。",
            "宜文：我很想去看，可是我最近胖了五公斤，我怕衣服不好買。", "元真：妳胖了嗎？我不覺得啊，我跟妳一起去看。我也想去買今年夏天的新衣服。",
            "宜文：好，我們找時間一起去。",
        ]),
        "d2": ("對話二：這條褲子太小了", [
            "宜文：妳看，這條黃色的褲子不錯吧？", "元真：很好看。這條藍的也很漂亮，藍色是今年很流行的顏色。",
            "宜文：這兩條我都去穿穿看。", "元真：妳覺得怎麼樣？", "宜文：都太短，也太小了。",
            "元真：沒關係，我們可以下個週末再來看。對了，妳要買鞋子吧？", "宜文：是啊，我想買一雙黑色的。",
            "元真：鞋子都在一樓，我們到樓下去吧！九點了，百貨公司快要關了。", "宜文：電梯在那裡！我們現在去買。",
        ]),
        "r": ("短文：年輕人喜歡新東西", [
            "百貨公司裡有很多衣服、鞋子和皮包。", "這些東西都是最新的。", "很多年輕女生喜歡到百貨公司去。",
            "漂亮的、流行的衣服，她們都想穿穿看。", "很多年輕男生愛在書店看汽車雜誌。", "汽車很貴。",
            "他們不一定可以買新車。", "可是他們都看得很開心。", "我覺得有的舊東西很不錯。",
            "有的新東西也很有趣。", "我很喜歡看新車、新衣服。", "可是我的錢不多。", "所以我不常買。",
        ]),
    },
}

RUBRIC = {"sourceUrl": "https://doi.org/10.1080/09588221.2025.2561608",
          "easy": {"focus": 8, "narrative": 6, "plot": 6, "wordChoice": 7, "conventions": 9, "total": 36},
          "medium": {"focus": 9, "narrative": 8, "plot": 8, "wordChoice": 8, "conventions": 9, "total": 42},
          "hard": {"focus": 10, "narrative": 9, "plot": 9, "wordChoice": 9, "conventions": 9, "total": 46}}

SAFE_VOCAB = ["天氣", "風景", "漂亮", "游泳", "跑步", "網球", "電影", "有趣", "休息", "運動", "腳踏車", "音樂", "朋友", "中文", "唱歌", "週末", "飯店", "捷運", "公車", "學校", "走路", "地圖", "附近", "郵局", "超級市場", "方便", "舒服", "機場", "衣服", "褲子", "裙子", "百貨公司", "生日", "東西", "流行", "鞋子", "電梯", "錢", "年輕"]

def tier_text(line: str, level: str) -> str:
    """Book-1-only scaffolding: complexity rises through connectors/questions."""
    if level == "easy":
        return line
    end = line[-1:] if line else "。"
    body = line[:-1] if end in "。！？" else line
    if level == "medium":
        return body + "，我覺得很好。" if end != "？" else body + "，你覺得呢？"
    return body + "，所以我們可以一起去，你覺得怎麼樣？" if end != "？" else body + "，如果有空，我們一起去，好嗎？"

def prepare_images() -> None:
    from PIL import Image
    UPLOADS.mkdir(parents=True, exist_ok=True)
    for key, (source, cols, rows, count) in SHEETS.items():
        if not source.exists():
            raise FileNotFoundError(source)
        with Image.open(source) as sheet:
            w, h = sheet.size
            for i in range(count):
                x, y = i % cols, i // cols
                box = (x * w // cols, y * h // rows, (x + 1) * w // cols, (y + 1) * h // rows)
                out = UPLOADS / f"{key}-frame-{i + 1}.png"
                sheet.crop(box).save(out)

def _wrap_cjk(text: str, font, max_width: int, draw) -> list[str]:
    """Wrap Chinese text by character so every bubble stays readable."""
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]

def prepare_bubble_images() -> None:
    """Crop each grid cell cleanly and add the exact scene script in a bubble."""
    from PIL import Image, ImageDraw, ImageFont
    SPEECH_UPLOADS.mkdir(parents=True, exist_ok=True)
    font_path = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
    if not font_path.exists():
        font_path = Path(r"C:\Windows\Fonts\mingliu.ttc")
    for key, (source, cols, rows, count) in SHEETS.items():
        with Image.open(source).convert("RGB") as sheet:
            cw, ch = sheet.width // cols, sheet.height // rows
            # Find the matching lesson text from the same order used by stories().
            lesson = int(key[1])
            part = {"d1": "d1", "d2": "d2", "r": "r"}[key[2:]]
            lines = LESSONS[lesson][part][1]
            for i, script in enumerate(lines):
                x, y = i % cols, i // cols
                # A small, symmetric inset removes the generated sheet's white gutter
                # without cutting into the illustration itself.
                inset = max(8, int(min(cw, ch) * 0.025))
                scene = sheet.crop((x * cw + inset, y * ch + inset,
                                    (x + 1) * cw - inset, (y + 1) * ch - inset))
                font_size = max(26, min(42, scene.width // 18))
                font = ImageFont.truetype(str(font_path), font_size)
                probe = ImageDraw.Draw(scene)
                wrapped = _wrap_cjk(script, font, int(scene.width * 0.88), probe)
                line_gap = max(8, font_size // 5)
                line_height = font_size + line_gap
                bubble_h = max(100, line_height * len(wrapped) + 34)
                canvas = Image.new("RGB", (scene.width, scene.height + bubble_h), "#f7f5ef")
                canvas.paste(scene, (0, 0))
                draw = ImageDraw.Draw(canvas)
                pad = max(16, scene.width // 32)
                left, top = pad, scene.height + 12
                right, bottom = scene.width - pad, canvas.height - pad
                radius = max(18, pad)
                draw.rounded_rectangle((left, top, right, bottom), radius=radius,
                                       fill="#fffdf7", outline="#20252b", width=3)
                # Speech-bubble tail points toward the speaker area while staying outside text.
                tail_x = left + max(24, scene.width // 7)
                draw.polygon([(tail_x, top), (tail_x + 28, top), (tail_x - 4, top - 22)],
                             fill="#fffdf7", outline="#20252b")
                tx = left + pad
                ty = top + (bottom - top - line_height * len(wrapped)) // 2
                for line in wrapped:
                    draw.text((tx, ty), line, fill="#16191d", font=font)
                    ty += line_height
                out = SPEECH_UPLOADS / f"{key}-frame-{i + 1}.png"
                canvas.save(out)

def refresh_published_bubble_urls() -> None:
    """Replace the published materials' image URLs with the bubble-image set."""
    with urllib.request.urlopen(API, timeout=60) as response:
        current = json.load(response)
    for story in current:
        if not story.get("id", "").startswith("modern-chinese-l"):
            continue
        for index, frame in enumerate(story.get("frames", []), 1):
            key = story["id"].replace("modern-chinese-", "").replace("-dialogue-1", "d1").replace("-dialogue-2", "d2").replace("-reading", "r")
            image = f"/uploads/images/lesson-6-8-bubble/{key}-frame-{index}.png"
            frame["imageUrl"] = image
            frame["imageUrlMedium"] = image
            frame["imageUrlHard"] = image
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story['id']}: HTTP {response.status}")
        print(f"updated bubble images: {story['id']}")

def apply_dialogue_bubble_text() -> None:
    """Put the exact spoken line (without the speaker label) in each full scene."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
    if not font_path.exists():
        font_path = Path(r"C:\Windows\Fonts\mingliu.ttc")
    for lesson in (6, 7, 8):
        for part in ("d1", "d2"):
            lines = LESSONS[lesson][part][1]
            key = f"l{lesson}{part}"
            for index, full_line in enumerate(lines, 1):
                path = FULL_UPLOADS / f"{key}-{index}.png"
                with Image.open(path).convert("RGB") as image:
                    draw = ImageDraw.Draw(image)
                    spoken = full_line.split("：", 1)[1] if "：" in full_line else full_line
                    max_width = int(image.width * 0.66)
                    size = 52
                    while size > 30:
                        font = ImageFont.truetype(str(font_path), size)
                        words: list[str] = []
                        current = ""
                        for char in spoken:
                            candidate = current + char
                            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                                words.append(current)
                                current = char
                            else:
                                current = candidate
                        if current:
                            words.append(current)
                        # Keep the dialogue in the bubble body, above its tail.
                        if len(words) <= 3 and len(words) * (size + 8) <= int(image.height * 0.15):
                            break
                        size -= 2
                    if len(words) > 3:
                        # Safety fallback for the longest book turn.
                        size = 28
                        font = ImageFont.truetype(str(font_path), size)
                        words = []
                        current = ""
                        for char in spoken:
                            candidate = current + char
                            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                                words.append(current)
                                current = char
                            else:
                                current = candidate
                        if current:
                            words.append(current)
                    line_height = size + 8
                    bubble_top = int(image.height * 0.055)
                    bubble_bottom = int(image.height * 0.23)
                    # The command is intentionally repeatable: clear any prior
                    # text from the bubble interior before redrawing the exact line.
                    bubble_left = int(image.width * 0.12)
                    bubble_right = int(image.width * 0.86)
                    bubble_top = int(image.height * 0.025)
                    bubble_bottom = int(image.height * 0.225)
                    draw.rounded_rectangle((bubble_left, bubble_top, bubble_right, bubble_bottom),
                                           radius=int(image.width * 0.055), fill="#ffffff",
                                           outline="#111820", width=max(4, image.width // 260))
                    tail_x = int(image.width * 0.47)
                    draw.polygon([(tail_x, bubble_bottom - 3), (tail_x + int(image.width * 0.055), bubble_bottom - 3),
                                  (tail_x + int(image.width * 0.025), int(image.height * 0.285))],
                                 fill="#ffffff", outline="#111820")
                    text_height = len(words) * line_height
                    y = bubble_top + max(0, (bubble_bottom - bubble_top - text_height) // 2) - 3
                    for text_line in words:
                        width = draw.textbbox((0, 0), text_line, font=font)[2]
                        x = (image.width - width) // 2
                        draw.text((x, y), text_line, font=font, fill="#111820")
                        y += line_height
                    image.save(path)

def refresh_dialogue_full_urls() -> None:
    """Point only the six dialogue materials at their full-scene assets."""
    with urllib.request.urlopen(API, timeout=60) as response:
        current = json.load(response)
    for story in current:
        story_id = story.get("id", "")
        if not story_id.startswith("modern-chinese-l") or "-dialogue-" not in story_id:
            continue
        lesson = story_id.split("-l", 1)[1].split("-", 1)[0]
        part = "d1" if story_id.endswith("dialogue-1") else "d2"
        key = f"l{lesson}{part}"
        for index, frame in enumerate(story.get("frames", []), 1):
            image = f"/uploads/images/lesson-6-8-full/{key}-{index}.png"
            frame["imageUrl"] = image
            frame["imageUrlMedium"] = image
            frame["imageUrlHard"] = image
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story_id}: HTTP {response.status}")
        print(f"updated full-scene dialogue images: {story_id}")

def apply_v2_dialogue_bubble_text() -> None:
    """Add exact dialogue text inside the deliberately oversized v2 bubbles."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
    if not font_path.exists():
        font_path = Path(r"C:\Windows\Fonts\mingliu.ttc")
    for lesson in (6, 7, 8):
        for part in ("d1", "d2"):
            for index, full_line in enumerate(LESSONS[lesson][part][1], 1):
                path = FULL_V2_UPLOADS / f"l{lesson}{part}-{index}.png"
                with Image.open(path).convert("RGB") as image:
                    draw = ImageDraw.Draw(image)
                    spoken = full_line.split("：", 1)[1] if "：" in full_line else full_line
                    max_width = int(image.width * 0.80)
                    size = 54
                    while size >= 30:
                        font = ImageFont.truetype(str(font_path), size)
                        lines: list[str] = []
                        current = ""
                        for char in spoken:
                            candidate = current + char
                            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                                lines.append(current)
                                current = char
                            else:
                                current = candidate
                        if current:
                            lines.append(current)
                        line_height = size + 10
                        if len(lines) <= 3 and len(lines) * line_height <= int(image.height * 0.25):
                            break
                        size -= 2
                    line_height = size + 10
                    total_height = len(lines) * line_height
                    top = int(image.height * 0.045)
                    bottom = int(image.height * 0.345)
                    y = top + max(0, (bottom - top - total_height) // 2) - 3
                    for line in lines:
                        width = draw.textbbox((0, 0), line, font=font)[2]
                        draw.text(((image.width - width) // 2, y), line, font=font, fill="#111820")
                        y += line_height
                    image.save(path)

def refresh_v2_dialogue_full_urls() -> None:
    """Publish the v2 full-scene image URLs for dialogues only."""
    with urllib.request.urlopen(API, timeout=60) as response:
        current = json.load(response)
    for story in current:
        story_id = story.get("id", "")
        if not story_id.startswith("modern-chinese-l") or "-dialogue-" not in story_id:
            continue
        lesson = story_id.split("-l", 1)[1].split("-", 1)[0]
        part = "d1" if story_id.endswith("dialogue-1") else "d2"
        key = f"l{lesson}{part}"
        for index, frame in enumerate(story.get("frames", []), 1):
            image = f"/uploads/images/lesson-6-8-full-v2/{key}-{index}.png"
            frame["imageUrl"] = image
            frame["imageUrlMedium"] = image
            frame["imageUrlHard"] = image
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story_id}: HTTP {response.status}")
        print(f"published v2 full-scene images: {story_id}")

def apply_v3_dialogue_bubbles() -> None:
    """Create a compact bubble sized to exactly one speaker turn per image."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
    if not font_path.exists():
        font_path = Path(r"C:\Windows\Fonts\mingliu.ttc")
    FULL_V3_FINAL_UPLOADS.mkdir(parents=True, exist_ok=True)
    for lesson in (6, 7, 8):
        for part in ("d1", "d2"):
            for index, full_line in enumerate(LESSONS[lesson][part][1], 1):
                source = FULL_V3_UPLOADS / f"l{lesson}{part}-{index}.png"
                target = FULL_V3_FINAL_UPLOADS / source.name
                with Image.open(source).convert("RGB") as image:
                    draw = ImageDraw.Draw(image)
                    spoken = full_line.split("：", 1)[1] if "：" in full_line else full_line
                    max_text_width = int(image.width * 0.72)
                    size = 48
                    while size >= 26:
                        font = ImageFont.truetype(str(font_path), size)
                        lines: list[str] = []
                        current = ""
                        for char in spoken:
                            candidate = current + char
                            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_text_width:
                                lines.append(current)
                                current = char
                            else:
                                current = candidate
                        if current:
                            lines.append(current)
                        line_height = size + 8
                        if len(lines) <= 3 and len(lines) * line_height <= int(image.height * 0.16):
                            break
                        size -= 2
                    line_height = size + 8
                    max_line_width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
                    pad_x = max(34, size)
                    pad_y = max(24, size // 2)
                    bubble_width = min(int(image.width * 0.84), max(300, max_line_width + pad_x * 2))
                    bubble_height = len(lines) * line_height + pad_y * 2
                    left = (image.width - bubble_width) // 2
                    top = max(16, int(image.height * 0.025))
                    right = left + bubble_width
                    bottom = top + bubble_height
                    radius = max(24, size)
                    draw.rounded_rectangle((left, top, right, bottom), radius=radius,
                                           fill="#fffefa", outline="#151a20", width=max(4, size // 10))
                    tail_x = left + bubble_width // 2
                    tail_w = max(34, size)
                    draw.polygon([(tail_x - tail_w // 2, bottom - 3),
                                  (tail_x + tail_w // 2, bottom - 3),
                                  (tail_x, bottom + max(18, size // 2))],
                                 fill="#fffefa", outline="#151a20")
                    text_height = len(lines) * line_height
                    y = top + (bubble_height - text_height) // 2 - 2
                    for line in lines:
                        width = draw.textbbox((0, 0), line, font=font)[2]
                        draw.text(((image.width - width) // 2, y), line, font=font, fill="#111820")
                        y += line_height
                    image.save(target)

def refresh_v3_dialogue_urls() -> None:
    """Publish the compact-bubble v3 assets for dialogues only."""
    with urllib.request.urlopen(API, timeout=60) as response:
        current = json.load(response)
    for story in current:
        story_id = story.get("id", "")
        if not story_id.startswith("modern-chinese-l") or "-dialogue-" not in story_id:
            continue
        lesson = story_id.split("-l", 1)[1].split("-", 1)[0]
        part = "d1" if story_id.endswith("dialogue-1") else "d2"
        key = f"l{lesson}{part}"
        for index, frame in enumerate(story.get("frames", []), 1):
            image = f"/uploads/images/lesson-6-8-full-v3-final/{key}-{index}.png"
            frame["imageUrl"] = image
            frame["imageUrlMedium"] = image
            frame["imageUrlHard"] = image
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story_id}: HTTP {response.status}")
        print(f"published compact-bubble v3: {story_id}")

def frame_payload(key: str, lines: list[str]) -> list[dict]:
    frames = []
    for i, line in enumerate(lines, 1):
        words = [w for w in SAFE_VOCAB if w in line][:4]
        image = f"/uploads/images/lesson-6-8/{key}-frame-{i}.png"
        frames.append({"imageUrl": image, "imageUrlMedium": image, "imageUrlHard": image,
                       "prompt": "請看圖，說出這一句。", "promptMedium": "請用完整句子說明。", "promptHard": "請加上原因或感受。",
                       "vocabulary": ",".join(words), "vocabularyMedium": ",".join(words), "vocabularyHard": ",".join(words),
                       "suggestedAnswer": tier_text(line, "easy"), "suggestedAnswerMedium": tier_text(line, "medium"), "suggestedAnswerHard": tier_text(line, "hard")})
    return frames

def stories() -> list[dict]:
    result = []
    for lesson, parts in LESSONS.items():
        for order, key in enumerate(("d1", "d2", "r"), 1):
            title, lines = parts[key]
            slug = f"modern-chinese-l{lesson}-{'dialogue-1' if key == 'd1' else 'dialogue-2' if key == 'd2' else 'reading'}"
            image_key = f"l{lesson}{key}"
            result.append({"id": slug, "title": f"第{lesson}課 {title}",
                           "learningGoal": "Modern Chinese Book 1：依課文圖片練習中文口說。",
                           "frames": frame_payload(image_key, lines), "published": True, "linear": True,
                           "firstFrameIsExample": False, "lessonNumber": lesson, "lessonSubOrder": order,
                           "narrativeMode": "story", "rubricScores": RUBRIC})
    return result

def seed() -> None:
    for story in stories():
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story['id']}: HTTP {response.status}")
        print(f"published {story['id']} ({len(story['frames'])} frames)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-images", action="store_true")
    parser.add_argument("--prepare-bubble-images", action="store_true")
    parser.add_argument("--refresh-bubble-urls", action="store_true")
    parser.add_argument("--apply-dialogue-bubble-text", action="store_true")
    parser.add_argument("--refresh-dialogue-full-urls", action="store_true")
    parser.add_argument("--apply-v2-dialogue-bubble-text", action="store_true")
    parser.add_argument("--refresh-v2-dialogue-full-urls", action="store_true")
    parser.add_argument("--apply-v3-dialogue-bubbles", action="store_true")
    parser.add_argument("--refresh-v3-dialogue-urls", action="store_true")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    if args.prepare_images:
        prepare_images()
    if args.prepare_bubble_images:
        prepare_bubble_images()
    if args.refresh_bubble_urls:
        refresh_published_bubble_urls()
    if args.apply_dialogue_bubble_text:
        apply_dialogue_bubble_text()
    if args.refresh_dialogue_full_urls:
        refresh_dialogue_full_urls()
    if args.apply_v2_dialogue_bubble_text:
        apply_v2_dialogue_bubble_text()
    if args.refresh_v2_dialogue_full_urls:
        refresh_v2_dialogue_full_urls()
    if args.apply_v3_dialogue_bubbles:
        apply_v3_dialogue_bubbles()
    if args.refresh_v3_dialogue_urls:
        refresh_v3_dialogue_urls()
    if args.seed:
        seed()
