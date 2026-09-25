"""Server-authoritative vocabulary quiz progression for one story.

The completed-attempt table is the completion boundary.  The normalized
response ledger is used for correctness so a client cannot manufacture stars
by changing ``correctCount`` or ``correct`` in its JSON payload.
"""

from __future__ import annotations

from math import ceil
from typing import Any

from domain.vocabulary.story_scope import canonical_story_id, story_scope_ids
from repositories import quiz_attempt_repository


REQUIRED_STARS = 3
_PASS_RATIOS = {"tier1": 0.70, "tier2": 0.82, "tier3": 0.88}
_TIERS = ("tier1", "tier2", "tier3")


def _conversation_is_valid(turns: Any) -> bool:
    if not isinstance(turns, list) or not turns or len(turns) % 2:
        return False
    ids: set[str] = set()
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            return False
        turn_id = turn.get("id")
        text = turn.get("text")
        speaker = turn.get("speaker")
        if not isinstance(turn_id, str) or not turn_id.strip() or turn_id in ids:
            return False
        if not isinstance(text, str) or not text.strip():
            return False
        expected_speaker = "system" if index % 2 == 0 else "student"
        if speaker != expected_speaker:
            return False
        ids.add(turn_id)
    return True


def _authoritative_scores(db: Any, student_id: str, attempts: list[dict]) -> dict[str, dict[str, int]]:
    """Return validated correct/total response counts for completed attempts."""
    if not attempts:
        return {}

    attempt_by_quiz_id: dict[str, str] = {}
    for attempt in attempts:
        attempt_id = str(attempt["id"])
        attempt_by_quiz_id[attempt_id] = attempt_id
        for result in attempt.get("questionResults") or []:
            quiz_id = result.get("quizId") if isinstance(result, dict) else None
            if quiz_id:
                attempt_by_quiz_id[str(quiz_id)] = attempt_id

    rows = db.execute(
        """
        SELECT quiz_id, quiz_mode, correct
        FROM vocab_quiz_responses
        WHERE student_id = %s
          AND quiz_id = ANY(%s)
          AND lower(COALESCE(quiz_level, '')) IN ('tier1', 'tier2', 'tier3')
          AND quiz_mode IN ('tier1', 'tier2', 'tier3')
          AND bkt_eligible = TRUE
        ORDER BY quiz_id, attempt_order ASC
        """,
        [student_id, list(attempt_by_quiz_id)],
    ).fetchall()

    scores: dict[str, dict[str, int]] = {}
    for row in rows:
        attempt_id = attempt_by_quiz_id.get(str(row["quiz_id"]))
        mode = str(row.get("quiz_mode") or "")
        if not attempt_id or mode not in _TIERS:
            continue
        key = f"{attempt_id}:{mode}"
        score = scores.setdefault(key, {"correctCount": 0, "totalQuestions": 0})
        score["totalQuestions"] += 1
        score["correctCount"] += int(bool(row.get("correct")))
    return scores


def _story_conversation_available(db: Any, story_id: str) -> bool:
    rows = db.execute(
        "SELECT conversation_turns FROM custom_stories WHERE id = ANY(%s) AND published = TRUE",
        [story_scope_ids(story_id)],
    ).fetchall()
    return any(_conversation_is_valid(row.get("conversation_turns")) for row in rows)


def get_progression(db: Any, student_id: str, story_id: str) -> dict[str, Any]:
    canonical = canonical_story_id(story_id) or story_id
    attempts = quiz_attempt_repository.list_attempts(
        db, story_id=canonical, student_id=student_id, include_results=True,
    )
    scores = _authoritative_scores(db, student_id, attempts)
    tiers: dict[str, dict[str, Any]] = {}
    earned_tiers: set[str] = set()

    for tier in _TIERS:
        tier_attempts = [attempt for attempt in attempts if attempt.get("mode") == tier]
        best: dict[str, int] | None = None
        best_attempt: dict | None = None
        for attempt in tier_attempts:
            score = scores.get(f"{attempt['id']}:{tier}")
            if not score or score["totalQuestions"] < int(attempt.get("totalQuestions") or 0):
                continue
            if best is None or (score["correctCount"], score["totalQuestions"]) > (best["correctCount"], best["totalQuestions"]):
                best = score
                best_attempt = attempt
        total = best["totalQuestions"] if best else 0
        correct = best["correctCount"] if best else 0
        required = max(1, ceil(_PASS_RATIOS[tier] * total)) if total else 0
        # The policy belongs to the selected completed attempt. Production is
        # the default; research coverage remains separate from BKT status.
        passed = bool(best and best_attempt and (
            best_attempt.get("progressionPolicy") == "research_coverage" or correct >= required
        ))
        tiers[tier] = {
            "earned": passed,
            "correctCount": correct,
            "totalQuestions": total,
            "requiredCorrect": required,
        }
        if passed:
            earned_tiers.add(tier)

    stars = 0
    for tier in _TIERS:
        if tier not in earned_tiers:
            break
        stars += 1

    conversation_available = _story_conversation_available(db, canonical)
    speaking_unlocked = stars >= REQUIRED_STARS
    return {
        "storyId": canonical,
        "quizStars": stars,
        "requiredStars": REQUIRED_STARS,
        "tiers": tiers,
        "speakingUnlocked": speaking_unlocked,
        "conversationAvailable": conversation_available,
        "conversationUnlocked": speaking_unlocked and conversation_available,
    }
