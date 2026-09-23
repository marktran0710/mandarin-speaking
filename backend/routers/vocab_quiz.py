"""Compatibility facade for vocabulary quiz and mastery routes."""

from fastapi import APIRouter, Depends

import security.auth as auth
from routers.vocab_quiz_analytics import (
    get_vocab_quiz_frex,
    router as vocab_quiz_analytics_router,
)
from routers.vocab_quiz_attempts import (
    _dev_srs_today,
    _effective_srs_day_seconds,
    create_vocab_quiz_attempt,
    list_vocab_quiz_attempts,
    record_vocab_quiz_response,
    router as vocab_quiz_attempts_router,
)
from services.vocab_quiz_attempt_service import (
    _enroll_newly_strong_words,
    _srs_event_results,
    _validated_question_results,
)
from routers.vocab_quiz_mastery import (
    _assert_student_scope,
    get_seen_vocabulary_items,
    get_student_priority_review_words,
    get_student_review_queue,
    get_student_vocabulary_mastery,
    get_weak_words,
    router as vocab_quiz_mastery_router,
)


router = APIRouter(dependencies=[Depends(auth.get_current_identity)])
router.include_router(vocab_quiz_attempts_router)
router.include_router(vocab_quiz_mastery_router)
router.include_router(vocab_quiz_analytics_router)


__all__ = [
    "router",
    "_dev_srs_today",
    "_effective_srs_day_seconds",
    "_enroll_newly_strong_words",
    "_srs_event_results",
    "_validated_question_results",
    "_assert_student_scope",
    "list_vocab_quiz_attempts",
    "create_vocab_quiz_attempt",
    "record_vocab_quiz_response",
    "get_student_priority_review_words",
    "get_student_review_queue",
    "get_student_vocabulary_mastery",
    "get_seen_vocabulary_items",
    "get_weak_words",
    "get_vocab_quiz_frex",
]
