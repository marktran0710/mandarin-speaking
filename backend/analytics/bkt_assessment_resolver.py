"""Resolve BKT observations from published assessment facts, never the client."""

from __future__ import annotations

from typing import Any

from analytics.bkt_mastery import canonical_story_id
from domain.vocabulary.assessment import normalize_answer, numeric_to_tone_marked


# The three diagnostic rounds. The first element is the round key stored in
# ``quiz_level`` (tier1/tier2/tier3 — matches ``quiz_mode``); the rest are the
# round's semantic tags. A round is identified by its question kind, not by the
# quiz bank's own difficulty label, so the bank stays untouched (see
# ``_diagnostic_source``).
_ROUND_FACTS = {
    "tier1": ("tier1", "know_it", "meaning", "basic_meaning_mcq"),
    "tier2": ("tier2", "say_it", "pinyin_production", "character_to_pinyin_typing"),
    # Round 3 is a multiple-choice context cloze, not free-text hanzi typing —
    # most students have no Chinese IME, so a bare text input made the round
    # unplayable. The question kind here must match bkt.py's TYPED_QUESTION_TYPES
    # membership: "context_cloze_mcq" is guessable (MCQ guess/slip), unlike the
    # old "contextual_productive_recall" typed rate this round used to get.
    "tier3": ("tier3", "use_it", "contextual_recall", "context_cloze_mcq"),
}

# The published quiz bank tags each assessment question with its own difficulty
# label; that bank is owned by the quiz generate/approve pipeline and is not
# renamed here. We only need it to derive a round key for non-diagnostic
# (weak-word) responses, whose quiz_level is metadata the diagnostic filter
# ignores. Diagnostic responses never consult it.
_BANK_LABEL_TO_ROUND = {"easy": "tier1", "medium": "tier2", "hard": "tier3"}

_QUESTION_FACTS = {
    "basic_meaning_mcq": ("tier1", "know_it", "meaning"),
    "character_to_pinyin_typing": ("tier2", "say_it", "pinyin_production"),
    "context_cloze_mcq": ("tier3", "use_it", "contextual_recall"),
    "contextual_productive_recall": ("tier3", "use_it", "contextual_recall"),
    "productive_recall": ("tier3", "use_it", "contextual_recall"),
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
    round_key, round_type, _dimension, _question_kind = facts
    for item in assessment:
        # A word carries one bank question per round, discriminated by the
        # bank's own difficulty label. We translate that label to our round key
        # (tier1/2/3) rather than renaming the bank, which the quiz pipeline
        # owns. quiz_level is then stored as the round key, never the label.
        if _BANK_LABEL_TO_ROUND.get(str(item.get("level") or "").casefold()) != round_key:
            continue
        expected_item_id = f"{item.get('wordId')}:{round_type}:v1"
        # Imported banks expose ``questionId`` directly; the current student
        # flow uses a stable round-specific derivative of the same word id.
        if submitted_item_id in {str(item.get("questionId") or ""), expected_item_id}:
            return item, facts
    return None


def _accepted_answers(item: dict[str, Any], mode: str, question_kind: str) -> tuple[str, list[str]]:
    if mode == "tier2" or question_kind == "character_to_pinyin_typing":
        pinyin = str(item.get("pinyin") or "").strip()
        accepted = [
            pinyin,
            *(part.strip() for part in pinyin.split("/")),
            *(str(value).strip() for value in (item.get("acceptedAnswers") or [])),
        ]
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
    if mode not in (*_ROUND_FACTS, "weak_words", "maintenance_review"):
        return _unresolved(submitted, "NON_BKT_ACTIVITY")
    if not isinstance(item_id, str) or not item_id or not isinstance(selected, str):
        return _unresolved(submitted, "MISSING_AUTHORITATIVE_RESPONSE_IDENTITY")

    published = _published_assessment(db, str(story_id or ""))
    if published is None:
        return _unresolved(submitted, "PUBLISHED_ASSESSMENT_UNAVAILABLE")
    source_story_id, assessment = published

    if mode in {"weak_words", "maintenance_review"}:
        item = next((row for row in assessment if row.get("questionId") == item_id), None)
        if item is None:
            return _unresolved(submitted, "UNKNOWN_PUBLISHED_ASSESSMENT_ITEM")
        level = _BANK_LABEL_TO_ROUND.get(str(item.get("level") or "").casefold())
        question_kind = str(item.get("questionType") or "")
        derived_facts = _QUESTION_FACTS.get(question_kind)
        round_type = derived_facts[1] if derived_facts else None
        knowledge_dimension = derived_facts[2] if derived_facts else None
        activity_type = "personalized_practice" if mode == "weak_words" else "scheduled_maintenance"
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

    correct_answer, accepted = _accepted_answers(item, mode, question_kind)
    # A learner typing pinyin on a plain keyboard writes tone numbers
    # ("ni3 hao3"); fold them to the tone-marked form the bank stores so this
    # BKT grade matches what the quiz UI showed. Scoped to the pinyin round so a
    # Chinese free-text answer is never rewritten. Tone stays required — a
    # toneless spelling produces no marks and won't match the marked answer.
    candidates = [selected]
    if question_kind == "character_to_pinyin_typing":
        candidates.append(numeric_to_tone_marked(selected))
    normalized_candidates = [normalized for normalized in (normalize_answer(value) for value in candidates) if normalized]
    correct = any(
        normalized == normalize_answer(answer)
        for normalized in normalized_candidates
        for answer in accepted
    )
    prompt = (
        f"Type the pinyin for {item.get('targetWord')}."
        if question_kind == "character_to_pinyin_typing"
        else str(item.get("prompt") or "")
    )
    if question_kind == "context_cloze_mcq":
        # Context questions are assembled from the lesson bank on the client;
        # retain the submitted choices as audit metadata while the server
        # still derives identity and correctness from the published item.
        options = [value for value in (submitted.get("presentedOptions") or []) if isinstance(value, str)]
    elif mode in {"tier1", "weak_words", "maintenance_review"}:
        options = list(item.get("options") or [])
    elif mode == "tier3":
        # `item` here is the round's hard-level bank row, which carries no
        # options (it's the free-text productive_recall entry) — Round 3's
        # actual MCQ choices are client-built from lesson + medium-level bank
        # data (see model.ts's buildDiagnosticRoundQuestions). presentedOptions
        # is harmless audit metadata, not authoritative for grading, so trust
        # what was submitted rather than re-deriving the same construction here.
        options = [value for value in (submitted.get("presentedOptions") or []) if isinstance(value, str)]
    else:
        options = []
    return {
        # Keep harmless audit fields such as response time, then overwrite
        # every field that can affect correctness, identity, or BKT routing.
        **submitted,
        "word": str(item.get("targetWord") or ""),
        "conceptId": str(item.get("wordId") or ""),
        "itemId": item_id,
        "questionKind": question_kind,
        "answerFormat": item.get("answerFormat"),
        "level": level,
        "roundType": round_type,
        "knowledgeDimension": knowledge_dimension,
        "activityType": activity_type,
        "correct": correct,
        "correctAnswer": correct_answer,
        "presentedOptions": options,
        "questionPrompt": prompt,
        "lessonId": source_story_id,
        "diagnosticExposureId": f"{source_story_id}:{mode}:{item_id}" if mode in _ROUND_FACTS else None,
        "assistedResponse": False,
        "bktValidationStatus": "APPROVED",
        "isBktEligible": is_bkt_eligible,
        "bktEligibilityErrors": eligibility_errors,
        "authoritativeResolved": True,
        "resolverVersion": ASSESSMENT_RESOLVER_VERSION,
    }
