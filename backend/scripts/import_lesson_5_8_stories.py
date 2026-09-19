"""One-off import of the 12 lesson 5-8 book-mode stories from their raw
create-story output (dialogue .txt + a single 3x3-style comic-grid PNG per
story) into the app's custom_stories frame format.

This is exactly the conversion the project's own history says "always
needed manual re-authoring, never a direct import" (dialogue-comic grid
output vs. one-scene-image-per-frame). It is attempted here anyway, at the
user's explicit request accepting that risk, by:
  - parsing only the EASY (A1) tier block of each dialogue .txt (book mode's
    easy tier is the textbook's own dialogue, verbatim);
  - cropping each story's single comic-grid PNG into one image per turn,
    using each story's own row/col grid (read from its -images.txt header,
    not assumed uniform 3x3 - some stories are 2x2, 1x3, etc.);
  - posting each story to the already-running dev backend's real
    /api/custom-stories endpoint (the same route the teacher's Story
    Builder uses), so persistence/validation is identical to a manual save.

Imported stories are created with published=False so a teacher reviews them
in the Story Builder before they go live to students.

Usage (with the dev backend already running on :8000):
    python -m scripts.import_lesson_5_8_stories
"""

from __future__ import annotations

import base64
import re
import subprocess
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

BACKEND_URL = "http://127.0.0.1:8000"
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class StorySpec:
    commit: str
    lesson: int
    slug: str
    sub_order: int
    cols: int
    rows: int


STORIES = [
    StorySpec("3ee60b5", 5, "afternoon-tea-invitation", 1, 3, 3),
    StorySpec("3ee60b5", 5, "looking-for-my-wallet", 2, 3, 3),
    StorySpec("3ee60b5", 5, "my-room", 3, 2, 2),
    StorySpec("0379030", 6, "lets-play-tennis", 1, 3, 3),
    StorySpec("0379030", 6, "movie-or-bike-ride", 2, 2, 3),
    StorySpec("0379030", 6, "my-hobbies", 3, 2, 2),
    StorySpec("0379030", 7, "how-do-we-get-there", 1, 3, 3),
    StorySpec("0379030", 7, "lets-take-the-mrt", 2, 3, 3),
    StorySpec("0379030", 7, "mrt-from-my-house", 3, 3, 2),
    StorySpec("3ee60b5", 8, "liking-a-new-brand", 1, 3, 3),
    StorySpec("3ee60b5", 8, "trying-on-new-clothes", 2, 3, 3),
    StorySpec("3ee60b5", 8, "young-people-like-new-things", 3, 1, 3),
]


def git_show(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    )
    return result.stdout


TITLE_RE = re.compile(r"^《(?P<zh>[^》]+)》(?P<en>.+)$")
# The scene note after the dash is English ("scene note: ...") in some
# stories and plain Chinese description in others - match either, up to the
# closing bracket, rather than requiring the "scene note:" label.
TURN_RE = re.compile(
    r"\[Turn (?P<num>\d+)[^\]\n]*\]\n"
    r"(?P<speaker>[^：\n]+)：(?P<zh>[^\n]+)\n"
    r"(?P<pinyin>[^\n]+)\n"
    r"(?P<en>[^\n]+)",
)
VOCAB_LINE_RE = re.compile(r"^\d+\s+([^\s]+)\s+.+$")


def parse_dialogue(text: str) -> dict:
    lines = text.splitlines()
    title_match = TITLE_RE.match(lines[0].strip())
    title_zh, title_en = (title_match.group("zh"), title_match.group("en")) if title_match else (lines[0], lines[0])

    easy_start = text.index("EASY (A1)")
    medium_marker = text.find("MEDIUM (A1-A2)")
    easy_block = text[easy_start:medium_marker if medium_marker != -1 else None]

    turns = []
    for match in TURN_RE.finditer(easy_block):
        turns.append({
            "num": int(match.group("num")),
            "speaker": match.group("speaker").strip(),
            "zh": match.group("zh").strip(),
            "pinyin": match.group("pinyin").strip(),
            "en": match.group("en").strip(),
        })
    turns.sort(key=lambda t: t["num"])

    vocab_start = easy_block.find("\nVocabulary\n")
    phrases_start = easy_block.find("\nKey Phrases\n")
    vocab_words, vocab_pinyin, vocab_pos, vocab_translation = [], [], [], []
    if vocab_start != -1:
        vocab_block = easy_block[vocab_start:phrases_start if phrases_start != -1 else None]
        for line in vocab_block.splitlines()[2:]:
            parts = line.split(None, 4)
            if len(parts) < 5 or not parts[0].isdigit():
                continue
            _, word, pinyin, pos, translation = parts
            vocab_words.append(word)
            vocab_pinyin.append(pinyin)
            vocab_pos.append(pos)
            vocab_translation.append(translation)

    phrases, phrases_translation = [], []
    if phrases_start != -1:
        phrases_block = easy_block[phrases_start:]
        for line in phrases_block.splitlines()[2:]:
            cols = [c.strip() for c in line.split("—")]
            if len(cols) < 3 or not re.match(r"^\d+\s", cols[0]):
                continue
            pattern = re.sub(r"^\d+\s+", "", cols[0])
            phrases.append(f"{pattern} ({cols[1]})")
            phrases_translation.append(cols[2])

    return {
        "title": f"{title_zh} {title_en}",
        "turns": turns,
        "vocabulary": ", ".join(vocab_words),
        "vocabulary_pinyin": ", ".join(vocab_pinyin),
        "vocabulary_pos": ", ".join(vocab_pos),
        "vocabulary_translation": ", ".join(vocab_translation),
        "phrases": "; ".join(phrases),
        "phrases_translation": "; ".join(phrases_translation),
    }


def crop_panels(png_bytes: bytes, cols: int, rows: int, count: int) -> list[str]:
    im = Image.open(BytesIO(png_bytes)).convert("RGB")
    w, h = im.size
    pw, ph = w // cols, h // rows
    data_urls = []
    n = 0
    for row in range(rows):
        for col in range(cols):
            if n >= count:
                break
            x0, y0 = col * pw, row * ph
            x1 = (col + 1) * pw if col < cols - 1 else w
            y1 = (row + 1) * ph if row < rows - 1 else h
            panel = im.crop((x0, y0, x1, y1))
            buf = BytesIO()
            panel.save(buf, format="JPEG", quality=85)
            data_urls.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"))
            n += 1
        if n >= count:
            break
    return data_urls


def build_story_payload(spec: StorySpec, dialogue: dict, panel_urls: list[str]) -> dict:
    frames = []
    for turn, image_url in zip(dialogue["turns"], panel_urls):
        frames.append({
            "imageUrl": image_url,
            "prompt": turn["en"],
            "vocabulary": "",
            "suggestedAnswer": turn["zh"],
        })
    return {
        "id": f"lesson-{spec.lesson}-{spec.slug}",
        "title": dialogue["title"],
        "frames": frames,
        "storyVocabulary": {"easy": {
            "vocabulary": dialogue["vocabulary"],
            "vocabularyPinyin": dialogue["vocabulary_pinyin"],
            "vocabularyPos": dialogue["vocabulary_pos"],
            "vocabularyTranslation": dialogue["vocabulary_translation"],
        }},
        "storyPhrases": {"easy": {
            "phrases": dialogue["phrases"],
            "phrasesTranslation": dialogue["phrases_translation"],
        }},
        "published": False,
        "lessonNumber": spec.lesson,
        "lessonSubOrder": spec.sub_order,
    }


def login_teacher_session() -> requests.Session:
    """Uses the local-only demo teacher account (scripts.seed_demo_accounts)
    so this import authenticates the same way the Story Builder does,
    instead of writing frames straight into the database."""
    session = requests.Session()
    response = session.post(
        f"{BACKEND_URL}/api/teachers/login",
        json={"name": "Teacher Demo", "password": "123456"},
        timeout=30,
    )
    response.raise_for_status()
    session.headers["X-Client-Role"] = "teacher"
    return session


def main() -> None:
    session = login_teacher_session()
    results = []
    for spec in STORIES:
        text_bytes = git_show(spec.commit, f"stories/lesson-{spec.lesson:02d}/{spec.slug}.txt")
        png_bytes = git_show(spec.commit, f"stories/lesson-{spec.lesson:02d}/images/{spec.slug}-easy.png")
        dialogue = parse_dialogue(text_bytes.decode("utf-8"))
        if not dialogue["turns"]:
            results.append((spec, "FAILED: no turns parsed"))
            continue
        panel_urls = crop_panels(png_bytes, spec.cols, spec.rows, len(dialogue["turns"]))
        payload = build_story_payload(spec, dialogue, panel_urls)
        response = session.post(f"{BACKEND_URL}/api/custom-stories", json=payload, timeout=60)
        if response.ok:
            results.append((spec, f"OK: {len(dialogue['turns'])} frames"))
        else:
            results.append((spec, f"FAILED: {response.status_code} {response.text[:300]}"))

    print("\n=== Import results ===")
    for spec, status in results:
        print(f"lesson-{spec.lesson}/{spec.slug}: {status}")


if __name__ == "__main__":
    main()
