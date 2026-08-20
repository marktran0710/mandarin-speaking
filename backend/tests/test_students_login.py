"""Student login endpoint: password check against the provisioned roster.

Success issues a signed session cookie. Runs against the isolated test
database so the dev roster is never touched.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import auth


@pytest.fixture()
def roster_client(client):
    """Client with one seeded student, returned as (client, student)."""
    created = client.post(
        "/api/students", json={"name": "Minh", "password": "minh-password"}
    ).json()
    return client, created


class TestStudentLogin:

    def test_provisioned_password_logs_in_by_id(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "minh-password"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == student["id"]
        assert "password" not in response.json()

    def test_login_by_name_is_case_insensitive(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"name": "  minh ", "password": "minh-password"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == student["id"]

    def test_wrong_password_is_401(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "654321"},
        )
        assert response.status_code == 401

    def test_unknown_student_is_404(self, roster_client):
        client, _ = roster_client
        response = client.post(
            "/api/students/login",
            json={"name": "Nobody", "password": "minh-password"},
        )
        assert response.status_code == 404

    def test_missing_identity_is_400(self, roster_client):
        client, _ = roster_client
        response = client.post(
            "/api/students/login", json={"password": "minh-password"}
        )
        assert response.status_code == 400

    def test_successful_login_sets_a_valid_student_session_cookie(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "minh-password"},
        )
        token = response.cookies.get(auth.COOKIE_NAME)
        assert token is not None
        identity = auth.decode_token(token)
        assert identity.role == "student"
        assert identity.id == student["id"]

    def test_wrong_password_does_not_set_a_cookie(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "wrong"},
        )
        assert response.cookies.get(auth.COOKIE_NAME) is None

    def test_logout_clears_the_session_cookie(self, roster_client):
        client, student = roster_client
        client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "minh-password"},
        )
        assert client.cookies.get(auth.COOKIE_NAME) is not None
        client.post("/api/students/logout")
        assert client.cookies.get(auth.COOKIE_NAME) is None
