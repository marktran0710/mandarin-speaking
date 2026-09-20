"""Regression coverage for the retired teacher pronunciation-review API."""

from main import app


def test_teacher_review_routes_are_not_registered(client):
    paths = {route.path for route in app.routes}
    assert "/api/teacher-review/queue" not in paths
    assert "/api/teacher-review/attempt/{audio_record_id}/stage1" not in paths
    assert "/api/teacher-review/attempt/{audio_record_id}/stage2" not in paths
    assert "/api/teacher-review/ratings/stage1" not in paths
    assert "/api/teacher-review/ratings/stage2" not in paths


def test_pilot_audio_compatibility_route_is_not_registered(client):
    assert "/api/pilot/audio-records" not in {route.path for route in app.routes}
