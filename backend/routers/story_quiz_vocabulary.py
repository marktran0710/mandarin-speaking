"""Admin-only edits of existing Speaking quiz vocabulary metadata."""
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.types.json import Jsonb

import auth
from db import connect_db, row_to_custom_story, vocab_assessment_revision
from vocab_assessment import LEVELS, QUESTION_TYPE_BY_LEVEL, normalize_answer, validate_assessment_payload

router = APIRouter(dependencies=[Depends(auth.require_admin)])


class QuizVocabularyQuestionInput(BaseModel):
    """One authorable observation; server-owned fields are derived from its level."""

    model_config = ConfigDict(extra="forbid")
    level: Literal["Easy", "Medium", "Hard"]
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


def _assessment_rows(row: dict) -> list[dict]:
    """Return a copyable assessment bank or fail before partially writing it."""
    assessment = row.get("vocab_assessment")
    if assessment is None:
        return []
    if not isinstance(assessment, list) or any(not isinstance(question, dict) for question in assessment):
        raise HTTPException(409, "Quiz bank changed. Reload the story before saving again.")
    return assessment


def _question_rows(word_id: str, word: QuizVocabularyWordInput) -> list[dict]:
    levels = [question.level for question in word.questions]
    if set(levels) != set(LEVELS) or len(levels) != len(LEVELS):
        raise HTTPException(422, "Each quiz word must include exactly one Easy, Medium, and Hard question.")
    rows = []
    for question in word.questions:
        is_mcq = question.level in ("Easy", "Medium")
        rows.append({
            "questionId": f"{word_id}_{question.level.upper()}",
            "wordId": word_id,
            "targetWord": word.targetWord,
            "pinyin": word.pinyin,
            "pos": word.pos,
            "simpleEnglishMeaning": word.simpleEnglishMeaning,
            "level": question.level,
            "difficultyWeight": {"Easy": 1, "Medium": 2, "Hard": 3}[question.level],
            "questionType": QUESTION_TYPE_BY_LEVEL[question.level],
            "answerFormat": "single_choice" if is_mcq else "free_text",
            "prompt": question.prompt,
            "options": question.options,
            "correctAnswer": question.correctAnswer,
            "acceptedAnswers": question.acceptedAnswers,
            "explanation": question.explanation,
        })
    return rows


def _ensure_unique_quiz_content(assessment: list[dict]) -> None:
    """Content duplication is confusing even when its generated IDs differ."""
    by_word: dict[str, str] = {}
    prompts: set[str] = set()
    for question in assessment:
        word_id = str(question.get("wordId") or "")
        target = normalize_answer(str(question.get("targetWord") or ""))
        if target and target in by_word and by_word[target] != word_id:
            raise HTTPException(422, "A quiz word with the same target word already exists.")
        if target:
            by_word[target] = word_id
        prompt = normalize_answer(str(question.get("prompt") or ""))
        if prompt and prompt in prompts:
            raise HTTPException(422, "Quiz questions must not use duplicate prompts.")
        if prompt:
            prompts.add(prompt)


def _validate_quiz_bank(assessment: list[dict]) -> None:
    _ensure_unique_quiz_content(assessment)
    issues = validate_assessment_payload(assessment)
    if issues:
        raise HTTPException(
            422,
            {"message": "Quiz bank failed validation.", "issues": [issue.__dict__ for issue in issues]},
        )


def _check_expected_revision(assessment: list[dict], expected_revision: str | None) -> None:
    if expected_revision is not None and expected_revision != vocab_assessment_revision(assessment):
        raise HTTPException(409, "Quiz vocabulary changed in another session. Refresh before saving again.")


def _write_quiz_bank(db, story_id: str, assessment: list[dict]) -> dict:
    db.execute(
        "UPDATE custom_stories SET vocab_assessment = %s::jsonb WHERE id = %s",
        (Jsonb(assessment), story_id),
    )
    return db.execute("SELECT * FROM custom_stories WHERE id = %s", (story_id,)).fetchone()


@router.post("/api/custom-stories/{story_id}/quiz-vocabulary")
async def create_quiz_vocabulary_word(story_id: str, word: QuizVocabularyWordInput):
    with connect_db() as db:
        row = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Story not found.")
        assessment = _assessment_rows(row)
        _check_expected_revision(assessment, word.expectedRevision)
        word_id = word.wordId or f"QUIZ_{uuid4().hex}"
        if any(question.get("wordId") == word_id for question in assessment):
            raise HTTPException(409, "A quiz word with this wordId already exists.")
        updated_assessment = [*assessment, *_question_rows(word_id, word)]
        _validate_quiz_bank(updated_assessment)
        updated = _write_quiz_bank(db, story_id, updated_assessment)
    return row_to_custom_story(updated)


@router.put("/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}")
async def update_quiz_vocabulary_word(story_id: str, word_id: str, word: QuizVocabularyWordInput):
    if word.wordId is not None and word.wordId != word_id:
        raise HTTPException(422, "wordId in the request must match the quiz word being edited.")
    with connect_db() as db:
        row = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Story not found.")
        assessment = _assessment_rows(row)
        _check_expected_revision(assessment, word.expectedRevision)
        if not any(question.get("wordId") == word_id for question in assessment):
            raise HTTPException(404, "Quiz word not found.")
        replacement = _question_rows(word_id, word)
        updated_assessment = [
            question for question in assessment if question.get("wordId") != word_id
        ]
        updated_assessment.extend(replacement)
        _validate_quiz_bank(updated_assessment)
        updated = _write_quiz_bank(db, story_id, updated_assessment)
    return row_to_custom_story(updated)


@router.delete("/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}")
async def delete_quiz_vocabulary_word(
    story_id: str,
    word_id: str,
    expected_revision: str | None = Query(default=None, alias="expectedRevision", min_length=64, max_length=64, pattern="^[0-9a-f]{64}$"),
):
    with connect_db() as db:
        row = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Story not found.")
        assessment = _assessment_rows(row)
        _check_expected_revision(assessment, expected_revision)
        updated_assessment = [
            question for question in assessment if question.get("wordId") != word_id
        ]
        if len(updated_assessment) == len(assessment):
            raise HTTPException(404, "Quiz word not found.")
        _validate_quiz_bank(updated_assessment)
        updated = _write_quiz_bank(db, story_id, updated_assessment)
    return row_to_custom_story(updated)
