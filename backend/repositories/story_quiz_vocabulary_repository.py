"""Persistence boundary for the quiz-vocabulary bank (``vocab_assessment``)
on ``custom_stories``.

Pure CRUD only - no HTTPException, no business decisions. Every function
takes an already-open connection so the caller controls the transaction
boundary.
"""
from typing import Optional

from psycopg.types.json import Jsonb


def find_story_for_update(db, story_id: str) -> Optional[dict]:
    return db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()


def write_quiz_bank(db, story_id: str, assessment: list[dict]) -> Optional[dict]:
    db.execute(
        "UPDATE custom_stories SET vocab_assessment = %s::jsonb WHERE id = %s",
        (Jsonb(assessment), story_id),
    )
    return db.execute("SELECT * FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
