"""Admin-only edits of existing Speaking quiz vocabulary metadata.

Holds the business logic that used to live inline in
routers/story_quiz_vocabulary.py. The validation helpers raise
``fastapi.HTTPException`` directly (rather than a domain exception) because
they are consumed directly - by name - from the ``routers.content.vocabulary``
compatibility facade; changing that would be a behavior change for that
caller, not just this router.
"""
from uuid import uuid4

from fastapi import HTTPException

from db import vocab_assessment_revision
from domain.vocabulary.assessment import ANSWER_FORMAT_BY_ROUND, QUESTION_TYPE_BY_ROUND, ROUNDS, TIER_BY_ROUND, normalize_answer, validate_assessment_payload
from repositories.content import quiz_vocabulary as repo
from repositories.database import row_to_custom_story


def _assessment_rows(row: dict) -> list[dict]:
    """Return a copyable assessment bank or fail before partially writing it."""
    assessment = row.get("vocab_assessment")
    if assessment is None:
        return []
    if not isinstance(assessment, list) or any(not isinstance(question, dict) for question in assessment):
        raise HTTPException(409, "Quiz bank changed. Reload the story before saving again.")
    return assessment


def _question_rows(word_id: str, word, audio_by_round: dict[int, str] | None = None) -> list[dict]:
    rounds = [question.round for question in word.questions]
    if set(rounds) != set(ROUNDS) or len(rounds) != len(ROUNDS):
        raise HTTPException(422, "Each quiz word must include exactly one question for rounds 1, 2, and 3.")
    rows = []
    for question in word.questions:
        round_number = int(question.round)
        row = {
            "questionId": f"Q_{uuid4().hex}",
            "wordId": word_id,
            "targetWord": word.targetWord,
            "pinyin": word.pinyin,
            "pos": word.pos,
            "simpleEnglishMeaning": word.simpleEnglishMeaning,
            "round": round_number,
            "tier": TIER_BY_ROUND[round_number],
            "questionType": QUESTION_TYPE_BY_ROUND[round_number],
            "answerFormat": ANSWER_FORMAT_BY_ROUND[round_number],
            "prompt": question.prompt,
            "options": question.options,
            "correctAnswer": question.correctAnswer,
            "acceptedAnswers": question.acceptedAnswers,
            "explanation": question.explanation,
        }
        if audio_by_round and audio_by_round.get(round_number):
            row["audioUrl"] = audio_by_round[round_number]
        rows.append(row)
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
    return repo.write_quiz_bank(db, story_id, assessment)


def create_word(db, story_id: str, word) -> dict:
    row = repo.find_story_for_update(db, story_id)
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


def update_word(db, story_id: str, word_id: str, word) -> dict:
    if word.wordId is not None and word.wordId != word_id:
        raise HTTPException(422, "wordId in the request must match the quiz word being edited.")
    row = repo.find_story_for_update(db, story_id)
    if row is None:
        raise HTTPException(404, "Story not found.")
    assessment = _assessment_rows(row)
    _check_expected_revision(assessment, word.expectedRevision)
    if not any(question.get("wordId") == word_id for question in assessment):
        raise HTTPException(404, "Quiz word not found.")
    audio_by_round = {
        int(question["round"]): question["audioUrl"]
        for question in assessment
        if question.get("wordId") == word_id
        and question.get("audioUrl")
        and question.get("round") is not None
    }
    replacement = _question_rows(word_id, word, audio_by_round)
    updated_assessment = [
        question for question in assessment if question.get("wordId") != word_id
    ]
    updated_assessment.extend(replacement)
    _validate_quiz_bank(updated_assessment)
    updated = _write_quiz_bank(db, story_id, updated_assessment)
    return row_to_custom_story(updated)


def delete_word(db, story_id: str, word_id: str, expected_revision: str | None) -> dict:
    row = repo.find_story_for_update(db, story_id)
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
