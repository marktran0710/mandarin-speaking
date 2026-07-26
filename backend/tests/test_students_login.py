"""Student login endpoint: password check against the roster (default 123456).

A classroom friction gate, not real auth — plaintext comparison, no tokens.
Runs against the isolated test database so the dev roster is never touched.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture()
def roster_client(client):
    """Client with one seeded student, returned as (client, student)."""
    created = client.post("/api/students", json={"name": "Minh"}).json()
    return client, created


class TestStudentLogin:

    def test_default_password_logs_in_by_id(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"studentId": student["id"], "password": "123456"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == student["id"]
        assert "password" not in response.json()

    def test_login_by_name_is_case_insensitive(self, roster_client):
        client, student = roster_client
        response = client.post(
            "/api/students/login",
            json={"name": "  minh ", "password": "123456"},
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
            json={"name": "Nobody", "password": "123456"},
        )
        assert response.status_code == 404

    def test_missing_identity_is_400(self, roster_client):
        client, _ = roster_client
        response = client.post(
            "/api/students/login", json={"password": "123456"}
        )
        assert response.status_code == 400
