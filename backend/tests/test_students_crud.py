"""Roster CRUD, with the case-insensitive behaviour SQLite got from
COLLATE NOCASE and Postgres has to get from lower()."""


def test_create_and_list_students(admin_client):
    client = admin_client
    client.post("/api/students", json={"name": "Mai", "password": "mai-password"})
    client.post("/api/students", json={"name": "an", "password": "an-password"})
    client.post("/api/students", json={"name": "Bảo", "password": "bao-password"})
    names = [s["name"] for s in client.get("/api/students").json()]
    # Case-insensitive alphabetical: an, Bảo, Mai
    assert names == ["an", "Bảo", "Mai"]


def test_create_student_requires_admin(logged_in_teacher):
    teacher_client, _ = logged_in_teacher
    response = teacher_client.post(
        "/api/students", json={"name": "Teacher Cannot Create", "password": "password"}
    )
    assert response.status_code == 403


def test_create_is_idempotent_case_insensitively(admin_client):
    client = admin_client
    first = client.post("/api/students", json={"name": "Mai", "password": "mai-password"}).json()
    second = client.post("/api/students", json={"name": "MAI", "password": "mai-password"}).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/students").json()) == 1


def test_blank_name_is_rejected(admin_client):
    client = admin_client
    assert client.post("/api/students", json={"name": "   ", "password": "long-password"}).status_code == 400


def test_login_by_name_is_case_insensitive(admin_client):
    client = admin_client
    created = client.post("/api/students", json={"name": "Mai", "password": "mai-password"}).json()
    response = client.post(
        "/api/students/login", json={"name": "mai", "password": "mai-password"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_login_with_wrong_password_is_401(admin_client):
    client = admin_client
    client.post("/api/students", json={"name": "Mai", "password": "mai-password"})
    response = client.post(
        "/api/students/login", json={"name": "Mai", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_for_unknown_student_is_404(admin_client):
    client = admin_client
    response = client.post(
        "/api/students/login", json={"name": "Ghost", "password": "123456"}
    )
    assert response.status_code == 404


def test_delete_student(admin_client):
    created = admin_client.post("/api/students", json={"name": "Mai", "password": "mai-password"}).json()
    assert admin_client.delete(f"/api/students/{created['id']}").json()["deleted"] is True
    assert admin_client.get("/api/students").json() == []


def test_delete_student_requires_login(admin_client):
    created = admin_client.post("/api/students", json={"name": "Mai", "password": "mai-password"}).json()
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as anonymous:
        assert anonymous.delete(f"/api/students/{created['id']}").status_code == 401


def test_help_requests_sort_open_first(admin_client):
    student_client = admin_client
    student = student_client.post(
        "/api/students", json={"name": "Help Student", "password": "help-password"}
    ).json()
    student_client.post(
        "/api/students/login", json={"studentId": student["id"], "password": "help-password"}
    )
    student_client.post("/api/help-requests", json={
        "id": "h1", "studentName": "Mai", "message": "help me",
        "status": "open", "createdAt": "2026-07-20T08:00:00Z"})
    student_client.post("/api/help-requests", json={
        "id": "h2", "studentName": "An", "message": "also help",
        "status": "open", "createdAt": "2026-07-21T08:00:00Z"})
    # A teacher session is needed to resolve/read the queue; use a fresh
    # staff client so the student cookie remains scoped to the submitter.
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    import main
    import database
    import auth
    import uuid
    with ExitStack() as stack:
        teacher_client = stack.enter_context(TestClient(main.app))
        with database.connect_db() as db:
            teacher = db.execute(
                "INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s) RETURNING *",
                (str(uuid.uuid4()), "Help Teacher", auth.hash_password("help-teacher-password")),
            ).fetchone()
        teacher_client.post(
            "/api/teachers/login",
            json={"name": teacher["name"], "password": "help-teacher-password"},
        )
        teacher_client.post("/api/help-requests/h2/resolve")
        requests = teacher_client.get("/api/help-requests").json()
    assert [r["id"] for r in requests] == ["h1", "h2"]
    assert requests[1]["status"] == "resolved"
    assert requests[1]["resolvedAt"] is not None


def test_resolving_a_missing_help_request_is_404(client):
    assert client.post("/api/help-requests/nope/resolve").status_code == 404
