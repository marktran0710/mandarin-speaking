import json

from fastapi import APIRouter, HTTPException, Query

from database import connect_db, row_to_custom_story
import main
from main import (
    CustomStoryRequest,
    VocabularyDistractorsUpdateRequest,
)

router = APIRouter()


@router.get("/api/custom-stories")
async def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@router.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = main.persist_story_frame_images(story.id, frames)
    stored_frames = main.persist_story_frame_audio(story.id, stored_frames)
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO custom_stories (
                id, title, learning_goal, level, frames, published, linear, lesson_number, narrative_mode, first_frame_is_example
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                story.level,
                json.dumps(stored_frames),
                1 if story.published else 0,
                1 if story.linear else 0,
                story.lessonNumber,
                story.narrativeMode,
                1 if story.firstFrameIsExample else 0,
            ),
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
    }


@router.delete("/api/custom-stories/{story_id}")
async def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?",
            (story_id,),
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = ?", (story_id,))
    if row:
        for frame in json.loads(row["frames"] or "[]"):
            main.remove_uploaded_file(frame.get("imageUrl", ""))
            main.remove_uploaded_file(frame.get("listenAudioUrl", ""))
    return {"ok": True}


@router.patch("/api/custom-stories/{story_id}/vocabulary-distractors")
async def update_vocabulary_distractors(
    story_id: str, request: VocabularyDistractorsUpdateRequest
):
    """
    Tops up a story's per-word distractor pool (grown over time as students
    complete quiz rounds) rather than replacing it — merges new distractors
    into the existing list per word, deduping case-insensitively and capping
    at MAX_VOCAB_DISTRACTORS_PER_WORD so the pool doesn't grow unbounded.
    """
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?", (story_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Story not found.")

        frames = json.loads(row["frames"] or "[]")
        for update in request.updates:
            if update.frameIndex < 0 or update.frameIndex >= len(frames):
                continue
            if update.wordIndex < 0:
                continue
            frame = frames[update.frameIndex]
            try:
                pool: list = json.loads(frame.get("vocabularyDistractors") or "[]")
            except (json.JSONDecodeError, TypeError):
                pool = []
            while len(pool) <= update.wordIndex:
                pool.append([])

            existing = pool[update.wordIndex]
            seen = {d.strip().lower() for d in existing}
            merged = list(existing)
            for distractor in update.distractors:
                distractor = distractor.strip()
                key = distractor.lower()
                if (
                    not distractor
                    or key in seen
                    or len(merged) >= main.MAX_VOCAB_DISTRACTORS_PER_WORD
                ):
                    continue
                seen.add(key)
                merged.append(distractor)
            pool[update.wordIndex] = merged
            frame["vocabularyDistractors"] = json.dumps(pool)

        db.execute(
            "UPDATE custom_stories SET frames = ? WHERE id = ?",
            (json.dumps(frames), story_id),
        )
    return {"ok": True}
