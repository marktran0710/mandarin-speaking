"""Integration tests for application/research_practice_session.py (Epic 4)."""
import pytest
from psycopg.types.json import Jsonb

import db
from application.research.practice_session import ResearchPracticeUnavailableError, build_practice_session
from repositories import research as repo


def _create_study(study_id: str, status: str = "active", practice_budget: int = 8) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status,
            config_json={"practiceBudget": practice_budget},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str, active: bool = True) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=active, created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id: str, student_id: str, word_id: str, bkt_policy: str, retention_policy: str) -> None:
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="lesson-5", section_id=None, bkt_policy=bkt_policy, retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _seed_response(
    *, student_id: str, word_id: str, quiz_id: str, attempt_order: int, correct: bool,
    quiz_mode: str, research_study_id: str | None = None, occurred_at: str = "2026-01-01T00:00:00Z",
) -> None:
    """Insert directly into the ledger - bypasses the resolver so tests can
    control exactly which evidence exists without re-deriving a whole
    published-assessment fixture for every scenario."""
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO vocab_quiz_responses
                (student_id, word_id, word, lesson_id, quiz_id, attempt_id, item_id, question_type,
                 presented_options, correct, response_time_ms, occurred_at, occurred_at_utc,
                 attempt_order, quiz_level, quiz_mode, bkt_eligible, research_study_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_id, word_id, word_id, "lesson-5", quiz_id, quiz_id,
                f"{word_id}:item:v1", "basic_meaning_mcq", Jsonb([]), correct, 1000,
                occurred_at, occurred_at, attempt_order, quiz_mode if quiz_mode in ("tier1", "tier2", "tier3") else None,
                quiz_mode, quiz_mode in ("tier1", "tier2", "tier3"), research_study_id,
            ),
        )


def test_raises_for_a_non_participant():
    with db.connect_db() as conn:
        with pytest.raises(ResearchPracticeUnavailableError):
            build_practice_session(conn, "no-such-student")


def test_raises_for_a_deactivated_participant():
    _create_study("study-inactive-participant")
    _add_participant("study-inactive-participant", "student-1", active=False)
    with db.connect_db() as conn:
        with pytest.raises(ResearchPracticeUnavailableError):
            build_practice_session(conn, "student-1")


def test_splits_the_configured_budget_evenly_across_all_four_conditions():
    _create_study("study-4cond", practice_budget=8)
    _add_participant("study-4cond", "student-1")
    # Two words per condition so each condition's 2-slot allocation has
    # exactly enough candidates without truncation ambiguity.
    for index, (bkt_policy, retention_policy) in enumerate([
        ("mastery_blind", "yoked"), ("mastery_blind", "yoked"),
        ("bkt_personalized", "yoked"), ("bkt_personalized", "yoked"),
        ("mastery_blind", "adaptive_sm2"), ("mastery_blind", "adaptive_sm2"),
        ("bkt_personalized", "adaptive_sm2"), ("bkt_personalized", "adaptive_sm2"),
    ]):
        _assign("study-4cond", "student-1", f"word-{index}", bkt_policy, retention_policy)

    with db.connect_db() as conn:
        session = build_practice_session(conn, "student-1")

    assert len(session["wordIds"]) == 8
    assert len(set(session["wordIds"])) == 8  # no word picked twice


def test_bkt_personalized_condition_picks_the_lowest_p_learned_word_first():
    _create_study("study-bkt-rank", practice_budget=1)
    _add_participant("study-bkt-rank", "student-1")
    _assign("study-bkt-rank", "student-1", "word-weak", "bkt_personalized", "yoked")
    _assign("study-bkt-rank", "student-1", "word-strong", "bkt_personalized", "yoked")
    # word-strong gets three correct diagnostic answers (high p_learned);
    # word-weak gets none (stays at the model's low prior). With budget=1 and
    # only this one condition present, the single slot must go to word-weak.
    for order, correct in enumerate([True, True, True]):
        _seed_response(
            student_id="student-1", word_id="word-strong", quiz_id=f"q{order}",
            attempt_order=order, correct=correct, quiz_mode="tier1",
        )

    with db.connect_db() as conn:
        session = build_practice_session(conn, "student-1")

    assert session["wordIds"] == ["word-weak"]


def test_bkt_personalized_selection_persists_a_treatment_bkt_state_snapshot():
    _create_study("study-bkt-persist", practice_budget=1)
    _add_participant("study-bkt-persist", "student-1")
    _assign("study-bkt-persist", "student-1", "word-a", "bkt_personalized", "yoked")

    with db.connect_db() as conn:
        build_practice_session(conn, "student-1")
        row = conn.execute(
            "SELECT * FROM vocab_research_bkt_state WHERE student_id = %s AND study_id = %s AND word_id = %s",
            ("student-1", "study-bkt-persist", "word-a"),
        ).fetchone()
    assert row is not None
    assert row["p_learned"] is not None


def test_mastery_blind_condition_never_writes_a_treatment_bkt_state_row():
    _create_study("study-blind-no-state", practice_budget=1)
    _add_participant("study-blind-no-state", "student-1")
    _assign("study-blind-no-state", "student-1", "word-a", "mastery_blind", "yoked")

    with db.connect_db() as conn:
        build_practice_session(conn, "student-1")
        rows = conn.execute(
            "SELECT * FROM vocab_research_bkt_state WHERE student_id = %s AND study_id = %s",
            ("student-1", "study-blind-no-state"),
        ).fetchall()
    assert rows == []


def test_mastery_blind_condition_picks_the_least_exposed_word_regardless_of_correctness():
    _create_study("study-blind-rotate", practice_budget=1)
    _add_participant("study-blind-rotate", "student-1")
    _assign("study-blind-rotate", "student-1", "word-many-wrong", "mastery_blind", "yoked")
    _assign("study-blind-rotate", "student-1", "word-unseen", "mastery_blind", "yoked")
    # word-many-wrong has heavy prior practice exposure (bad candidate for
    # rotation) but is answered CORRECTLY every time - if correctness leaked
    # into the blind selector this word would look "needs more practice" and
    # get picked. It must not: rotation goes purely by exposure count, so the
    # never-practiced word wins regardless of the other word's accuracy.
    for order in range(3):
        _seed_response(
            student_id="student-1", word_id="word-many-wrong", quiz_id=f"blind-{order}",
            attempt_order=order, correct=True, quiz_mode="weak_words",
            research_study_id="study-blind-rotate",
        )

    with db.connect_db() as conn:
        session = build_practice_session(conn, "student-1")

    assert session["wordIds"] == ["word-unseen"]


def test_treatment_bkt_ignores_production_weak_words_evidence_from_outside_the_study():
    _create_study("study-scope-a", practice_budget=1)
    _add_participant("study-scope-a", "student-1")
    _assign("study-scope-a", "student-1", "word-a", "bkt_personalized", "yoked")
    _assign("study-scope-a", "student-1", "word-b", "bkt_personalized", "yoked")
    # word-a has "strong" evidence, but tagged for a DIFFERENT study (or
    # production practice, research_study_id NULL) - none of it may count
    # toward this study's treatment replay, so word-a must still look
    # untouched (prior mastery) and be picked over word-b's real bad answer.
    for order in range(5):
        _seed_response(
            student_id="student-1", word_id="word-a", quiz_id=f"other-{order}",
            attempt_order=order, correct=True, quiz_mode="weak_words",
            research_study_id="study-scope-other",
        )
    _seed_response(
        student_id="student-1", word_id="word-b", quiz_id="own-0",
        attempt_order=0, correct=False, quiz_mode="weak_words",
        research_study_id="study-scope-a",
    )

    with db.connect_db() as conn:
        session = build_practice_session(conn, "student-1")

    assert session["wordIds"] == ["word-b"]


def test_a_condition_with_no_assigned_words_gets_no_slots_and_others_stay_correct():
    _create_study("study-partial", practice_budget=4)
    _add_participant("study-partial", "student-1")
    # Only two of the four conditions have any assigned words for this
    # student - the other two contribute zero candidates and zero slots
    # rather than the budget going unused or crashing.
    _assign("study-partial", "student-1", "word-c1", "mastery_blind", "yoked")
    _assign("study-partial", "student-1", "word-c2", "bkt_personalized", "yoked")

    with db.connect_db() as conn:
        session = build_practice_session(conn, "student-1")

    assert set(session["wordIds"]) == {"word-c1", "word-c2"}
