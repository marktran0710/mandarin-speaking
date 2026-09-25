"""Admin-only edits of existing Speaking quiz vocabulary metadata."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

import security.auth as auth
import services.content.quiz_vocabulary as story_quiz_vocabulary_service
from db import connect_db

router = APIRouter(dependencies=[Depends(auth.require_admin)])


class QuizVocabularyQuestionInput(BaseModel):
    """One authorable observation; question shape is derived from its round."""

    model_config = ConfigDict(extra="forbid")
    round: Literal[1, 2, 3]
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=4)
    correctAnswer: str = Field(min_length=1, max_length=500)
    acceptedAnswers: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt", "correctAnswer", "explanation")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank.")
        return value

    @field_validator("options", "acceptedAnswers")
    @classmethod
    def non_blank_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("List values must not be blank.")
        return cleaned


class QuizVocabularyWordInput(BaseModel):
    """An atomic word edit: exactly one observation per learner round."""

    model_config = ConfigDict(extra="forbid")
    wordId: str | None = Field(default=None, min_length=1, max_length=200)
    expectedRevision: str | None = Field(default=None, min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")
    targetWord: str = Field(min_length=1, max_length=200)
    pinyin: str = Field(min_length=1, max_length=300)
    pos: str = Field(min_length=1, max_length=50)
    simpleEnglishMeaning: str = Field(min_length=1, max_length=500)
    questions: list[QuizVocabularyQuestionInput] = Field(min_length=3, max_length=3)

    @field_validator("wordId", "targetWord", "pinyin", "pos", "simpleEnglishMeaning")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank.")
        return value


@router.post("/api/custom-stories/{story_id}/quiz-vocabulary")
async def create_quiz_vocabulary_word(story_id: str, word: QuizVocabularyWordInput):
    with connect_db() as db:
        return story_quiz_vocabulary_service.create_word(db, story_id, word)


@router.put("/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}")
async def update_quiz_vocabulary_word(story_id: str, word_id: str, word: QuizVocabularyWordInput):
    with connect_db() as db:
        return story_quiz_vocabulary_service.update_word(db, story_id, word_id, word)


@router.delete("/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}")
async def delete_quiz_vocabulary_word(
    story_id: str,
    word_id: str,
    expected_revision: str | None = Query(default=None, alias="expectedRevision", min_length=64, max_length=64, pattern="^[0-9a-f]{64}$"),
):
    with connect_db() as db:
        return story_quiz_vocabulary_service.delete_word(db, story_id, word_id, expected_revision)
