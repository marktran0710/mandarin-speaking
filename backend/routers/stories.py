"""Compatibility facade for legacy ``routers.stories`` imports."""

from fastapi import APIRouter

from routers.story_crud import router as story_crud_router
from routers.story_quiz_materials import router as story_quiz_materials_router
from routers.story_quiz_pools import router as story_quiz_pools_router


router = APIRouter()
router.include_router(story_crud_router)
router.include_router(story_quiz_materials_router)
router.include_router(story_quiz_pools_router)
