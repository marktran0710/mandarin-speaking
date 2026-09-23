from fastapi import APIRouter, Depends, HTTPException, Query

from db import connect_db
import security.auth as auth
import services.story_service as story_service
from api.schemas.models import CustomStoryRequest
from routers.story_quiz_vocabulary import router as story_quiz_vocabulary_router
from routers.story_vocabulary_metadata import router as story_vocabulary_metadata_router

# Students may read lesson content after login; story writes and generated
# media are restricted by auth.require_story_access to teacher/admin accounts.
router = APIRouter(dependencies=[Depends(auth.require_story_access)])

# Nested so both story-vocabulary responsibilities pick up this router's
# require_story_access dependency and their own require_admin dependency.
router.include_router(story_vocabulary_metadata_router)
router.include_router(story_quiz_vocabulary_router)

# Stories carried per-difficulty-tier fields before the Medium/Hard tiers
# were removed; kept for now since deleting it isn't this move's job.
_TIER_SUFFIX = {"easy": ""}


def _tier_field(base: str, tier: str) -> str:
    return f"{base}{_TIER_SUFFIX.get(tier, '')}"


@router.get("/api/custom-stories")
def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    published_only = identity.role == "student"
    with connect_db() as db:
        return story_service.list_stories(db, published_only=published_only, limit=limit, skip=skip)


@router.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    try:
        return story_service.create_story(story)
    except story_service.StoryValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/api/custom-stories/{story_id}")
def delete_custom_story(story_id: str):
    story_service.delete_story(story_id)
    return {"ok": True}
