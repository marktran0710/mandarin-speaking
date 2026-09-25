"""Compatibility facade for story vocabulary administration routes."""

from fastapi import APIRouter, HTTPException

from routers.story_quiz_vocabulary import (
    QuizVocabularyQuestionInput,
    QuizVocabularyWordInput,
    create_quiz_vocabulary_word,
    delete_quiz_vocabulary_word,
    router as story_quiz_vocabulary_router,
    update_quiz_vocabulary_word,
)
from services.story_quiz_vocabulary_service import (
    _assessment_rows,
    _check_expected_revision,
    _ensure_unique_quiz_content,
    _question_rows,
    _validate_quiz_bank,
    _write_quiz_bank,
)
from routers.story_vocabulary_metadata import (
    VocabularyColumns,
    VocabularyMetadataEdit,
    router as story_vocabulary_metadata_router,
    update_vocabulary_metadata,
)
from services.story_vocabulary_metadata_service import (
    FIELDS,
    SUFFIXES,
    _replace_answer_value,
    assessment_columns,
    effective_columns,
    metadata_changes,
    update_assessment_metadata,
)


router = APIRouter()
router.include_router(story_vocabulary_metadata_router)
router.include_router(story_quiz_vocabulary_router)


__all__ = [
    "router",
    "FIELDS",
    "SUFFIXES",
    "VocabularyColumns",
    "VocabularyMetadataEdit",
    "QuizVocabularyQuestionInput",
    "QuizVocabularyWordInput",
    "effective_columns",
    "metadata_changes",
    "assessment_columns",
    "update_assessment_metadata",
    "_replace_answer_value",
    "_assessment_rows",
    "_question_rows",
    "_ensure_unique_quiz_content",
    "_validate_quiz_bank",
    "_check_expected_revision",
    "_write_quiz_bank",
    "update_vocabulary_metadata",
    "create_quiz_vocabulary_word",
    "update_quiz_vocabulary_word",
    "delete_quiz_vocabulary_word",
]
