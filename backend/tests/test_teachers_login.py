"""Teacher login endpoint: password check against the roster, now also
issuing a signed session cookie on success.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import auth
from conftest import _insert_teacher_row


def _create_teacher(client, name="Ms. Lin", password="teach123"):
    # POST /api/teachers now requires an admin identity - login tests need
    # a teacher to already exist, so insert directly instead.
    return _insert_teacher_row(name, password)


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


class TestTeacherRosterManagement:
    """Account management (list/create/update/delete) - unlike login/logout,
    these require an already-authenticated caller, not just a roster
    lookup."""

    def test_list_requires_a_teacher_or_admin_identity(self, anonymous_client):
        assert anonymous_client.get("/api/teachers").status_code == 401

    def test_list_is_visible_to_a_logged_in_teacher(self, client, logged_in_teacher):
        teacher_client, _ = logged_in_teacher
        assert teacher_client.get("/api/teachers").status_code == 200

    def test_create_requires_admin(self, client, logged_in_teacher):
        teacher_client, _ = logged_in_teacher
        response = teacher_client.post(
            "/api/teachers", json={"name": "New Teacher", "password": "new-teacher-password"}
        )
        assert response.status_code == 403

    def test_create_is_allowed_for_admin(self, client, monkeypatch):
        import routers.admin as admin_module

        monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "test-admin-pw")
        client.post("/api/admin/login", json={"password": "test-admin-pw"})
        response = client.post(
            "/api/teachers", json={"name": "New Teacher", "password": "new-teacher-password"}
        )
        assert response.status_code == 200

    def test_update_and_delete_require_admin(self, logged_in_teacher, monkeypatch):
        import routers.admin as admin_module
        from fastapi.testclient import TestClient
        import main

        monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "test-admin-pw")
        with TestClient(main.app) as admin_client:
            admin_client.post("/api/admin/login", json={"password": "test-admin-pw"})
            teacher = admin_client.post(
                "/api/teachers", json={"name": "Target Teacher", "password": "teacher-password"}
            ).json()

        teacher_client, _ = logged_in_teacher
        assert teacher_client.patch(
            f"/api/teachers/{teacher['id']}", json={"status": "inactive"}
        ).status_code == 403
        assert teacher_client.delete(f"/api/teachers/{teacher['id']}").status_code == 403

    def test_admin_can_rename_and_suspend_teacher(self, client, monkeypatch):
        import routers.admin as admin_module

        monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "test-admin-pw")
        client.post("/api/admin/login", json={"password": "test-admin-pw"})
        teacher = client.post(
            "/api/teachers", json={"name": "Target Teacher", "password": "teacher-password"}
        ).json()
        updated = client.patch(
            f"/api/teachers/{teacher['id']}",
            json={"name": "Renamed Teacher", "status": "inactive"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed Teacher"
        assert updated.json()["status"] == "inactive"
        assert client.post(
            "/api/teachers/login", json={"name": "Renamed Teacher", "password": "teacher-password"}
        ).status_code == 403

    def test_admin_cannot_rename_teacher_to_a_duplicate(self, client, monkeypatch):
        import routers.admin as admin_module

        monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "test-admin-pw")
        client.post("/api/admin/login", json={"password": "test-admin-pw"})
        first = client.post(
            "/api/teachers", json={"name": "First Teacher", "password": "first-password"}
        ).json()
        second = client.post(
            "/api/teachers", json={"name": "Second Teacher", "password": "second-password"}
        ).json()
        response = client.patch(
            f"/api/teachers/{first['id']}", json={"name": second["name"]}
        )
        assert response.status_code == 409
