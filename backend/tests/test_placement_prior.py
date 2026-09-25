from datetime import datetime, timezone

import pytest
from psycopg.types.json import Jsonb

import db
from analytics.learner_model.bkt.core import BKT_CONFIG, replay_bkt_typed, update_bkt
from analytics.learner_model.bkt.mastery import (
    _mastery_states_from_responses,
    _treatment_ordered_responses,
    get_vocabulary_mastery,
    rebuild_student_vocabulary_mastery,
    upsert_raw_responses,
)
from analytics.learner_model.bkt.placement_prior import (
    PLACEMENT_PRIOR_SHRINKAGE_K,
    compute_chapter_placement_priors,
    get_published_word_chapters,
)
from analytics.learner_model.vocabulary_state import build_vocabulary_state


def _placement_rows(chapter: int, correct_count: int, *, origin: str = "real") -> list[dict]:
    return [
        {
            "chapter": chapter,
            "item_id": f"placement-{chapter}-{index}",
            "correct": index <= correct_count,
            "bkt_eligible": True,
            "activity_type": "diagnostic",
            "diagnostic_exposure_id": f"placement:attempt-{chapter}:Q{index}",
            "evidence_origin": origin,
            "resolver_version": "placement-assessment-v1",
        }
        for index in range(1, 8)
    ]


def _history_row(
    word_id: str,
    correct: bool,
    item_id: str,
    *,
    placement: bool = False,
) -> dict:
    return {
        "word_id": word_id,
        "correct": correct,
        "item_id": item_id,
        "question_type": "basic_meaning_mcq",
        "occurred_at": "2026-09-25T00:00:00+00:00",
        "lesson_id": "story-5",
        "round_type": "meaning",
        "bkt_eligible": True,
        "activity_type": "diagnostic",
        "diagnostic_exposure_id": f"placement:attempt:{item_id}" if placement else None,
        "evidence_origin": "real" if placement else None,
        "resolver_version": "placement-assessment-v1" if placement else None,
    }


def test_chapter_priors_use_shrinkage_and_remain_chapter_specific():
    priors = compute_chapter_placement_priors(
        _placement_rows(5, 6) + _placement_rows(8, 2),
    )

    expected_ch5 = 0.5 * (6 / 7) + 0.5 * BKT_CONFIG.initial_mastery
    expected_ch8 = 0.5 * (2 / 7) + 0.5 * BKT_CONFIG.initial_mastery
    assert PLACEMENT_PRIOR_SHRINKAGE_K == 7.0
    assert priors[5] == pytest.approx(expected_ch5)
    assert priors[8] == pytest.approx(expected_ch8)
    assert priors[5] > priors[8]


def test_mixed_origin_or_incomplete_chapter_falls_back_without_mixing():
    assert compute_chapter_placement_priors(
        _placement_rows(5, 6) + _placement_rows(5, 2, origin="synthetic")
    ) == {}
    assert compute_chapter_placement_priors(_placement_rows(5, 6)[:6]) == {}
    assert compute_chapter_placement_priors([]) == {}


def test_custom_initial_mastery_is_used_once_for_first_observation():
    prior = 0.53
    history = [
        _history_row("word-5", True, "practice-1"),
        _history_row("word-5", False, "practice-2"),
    ]
    states = _mastery_states_from_responses(
        history,
        BKT_CONFIG,
        initial_priors_by_word={"word-5": prior},
    )

    expected = replay_bkt_typed(
        [(True, "basic_meaning_mcq"), (False, "basic_meaning_mcq")],
        initial_mastery=prior,
    )
    reset_each_time = update_bkt(prior, False)
    assert states["word-5"]["p_learned"] == pytest.approx(expected)
    assert states["word-5"]["p_learned"] != pytest.approx(reset_each_time)


def test_directly_tested_word_uses_normal_global_replay():
    history = [_history_row("word-5", True, "placement-1", placement=True)]
    states = _mastery_states_from_responses(
        history,
        BKT_CONFIG,
        initial_priors_by_word={"word-5": 0.53},
    )

    assert states["word-5"]["p_learned"] == pytest.approx(
        update_bkt(BKT_CONFIG.initial_mastery, True),
    )


def test_prior_only_state_is_unassessed_and_not_scheduled():
    state = build_vocabulary_state(
        history=[],
        p_learned=0.53,
        observation_count=0,
        diagnostic_complete=True,
        mastery_threshold=BKT_CONFIG.mastery_threshold,
        minimum_observations=BKT_CONFIG.minimum_observations,
        model_version="test-bkt",
        parameter_fingerprint="test-fingerprint",
    )

    assert state["bkt"]["status"] == "UNASSESSED"
    assert state["review"] == {"status": "NOT_ASSESSED", "candidate": False}
    assert state["scheduling"]["status"] == "NOT_SCHEDULED"


class _StoryDb:
    def __init__(self, stories):
        self.stories = stories

    def execute(self, query, params=()):
        assert "FROM custom_stories" in query
        return _Rows(self.stories)


class _Rows(list):
    def fetchall(self):
        return self


def test_word_chapter_mapping_uses_canonical_story_metadata_not_word_id_parsing():
    db_stub = _StoryDb([
        {
            "id": "story-c5",
            "lesson_number": 5,
            "frames": [],
            "story_vocabulary": {},
            "vocab_assessment": [{"wordId": "W037", "targetWord": "你好"}],
            "published": True,
        },
    ])

    assert get_published_word_chapters(db_stub, ["W037", "lesson-5-1"]) == {"W037": 5}


def _insert_story(conn, story_id: str, chapter: int, word_ids: list[str]) -> None:
    assessment = [
        {
            "questionId": f"{word_id}:question",
            "wordId": word_id,
            "targetWord": word_id,
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
            "correctAnswer": "yes",
            "acceptedAnswers": ["yes"],
            "options": ["yes", "no"],
        }
        for word_id in word_ids
    ]
    conn.execute(
        """
        INSERT INTO custom_stories (id, title, frames, published, lesson_number, vocab_assessment)
        VALUES (%s, %s, %s, TRUE, %s, %s)
        """,
        (story_id, f"Placement Chapter {chapter}", Jsonb([]), chapter, Jsonb(assessment)),
    )


def _insert_placement_attempt(
    conn,
    student_id: str,
    chapter: int,
    story_id: str,
    correct_count: int,
    *,
    evidence_origin: str = "real",
) -> None:
    attempt_id = f"placement-{student_id}-{chapter}"
    now = "2026-09-25T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO placement_test_attempts
            (id, student_id, blueprint_revision, question_snapshot,
             response_snapshot, status, started_at, completed_at,
             total_questions, correct_count, total_time_ms, created_at, updated_at)
        VALUES (%s, %s, 1, %s, %s, 'completed', %s, %s, 7, %s, 7000, %s, %s)
        """,
        (attempt_id, student_id, Jsonb([]), Jsonb([]), now, now, correct_count, now, now),
    )
    rows = []
    for index in range(1, 8):
        item_id = f"placement-{chapter}-{index}"
        rows.append({
            "student_id": student_id,
            "word_id": f"{story_id}-tested-{index}",
            "word": f"{story_id}-tested-{index}",
            "lesson_id": story_id,
            "quiz_id": attempt_id,
            "attempt_id": attempt_id,
            "item_id": item_id,
            "question_type": "basic_meaning_mcq",
            "selected_answer": "yes" if index <= correct_count else "no",
            "correct_answer": "yes",
            "presented_options": ["yes", "no"],
            "question_prompt": "Placement question",
            "answered_at": now,
            "bkt_eligible": True,
            "diagnostic_exposure_id": f"placement:{attempt_id}:{item_id}",
            "bkt_eligibility_errors": [],
            "correct": index <= correct_count,
            "response_time_ms": 1000,
            "occurred_at": now,
            "occurred_at_utc": datetime(2026, 9, 25, tzinfo=timezone.utc),
            "evidence_origin": evidence_origin,
            "resolver_version": (
                "placement-assessment-v1"
                if evidence_origin == "real"
                else "placement-workbook-import-v1"
            ),
            "attempt_order": index - 1,
            "quiz_level": "tier1",
            "quiz_mode": "tier1",
            "round_type": "meaning",
            "knowledge_dimension": "meaning",
            "activity_type": "diagnostic",
            "research_study_id": None,
        })
    upsert_raw_responses(conn, rows)


def test_mastery_projection_uses_dynamic_prior_and_keeps_unseen_words_out_of_cache():
    student_id = "placement-prior-student"
    with db.connect_db() as conn:
        _insert_story(conn, "story-c5", 5, [
            "story-c5-tested-1", "story-c5-tested-2", "story-c5-tested-3",
            "story-c5-tested-4", "story-c5-tested-5", "story-c5-tested-6",
            "story-c5-tested-7", "story-c5-unseen",
        ])
        _insert_story(conn, "story-c8", 8, [
            "story-c8-tested-1", "story-c8-tested-2", "story-c8-tested-3",
            "story-c8-tested-4", "story-c8-tested-5", "story-c8-tested-6",
            "story-c8-tested-7", "story-c8-unseen",
        ])
        _insert_placement_attempt(conn, student_id, 5, "story-c5", 6)
        _insert_placement_attempt(conn, student_id, 8, "story-c8", 2)
        rebuild_student_vocabulary_mastery(conn, student_id)

        fallback = get_vocabulary_mastery(conn, "student-without-placement")
        mastery = get_vocabulary_mastery(conn, student_id)
        fallback_unseen = next(row for row in fallback if row["wordId"] == "story-c5-unseen")
        by_id = {row["wordId"]: row for row in mastery}
        unseen_c5 = by_id["story-c5-unseen"]
        unseen_c8 = by_id["story-c8-unseen"]
        tested_c5 = by_id["story-c5-tested-1"]
        cache_row = conn.execute(
            "SELECT 1 FROM student_vocab_mastery WHERE student_id = %s AND word_id = %s",
            (student_id, "story-c5-unseen"),
        ).fetchone()
        srs_row = conn.execute(
            "SELECT 1 FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student_id, "story-c5-unseen"),
        ).fetchone()

    assert fallback_unseen["pLearned"] == pytest.approx(BKT_CONFIG.initial_mastery)
    assert fallback_unseen["observationCount"] == 0
    assert unseen_c5["pLearned"] == pytest.approx(0.5 * (6 / 7) + 0.5 * 0.20)
    assert unseen_c8["pLearned"] == pytest.approx(0.5 * (2 / 7) + 0.5 * 0.20)
    assert unseen_c5["pLearned"] > unseen_c8["pLearned"]
    assert unseen_c5["observationCount"] == 0
    assert unseen_c5["correctCount"] == 0
    assert unseen_c5["incorrectCount"] == 0
    assert unseen_c5["lastResponseAt"] is None
    assert unseen_c5["status"] == "NOT_ASSESSED"
    assert cache_row is None
    assert srs_row is None
    assert tested_c5["observationCount"] == 1
    assert tested_c5["pLearned"] == pytest.approx(update_bkt(0.20, True))


def test_synthetic_placement_is_excluded_from_real_treatment_replay():
    with db.connect_db() as conn:
        _insert_placement_attempt(
            conn,
            "synthetic-research-student",
            5,
            "synthetic-story-c5",
            6,
            evidence_origin="synthetic",
        )

        rows = _treatment_ordered_responses(
            conn,
            "synthetic-research-student",
            "real-study",
        )

    assert rows == []
