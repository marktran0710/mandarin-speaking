"""Teacher login endpoint: password check against the roster, now also
issuing a signed session cookie on success.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import auth


def _create_teacher(client, name="Ms. Lin", password="teach123"):
    return client.post("/api/teachers", json={"name": name, "password": password}).json()


class TestTeacherLogin:
    def test_correct_password_logs_in_and_sets_a_session_cookie(self, client):
        teacher = _create_teacher(client)
        response = client.post(
            "/api/teachers/login", json={"name": "Ms. Lin", "password": "teach123"}
        )
        assert response.status_code == 200
        token = response.cookies.get(auth.COOKIE_NAME)
        assert token is not None
        identity = auth.decode_token(token)
        assert identity.role == "teacher"
        assert identity.id == teacher["id"]

    def test_wrong_password_is_401_and_sets_no_cookie(self, client):
        _create_teacher(client)
        response = client.post(
            "/api/teachers/login", json={"name": "Ms. Lin", "password": "nope"}
        )
        assert response.status_code == 401
        assert response.cookies.get(auth.COOKIE_NAME) is None

    def test_unknown_teacher_is_404(self, client):
        response = client.post(
            "/api/teachers/login", json={"name": "Nobody", "password": "x"}
        )
        assert response.status_code == 404

    def test_logout_clears_the_session_cookie(self, client):
        _create_teacher(client)
        client.post("/api/teachers/login", json={"name": "Ms. Lin", "password": "teach123"})
        assert client.cookies.get(auth.COOKIE_NAME) is not None
        client.post("/api/teachers/logout")
        assert client.cookies.get(auth.COOKIE_NAME) is None
