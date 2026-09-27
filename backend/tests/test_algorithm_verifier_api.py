def test_algorithm_verifier_math_endpoints_are_admin_scoped(admin_client):
    bkt = admin_client.post(
        "/api/admin/algorithm-verifier/bkt",
        json={"prior": 0.2, "correct": True, "questionFormat": "mcq"},
    )
    assert bkt.status_code == 200
    assert bkt.json()["result"] == "PASS"

    sm2 = admin_client.post(
        "/api/admin/algorithm-verifier/sm2",
        json={"operation": "enroll", "now": "2026-08-01T00:00:00Z", "daySeconds": 60},
    )
    assert sm2.status_code == 200
    assert sm2.json()["production"]["repetitions"] == 1


def test_algorithm_verifier_math_endpoint_rejects_non_admin(client):
    response = client.post(
        "/api/admin/algorithm-verifier/bkt",
        json={"prior": 0.2, "correct": True},
    )
    assert response.status_code == 403
