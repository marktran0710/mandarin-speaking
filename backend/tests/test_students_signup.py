"""Public student self-signup: a basic name + password creates an account and
signs the student in. It must never hand out someone else's account."""

import pytest

import db
import security.auth as auth

URL = "/api/students/signup"


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    # Signup shares the login limiter store; every test starts from zero.
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


def _signup(client, name="Lan", password="lan-password"):
    return client.post(URL, json={"name": name, "password": password})


def test_signup_creates_the_account_and_signs_the_student_in(anonymous_client):
    response = _signup(anonymous_client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Lan" and body["id"]
    assert "password" not in body
    # The session cookie from signup alone is enough to act as this student.
    settings = anonymous_client.get("/api/students/me/settings")
    assert settings.status_code == 200


def test_the_password_is_stored_hashed_and_works_for_a_later_login(anonymous_client):
    student_id = _signup(anonymous_client).json()["id"]
    with db.connect_db() as conn:
        stored = conn.execute("SELECT password FROM students WHERE id = %s", (student_id,)).fetchone()["password"]
    assert stored != "lan-password" and stored.startswith("$2")

    anonymous_client.post("/api/students/logout")
    login = anonymous_client.post("/api/students/login", json={"name": "lan", "password": "lan-password"})
    assert login.status_code == 200 and login.json()["id"] == student_id


def test_the_name_is_trimmed(anonymous_client):
    assert _signup(anonymous_client, name="  Mai  ").json()["name"] == "Mai"


def test_a_taken_name_is_a_conflict_in_any_case_and_leaves_the_owner_untouched(anonymous_client):
    first = _signup(anonymous_client, name="Minh", password="minh-password").json()
    anonymous_client.post("/api/students/logout")

    clash = _signup(anonymous_client, name="mINH", password="attacker-password")
    assert clash.status_code == 409
    # The conflict must not sign anyone in, and must not change the owner's password.
    assert anonymous_client.get("/api/students/me/settings").status_code in (401, 403)
    ok = anonymous_client.post("/api/students/login", json={"studentId": first["id"], "password": "minh-password"})
    assert ok.status_code == 200
    bad = anonymous_client.post("/api/students/login", json={"studentId": first["id"], "password": "attacker-password"})
    assert bad.status_code == 401


@pytest.mark.parametrize("name", ["admin", "Admin", "  ADMIN  "])
def test_the_reserved_admin_name_cannot_be_registered(anonymous_client, name):
    # The frontend treats a student named "admin" as the progression-bypass admin.
    assert _signup(anonymous_client, name=name).status_code == 400
    with db.connect_db() as conn:
        assert conn.execute("SELECT count(*) AS n FROM students").fetchone()["n"] == 0


def test_a_short_password_is_rejected(anonymous_client):
    assert _signup(anonymous_client, password="abc").status_code in (400, 422)


@pytest.mark.parametrize("name", ["", "   "])
def test_a_blank_name_is_rejected(anonymous_client, name):
    assert _signup(anonymous_client, name=name).status_code in (400, 422)


def test_signup_is_rate_limited_per_client(anonymous_client):
    for index in range(5):
        assert _signup(anonymous_client, name=f"Student {index}").status_code == 201
        anonymous_client.post("/api/students/logout")
    assert _signup(anonymous_client, name="One too many").status_code == 429


def test_creating_a_student_through_the_roster_endpoint_is_still_admin_only(anonymous_client):
    response = anonymous_client.post("/api/students", json={"name": "Sneaky", "password": "sneaky-password"})
    assert response.status_code in (401, 403)
