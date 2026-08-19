"""Admin console login: real backend password check + JWT session cookie,
replacing the old client-side-only "admin123" gate in AdminApp.tsx.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import auth
import routers.admin as admin_module


@pytest.fixture(autouse=True)
def admin_password(monkeypatch):
    monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "test-admin-pw")


class TestAdminLogin:
    def test_correct_password_logs_in_and_sets_a_session_cookie(self, client):
        response = client.post("/api/admin/login", json={"password": "test-admin-pw"})
        assert response.status_code == 200
        token = response.cookies.get(auth.COOKIE_NAME)
        assert token is not None
        identity = auth.decode_token(token)
        assert identity.role == "admin"

    def test_wrong_password_is_401_and_sets_no_cookie(self, client):
        response = client.post("/api/admin/login", json={"password": "nope"})
        assert response.status_code == 401
        assert response.cookies.get(auth.COOKIE_NAME) is None

    def test_logout_clears_the_session_cookie(self, client):
        client.post("/api/admin/login", json={"password": "test-admin-pw"})
        assert client.cookies.get(auth.COOKIE_NAME) is not None
        client.post("/api/admin/logout")
        assert client.cookies.get(auth.COOKIE_NAME) is None

    def test_login_is_refused_when_no_admin_password_is_configured(self, client, monkeypatch):
        monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "")
        response = client.post("/api/admin/login", json={"password": "anything"})
        assert response.status_code == 503
