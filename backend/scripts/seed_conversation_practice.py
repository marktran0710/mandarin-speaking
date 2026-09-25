"""Backfill canonical Conversation Practice turns for the lesson 5-8 stories.

The book-mode importer originally stored only scene frames. This development
seed derives alternating practice exchanges from each lesson's EASY dialogue
and keeps the authored story row, publication state, and media untouched.

Usage (from ``backend``):
    python -m scripts.seed_conversation_practice

By default, existing conversation content is preserved. Pass ``--overwrite``
only when intentionally replacing the conversation field for these known
lesson story IDs.
"""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg.types.json import Jsonb

from scripts.import_lesson_5_8_stories import (
    STORIES,
    build_conversation_turns,
    git_show,
    parse_dialogue,
)


DEFAULT_DATABASE_URL = "postgresql://mandarin:mandarin@127.0.0.1:5433/mandarin"


def main() -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise SystemExit("Development conversation seed is disabled in production.")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing conversation content for the 12 lesson stories.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL connection URL.",
    )
    args = parser.parse_args()

    updated = 0
    skipped_existing = 0
    missing_stories = 0
    with psycopg.connect(args.database_url) as db:
        for spec in STORIES:
            story_id = f"lesson-{spec.lesson}-{spec.slug}"
            dialogue = parse_dialogue(
                git_show(
                    spec.commit,
                    f"stories/lesson-{spec.lesson:02d}/{spec.slug}.txt",
                ).decode("utf-8")
            )
            turns = build_conversation_turns(story_id, dialogue)
            if not turns:
                raise SystemExit(f"No conversation turns generated for {story_id}")

            content_guard = "" if args.overwrite else "AND (conversation_turns IS NULL OR conversation_turns = '[]'::jsonb)"
            row = db.execute(
                f"""
                UPDATE custom_stories
                SET conversation_turns = %s
                WHERE id = %s {content_guard}
                RETURNING id
                """,
                (Jsonb(turns), story_id),
            ).fetchone()
            if row:
                updated += 1
            else:
                exists = db.execute(
                    "SELECT 1 FROM custom_stories WHERE id = %s",
                    (story_id,),
                ).fetchone()
                if exists:
                    skipped_existing += 1
                else:
                    missing_stories += 1

    print(
        "Conversation seed complete: "
        f"updated={updated}, skipped_existing={skipped_existing}, "
        f"missing_stories={missing_stories}"
    )


if __name__ == "__main__":
    main()
