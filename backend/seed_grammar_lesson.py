"""
Seed the "你做什麼？" grammar lesson (S + Vaux + V(O), e.g. 我要喝茶) as a
published custom story so it shows up for students immediately.

Usage:
    python seed_grammar_lesson.py [--overwrite]
"""

import argparse
import json
import os
import sqlite3

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)

STORY_ID = "lesson-ni-zuo-shenme"

STORY = {
    "id": STORY_ID,
    "title": "你做什麼？",
    "learning_goal": "Students use the pattern S + Vaux + V(O) to say what they want to do, e.g. 我要喝茶。",
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


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_stories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            learning_goal TEXT NOT NULL,
            level TEXT NOT NULL,
            frames TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="Replace the lesson if it already exists")
    args = parser.parse_args()

    conn = sqlite3.connect(DATABASE_PATH)
    init_db(conn)

    existing = conn.execute("SELECT id FROM custom_stories WHERE id = ?", (STORY_ID,)).fetchone()
    if existing and not args.overwrite:
        print(f"Lesson '{STORY_ID}' already exists. Use --overwrite to replace it.")
        conn.close()
        return

    conn.execute(
        """
        INSERT OR REPLACE INTO custom_stories
            (id, title, learning_goal, level, frames, published)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            STORY["id"],
            STORY["title"],
            STORY["learning_goal"],
            STORY["level"],
            json.dumps(STORY["frames"], ensure_ascii=False),
            STORY["published"],
        ),
    )
    conn.commit()
    conn.close()
    print(f"Seeded lesson '{STORY['title']}' (id={STORY_ID}).")


if __name__ == "__main__":
    main()
