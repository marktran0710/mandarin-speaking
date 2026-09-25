"""Pure unit tests for domain/vocabulary/research_policy.py - no database."""
from domain.research.policy import (
    VocabularyProgressionPolicy,
    build_research_context,
)


def test_a_student_with_no_participation_gets_an_inactive_production_context():
    context = build_research_context(
        study_id=None,
        study_status=None,
        policy_version=None,
        assignment_version=None,
        practice_budget=None,
        participant_active=False,
    )
    assert context.active is False
    assert context.progression_policy == VocabularyProgressionPolicy.PRODUCTION_ACCURACY


def test_an_active_participant_in_an_active_study_gets_research_coverage():
    context = build_research_context(
        study_id="study-1",
        study_status="active",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=8,
        participant_active=True,
    )
    assert context.active is True
    assert context.progression_policy == VocabularyProgressionPolicy.RESEARCH_COVERAGE


def test_a_pilot_study_participant_also_counts_as_active():
    context = build_research_context(
        study_id="study-1",
        study_status="pilot",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=8,
        participant_active=True,
    )
    assert context.active is True


def test_a_draft_study_does_not_activate_research_policy_yet():
    context = build_research_context(
        study_id="study-1",
        study_status="draft",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=None,
        participant_active=True,
    )
    assert context.active is False
    assert context.progression_policy == VocabularyProgressionPolicy.PRODUCTION_ACCURACY


def test_a_frozen_study_does_not_activate_research_policy():
    context = build_research_context(
        study_id="study-1",
        study_status="frozen",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=None,
        participant_active=True,
    )
    assert context.active is False


def test_a_completed_study_no_longer_applies_its_policy():
    context = build_research_context(
        study_id="study-1",
        study_status="completed",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=None,
        participant_active=True,
    )
    assert context.active is False


def test_an_individually_deactivated_participant_falls_back_to_production_even_in_an_active_study():
    context = build_research_context(
        study_id="study-1",
        study_status="active",
        policy_version="v1",
        assignment_version="v1",
        practice_budget=8,
        participant_active=False,
    )
    assert context.active is False
    assert context.progression_policy == VocabularyProgressionPolicy.PRODUCTION_ACCURACY
