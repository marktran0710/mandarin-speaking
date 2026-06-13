"""Custom story and image-generation endpoints."""
import json

from fastapi import APIRouter, HTTPException, Query, Request

from config import GEMINI_API_KEY, check_rate_limit, logger
from database import connect_db, row_to_custom_story
from models import CustomStoryRequest, StoryImageGenerationRequest, StoryImageGenerationResponse
from services.files import persist_story_frame_images, remove_uploaded_file
from services.image_gen import build_story_image_fallback, generate_story_images_with_gemini, normalize_story_image_response

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
    stored_frames = persist_story_frame_images(story.id, frames)
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO custom_stories
                (id, title, learning_goal, level, frames, published)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                story.level,
                json.dumps(stored_frames),
                1 if story.published else 0,
            ),
        )
    return {**story.model_dump(), "frames": stored_frames}


@router.delete("/api/custom-stories/{story_id}")
async def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?", (story_id,)
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = ?", (story_id,))
    if row:
        for frame in json.loads(row["frames"] or "[]"):
            remove_uploaded_file(frame.get("imageUrl", ""))
    return {"ok": True}


@router.post("/api/generate-story-images", response_model=StoryImageGenerationResponse)
async def generate_story_images(request: StoryImageGenerationRequest, req: Request):
    client_ip = req.client.host if req.client else "unknown"
    check_rate_limit(f"gen-images:{client_ip}", max_requests=10, window_seconds=60)

    if len(request.situation.strip()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Describe the situation context with at least 8 characters.",
        )

    if GEMINI_API_KEY:
        try:
            return await generate_story_images_with_gemini(request)
        except Exception as exc:
            logger.warning("Gemini story image planning failed, using local fallback: %s", exc)

    fallback = build_story_image_fallback(request, provider="local")
    return await normalize_story_image_response(
        {
            "title": fallback.title,
            "learning_goal": fallback.learning_goal,
            "frames": [
                {
                    "title": f.title,
                    "student_prompt": f.student_prompt,
                    "vocabulary": f.vocabulary,
                    "image_prompt": f.image_prompt,
                }
                for f in fallback.frames
            ],
        },
        request,
        provider="local",
    )
