"""Persistence boundary for the per-frame quiz-material pools (exclusions,
pending approvals, and candidate distractors/cloze/synonym pools) stored on
``custom_stories.frames``.

``load_frames`` raises ``fastapi.HTTPException`` directly (rather than
returning ``None``) because it is consumed directly - by name - as a
request-handling helper from multiple routers (story_quiz_materials,
story_quiz_pools), not as a pure persistence function; this mirrors its
pre-refactor behavior exactly and keeps those other routers' 404 handling
unchanged.
"""
from typing import Optional

from fastapi import HTTPException
from psycopg.types.json import Jsonb


def load_frames(db, story_id: str) -> list:
    row = db.execute(
        "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Story not found.")
    return row["frames"] or []


def write_frame_field(db, story_id: str, frame_index: int, field: str, value_json: str) -> None:
    db.execute(
        "UPDATE custom_stories "
        "SET frames = jsonb_set(frames, ARRAY[%s, %s], to_jsonb(%s::text), true) "
        "WHERE id = %s",
        (str(frame_index), field, value_json, story_id),
    )


def set_quiz_exclusions(
    db, story_id: str, exclusions: list[dict], material_snapshot: Optional[dict]
) -> Optional[dict]:
    return db.execute(
        "UPDATE custom_stories SET quiz_exclusions = %s, "
        "quiz_material_snapshot = COALESCE(%s, quiz_material_snapshot) "
        "WHERE id = %s RETURNING id",
        (
            Jsonb(exclusions),
            Jsonb(material_snapshot) if material_snapshot is not None else None,
            story_id,
        ),
    ).fetchone()


def set_quiz_pending_approvals(db, story_id: str, level: str, approvals: list[dict]) -> Optional[dict]:
    return db.execute(
        "UPDATE custom_stories SET quiz_pending_approvals = "
        "jsonb_set(COALESCE(quiz_pending_approvals, '{}'::jsonb), ARRAY[%s], %s) "
        "WHERE id = %s RETURNING id",
        (level, Jsonb(approvals), story_id),
    ).fetchone()


def invalidate_translation_word_from_approved_snapshot(db, word: str, story_id: str) -> None:
    db.execute(
        "UPDATE custom_stories SET quiz_approved_snapshot = "
        "COALESCE((SELECT jsonb_object_agg(k, COALESCE((SELECT jsonb_agg(item) "
        "FROM jsonb_array_elements(v) AS item WHERE item->>'word' <> %s), '[]'::jsonb)) "
        "FROM jsonb_each(quiz_approved_snapshot) AS entries(k, v)), '{}'::jsonb) "
        "WHERE id = %s",
        (word, story_id),
    )
