"""Regression checks for the public-deployment authentication boundary."""

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/api/students",
        "/api/custom-stories",
        "/api/help-requests",
        "/api/measurement-events",
        "/api/benchmark/ompal/status",
        "/api/ai-providers",
        "/api/inline-media?url=/uploads/not-a-real-file.png",
        "/uploads/not-a-real-file.wav",
    ],
)
def test_sensitive_endpoints_reject_anonymous_requests(anonymous_client, path):
    assert anonymous_client.get(path).status_code == 401


def test_student_cannot_create_roster_account_without_staff_session(anonymous_client):
    response = anonymous_client.post(
        "/api/students",
        json={"name": "Unauthorised", "password": "long-enough-password"},
    )
    assert response.status_code == 401


def test_expensive_ai_mutation_rejects_anonymous_requests(anonymous_client):
    response = anonymous_client.post("/api/tts", json={"text": "你好"})
    assert response.status_code == 401
