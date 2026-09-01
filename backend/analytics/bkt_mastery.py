"""Persistence and recommendation helpers for vocabulary BKT state."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
import unicodedata

from psycopg.types.json import Jsonb

from analytics.bkt import BKT_CONFIG, BktConfig, mastery_status, replay_bkt
from analytics.bkt_question_validation import classify_bkt_response


def normalize_word_id(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _word_id(result: dict[str, Any]) -> str | None:
    concept = result.get("conceptId") or result.get("concept_id") or result.get("word")
    if not isinstance(concept, str) or not concept.strip():
        return None
    return normalize_word_id(concept)


def response_rows_for_attempt(attempt: Any, student_id: str, response_results: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    """Convert the existing attempt payload to normalized immutable facts."""
    def value(name: str, default: Any = None) -> Any:
        if isinstance(attempt, dict):
            return attempt.get(name, default)
        return getattr(attempt, name, default)

    results = list(response_results) if response_results is not None else value("questionResults", [])
    rows: list[dict[str, Any]] = []
    completed_at = value("completedAt")
    story_id = value("storyId")
    base_story_id = value("baseStoryId")
    level = value("level")
    mode = value("mode")
    attempt_id = value("id")
    for order, raw in enumerate(results or []):
        result = raw.model_dump(exclude_none=True) if hasattr(raw, "model_dump") else dict(raw)
        eligible, _reasons = classify_bkt_response(result, attempt)
        quiz_mode = result.get("mode") or mode
        # Diagnostic evidence is server-gated. A personalized review answer is
        # still a normal learning observation and must update BKT even though
        # it is not eligible to count toward the three-quiz unlock.
        if not eligible and quiz_mode != "weak_words":
            # The original JSONB attempt remains the lossless raw record. This
            # normalized ledger is intentionally restricted to observations
            # that can affect word-level BKT.
            continue
        word_id = _word_id(result)
        if not word_id or not isinstance(result.get("correct"), bool):
            continue
        rows.append({
            "student_id": student_id,
            "word_id": word_id,
            "word": result.get("word") or word_id,
            "lesson_id": result.get("lessonId") or base_story_id or story_id,
            "quiz_id": result.get("quizId") or attempt_id,
            "attempt_id": attempt_id,
            "item_id": result.get("itemId") or f"{base_story_id or story_id}:{word_id}:{result.get('questionKind', 'unknown')}:v1",
            "question_type": result.get("questionKind") or "unknown",
            "diagnostic_exposure_id": result.get("diagnosticExposureId") or result.get("diagnostic_exposure_id"),
            "bkt_eligible": bool(eligible),
            "bkt_eligibility_errors": result.get("bktEligibilityErrors") or [],
            "selected_answer": result.get("selectedAnswer"),
            "correct_answer": result.get("correctAnswer"),
            "presented_options": result.get("presentedOptions") or [],
            "question_prompt": result.get("questionPrompt"),
            "answered_at": result.get("answeredAt"),
            "correct": result["correct"],
            "response_time_ms": int(result.get("timeMs") or 0),
            "occurred_at": completed_at,
            "attempt_order": order,
            "quiz_level": result.get("level") or level,
            "quiz_mode": mode,
        })
    return rows


def upsert_raw_responses(db: Any, rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        values = [row[key] for key in (
            "student_id", "word_id", "word", "lesson_id", "quiz_id", "attempt_id",
            "item_id", "question_type", "selected_answer", "correct_answer",
            "presented_options", "question_prompt", "answered_at", "bkt_eligible",
            "diagnostic_exposure_id", "bkt_eligibility_errors", "correct", "response_time_ms", "occurred_at",
            "attempt_order", "quiz_level", "quiz_mode",
        )]
        values[10] = Jsonb(values[10])
        values[15] = Jsonb(values[15])
        db.execute(
            """
            INSERT INTO vocab_quiz_responses
                (student_id, word_id, word, lesson_id, quiz_id, attempt_id,
                item_id, question_type, selected_answer, correct_answer,
                presented_options, question_prompt, answered_at, bkt_eligible,
                diagnostic_exposure_id, bkt_eligibility_errors, correct,
                response_time_ms, occurred_at, attempt_order, quiz_level, quiz_mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (quiz_id, attempt_order) DO UPDATE SET
                student_id = EXCLUDED.student_id,
                word_id = EXCLUDED.word_id,
                word = EXCLUDED.word,
                lesson_id = EXCLUDED.lesson_id,
                attempt_id = EXCLUDED.attempt_id,
                item_id = EXCLUDED.item_id,
                question_type = EXCLUDED.question_type,
                selected_answer = EXCLUDED.selected_answer,
                correct_answer = EXCLUDED.correct_answer,
                presented_options = EXCLUDED.presented_options,
                question_prompt = EXCLUDED.question_prompt,
                answered_at = EXCLUDED.answered_at,
                bkt_eligible = EXCLUDED.bkt_eligible,
                diagnostic_exposure_id = EXCLUDED.diagnostic_exposure_id,
                bkt_eligibility_errors = EXCLUDED.bkt_eligibility_errors,
                correct = EXCLUDED.correct,
                response_time_ms = EXCLUDED.response_time_ms,
                occurred_at = EXCLUDED.occurred_at,
                quiz_level = EXCLUDED.quiz_level,
                quiz_mode = EXCLUDED.quiz_mode
            """,
            values,
        )


def _ordered_responses(db: Any, student_id: str) -> list[dict[str, Any]]:
    return list(db.execute(
        """
        SELECT id, student_id, word_id, word, lesson_id, quiz_id, attempt_id,
               item_id, question_type, diagnostic_exposure_id, bkt_eligible, correct, response_time_ms, occurred_at,
               attempt_order, quiz_level, quiz_mode
        FROM vocab_quiz_responses
        WHERE student_id = %s
          AND (
            (lower(COALESCE(quiz_level, '')) = 'easy' AND quiz_mode IN ('tier1', 'tier2', 'tier3') AND bkt_eligible = TRUE)
            OR quiz_mode = 'weak_words'
          )
        ORDER BY occurred_at ASC NULLS LAST, id ASC, attempt_order ASC
        """,
        (student_id,),
    ).fetchall())


def rebuild_student_vocabulary_mastery(db: Any, student_id: str, params: BktConfig = BKT_CONFIG) -> None:
    """Rebuild one learner's cache entirely from the raw response ledger."""
    responses = _ordered_responses(db, student_id)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_diagnostic_exposures: set[tuple[str, str]] = set()
    for response in responses:
        exposure_id = response.get("diagnostic_exposure_id")
        if response.get("bkt_eligible") and exposure_id:
            exposure_key = (response["item_id"], exposure_id)
            if exposure_key in seen_diagnostic_exposures:
                continue
            seen_diagnostic_exposures.add(exposure_key)
        grouped[response["word_id"]].append(response)

    db.execute("DELETE FROM student_vocab_mastery WHERE student_id = %s", (student_id,))
    now = datetime.now(timezone.utc).isoformat()
    for word_id, history in grouped.items():
        p_learned = replay_bkt((bool(row["correct"]) for row in history), params)
        last = history[-1]
        correct_count = sum(1 for row in history if row["correct"])
        db.execute(
            """
            INSERT INTO student_vocab_mastery
                (student_id, word_id, p_learned, observation_count, correct_count,
                 incorrect_count, last_response_at, last_item_id, last_question_type,
                 last_lesson_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_id, word_id, p_learned, len(history), correct_count,
                len(history) - correct_count, last["occurred_at"], last["item_id"],
                last["question_type"], last["lesson_id"], now, now,
            ),
        )


def rebuild_all_vocabulary_mastery(db: Any, params: BktConfig = BKT_CONFIG) -> None:
    students = db.execute("SELECT DISTINCT student_id FROM vocab_quiz_responses WHERE student_id IS NOT NULL").fetchall()
    for row in students:
        rebuild_student_vocabulary_mastery(db, row["student_id"], params)


def record_attempt_and_rebuild(db: Any, attempt: Any, student_id: str, params: BktConfig = BKT_CONFIG, response_results: Iterable[Any] | None = None) -> None:
    upsert_raw_responses(db, response_rows_for_attempt(attempt, student_id, response_results))
    rebuild_student_vocabulary_mastery(db, student_id, params)


def _completed_diagnostic_quizzes(db: Any, student_id: str, params: BktConfig = BKT_CONFIG) -> int:
    row = db.execute(
        """
        SELECT COUNT(DISTINCT quiz_mode) AS count
        FROM vocab_quiz_responses
        WHERE student_id = %s AND lower(COALESCE(quiz_level, '')) = 'easy'
          AND quiz_mode IN ('tier1', 'tier2', 'tier3')
          AND bkt_eligible = TRUE
        """,
        (student_id,),
    ).fetchone()
    return min(int(row["count"] if row else 0), params.required_diagnostic_quizzes)


def has_completed_weak_word_diagnostic(db: Any, student_id: str, params: BktConfig = BKT_CONFIG) -> bool:
    """Return whether the learner has completed all validated Easy tier slots."""
    return _completed_diagnostic_quizzes(db, student_id, params) >= params.required_diagnostic_quizzes


def diagnostic_status(db: Any, student_id: str, story_id: str | None = None, params: BktConfig = BKT_CONFIG) -> dict[str, Any]:
    completed = _completed_diagnostic_quizzes(db, student_id, params)
    known = _known_words(db, story_id=story_id)
    # A unit-test or a newly published lesson may not have a row in
    # custom_stories yet. In that narrow case, use the server-validated words
    # already observed for this learner as the temporary coverage universe;
    # never use unvalidated raw attempts to create the universe.
    if not known:
        observed_words = db.execute(
            """
            SELECT DISTINCT word_id, word, lesson_id
            FROM vocab_quiz_responses
            WHERE student_id = %s AND bkt_eligible = TRUE
              AND lower(COALESCE(quiz_level, '')) = 'easy'
              AND quiz_mode IN ('tier1', 'tier2', 'tier3')
            """,
            (student_id,),
        ).fetchall()
        known = {
            row["word_id"]: {
                "word": row["word"],
                "meaning": None,
                "lessonId": row["lesson_id"],
                "lessonNumber": None,
            }
            for row in observed_words
        }
    coverage = {
        row["word_id"]: int(row["count"])
        for row in db.execute(
            """
            SELECT word_id, COUNT(DISTINCT item_id || ':' || COALESCE(diagnostic_exposure_id, quiz_id || ':' || quiz_mode)) AS count
            FROM vocab_quiz_responses
            WHERE student_id = %s AND lower(COALESCE(quiz_level, '')) = 'easy'
              AND quiz_mode IN ('tier1', 'tier2', 'tier3') AND bkt_eligible = TRUE
            GROUP BY word_id
            """,
            (student_id,),
        ).fetchall()
    }
    return {
        # The three validated Easy slots are the unlock gate. Coverage is
        # reported separately so sparse quiz structure does not pretend every
        # published word was assessed; only sufficiently observed words can
        # enter Bottom-K below.
        "unlocked": has_completed_weak_word_diagnostic(db, student_id, params),
        "requiredDiagnosticQuizzes": params.required_diagnostic_quizzes,
        "completedDiagnosticQuizzes": completed,
        "requiredWords": len(known),
        "sufficientWords": sum(value >= params.minimum_observations for value in coverage.values()),
        "wordCoverage": coverage,
    }


def _known_words(db: Any, story_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Read the current published vocabulary pool without inventing evidence."""
    known: dict[str, dict[str, Any]] = {}
    query = "SELECT id, lesson_number, frames FROM custom_stories WHERE published = TRUE"
    params: list[Any] = []
    if story_id:
        query += " AND id = %s"
        # Student topic ids prefix teacher stories while the database stores
        # the underlying story id. Resolve both forms without widening the
        # vocabulary scope to an unrelated story.
        query = "SELECT id, lesson_number, frames FROM custom_stories WHERE published = TRUE AND (id = %s OR %s = 'teacher-' || id OR left(%s, length('teacher-' || id || '-')) = 'teacher-' || id || '-')"
        params = [story_id, story_id, story_id]
    stories = db.execute(query, params).fetchall()
    for story in stories:
        for frame in story.get("frames") or []:
            if not isinstance(frame, dict):
                continue
            words = frame.get("vocabulary") or ""
            translations = frame.get("vocabularyTranslation") or ""
            word_list = [part.strip() for part in words.split(",") if part.strip()] if isinstance(words, str) else []
            meaning_list = [part.strip() for part in translations.split(",") if part.strip()] if isinstance(translations, str) else []
            for index, word in enumerate(word_list):
                known.setdefault(normalize_word_id(word), {
                    "word": word,
                    "meaning": meaning_list[index] if index < len(meaning_list) else None,
                    "lessonId": story_id or story["id"],
                    "lessonNumber": story.get("lesson_number"),
                })
    return known


def get_vocabulary_mastery(db: Any, student_id: str, params: BktConfig = BKT_CONFIG, story_id: str | None = None) -> list[dict[str, Any]]:
    states = {row["word_id"]: dict(row) for row in db.execute(
        "SELECT * FROM student_vocab_mastery WHERE student_id = %s", (student_id,)
    ).fetchall()}
    known = _known_words(db, story_id=story_id)
    raw_words = db.execute(
        "SELECT DISTINCT word_id, word, lesson_id FROM vocab_quiz_responses WHERE student_id = %s",
        (student_id,),
    ).fetchall()
    for row in raw_words:
        if story_id and row.get("lesson_id") not in {story_id}:
            continue
        known.setdefault(row["word_id"], {"word": row["word"], "meaning": None, "lessonId": row["lesson_id"], "lessonNumber": None})

    result: list[dict[str, Any]] = []
    for word_id, word in known.items():
        state = states.get(word_id)
        observations = int(state["observation_count"]) if state else 0
        p_learned = float(state["p_learned"]) if state else params.initial_mastery
        result.append({
            "wordId": word_id,
            "word": word["word"],
            "meaning": word.get("meaning"),
            "pLearned": p_learned,
            "status": mastery_status(observations, p_learned, params=params),
            "observationCount": observations,
            "correctCount": int(state["correct_count"]) if state else 0,
            "incorrectCount": int(state["incorrect_count"]) if state else 0,
            "lastResponseAt": state.get("last_response_at") if state else None,
            "lastItemId": state.get("last_item_id") if state else None,
            "lessonId": word.get("lessonId"),
            "seenQuestionTypes": [],
        })
    seen_types = {
        row["word_id"]: row["types"]
        for row in db.execute(
            """
            SELECT word_id, ARRAY_AGG(DISTINCT question_type) AS types
            FROM vocab_quiz_responses
            WHERE student_id = %s
            GROUP BY word_id
            """,
            (student_id,),
        ).fetchall()
    }
    for row in result:
        row["seenQuestionTypes"] = [value for value in (seen_types.get(row["wordId"]) or []) if value]
    return sorted(result, key=lambda row: (
        row["pLearned"],
        row["observationCount"],
        row["lastResponseAt"] or "",
        row["wordId"],
    ))


def get_priority_review_words(db: Any, student_id: str, options: dict[str, Any] | None = None, params: BktConfig = BKT_CONFIG) -> dict[str, Any]:
    options = options or {}
    review_count = max(1, min(int(options.get("reviewCount", params.review_count)), 50))
    diagnostic = diagnostic_status(db, student_id, story_id=options.get("storyId"), params=params)
    story_id = options.get("storyId")
    mastery = get_vocabulary_mastery(db, student_id, params, story_id=story_id)
    eligible = [row for row in mastery if row["observationCount"] >= params.minimum_observations and row["pLearned"] < params.mastery_threshold]
    selected = eligible[:review_count] if diagnostic["unlocked"] else []
    selected_ids = {row["wordId"] for row in selected}
    for row in mastery:
        row["status"] = mastery_status(row["observationCount"], row["pLearned"], selected_for_review=row["wordId"] in selected_ids, params=params)
    return {**diagnostic, "reviewCount": review_count, "words": selected, "mastery": mastery}


def seen_item_ids(db: Any, student_id: str, word_id: str) -> list[str]:
    rows = db.execute(
        "SELECT item_id FROM vocab_quiz_responses WHERE student_id = %s AND word_id = %s ORDER BY occurred_at ASC NULLS LAST, id ASC",
        (student_id, normalize_word_id(word_id)),
    ).fetchall()
    return [row["item_id"] for row in rows if row.get("item_id")]
