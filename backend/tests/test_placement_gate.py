"""New accounts must take the placement test before anything else unlocks.

``GET /api/placement-test/status`` tells the client whether this student is
gated: only a new account (students.placement_required), only while a placement
test is actually published, and only until a completed attempt exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import db
import security.auth as auth
from services.placement_test_service import replace_from_upload
from test_placement_test import _publish, _student_session

STATUS_URL = "/api/placement-test/status"


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


def _configure_placement() -> None:
    _publish("gate-story", "GATE")
    with db.connect_db() as conn:
        replace_from_upload(conn, b"Word Key,Round\nGATE-W001,1\nGATE-W002,2\nGATE-W003,3\n", "gate.csv")


def _complete_attempt(client) -> None:
    attempt = client.post("/api/placement-test/attempts").json()
    done = client.post(
        f"/api/placement-test/attempts/{attempt['attemptId']}/complete",
        json={
            "responses": [
                {"questionId": "Q-GATE-001", "selectedAnswer": "book", "timeMs": 10},
                {"questionId": "Q-GATE-002", "selectedAnswer": "ni3 hao3", "timeMs": 10},
                {"questionId": "Q-GATE-003", "selectedAnswer": "家", "timeMs": 10},
            ],
            "completedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert done.status_code == 200


def test_a_new_account_is_not_gated_while_no_placement_test_is_published(admin_client):
    _student_session(admin_client)
    body = admin_client.get(STATUS_URL).json()
    assert body == {"configured": False, "required": True, "completed": False, "gated": False}


def test_an_admin_created_account_is_gated_once_a_placement_test_exists(admin_client):
    _configure_placement()
    _student_session(admin_client)
    body = admin_client.get(STATUS_URL).json()
    assert body == {"configured": True, "required": True, "completed": False, "gated": True}


def test_a_self_signup_account_is_gated_too(anonymous_client):
    _configure_placement()
    anonymous_client.post("/api/students/signup", json={"name": "Lan", "password": "lan-password"})
    body = anonymous_client.get(STATUS_URL).json()
    assert body["required"] is True and body["gated"] is True


def test_starting_the_test_does_not_clear_the_gate_but_finishing_it_does(admin_client):
    _configure_placement()
    _student_session(admin_client)
    admin_client.post("/api/placement-test/attempts")  # started, never completed
    assert admin_client.get(STATUS_URL).json()["gated"] is True

    _complete_attempt(admin_client)
    body = admin_client.get(STATUS_URL).json()
    assert body == {"configured": True, "required": True, "completed": True, "gated": False}


def test_an_existing_student_is_never_gated(admin_client):
    # Accounts that predate the feature keep placement_required = FALSE.
    _configure_placement()
    student = _student_session(admin_client)
    with db.connect_db() as conn:
        conn.execute("UPDATE students SET placement_required = FALSE WHERE id = %s", (student["id"],))
    body = admin_client.get(STATUS_URL).json()
    assert body == {"configured": True, "required": False, "completed": False, "gated": False}


def test_the_status_is_only_for_signed_in_students(admin_client, anonymous_client):
    assert anonymous_client.get(STATUS_URL).status_code == 401
    # admin_client is signed in as the admin, not as a student.
    assert admin_client.get(STATUS_URL).status_code in (401, 403)


def test_the_flag_is_not_leaked_through_the_public_student_shape(anonymous_client):
    created = anonymous_client.post("/api/students/signup", json={"name": "Mai", "password": "mai-password"}).json()
    assert "placement_required" not in created and "placementRequired" not in created
