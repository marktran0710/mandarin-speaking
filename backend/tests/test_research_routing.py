"""Epic 6, Task 6.1: pure activity-routing policy."""
import pytest

from domain.research.routing import (
    ResearchActivityType,
    activity_type_for_mode,
    route_research_response,
)


def test_core_feeds_treatment_and_shadow_bkt_never_retention():
    routing = route_research_response(ResearchActivityType.CORE)
    assert routing.treatment_bkt is True
    assert routing.shadow_bkt is True
    assert routing.retention is False


def test_practice_feeds_treatment_and_shadow_bkt_never_retention():
    routing = route_research_response(ResearchActivityType.PRACTICE)
    assert routing.treatment_bkt is True
    assert routing.shadow_bkt is True
    assert routing.retention is False


def test_review_feeds_only_retention_never_treatment_bkt():
    routing = route_research_response(ResearchActivityType.REVIEW)
    assert routing.treatment_bkt is False
    assert routing.shadow_bkt is None  # optional, not a forced yes/no
    assert routing.retention is True


def test_probe_and_posttest_touch_nothing():
    for activity_type in (ResearchActivityType.PROBE, ResearchActivityType.POSTTEST):
        routing = route_research_response(activity_type)
        assert routing.treatment_bkt is False
        assert routing.shadow_bkt is False
        assert routing.retention is False


def test_route_research_response_accepts_the_raw_string_value_too():
    assert route_research_response("diagnostic") == route_research_response(ResearchActivityType.CORE)


def test_route_research_response_rejects_an_unknown_activity_type():
    with pytest.raises(ValueError):
        route_research_response("not_a_real_activity_type")


def test_activity_type_for_mode_maps_every_core_tier():
    assert activity_type_for_mode("tier1") == ResearchActivityType.CORE
    assert activity_type_for_mode("tier2") == ResearchActivityType.CORE
    assert activity_type_for_mode("tier3") == ResearchActivityType.CORE


def test_activity_type_for_mode_maps_practice_and_review():
    assert activity_type_for_mode("weak_words") == ResearchActivityType.PRACTICE
    assert activity_type_for_mode("maintenance_review") == ResearchActivityType.REVIEW


def test_activity_type_for_mode_is_none_for_modes_with_no_research_routing():
    assert activity_type_for_mode("challenge") is None
    assert activity_type_for_mode("free") is None
    assert activity_type_for_mode(None) is None
    assert activity_type_for_mode("") is None
