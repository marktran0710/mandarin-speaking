"""Password storage and legacy-login migration coverage."""
import uuid

import auth
import database


def _set_admin_session(client) -> None:
    client.cookies.set(auth.COOKIE_NAME, auth.issue_token("admin", "admin"))


def test_student_creation_stores_a_bcrypt_hash(client):
    _set_admin_session(client)
    response = client.post(
        "/api/students", json={"name": "Password Test Student", "password": "correct horse"}
    )
    assert response.status_code == 200

    with database.connect_db() as db:
        stored_password = db.execute(
            "SELECT password FROM students WHERE id = %s", (response.json()["id"],)
        ).fetchone()["password"]

    assert stored_password != "correct horse"
    assert stored_password.startswith("$2")
    assert auth.verify_password(stored_password, "correct horse") == (True, None)


def test_legacy_plaintext_password_is_hashed_after_successful_student_login(client):
    student_id = str(uuid.uuid4())
    with database.connect_db() as db:
        db.execute(
            "INSERT INTO students (id, name, password) VALUES (%s, %s, %s)",
            (student_id, "Legacy Student", "legacy-password"),
        )

    response = client.post(
        "/api/students/login",
        json={"studentId": student_id, "password": "legacy-password"},
    )
    assert response.status_code == 200

    with database.connect_db() as db:
        stored_password = db.execute(
            "SELECT password FROM students WHERE id = %s", (student_id,)
        ).fetchone()["password"]

    assert stored_password != "legacy-password"
    assert auth.verify_password(stored_password, "legacy-password") == (True, None)


def test_legacy_plaintext_password_is_hashed_after_successful_teacher_login(client):
    teacher_id = str(uuid.uuid4())
    with database.connect_db() as db:
        db.execute(
            "INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s)",
            (teacher_id, "Legacy Teacher", "legacy-password"),
        )

    response = client.post(
        "/api/teachers/login",
        json={"name": "Legacy Teacher", "password": "legacy-password"},
    )
    assert response.status_code == 200

    with database.connect_db() as db:
        stored_password = db.execute(
            "SELECT password FROM teachers WHERE id = %s", (teacher_id,)
        ).fetchone()["password"]

    assert stored_password != "legacy-password"
    assert auth.verify_password(stored_password, "legacy-password") == (True, None)


def test_password_hashing_supports_passwords_longer_than_bcrypts_limit():
    password = "密碼" * 50
    stored_password = auth.hash_password(password)

    assert auth.verify_password(stored_password, password) == (True, None)
    assert auth.verify_password(stored_password, password + "x") == (False, None)
