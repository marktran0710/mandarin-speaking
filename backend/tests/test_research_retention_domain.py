"""Epic 5, Task 5.3/5.5/5.6: pure retention enrollment/yoke-mirroring rules."""
from datetime import datetime, timedelta, timezone

from analytics.srs import DAY_SECONDS, SrsState
from domain.vocabulary.research_retention import initial_enrollment_state, mirror_yoked_state


def test_initial_enrollment_state_gives_a_one_day_interval():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = initial_enrollment_state(now, DAY_SECONDS)
    assert state.reps == 1
    assert state.interval_days == 1
    assert state.due_on == now + timedelta(days=1)
    assert state.last_reviewed_on == now


def test_adaptive_and_yoked_words_enroll_identically():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    adaptive = initial_enrollment_state(now, DAY_SECONDS)
    yoked = initial_enrollment_state(now, DAY_SECONDS)
    assert adaptive == yoked


def test_mirror_yoked_state_copies_the_sources_schedule_exactly():
    source = SrsState(reps=3, ease=2.7, interval_days=14, due_on=datetime(2026, 2, 1, tzinfo=timezone.utc), last_reviewed_on=datetime(2026, 1, 18, tzinfo=timezone.utc))
    mirrored = mirror_yoked_state(source)
    assert mirrored == source


def test_mirror_yoked_state_never_reads_the_yoked_words_own_correctness():
    # mirror_yoked_state's signature takes only the SOURCE state - there is
    # no parameter for the yoked word's own answer, so a caller cannot even
    # accidentally pass it in. This test documents that guarantee by
    # confirming the function's only input is the source.
    import inspect
    signature = inspect.signature(mirror_yoked_state)
    assert list(signature.parameters) == ["source_state"]
