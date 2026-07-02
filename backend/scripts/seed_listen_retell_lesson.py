"""
Seed the "我的房間" Listen & Retell lesson: students listen to a short
description of a room (TTS, since no audio was uploaded) and then retell it
in their own words from a single picture.

Usage:
    python seed_listen_retell_lesson.py [--overwrite]
"""

import argparse
import json
import os
import sqlite3

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)

STORY_ID = "lesson-wo-de-fangjian"

LISTEN_SCRIPT = (
    "的房間裡有一張桌子、一張床跟一張沙發。沙發前"
    "面有一台很新的電視機,可是我不常看電視,我最喜歡在"
    "沙發上看書。我的書很多,有中文書,也有英文書。我房"
    "間的窗戶很大,我的貓喜歡在窗戶旁邊曬太陽。"
)

STORY = {
    "id": STORY_ID,
    "title": "我的房間",
    "learning_goal": "Students listen to a short description of a room, then retell it in their own words from the picture.",
    "level": "Beginner speaking",
    "frames": [
        {
            "imageUrl": "",
            "prompt": "聽完錄音後，用自己的話描述這個房間。",
            "vocabulary": "房間,桌子,床,沙發,電視機,看書,書,中文書,英文書,窗戶,貓,曬太陽",
            "listenScript": LISTEN_SCRIPT,
        },
    ],
    "published": 1,
    "narrative_mode": "listen_retell",
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
            (id, title, learning_goal, level, frames, published, narrative_mode)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            STORY["id"],
            STORY["title"],
            STORY["learning_goal"],
            STORY["level"],
            json.dumps(STORY["frames"], ensure_ascii=False),
            STORY["published"],
            STORY["narrative_mode"],
        ),
    )
    conn.commit()
    conn.close()
    print(f"Seeded lesson '{STORY['title']}' (id={STORY_ID}).")


if __name__ == "__main__":
    main()
