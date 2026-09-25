"""Persistence boundary for the quiz-approval (``quiz_approved_snapshot``)
publish flow on ``custom_stories``."""
from typing import Optional

from psycopg.types.json import Jsonb


def story_exists(db, story_id: str) -> bool:
    return db.execute("SELECT 1 FROM custom_stories WHERE id = %s", (story_id,)).fetchone() is not None


def set_approved_snapshot_for_level(db, story_id: str, level: str, material: list[dict]) -> Optional[dict]:
    return db.execute(
        "UPDATE custom_stories SET quiz_approved_snapshot = "
        "jsonb_set(COALESCE(quiz_approved_snapshot, '{}'::jsonb), ARRAY[%s], %s) "
        "WHERE id = %s RETURNING id",
        (level, Jsonb(material), story_id),
    ).fetchone()
