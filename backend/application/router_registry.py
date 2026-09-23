"""Mounts every router onto the app, in order.

frontend_router's catch-all (`/{frontend_path:path}`) must stay registered
last - every other router would otherwise never be reached.
"""

from __future__ import annotations

from fastapi import FastAPI

from routers.admin import router as admin_router
from routers.bkt_debug import router as bkt_debug_router
from routers.knowledge_analytics import router as knowledge_analytics_router
from routers.asr import router as asr_router
from routers.verified_speaking import router as verified_speaking_router
from routers.audio import router as audio_router
from routers.health import router as health_router
from routers.help_requests import router as help_requests_router
from routers.media import router as media_router
from routers.measurement import router as measurement_router
from routers.pinyin import router as pinyin_router
from routers.quiz_review import router as quiz_review_router
from routers.speaking_progress import router as speaking_progress_router
from routers.story_crud import router as story_crud_router
from routers.story_quiz_materials import router as story_quiz_materials_router
from routers.story_quiz_pools import router as story_quiz_pools_router
from routers.students import router as students_router
from routers.teachers import router as teachers_router
from routers.submissions import router as submissions_router
from routers.tones import router as tones_router
from routers.tts import router as tts_router
from routers.vocab_quiz import router as vocab_quiz_router
from routers.vocab_quiz_research import router as vocab_quiz_research_router
from routers.frontend import router as frontend_router


def register_routers(app: FastAPI) -> None:
    app.include_router(admin_router)
    app.include_router(bkt_debug_router)
    app.include_router(knowledge_analytics_router)
    app.include_router(asr_router)
    app.include_router(verified_speaking_router)
    app.include_router(audio_router)
    app.include_router(health_router)
    app.include_router(help_requests_router)
    app.include_router(media_router)
    app.include_router(measurement_router)
    app.include_router(pinyin_router)
    app.include_router(quiz_review_router)
    app.include_router(speaking_progress_router)
    app.include_router(story_crud_router)
    app.include_router(story_quiz_materials_router)
    app.include_router(story_quiz_pools_router)
    app.include_router(students_router)
    app.include_router(teachers_router)
    app.include_router(submissions_router)
    app.include_router(tts_router)
    app.include_router(tones_router)
    app.include_router(vocab_quiz_router)
    app.include_router(vocab_quiz_research_router)
    app.include_router(frontend_router)
