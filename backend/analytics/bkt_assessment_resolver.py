"""Resolve BKT observations from published assessment facts, never the client."""

from __future__ import annotations

from typing import Any

from analytics.bkt_mastery import canonical_story_id
from vocab_assessment import normalize_answer


# The student UI deliberately turns the three imported assessment levels into
# one meaning, one pinyin-production, and one contextual-recall observation.
# Keep that transformation mirrored here so the browser only needs to submit
# an immutable item id and the learner's selected answer.
_ROUND_FACTS = {
    "tier1": ("easy", "know_it", "meaning", "basic_meaning_mcq"),
    "tier2": ("medium", "say_it", "pinyin_production", "character_to_pinyin_typing"),
    "tier3": ("hard", "use_it", "contextual_recall", "contextual_productive_recall"),
}

ASSESSMENT_RESOLVER_VERSION = "authoritative-assessment-v1"


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _unresolved(submitted: dict[str, Any], reason: str) -> dict[str, Any]:
    errors = list(dict.fromkeys([*(submitted.get("bktEligibilityErrors") or []), reason]))
    return {
        **submitted,
        "authoritativeResolved": False,
        "isBktEligible": False,
        "bktEligibilityErrors": errors,
    }


def _published_assessment(db: Any, story_id: str) -> tuple[str, list[dict[str, Any]]] | None:
    source_story_id = canonical_story_id(story_id) or story_id
    story = db.execute(
        "SELECT id, vocab_assessment FROM custom_stories WHERE id = %s AND published = TRUE",
        (source_story_id,),
    ).fetchone()
    if not story or not isinstance(story.get("vocab_assessment"), list):
        return None
    assessment = [row for row in story["vocab_assessment"] if isinstance(row, dict)]
    return str(story["id"]), assessment


def _diagnostic_source(
    assessment: list[dict[str, Any]], mode: str, submitted_item_id: str,
) -> tuple[dict[str, Any], tuple[str, str, str, str]] | None:
    facts = _ROUND_FACTS.get(mode)
    if facts is None:
        return None
    expected_level, round_type, _dimension, _question_kind = facts
    for item in assessment:
        if str(item.get("level") or "").casefold() != expected_level:
            continue
        expected_item_id = f"{item.get('wordId')}:{round_type}:v1"
        # Imported banks expose ``questionId`` directly; the current student
        # flow uses a stable round-specific derivative of the same word id.
        if submitted_item_id in {str(item.get("questionId") or ""), expected_item_id}:
            return item, facts
    return None


def _accepted_answers(item: dict[str, Any], mode: str) -> tuple[str, list[str]]:
    if mode == "tier2":
        pinyin = str(item.get("pinyin") or "").strip()
        accepted = [pinyin, *(part.strip() for part in pinyin.split("/"))]
        return pinyin, list(dict.fromkeys(value for value in accepted if value))
    correct_answer = str(item.get("correctAnswer") or "")
    accepted = [str(value) for value in (item.get("acceptedAnswers") or [correct_answer]) if value is not None]
    return correct_answer, list(dict.fromkeys([correct_answer, *accepted]))


def resolve_assessment_response(db: Any, attempt: Any, submitted: dict[str, Any]) -> dict[str, Any]:
    """Return server-derived response facts or an audit-only unresolved row.

    An unresolved or legacy question must not break quiz completion: its raw
    payload is still retained in ``vocab_quiz_attempts``. It simply cannot
    enter the normalized BKT ledger or influence a recommendation.
    """
    mode = str(_value(attempt, "mode") or "")
    story_id = _value(attempt, "baseStoryId") or _value(attempt, "storyId")
    item_id = submitted.get("itemId")
    selected = submitted.get("selectedAnswer")
    if mode not in (*_ROUND_FACTS, "weak_words"):
        return _unresolved(submitted, "NON_BKT_ACTIVITY")
    if not isinstance(item_id, str) or not item_id or not isinstance(selected, str):
        return _unresolved(submitted, "MISSING_AUTHORITATIVE_RESPONSE_IDENTITY")

    published = _published_assessment(db, str(story_id or ""))
    if published is None:
        return _unresolved(submitted, "PUBLISHED_ASSESSMENT_UNAVAILABLE")
    source_story_id, assessment = published

    if mode == "weak_words":
        item = next((row for row in assessment if row.get("questionId") == item_id), None)
        if item is None:
            return _unresolved(submitted, "UNKNOWN_PUBLISHED_ASSESSMENT_ITEM")
        level = str(item.get("level") or "").casefold()
        round_type = knowledge_dimension = None
        question_kind = str(item.get("questionType") or "")
        activity_type = "personalized_practice"
        is_bkt_eligible = False
        eligibility_errors = ["NON_DIAGNOSTIC_MODE"]
    else:
        source = _diagnostic_source(assessment, mode, item_id)
        if source is None:
            return _unresolved(submitted, "UNKNOWN_OR_STALE_DIAGNOSTIC_ITEM")
        item, (level, round_type, knowledge_dimension, question_kind) = source
        activity_type = "diagnostic"
        is_bkt_eligible = True
        eligibility_errors = []

    correct_answer, accepted = _accepted_answers(item, mode)
    normalized_selected = normalize_answer(selected)
    correct = bool(normalized_selected) and any(
        normalized_selected == normalize_answer(answer) for answer in accepted
    )
    prompt = (
        f"Type the pinyin for {item.get('targetWord')}."
        if mode == "tier2"
        else str(item.get("prompt") or "")
    )
    options = list(item.get("options") or []) if mode in {"tier1", "weak_words"} else []
    return {
        # Keep harmless audit fields such as response time, then overwrite
        # every field that can affect correctness, identity, or BKT routing.
        **submitted,
        "word": str(item.get("targetWord") or ""),
        "conceptId": str(item.get("wordId") or ""),
        "itemId": item_id,
        "questionKind": question_kind,
        "level": level,
        "roundType": round_type,
        "knowledgeDimension": knowledge_dimension,
        "activityType": activity_type,
        "correct": correct,
        "correctAnswer": correct_answer,
        "presentedOptions": options,
        "questionPrompt": prompt,
        "lessonId": source_story_id,
        "diagnosticExposureId": (
            f"{source_story_id}:{mode}:{item_id}" if mode in _ROUND_FACTS else None
        ),
        "assistedResponse": False,
        "bktValidationStatus": "APPROVED",
        "isBktEligible": is_bkt_eligible,
        "bktEligibilityErrors": eligibility_errors,
        "authoritativeResolved": True,
        "resolverVersion": ASSESSMENT_RESOLVER_VERSION,
    }
