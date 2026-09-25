"""Persistence boundary for ``custom_stories`` CRUD.

Pure CRUD only - no HTTPException, no business decisions. Every function
takes an already-open connection so the caller controls the transaction
boundary.
"""
from typing import Optional

from psycopg.types.json import Jsonb


def list_stories(db, *, published_only: bool, limit: int, skip: int) -> list[dict]:
    visibility = "WHERE published = TRUE" if published_only else ""
    return db.execute(
        f"SELECT * FROM custom_stories {visibility} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (limit, skip),
    ).fetchall()


def upsert_story(
    db,
    *,
    id: str,
    title: str,
    frames: list,
    published: bool,
    lesson_number,
    lesson_sub_order,
    rubric_scores,
    story_vocabulary,
    story_phrases,
    vocab_assessment,
    conversation_turns,
    assessment_update_clause: str,
) -> None:
    db.execute(
        f"""
        INSERT INTO custom_stories (
            id, title, frames, published,
            lesson_number, lesson_sub_order, rubric_scores,
            story_vocabulary, story_phrases, vocab_assessment,
            conversation_turns
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            frames = EXCLUDED.frames,
            published = EXCLUDED.published,
            lesson_number = EXCLUDED.lesson_number,
            lesson_sub_order = EXCLUDED.lesson_sub_order,
            rubric_scores = EXCLUDED.rubric_scores,
            story_vocabulary = EXCLUDED.story_vocabulary,
            story_phrases = EXCLUDED.story_phrases,
            conversation_turns = EXCLUDED.conversation_turns,
            {assessment_update_clause}
        """,
        (
            id,
            title,
            Jsonb(frames),
            published,
            lesson_number,
            lesson_sub_order,
            Jsonb(rubric_scores) if rubric_scores is not None else None,
            Jsonb(story_vocabulary) if story_vocabulary is not None else None,
            Jsonb(story_phrases) if story_phrases is not None else None,
            Jsonb(vocab_assessment) if vocab_assessment is not None else None,
            Jsonb(conversation_turns) if conversation_turns is not None else None,
        ),
    )


def find_story_frames_row(db, story_id: str) -> Optional[dict]:
    """Raw media-bearing story columns for delete cleanup."""
    return db.execute(
        "SELECT frames, conversation_turns FROM custom_stories WHERE id = %s",
        (story_id,),
    ).fetchone()


def delete_story(db, story_id: str) -> None:
    db.execute("DELETE FROM custom_stories WHERE id = %s", (story_id,))
