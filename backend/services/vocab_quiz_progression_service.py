"""Server-authoritative vocabulary quiz progression for one story.

A round ("tier") is earned once the learner has finished it: a completed
attempt whose answers are all present in the normalized response ledger.
There is no accuracy threshold — the score is reported, never a gate.  Each
round reports its most recent finished attempt's score (correct/total from
the ledger, so a client cannot inflate it by editing ``correctCount``).
"""

from __future__ import annotations

from typing import Any

from analytics.learner_model.bkt.mastery import _known_words
from domain.vocabulary.story_scope import canonical_story_id, story_scope_ids
from repositories import quiz_attempt_repository


REQUIRED_STARS = 3
_TIERS = ("tier1", "tier2", "tier3")


def _conversation_is_valid(turns: Any) -> bool:
    if not isinstance(turns, list) or len(turns) < 2:
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


def _frames_conversation_available(frames: Any) -> bool:
    """The shared-content fallback has one alternating turn per scene."""
    if not isinstance(frames, list):
        return False
    usable = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        text = frame.get("suggestedAnswer") or frame.get("prompt")
        if isinstance(text, str) and text.strip():
            usable.append(text)
    return len(usable) >= 2


def _authoritative_scores(db: Any, student_id: str, attempts: list[dict], word_ids: set[str]) -> dict[str, dict[str, int]]:
    """Return validated correct/total response counts for completed attempts."""
    if not attempts or not word_ids:
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
        SELECT quiz_id, quiz_mode, word_id, correct
        FROM vocab_quiz_responses
        WHERE student_id = %s
          AND quiz_id = ANY(%s)
          AND lower(COALESCE(quiz_level, '')) IN ('tier1', 'tier2', 'tier3')
          AND quiz_mode IN ('tier1', 'tier2', 'tier3')
          AND bkt_eligible = TRUE
          AND word_id = ANY(%s)
        ORDER BY quiz_id, attempt_order ASC
        """,
        [student_id, list(attempt_by_quiz_id), sorted(word_ids)],
    ).fetchall()

    scores: dict[str, dict[str, int]] = {}
    covered_words: dict[str, set[str]] = {}
    for row in rows:
        attempt_id = attempt_by_quiz_id.get(str(row["quiz_id"]))
        mode = str(row.get("quiz_mode") or "")
        if not attempt_id or mode not in _TIERS or row["word_id"] not in word_ids:
            continue
        key = f"{attempt_id}:{mode}"
        score = scores.setdefault(key, {"correctCount": 0, "totalQuestions": 0})
        score["totalQuestions"] += 1
        score["correctCount"] += int(bool(row.get("correct")))
        covered_words.setdefault(key, set()).add(row["word_id"])
    # A completed round must still cover the current vocabulary pool. Old
    # IDs and a short surviving subset cannot keep a reset lesson unlocked.
    return {key: score for key, score in scores.items() if covered_words[key] == word_ids}


def _story_conversation_available(db: Any, story_id: str) -> bool:
    rows = db.execute(
        "SELECT conversation_turns, frames FROM custom_stories WHERE id = ANY(%s) AND published = TRUE",
        [story_scope_ids(story_id)],
    ).fetchall()
    return any(
        _conversation_is_valid(row.get("conversation_turns"))
        or _frames_conversation_available(row.get("frames"))
        for row in rows
    )


def get_progression(db: Any, student_id: str, story_id: str) -> dict[str, Any]:
    canonical = canonical_story_id(story_id) or story_id
    attempts = quiz_attempt_repository.list_attempts(
        db, story_id=canonical, student_id=student_id, include_results=True,
    )
    scores = _authoritative_scores(db, student_id, attempts, set(_known_words(db, story_id=canonical)))
    tiers: dict[str, dict[str, Any]] = {}
    earned_tiers: set[str] = set()

    for tier in _TIERS:
        tier_attempts = [attempt for attempt in attempts if attempt.get("mode") == tier]
        latest: dict[str, int] | None = None
        latest_at = ""
        for attempt in tier_attempts:
            score = scores.get(f"{attempt['id']}:{tier}")
            # A round counts as finished only when every answer of the
            # completed attempt reached the ledger.
            if not score or score["totalQuestions"] < int(attempt.get("totalQuestions") or 0):
                continue
            completed_at = str(attempt.get("completedAt") or "")
            if latest is None or completed_at >= latest_at:
                latest = score
                latest_at = completed_at
        total = latest["totalQuestions"] if latest else 0
        correct = latest["correctCount"] if latest else 0
        tiers[tier] = {
            "earned": latest is not None,
            "correctCount": correct,
            "totalQuestions": total,
            "score": round(100 * correct / total) if total else 0,
            "completedAt": latest_at or None,
        }
        if latest is not None:
            earned_tiers.add(tier)

    stars = 0
    for tier in _TIERS:
        if tier not in earned_tiers:
            break
        stars += 1

    conversation_available = _story_conversation_available(db, canonical)
    practice_unlocked = stars >= REQUIRED_STARS
    return {
        "storyId": canonical,
        "quizStars": stars,
        "requiredStars": REQUIRED_STARS,
        "tiers": tiers,
        "speakingUnlocked": practice_unlocked,
        "conversationAvailable": conversation_available,
        # Both modes share one progression gate. Content readiness is
        # reported separately so it cannot change either mode's lock state.
        "conversationUnlocked": practice_unlocked,
    }
