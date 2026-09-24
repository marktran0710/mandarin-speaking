"""Compatibility facade for legacy ``routers.stories`` imports."""

from fastapi import APIRouter

from routers.story_crud import router as story_crud_router


router = APIRouter()
router.include_router(story_crud_router)
