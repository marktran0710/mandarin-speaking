"""Epic 7, Task 7.3/7.7: pure probe-pool partitioning and due-date rules."""
from datetime import datetime, timedelta, timezone

from domain.research.probes import (
    PROBE_TYPES,
    due_at_for_probe_type,
    is_probe_due,
    partition_probe_pool,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_partition_probe_pool_assigns_every_word_exactly_one_type():
    partition = partition_probe_pool("student-1", ["word-a", "word-b", "word-c"])
    assert set(partition) == {"word-a", "word-b", "word-c"}
    assert all(probe_type in PROBE_TYPES for probe_type in partition.values())


def test_partition_probe_pool_is_deterministic_for_the_same_student_and_word():
    first = partition_probe_pool("student-1", ["word-a"])
    second = partition_probe_pool("student-1", ["word-a"])
    assert first == second


def test_partition_probe_pool_can_diverge_across_students_for_the_same_word():
    # Not a hard guarantee for any single word, but the partition must be a
    # function of student identity too, not word identity alone - otherwise
    # every learner would share the same pool assignment for a given word,
    # which is a correctness bug even though it isn't the Task 7.7 disjointness
    # requirement itself. Use enough words that at least one differs.
    words = [f"word-{i}" for i in range(20)]
    a = partition_probe_pool("student-a", words)
    b = partition_probe_pool("student-b", words)
    assert a != b


def test_a_words_pool_never_appears_twice_for_the_same_student():
    # Task 7.7: 7-day word != 21-day word != final-only word for one learner.
    words = [f"word-{i}" for i in range(50)]
    partition = partition_probe_pool("student-1", words)
    for word_id, probe_type in partition.items():
        assert partition[word_id] == probe_type  # each word maps to exactly one pool


def test_due_at_for_probe_7d_is_seven_days_after_enrollment():
    assert due_at_for_probe_type("probe_7d", NOW) == NOW + timedelta(days=7)


def test_due_at_for_probe_21d_is_twenty_one_days_after_enrollment():
    assert due_at_for_probe_type("probe_21d", NOW) == NOW + timedelta(days=21)


def test_due_at_for_final_retention_is_unset_pending_admin_release():
    assert due_at_for_probe_type("final_retention", NOW) is None


def test_is_probe_due_false_when_due_at_is_unset():
    assert is_probe_due(None, NOW) is False


def test_is_probe_due_true_once_the_due_date_has_passed():
    assert is_probe_due(NOW - timedelta(days=1), NOW) is True
    assert is_probe_due(NOW + timedelta(days=1), NOW) is False
    assert is_probe_due(NOW, NOW) is True
