"""
Seed the "你做什麼？" grammar lesson (S + Vaux + V(O), e.g. 我要喝茶) as a
published custom story so it shows up for students immediately.

Usage:
    python seed_grammar_lesson.py [--overwrite]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402

STORY_ID = "lesson-ni-zuo-shenme"

STORY = {
    "id": STORY_ID,
    "title": "你做什麼？",
    "level": "Beginner speaking",
    "frames": [
        {
            "imageUrl": "",
            "prompt": "你做什麼？",
            "vocabulary": "我,你,他,她,要,想,喝,吃,看,做,買,去,茶,水,飯,書,電影,什麼",
            "vocabularyGroups": [
                {"name": "Subject", "words": ["我", "你", "他", "她"]},
                {"name": "Verb", "words": ["要", "想", "喝", "吃", "看", "做", "買", "去"]},
                {"name": "Object", "words": ["茶", "水", "飯", "書", "電影", "什麼"]},
            ],
            "grammarPattern": "S + Vaux + V(O) — 我要喝茶",
        },
    ],
    "published": 1,
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
                (id, title, frames, published)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                frames = EXCLUDED.frames,
                published = EXCLUDED.published
            """,
            (
                STORY["id"],
                STORY["title"],
                Jsonb(STORY["frames"]),
                bool(STORY["published"]),
            ),
        )
    print(f"Seeded lesson '{STORY['title']}' (id={STORY_ID}).")


if __name__ == "__main__":
    main()
