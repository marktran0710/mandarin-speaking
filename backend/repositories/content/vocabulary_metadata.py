"""Persistence boundary for story-wide/per-frame/quiz-assessment vocabulary
metadata edits on ``custom_stories``.

Pure CRUD only - no HTTPException, no business decisions. Every function
takes an already-open connection so the caller controls the transaction
boundary.
"""
from typing import Optional

from psycopg.types.json import Jsonb


def find_story_for_update(db, story_id: str) -> Optional[dict]:
    return db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()


def find_story(db, story_id: str) -> Optional[dict]:
    return db.execute("SELECT * FROM custom_stories WHERE id = %s", (story_id,)).fetchone()


def set_vocab_assessment(db, story_id: str, assessment: list) -> None:
    db.execute(
        "UPDATE custom_stories SET vocab_assessment = %s::jsonb WHERE id = %s",
        (Jsonb(assessment), story_id),
    )


def set_story_vocabulary_field(db, story_id: str, field: str, value: str) -> None:
    db.execute(
        "UPDATE custom_stories SET story_vocabulary = jsonb_set("
        "COALESCE(story_vocabulary, '{}'::jsonb), ARRAY['easy', %s], "
        "to_jsonb(%s::text), true) WHERE id = %s",
        (field, value, story_id),
    )


def set_frame_field(db, story_id: str, frame_index: int, field: str, value: str) -> None:
    db.execute(
        "UPDATE custom_stories SET frames = jsonb_set(frames, ARRAY[%s, %s], "
        "to_jsonb(%s::text), true) WHERE id = %s",
        (str(frame_index), field, value, story_id),
    )
