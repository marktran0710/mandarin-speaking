"""Integration tests for application/research_probes.py (Epic 7)."""
from datetime import datetime, timedelta, timezone

import pytest

import db
from application.research.probes import (
    PROBE_TYPES,
    ResearchProbeAssignmentNotFoundError,
    ResearchProbeUnavailableError,
    build_due_probes,
    enroll_section_probes,
    submit_probe_response,
)
from repositories import research as repo


def _create_study(study_id: str, status: str = "active") -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status, config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=True, created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id, student_id, word_id, *, section_id="s"):
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id=section_id, bkt_policy="mastery_blind", retention_policy="adaptive_sm2",
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _insert_item(study_id: str, word_id: str, assessment_type: str, *, item_id: str | None = None, correct_answer="A") -> str:
    item_id = item_id or f"item-{study_id}-{word_id}-{assessment_type}"
    with db.connect_db() as conn:
        repo.insert_assessment_item(
            conn, id=item_id, study_id=study_id, word_id=word_id, assessment_type=assessment_type,
            question_type="mc_translation", prompt=f"What does {word_id} mean?",
            choices=["A", "B", "C"], correct_answer=correct_answer, created_at="2026-01-01T00:00:00Z",
        )
    return item_id


def _insert_item_for_every_probe_type(study_id: str, word_id: str) -> None:
    for probe_type in PROBE_TYPES:
        _insert_item(study_id, word_id, probe_type)


def _probe_assignments(student_id: str, study_id: str) -> list[dict]:
    with db.connect_db() as conn:
        return conn.execute(
            "SELECT * FROM vocab_research_probe_assignments WHERE student_id = %s AND study_id = %s ORDER BY word_id",
            (student_id, study_id),
        ).fetchall()


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestEnrollSectionProbes:
    def test_schedules_every_assigned_word_that_has_a_bank_item(self):
        _create_study("study-probe-enroll")
        for word_id in ("word-a", "word-b", "word-c"):
            _assign("study-probe-enroll", "student-1", word_id)
            _insert_item_for_every_probe_type("study-probe-enroll", word_id)

        with db.connect_db() as conn:
            scheduled = enroll_section_probes(conn, "student-1", "study-probe-enroll", "s", now=NOW)
        rows = _probe_assignments("student-1", "study-probe-enroll")

        assert scheduled == 3
        assert {row["word_id"] for row in rows} == {"word-a", "word-b", "word-c"}

    def test_skips_a_word_with_no_bank_item(self):
        _create_study("study-probe-skip")
        _assign("study-probe-skip", "student-1", "word-with-item")
        _insert_item_for_every_probe_type("study-probe-skip", "word-with-item")
        _assign("study-probe-skip", "student-1", "word-without-item")

        with db.connect_db() as conn:
            scheduled = enroll_section_probes(conn, "student-1", "study-probe-skip", "s", now=NOW)
        rows = _probe_assignments("student-1", "study-probe-skip")

        assert scheduled == 1
        assert {row["word_id"] for row in rows} == {"word-with-item"}

    def test_is_idempotent_and_never_reschedules_an_existing_word(self):
        _create_study("study-probe-idempotent")
        _assign("study-probe-idempotent", "student-1", "word-a")
        _insert_item_for_every_probe_type("study-probe-idempotent", "word-a")

        with db.connect_db() as conn:
            first = enroll_section_probes(conn, "student-1", "study-probe-idempotent", "s", now=NOW)
            second = enroll_section_probes(conn, "student-1", "study-probe-idempotent", "s", now=NOW + timedelta(days=5))

        assert first == 1
        assert second == 0

    def test_only_schedules_words_from_the_target_section(self):
        _create_study("study-probe-scoped")
        _assign("study-probe-scoped", "student-1", "word-here", section_id="story-5-1")
        _insert_item_for_every_probe_type("study-probe-scoped", "word-here")
        _assign("study-probe-scoped", "student-1", "word-elsewhere", section_id="story-5-2")
        _insert_item_for_every_probe_type("study-probe-scoped", "word-elsewhere")

        with db.connect_db() as conn:
            enroll_section_probes(conn, "student-1", "study-probe-scoped", "story-5-1", now=NOW)
        rows = _probe_assignments("student-1", "study-probe-scoped")

        assert {row["word_id"] for row in rows} == {"word-here"}

    def test_each_word_lands_in_exactly_one_disjoint_probe_pool(self):
        # Task 7.7: a word is never both a 7-day AND a 21-day (or final)
        # probe for the same learner.
        study_id = "study-probe-disjoint"
        _create_study(study_id)
        word_ids = [f"word-{i}" for i in range(20)]
        for word_id in word_ids:
            _assign(study_id, "student-1", word_id)
            _insert_item_for_every_probe_type(study_id, word_id)

        with db.connect_db() as conn:
            enroll_section_probes(conn, "student-1", study_id, "s", now=NOW)
        rows = _probe_assignments("student-1", study_id)

        by_word: dict[str, list[str]] = {}
        for row in rows:
            by_word.setdefault(row["word_id"], []).append(row["probe_type"])
        assert set(by_word) == set(word_ids)
        assert all(len(types) == 1 for types in by_word.values())

    def test_due_at_matches_the_seven_and_twenty_one_day_offsets_and_final_is_unset(self):
        study_id = "study-probe-due-at"
        _create_study(study_id)
        word_ids = [f"word-{i}" for i in range(30)]
        for word_id in word_ids:
            _assign(study_id, "student-1", word_id)
            _insert_item_for_every_probe_type(study_id, word_id)

        with db.connect_db() as conn:
            enroll_section_probes(conn, "student-1", study_id, "s", now=NOW)
        rows = _probe_assignments("student-1", study_id)

        # With 30 words, a 3-way hash partition should populate all three
        # pools - if this ever flakes it means the partition function
        # stopped being roughly uniform, itself worth knowing about.
        by_type: dict[str, list] = {}
        for row in rows:
            by_type.setdefault(row["probe_type"], []).append(row["due_at"])
        assert set(by_type) == set(PROBE_TYPES)
        for due_at in by_type["probe_7d"]:
            assert due_at == NOW + timedelta(days=7)
        for due_at in by_type["probe_21d"]:
            assert due_at == NOW + timedelta(days=21)
        for due_at in by_type["final_retention"]:
            assert due_at is None


class TestBuildDueProbes:
    def test_raises_for_a_non_participant(self):
        with db.connect_db() as conn:
            with pytest.raises(ResearchProbeUnavailableError):
                build_due_probes(conn, "no-such-student")

    def test_returns_only_a_due_question_and_never_the_answer(self):
        study_id = "study-due-probes"
        _create_study(study_id)
        _add_participant(study_id, "student-1")
        due_item = _insert_item(study_id, "word-due", "probe_7d", correct_answer="B")
        not_due_item = _insert_item(study_id, "word-not-due", "probe_21d")
        # build_due_probes reads the real wall clock, not a caller-supplied
        # "now" - so "due"/"not due" here must be relative to it too.
        real_now = datetime.now(timezone.utc)
        with db.connect_db() as conn:
            repo.insert_probe_assignment(
                conn, study_id=study_id, student_id="student-1", word_id="word-due",
                assessment_item_id=due_item, probe_type="probe_7d",
                due_at=real_now - timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
            )
            repo.insert_probe_assignment(
                conn, study_id=study_id, student_id="student-1", word_id="word-not-due",
                assessment_item_id=not_due_item, probe_type="probe_21d",
                due_at=real_now + timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
            )
            result = build_due_probes(conn, "student-1")

        assert len(result["questions"]) == 1
        question = result["questions"][0]
        assert question["wordId"] == "word-due"
        assert "correctAnswer" not in question
        assert "probeType" not in question
        assert "studyId" not in question

    def test_excludes_an_already_answered_probe(self):
        study_id = "study-answered-probe"
        _create_study(study_id)
        _add_participant(study_id, "student-1")
        item_id = _insert_item(study_id, "word-answered", "probe_7d")
        with db.connect_db() as conn:
            repo.insert_probe_assignment(
                conn, study_id=study_id, student_id="student-1", word_id="word-answered",
                assessment_item_id=item_id, probe_type="probe_7d",
                due_at=NOW - timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
            )
            assignment = repo.find_probe_assignments_for_student(conn, study_id, "student-1")["word-answered"]
            repo.insert_probe_response(
                conn, probe_assignment_id=assignment["id"], study_id=study_id, student_id="student-1",
                word_id="word-answered", assessment_item_id=item_id, response_value="A", correct=True,
                source_response_id="resp-1", responded_at=NOW, created_at=NOW.isoformat(),
            )
            result = build_due_probes(conn, "student-1")

        assert result["questions"] == []


class TestSubmitProbeResponse:
    def _due_assignment(self, study_id: str, student_id: str = "student-1", correct_answer: str = "A") -> int:
        _create_study(study_id)
        item_id = _insert_item(study_id, "word-a", "probe_7d", correct_answer=correct_answer)
        with db.connect_db() as conn:
            repo.insert_probe_assignment(
                conn, study_id=study_id, student_id=student_id, word_id="word-a",
                assessment_item_id=item_id, probe_type="probe_7d",
                due_at=NOW - timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
            )
            return repo.find_probe_assignments_for_student(conn, study_id, student_id)["word-a"]["id"]

    def test_accepts_a_response_and_never_returns_correctness(self):
        assignment_id = self._due_assignment("study-submit-shape")
        with db.connect_db() as conn:
            result = submit_probe_response(conn, "student-1", assignment_id, "A", source_response_id="src-1", now=NOW)
        assert result == {"accepted": True}

    def test_grades_correctly_internally_without_exposing_it(self):
        assignment_id = self._due_assignment("study-submit-correct", correct_answer="B")
        with db.connect_db() as conn:
            submit_probe_response(conn, "student-1", assignment_id, "B", source_response_id="src-1", now=NOW)
            stored = repo.find_probe_response(conn, assignment_id)
        assert stored["correct"] is True

    def test_grades_incorrectly_internally_without_exposing_it(self):
        assignment_id = self._due_assignment("study-submit-incorrect", correct_answer="B")
        with db.connect_db() as conn:
            submit_probe_response(conn, "student-1", assignment_id, "C", source_response_id="src-1", now=NOW)
            stored = repo.find_probe_response(conn, assignment_id)
        assert stored["correct"] is False

    def test_is_idempotent_for_a_repeat_submission(self):
        assignment_id = self._due_assignment("study-submit-idempotent", correct_answer="B")
        with db.connect_db() as conn:
            submit_probe_response(conn, "student-1", assignment_id, "B", source_response_id="src-1", now=NOW)
            # A second, different answer must not overwrite the first grade.
            submit_probe_response(conn, "student-1", assignment_id, "C", source_response_id="src-2", now=NOW)
            stored = repo.find_probe_response(conn, assignment_id)
        assert stored["response_value"] == "B"
        assert stored["correct"] is True

    def test_raises_for_an_assignment_that_does_not_belong_to_the_student(self):
        assignment_id = self._due_assignment("study-submit-wrong-owner", student_id="student-1")
        with db.connect_db() as conn:
            with pytest.raises(ResearchProbeAssignmentNotFoundError):
                submit_probe_response(conn, "student-2", assignment_id, "A", source_response_id="src-1", now=NOW)
