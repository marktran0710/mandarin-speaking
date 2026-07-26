"""
Seed the "VV看 — 大家來推薦" lesson: students use the reduplicated-verb
pattern V+V+看 ("try V-ing and see") to recommend something to a friend,
e.g. 我覺得這種巧克力很好吃，你要不要吃吃看？

Modeled on a classroom worksheet with one worked example (chocolate) and
five picture prompts (drink, MRT, jacket, bicycle, music) that students
fill in themselves — kept here as five practice scenes.

Run this after `python -m alembic upgrade head` has created the
custom_stories table (published/linear/lesson_number columns included).

Usage:
    python seed_vv_kan_lesson.py [--overwrite]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402

STORY_ID = "lesson-vv-kan"
GRAMMAR_PATTERN_BASE = "VV看 — 我覺得...很...，你要不要 VV看？ (try V-ing and see)"

STORY = {
    "id": STORY_ID,
    "title": "VV看 — 大家來推薦",
    "learning_goal": (
        "Students use the reduplicated-verb pattern V+V+看 to recommend "
        "something to a friend, e.g. 我覺得這種巧克力很好吃，你要不要吃吃看？"
    ),
    "level": "Beginner speaking",
    "lesson_number": 5,
    "frames": [
        {
            "imageUrl": "",
            "prompt": (
                "看圖，老師示範：「我覺得這種巧克力很好吃，你要不要吃吃看？」"
                "(Model example: I think this chocolate is delicious, do you want to try it?)"
            ),
            "vocabulary": "我,你,覺得,這種,巧克力,很,好吃,要不要,吃吃看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "好吃", "要不要", "吃吃看"]},
                {"name": "Object", "words": ["這種", "巧克力"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 吃 → 吃吃看",
        },
        {
            "imageUrl": "",
            "prompt": (
                "你覺得這杯飲料好喝嗎？請用「VV看」的句型推薦給朋友。"
                "(Recommend this drink to a friend using VV看.)"
            ),
            "vocabulary": "我,你,覺得,這杯,飲料,很,好喝,要不要,喝喝看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "好喝", "要不要", "喝喝看"]},
                {"name": "Object", "words": ["這杯", "飲料"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 喝 → 喝喝看",
        },
        {
            "imageUrl": "",
            "prompt": (
                "你覺得搭捷運方便嗎？請推薦朋友坐坐看。"
                "(Recommend riding the MRT to a friend using VV看.)"
            ),
            "vocabulary": "我,你,覺得,搭,捷運,很,方便,要不要,坐坐看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "方便", "要不要", "坐坐看"]},
                {"name": "Object", "words": ["搭", "捷運"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 坐 → 坐坐看",
        },
        {
            "imageUrl": "",
            "prompt": (
                "你覺得這件外套好看嗎？請推薦朋友穿穿看。"
                "(Recommend this jacket to a friend using VV看.)"
            ),
            "vocabulary": "我,你,覺得,這件,外套,很,好看,要不要,穿穿看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "好看", "要不要", "穿穿看"]},
                {"name": "Object", "words": ["這件", "外套"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 穿 → 穿穿看",
        },
        {
            "imageUrl": "",
            "prompt": (
                "你覺得騎這台腳踏車好玩嗎？請推薦朋友騎騎看。"
                "(Recommend riding this bicycle to a friend using VV看.)"
            ),
            "vocabulary": "我,你,覺得,這台,腳踏車,很,好玩,要不要,騎騎看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "好玩", "要不要", "騎騎看"]},
                {"name": "Object", "words": ["這台", "腳踏車"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 騎 → 騎騎看",
        },
        {
            "imageUrl": "",
            "prompt": (
                "你覺得這首歌好聽嗎？請推薦朋友聽聽看。"
                "(Recommend this song to a friend using VV看.)"
            ),
            "vocabulary": "我,你,覺得,這首,歌,很,好聽,要不要,聽聽看",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你"]},
                {"name": "Verb", "words": ["覺得", "好聽", "要不要", "聽聽看"]},
                {"name": "Object", "words": ["這首", "歌"]},
            ],
            "grammarPattern": GRAMMAR_PATTERN_BASE + " ｜ 聽 → 聽聽看",
        },
    ],
    "published": 1,
    "linear": 1,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="Replace the lesson if it already exists")
    args = parser.parse_args()

    with connect_db() as db:
        existing = db.execute("SELECT id FROM custom_stories WHERE id = %s", (STORY_ID,)).fetchone()
        if existing and not args.overwrite:
            print(f"Lesson '{STORY_ID}' already exists. Use --overwrite to replace it.")
            return

        db.execute(
            """
            INSERT INTO custom_stories
                (id, title, learning_goal, frames, published, linear, lesson_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                learning_goal = EXCLUDED.learning_goal,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published,
                linear = EXCLUDED.linear,
                lesson_number = EXCLUDED.lesson_number
            """,
            (
                STORY["id"],
                STORY["title"],
                STORY["learning_goal"],
                Jsonb(STORY["frames"]),
                bool(STORY["published"]),
                bool(STORY["linear"]),
                STORY["lesson_number"],
            ),
        )
    print(f"Seeded lesson '{STORY['title']}' (id={STORY_ID}).")


if __name__ == "__main__":
    main()
