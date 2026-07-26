"""Roster CRUD, with the case-insensitive behaviour SQLite got from
COLLATE NOCASE and Postgres has to get from lower()."""


def test_create_and_list_students(client):
    client.post("/api/students", json={"name": "Mai"})
    client.post("/api/students", json={"name": "an"})
    client.post("/api/students", json={"name": "Bảo"})
    names = [s["name"] for s in client.get("/api/students").json()]
    # Case-insensitive alphabetical: an, Bảo, Mai
    assert names == ["an", "Bảo", "Mai"]


def test_create_is_idempotent_case_insensitively(client):
    first = client.post("/api/students", json={"name": "Mai"}).json()
    second = client.post("/api/students", json={"name": "MAI"}).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/students").json()) == 1


def test_blank_name_is_rejected(client):
    assert client.post("/api/students", json={"name": "   "}).status_code == 400


def test_login_by_name_is_case_insensitive(client):
    created = client.post("/api/students", json={"name": "Mai"}).json()
    response = client.post(
        "/api/students/login", json={"name": "mai", "password": "123456"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_login_with_wrong_password_is_401(client):
    client.post("/api/students", json={"name": "Mai"})
    response = client.post(
        "/api/students/login", json={"name": "Mai", "password": "nope"}
    )
    assert response.status_code == 401


def test_login_for_unknown_student_is_404(client):
    response = client.post(
        "/api/students/login", json={"name": "Ghost", "password": "123456"}
    )
    assert response.status_code == 404


def test_delete_student(client):
    created = client.post("/api/students", json={"name": "Mai"}).json()
    assert client.delete(f"/api/students/{created['id']}").json()["deleted"] is True
    assert client.get("/api/students").json() == []


def test_help_requests_sort_open_first(client):
    client.post("/api/help-requests", json={
        "id": "h1", "studentName": "Mai", "message": "help me",
        "status": "open", "createdAt": "2026-07-20T08:00:00Z"})
    client.post("/api/help-requests", json={
        "id": "h2", "studentName": "An", "message": "also help",
        "status": "open", "createdAt": "2026-07-21T08:00:00Z"})
    client.post("/api/help-requests/h2/resolve")

    requests = client.get("/api/help-requests").json()
    assert [r["id"] for r in requests] == ["h1", "h2"]
    assert requests[1]["status"] == "resolved"
    assert requests[1]["resolvedAt"] is not None


def test_resolving_a_missing_help_request_is_404(client):
    assert client.post("/api/help-requests/nope/resolve").status_code == 404
