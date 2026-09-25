"""Auth gating and content shape for the admin Learning Engine metadata endpoint."""


def test_requires_authentication(anonymous_client):
    response = anonymous_client.get("/api/admin/learning-engine")
    assert response.status_code in (401, 403)


def test_teacher_is_forbidden(logged_in_teacher):
    client, _ = logged_in_teacher
    response = client.get("/api/admin/learning-engine")
    assert response.status_code == 403


def test_student_is_forbidden(logged_in_student):
    client, _ = logged_in_student
    response = client.get("/api/admin/learning-engine")
    assert response.status_code == 403


def test_admin_sees_runtime_bkt_srs_and_voice_metadata(admin_client):
    response = admin_client.get("/api/admin/learning-engine")
    assert response.status_code == 200
    body = response.json()

    bkt = body["bkt"]
    assert bkt["name"] == "Bayesian Knowledge Tracing"
    assert bkt["parameters"]["P_L0_initial_mastery"]["value"] == 0.20
    assert bkt["parameters"]["mastery_threshold"]["value"] == 0.95
    assert bkt["parameterStatus"] == "provisional"

    retention = body["retention"]
    assert retention["name"] == "Modified SM-2"
    assert retention["parameters"]["initial_ease"]["value"] == 2.5
    assert retention["parameters"]["minimum_ease"]["value"] == 1.3

    voice = body["voice"]
    assert voice["acousticEngine"]["technology"] == "Praat via python-parselmouth"
    thresholds = voice["thresholds"]
    assert thresholds["SYLLABLE_PASS_THRESHOLD"]["value"] == 58.0
    assert thresholds["SYLLABLE_PASS_THRESHOLD"]["controlsProgression"] is True
    # The diagnostic thresholds are feedback-only and must not be mislabeled
    # as progression-gating - see domain/speech/tone_decision.py's docstring.
    assert thresholds["TONE_CONFIRM_THRESHOLD"]["controlsProgression"] is False
    assert isinstance(voice["asrProviders"], list) and voice["asrProviders"]


def test_no_secret_values_are_ever_exposed(admin_client):
    response = admin_client.get("/api/admin/learning-engine")
    body_text = response.text
    for forbidden in ("sk-", "gsk_", "AIza"):
        assert forbidden not in body_text
    voice = response.json()["voice"]
    for provider in voice["asrProviders"] + voice["feedbackProviders"]["providers"]:
        assert set(provider) <= {"provider", "role", "configured"}
        assert isinstance(provider["configured"], bool)
