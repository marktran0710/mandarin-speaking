"""Persistence and recommendation helpers for vocabulary BKT state."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
import unicodedata

from psycopg.types.json import Jsonb

from analytics.bkt import BKT_CONFIG, BktConfig, mastery_status, replay_bkt
from analytics.bkt_question_validation import classify_bkt_response


DIAGNOSTIC_MODES = ("tier1", "tier2", "tier3")
DIAGNOSTIC_LEVELS = ("easy", "medium", "hard")


def normalize_word_id(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def canonical_story_id(story_id: str | None) -> str | None:
    """Return the source story id behind a teacher/topic tier id."""
    if not story_id:
        return None
    value = str(story_id).strip()
    if value.startswith("teacher-"):
        value = value[len("teacher-"):]
    for suffix in ("-medium", "-hard"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value or None


def story_scope_ids(story_id: str | None) -> list[str]:
    """All legacy/current ids that represent one story's learning scope."""
    if not story_id:
        return []
    canonical = canonical_story_id(story_id)
    if not canonical:
        return [str(story_id)]
    return sorted({
        str(story_id),
        canonical,
        f"teacher-{canonical}",
        f"teacher-{canonical}-medium",
        f"teacher-{canonical}-hard",
    })


def _lesson_scope_filter(story_id: str | None) -> tuple[str, list[Any]]:
    if not story_id:
        return "", []
    return " AND lesson_id = ANY(%s)", [story_scope_ids(story_id)]


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
            "round_type": result.get("roundType") or result.get("round_type"),
            "knowledge_dimension": result.get("knowledgeDimension") or result.get("knowledge_dimension"),
            "activity_type": result.get("activityType") or ("personalized_practice" if quiz_mode == "weak_words" else "diagnostic" if quiz_mode in DIAGNOSTIC_MODES else "practice"),
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
            "attempt_order", "quiz_level", "quiz_mode", "round_type", "knowledge_dimension", "activity_type",
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
                response_time_ms, occurred_at, attempt_order, quiz_level, quiz_mode,
                round_type, knowledge_dimension, activity_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                quiz_mode = EXCLUDED.quiz_mode,
                round_type = EXCLUDED.round_type,
                knowledge_dimension = EXCLUDED.knowledge_dimension,
                activity_type = EXCLUDED.activity_type
            """,
            values,
        )


def _ordered_responses(db: Any, student_id: str, story_id: str | None = None) -> list[dict[str, Any]]:
    scope_filter, scope_params = _lesson_scope_filter(story_id)
    return list(db.execute(
        f"""
        SELECT id, student_id, word_id, word, lesson_id, quiz_id, attempt_id,
               item_id, question_type, diagnostic_exposure_id, bkt_eligible, correct, response_time_ms, occurred_at,
               attempt_order, quiz_level, quiz_mode, round_type, knowledge_dimension, activity_type
        FROM vocab_quiz_responses
        WHERE student_id = %s
          AND (
            (lower(COALESCE(quiz_level, '')) IN ('easy', 'medium', 'hard') AND quiz_mode IN ('tier1', 'tier2', 'tier3') AND bkt_eligible = TRUE)
            OR quiz_mode = 'weak_words'
          )
          {scope_filter}
        ORDER BY occurred_at ASC NULLS LAST, id ASC, attempt_order ASC
        """,
        [student_id, *scope_params],
    ).fetchall())


def _group_response_history(responses: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
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
    return grouped


def _mastery_states_from_responses(responses: Iterable[dict[str, Any]], params: BktConfig) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for word_id, history in _group_response_history(responses).items():
        p_learned = replay_bkt((bool(row["correct"]) for row in history), params)
        last = history[-1]
        correct_count = sum(1 for row in history if row["correct"])
        states[word_id] = {
            "word_id": word_id,
            "p_learned": p_learned,
            "observation_count": len(history),
            "correct_count": correct_count,
            "incorrect_count": len(history) - correct_count,
            "last_response_at": last["occurred_at"],
            "last_item_id": last["item_id"],
            "last_question_type": last["question_type"],
            "last_lesson_id": last["lesson_id"],
            "seen_question_types": sorted({row["question_type"] for row in history if row.get("question_type")}),
            "failed_question_types": sorted({row["question_type"] for row in history if not row["correct"] and row.get("question_type")}),
            "round_types": sorted({row.get("round_type") for row in history if row.get("round_type")}),
        }
    return states


def rebuild_student_vocabulary_mastery(db: Any, student_id: str, params: BktConfig = BKT_CONFIG) -> None:
    """Rebuild one learner's cache entirely from the raw response ledger."""
    states = _mastery_states_from_responses(_ordered_responses(db, student_id), params)

    db.execute("DELETE FROM student_vocab_mastery WHERE student_id = %s", (student_id,))
    now = datetime.now(timezone.utc).isoformat()
    for state in states.values():
        db.execute(
            """
            INSERT INTO student_vocab_mastery
                (student_id, word_id, p_learned, observation_count, correct_count,
                 incorrect_count, last_response_at, last_item_id, last_question_type,
                 last_lesson_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_id, state["word_id"], state["p_learned"], state["observation_count"], state["correct_count"],
                state["incorrect_count"], state["last_response_at"], state["last_item_id"],
                state["last_question_type"], state["last_lesson_id"], now, now,
            ),
        )


def rebuild_all_vocabulary_mastery(db: Any, params: BktConfig = BKT_CONFIG) -> None:
    students = db.execute("SELECT DISTINCT student_id FROM vocab_quiz_responses WHERE student_id IS NOT NULL").fetchall()
    for row in students:
        rebuild_student_vocabulary_mastery(db, row["student_id"], params)


def record_attempt_and_rebuild(db: Any, attempt: Any, student_id: str, params: BktConfig = BKT_CONFIG, response_results: Iterable[Any] | None = None) -> None:
    upsert_raw_responses(db, response_rows_for_attempt(attempt, student_id, response_results))
    rebuild_student_vocabulary_mastery(db, student_id, params)


def _diagnostic_round_counts(db: Any, student_id: str, story_id: str | None = None) -> dict[str, int]:
    """Return unique lesson words observed in each validated diagnostic round.

    This is kept as a small compatibility helper for callers that only need
    the word counts. Completion uses ``_diagnostic_round_metrics`` below so a
    second exposure of the same word cannot silently satisfy an exact-once
    round.
    """
    return {
        mode: metrics["word_count"]
        for mode, metrics in _diagnostic_round_metrics(db, student_id, story_id).items()
    }


def _diagnostic_round_metrics(db: Any, student_id: str, story_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Summarize validated round evidence and clean completed runs.

    A learner can retry a failed round. Aggregating every retry into one
    global observation count would make the round permanently incomplete
    after the first retry (N words would become 2N observations). Keep the
    aggregate counts for reporting, but also retain per-quiz run coverage so
    completion can be satisfied by one clean, complete run.
    """
    scope_filter, scope_params = _lesson_scope_filter(story_id)
    rows = db.execute(
        f"""
        SELECT quiz_mode, quiz_id, word_id, item_id, diagnostic_exposure_id
        FROM vocab_quiz_responses
        WHERE student_id = %s AND lower(COALESCE(quiz_level, '')) IN ('easy', 'medium', 'hard')
          AND quiz_mode IN ('tier1', 'tier2', 'tier3')
          AND bkt_eligible = TRUE
          {scope_filter}
        ORDER BY quiz_mode, quiz_id, id ASC
        """,
        [student_id, *scope_params],
    ).fetchall()
    modes: dict[str, dict[str, Any]] = {}
    for row in rows:
        mode = row["quiz_mode"]
        metric = modes.setdefault(mode, {
            "word_ids": set(),
            "observations": set(),
            "runs": {},
        })
        word_id = row["word_id"]
        observation = (word_id, row["item_id"], row["diagnostic_exposure_id"])
        metric["word_ids"].add(word_id)
        metric["observations"].add(observation)
        run_id = row["quiz_id"] or f"row:{row['id']}"
        run = metric["runs"].setdefault(run_id, {"word_ids": set(), "observations": set()})
        run["word_ids"].add(word_id)
        run["observations"].add(observation)

    return {
        mode: {
            "word_count": len(metric["word_ids"]),
            "observation_count": len(metric["observations"]),
            "runs": [
                {
                    "word_ids": set(run["word_ids"]),
                    "word_count": len(run["word_ids"]),
                    "observation_count": len(run["observations"]),
                }
                for run in metric["runs"].values()
            ],
        }
        for mode, metric in modes.items()
    }


def _round_has_complete_run(
    metrics: dict[str, dict[str, Any]],
    mode: str,
    known_word_ids: set[str] | None,
    known_count: int,
) -> bool:
    """Return whether one quiz run covered every lesson word exactly once."""
    for run in metrics.get(mode, {}).get("runs", []):
        if run["word_count"] != known_count or run["observation_count"] != known_count:
            continue
        if known_word_ids is None or run["word_ids"] == known_word_ids:
            return True
    return False


def _completed_diagnostic_quizzes(db: Any, student_id: str, story_id: str | None = None, params: BktConfig = BKT_CONFIG) -> int:
    metrics = _diagnostic_round_metrics(db, student_id, story_id)
    known = _known_words(db, story_id=story_id)
    known_word_ids = set(known) if known else None
    known_count = len(known)
    if not known_count:
        known_count = max((value["word_count"] for value in metrics.values()), default=0)
    completed = sum(
        1
        for mode in DIAGNOSTIC_MODES
        if known_count > 0
        and _round_has_complete_run(metrics, mode, known_word_ids, known_count)
    )
    return min(completed, params.required_diagnostic_quizzes)


def has_completed_weak_word_diagnostic(db: Any, student_id: str, params: BktConfig = BKT_CONFIG) -> bool:
    """Return whether all three validated diagnostic rounds are complete."""
    return _completed_diagnostic_quizzes(db, student_id, params=params) >= params.required_diagnostic_quizzes


def diagnostic_status(db: Any, student_id: str, story_id: str | None = None, params: BktConfig = BKT_CONFIG) -> dict[str, Any]:
    round_metrics = _diagnostic_round_metrics(db, student_id, story_id)
    known = _known_words(db, story_id=story_id)
    # A unit-test or a newly published lesson may not have a row in
    # custom_stories yet. In that narrow case, use the server-validated words
    # already observed for this learner as the temporary coverage universe;
    # never use unvalidated raw attempts to create the universe.
    if not known:
        scope_filter, scope_params = _lesson_scope_filter(story_id)
        observed_words = db.execute(
            f"""
            SELECT DISTINCT word_id, word, lesson_id
            FROM vocab_quiz_responses
            WHERE student_id = %s AND bkt_eligible = TRUE
              AND lower(COALESCE(quiz_level, '')) IN ('easy', 'medium', 'hard')
              AND quiz_mode IN ('tier1', 'tier2', 'tier3')
              {scope_filter}
            """,
            [student_id, *scope_params],
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
    known_word_ids = set(known)
    known_count = len(known)
    completed = _completed_diagnostic_quizzes(db, student_id, story_id=story_id, params=params)
    scope_filter, scope_params = _lesson_scope_filter(story_id)
    coverage = {
        row["word_id"]: int(row["count"])
        for row in db.execute(
            f"""
            SELECT word_id, COUNT(DISTINCT item_id || ':' || COALESCE(diagnostic_exposure_id, quiz_id || ':' || quiz_mode)) AS count
            FROM vocab_quiz_responses
            WHERE student_id = %s AND lower(COALESCE(quiz_level, '')) IN ('easy', 'medium', 'hard')
              AND quiz_mode IN ('tier1', 'tier2', 'tier3') AND bkt_eligible = TRUE
              {scope_filter}
            GROUP BY word_id
            """,
            [student_id, *scope_params],
        ).fetchall()
    }
    return {
        # A round is complete only after every lesson word has one validated
        # response in that round. This keeps partial attempts visible without
        # treating them as final weak-word classifications.
        "unlocked": completed >= params.required_diagnostic_quizzes,
        "requiredDiagnosticQuizzes": params.required_diagnostic_quizzes,
        "completedDiagnosticQuizzes": completed,
        "requiredWords": len(known),
        "sufficientWords": sum(value >= params.minimum_observations for value in coverage.values()),
        "wordCoverage": coverage,
        "roundPresence": {
            mode: {
                "level": DIAGNOSTIC_LEVELS[index],
                "roundType": ("know_it", "say_it", "use_it")[index],
                "observedWords": round_metrics.get(mode, {}).get("word_count", 0),
                "observations": round_metrics.get(mode, {}).get("observation_count", 0),
                "complete": known_count > 0 and _round_has_complete_run(round_metrics, mode, known_word_ids, known_count),
            }
            for index, mode in enumerate(DIAGNOSTIC_MODES)
        },
    }


def _known_words(db: Any, story_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Read the current published vocabulary pool without inventing evidence."""
    known: dict[str, dict[str, Any]] = {}
    query = "SELECT id, lesson_number, frames, story_vocabulary, vocab_assessment FROM custom_stories WHERE published = TRUE"
    params: list[Any] = []
    if story_id:
        canonical = canonical_story_id(story_id)
        query += " AND (id = %s OR id = %s)"
        params = [canonical or story_id, story_id]
    stories = db.execute(query, params).fetchall()
    for story in stories:
        assessment_word_ids = {
            normalize_word_id(item.get("targetWord")): item.get("wordId")
            for item in (story.get("vocab_assessment") or [])
            if isinstance(item, dict) and item.get("targetWord") and item.get("wordId")
        }

        def add_words(raw_words: Any, raw_translations: Any) -> None:
            word_list = [part.strip() for part in raw_words.split(",") if part.strip()] if isinstance(raw_words, str) else []
            meaning_list = [part.strip() for part in raw_translations.split(",") if part.strip()] if isinstance(raw_translations, str) else []
            for index, word in enumerate(word_list):
                word_id = assessment_word_ids.get(normalize_word_id(word), normalize_word_id(word))
                known.setdefault(word_id, {
                    "word": word,
                    "meaning": meaning_list[index] if index < len(meaning_list) else None,
                    "lessonId": story["id"],
                    "lessonNumber": story.get("lesson_number"),
                })

        for item in (story.get("vocab_assessment") or []):
            if isinstance(item, dict) and item.get("wordId") and item.get("targetWord"):
                known.setdefault(str(item["wordId"]), {
                    "word": item["targetWord"],
                    "meaning": item.get("simpleEnglishMeaning"),
                    "lessonId": story["id"],
                    "lessonNumber": story.get("lesson_number"),
                })

        for frame in story.get("frames") or []:
            if not isinstance(frame, dict):
                continue
            for suffix in ("", "Medium", "Hard"):
                add_words(frame.get(f"vocabulary{suffix}"), frame.get(f"vocabularyTranslation{suffix}"))
        for tier_content in (story.get("story_vocabulary") or {}).values():
            if isinstance(tier_content, dict):
                add_words(tier_content.get("vocabulary"), tier_content.get("vocabularyTranslation"))
    return known


def get_vocabulary_mastery(db: Any, student_id: str, params: BktConfig = BKT_CONFIG, story_id: str | None = None) -> list[dict[str, Any]]:
    diagnostic_complete = _completed_diagnostic_quizzes(db, student_id, story_id=story_id, params=params) >= params.required_diagnostic_quizzes
    if story_id:
        # The cache is intentionally pooled for the dashboard, but a story
        # review must replay this story's full ledger so one identical word
        # in another story cannot change this story's weak-word decision.
        states = _mastery_states_from_responses(_ordered_responses(db, student_id, story_id=story_id), params)
    else:
        states = {row["word_id"]: dict(row) for row in db.execute(
            "SELECT * FROM student_vocab_mastery WHERE student_id = %s", (student_id,)
        ).fetchall()}
    known = _known_words(db, story_id=story_id)
    scope_filter, scope_params = _lesson_scope_filter(story_id)
    raw_words = db.execute(
        f"""
        SELECT word_id, word, lesson_id,
               ARRAY_AGG(DISTINCT round_type) FILTER (WHERE round_type IS NOT NULL) AS round_types
        FROM vocab_quiz_responses
        WHERE student_id = %s{scope_filter}
        GROUP BY word_id, word, lesson_id
        """,
        [student_id, *scope_params],
    ).fetchall()
    for row in raw_words:
        known.setdefault(row["word_id"], {
            "word": row["word"],
            "meaning": None,
            "lessonId": row["lesson_id"],
            "lessonNumber": None,
        })
        if not story_id and row.get("round_types"):
            cached = states.get(row["word_id"])
            if cached is not None:
                cached["round_types"] = sorted({value for value in row["round_types"] if value})

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
            "status": mastery_status(observations, p_learned, params=params) if diagnostic_complete else "UNASSESSED",
            "observationCount": observations,
            "correctCount": int(state["correct_count"]) if state else 0,
            "incorrectCount": int(state["incorrect_count"]) if state else 0,
            "lastResponseAt": state.get("last_response_at") if state else None,
            "lastItemId": state.get("last_item_id") if state else None,
            "lessonId": word.get("lessonId"),
            "seenQuestionTypes": [],
            "failedQuestionTypes": [],
            "roundTypes": state.get("round_types", []) if state else [],
        })
    seen_types = {
        row["word_id"]: row
        for row in db.execute(
            f"""
            SELECT word_id,
                   ARRAY_AGG(DISTINCT question_type) AS types,
                   ARRAY_AGG(DISTINCT question_type) FILTER (WHERE correct = FALSE) AS failed_types
            FROM vocab_quiz_responses
            WHERE student_id = %s
              {scope_filter}
            GROUP BY word_id
            """,
            [student_id, *scope_params],
        ).fetchall()
    }
    for row in result:
        observed = seen_types.get(row["wordId"]) or {}
        row["seenQuestionTypes"] = [value for value in (observed.get("types") or []) if value]
        row["failedQuestionTypes"] = [value for value in (observed.get("failed_types") or []) if value]
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
    include_all_weak = bool(options.get("includeAllWeak"))
    eligible = [row for row in mastery if row["pLearned"] < params.mastery_threshold and row["observationCount"] >= params.minimum_observations]
    # Final weak-word recommendations require all three diagnostic rounds.
    # Partial answers remain in the ledger and are reported as UNASSESSED, but
    # cannot accidentally open personalized practice early.
    if not diagnostic["unlocked"]:
        eligible = []
    eligible.sort(key=lambda row: (
        0 if row.get("failedQuestionTypes") else 1,
        len(row.get("seenQuestionTypes") or []),
        row["pLearned"],
        row["lastResponseAt"] or "",
        row["wordId"],
    ))
    selected = eligible if include_all_weak else eligible[:review_count]
    selected_ids = {row["wordId"] for row in selected}
    for row in mastery:
        row["status"] = "UNASSESSED" if not diagnostic["unlocked"] else mastery_status(row["observationCount"], row["pLearned"], selected_for_review=row["wordId"] in selected_ids, params=params)
    return {**diagnostic, "reviewCount": review_count, "words": selected, "mastery": mastery}


def seen_item_ids(db: Any, student_id: str, word_id: str) -> list[str]:
    rows = db.execute(
        "SELECT item_id FROM vocab_quiz_responses WHERE student_id = %s AND word_id = %s ORDER BY occurred_at ASC NULLS LAST, id ASC",
        (student_id, normalize_word_id(word_id)),
    ).fetchall()
    return [row["item_id"] for row in rows if row.get("item_id")]
