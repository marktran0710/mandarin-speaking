"""Compatibility facade for legacy ``routers.content.stories`` imports."""

from fastapi import APIRouter

from routers.content.crud import router as story_crud_router


router = APIRouter()
router.include_router(story_crud_router)
