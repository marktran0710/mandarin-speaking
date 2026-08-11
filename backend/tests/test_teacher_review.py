"""Teacher pronunciation-validation review flow: Stage 1 (blind) and Stage 2
(system feedback review), against routers/teacher_review.py."""

ASSISTIVE_FEEDBACK = [
    {
        "syllable_index": 0,
        "character": "你",
        "expected_underlying_tone": 3,
        "accepted_surface_tones": [2],
        "context_rule": "third_sandhi",
        "realization": "third_sandhi",
        "assistive_state": "NEEDS_PRACTICE",
        "assistive_state_label": "CHECK_THIS_TONE",
        "assistive_message": "This tone may be worth checking.",
        "e2_diagnostic_category": "C_t3_t3_to_t2",
        "explanation": {
            "e2_provenance": "measured",
            "e2_matched_tone": 2,
            "boundary_before": 0.0,
            "boundary_after": 0.3,
        },
    },
    {
        "syllable_index": 1,
        "character": "好",
        "expected_underlying_tone": 3,
        "accepted_surface_tones": [3],
        "context_rule": None,
        "realization": "full_third",
        "assistive_state": "ACCEPT",
        "assistive_state_label": "NO_ISSUE_DETECTED",
        "assistive_message": "No pronunciation issue was detected.",
        "e2_diagnostic_category": "A_full_third",
        "explanation": {
            "e2_provenance": "measured",
            "e2_matched_tone": 3,
            "boundary_before": 0.3,
            "boundary_after": 0.6,
        },
    },
]

AUDIO_RECORD = {
    "id": "rec-pilot-1",
    "timestamp": "2026-08-09T08:00:00Z",
    "duration": 1500,
    "transcription": "你好",
    "model": "whisper",
    "topicId": "lesson-1",
    "studentId": "participant-p001",
    "imageIndex": 0,
    "audioUrl": "/uploads/audio/rec-pilot-1.wav",
    "praatMetrics": {
        "pitch_contour": [[0.0, 220.0], [0.1, 210.0]],
        "word_prosody": [{"word": "你好", "passed": False, "accuracy": 40}],
        "assistive_feedback": ASSISTIVE_FEEDBACK,
    },
    "sessionId": "session-abc",
    "attemptId": "attempt-1",
    "attemptNumber": 1,
    "attemptType": "WHOLE_SENTENCE_INITIAL",
}


def _seed_audio_record(client, overrides=None):
    payload = {**AUDIO_RECORD, **(overrides or {})}
    response = client.post("/api/audio-records", json=payload)
    assert response.status_code == 200
    return payload


def test_stage1_view_excludes_all_system_judgment_fields(client):
    _seed_audio_record(client)
    response = client.get("/api/teacher-review/attempt/rec-pilot-1/stage1")
    assert response.status_code == 200
    body = response.json()

    assert body["audio_record_id"] == "rec-pilot-1"
    assert body["script"] == "你好"
    assert body["item_id"] == "lesson-1:0"
    assert body["attempt_id"] == "attempt-1"

    # Ground-truth targets are allowed (a rubric grader needs the answer key)...
    assert body["targets"][0]["character"] == "你"
    assert body["targets"][0]["expected_underlying_tone"] == 3
    assert body["targets"][0]["context_rule"] == "third_sandhi"

    # ...but no machine judgment about THIS recording may leak into Stage 1.
    forbidden_keys = {
        "assistive_state", "assistive_state_label", "assistive_message",
        "e2_diagnostic_category", "explanation", "passed", "word_prosody",
        "f1_risk_score", "e2_score", "policy_state",
    }
    for target in body["targets"]:
        assert forbidden_keys.isdisjoint(target.keys())
    body_str = str(body)
    for forbidden in ("NEEDS_PRACTICE", "CHECK_THIS_TONE", "ACCEPT", "NO_ISSUE_DETECTED", "passed"):
        assert forbidden not in body_str


def test_stage2_locked_until_stage1_submitted(client):
    _seed_audio_record(client)

    locked = client.get(
        "/api/teacher-review/attempt/rec-pilot-1/stage2", params={"teacher_id": "Ms. Chen"}
    )
    assert locked.status_code == 403

    submit = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-pilot-1",
            "syllable_index": None,
            "accuracy_score": 3,
            "fluency_score": 3,
            "prosody_score": 3,
        },
    )
    assert submit.status_code == 200

    unlocked = client.get(
        "/api/teacher-review/attempt/rec-pilot-1/stage2", params={"teacher_id": "Ms. Chen"}
    )
    assert unlocked.status_code == 200
    body = unlocked.json()
    assert body["system_output"][0]["assistive_state_label"] == "CHECK_THIS_TONE"
    assert body["system_output"][0]["e2_diagnostic_category"] == "C_t3_t3_to_t2"
    assert body["pitch_contour"] == [[0.0, 220.0], [0.1, 210.0]]

    # Stage 2 stays locked for a DIFFERENT teacher who hasn't done Stage 1 yet.
    still_locked = client.get(
        "/api/teacher-review/attempt/rec-pilot-1/stage2", params={"teacher_id": "Mr. Lin"}
    )
    assert still_locked.status_code == 403


def test_two_teachers_rate_independently_without_overwriting(client):
    _seed_audio_record(client)

    for teacher in ("Ms. Chen", "Mr. Lin"):
        response = client.post(
            "/api/teacher-review/ratings/stage1",
            json={
                "teacher_id": teacher,
                "audio_record_id": "rec-pilot-1",
                "syllable_index": 0,
                "consonant_score": 1,
                "vowel_score": 1,
                "tone_score": 0,
            },
        )
        assert response.status_code == 200

    with_db_module = __import__("database")
    with with_db_module.connect_db() as db:
        rows = db.execute(
            "SELECT teacher_id, tone_score FROM teacher_pronunciation_ratings "
            "WHERE attempt_id = 'attempt-1' AND syllable_index = 0 ORDER BY teacher_id"
        ).fetchall()
    assert [r["teacher_id"] for r in rows] == ["Mr. Lin", "Ms. Chen"]
    assert all(r["tone_score"] == 0 for r in rows)


def test_same_teacher_cannot_overwrite_own_rating(client):
    _seed_audio_record(client)
    body = {
        "teacher_id": "Ms. Chen",
        "audio_record_id": "rec-pilot-1",
        "syllable_index": 0,
        "consonant_score": 1,
        "vowel_score": 1,
        "tone_score": 1,
    }
    first = client.post("/api/teacher-review/ratings/stage1", json=body)
    assert first.status_code == 200
    duplicate = client.post("/api/teacher-review/ratings/stage1", json={**body, "tone_score": 0})
    assert duplicate.status_code == 409


def test_sentence_and_syllable_level_ratings_stay_distinct(client):
    _seed_audio_record(client)
    syllable = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-pilot-1",
            "syllable_index": 0,
            "consonant_score": 1,
            "vowel_score": 1,
            "tone_score": 0,
        },
    )
    sentence = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-pilot-1",
            "syllable_index": None,
            "accuracy_score": 4,
            "fluency_score": 4,
            "prosody_score": 4,
        },
    )
    assert syllable.status_code == 200
    assert sentence.status_code == 200
    assert syllable.json()["rating_id"] != sentence.json()["rating_id"]


def test_mixed_syllable_and_sentence_fields_rejected(client):
    _seed_audio_record(client)
    response = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-pilot-1",
            "syllable_index": 0,
            "consonant_score": 1,
            "vowel_score": 1,
            "tone_score": 1,
            "accuracy_score": 5,
        },
    )
    assert response.status_code == 422


def test_rating_identity_joins_by_id_fields_from_audio_record(client):
    _seed_audio_record(client, overrides={"studentId": "participant-p001"})
    client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-pilot-1",
            "syllable_index": None,
            "accuracy_score": 3,
            "fluency_score": 3,
            "prosody_score": 3,
        },
    )
    database = __import__("database")
    with database.connect_db() as db:
        row = db.execute(
            "SELECT * FROM teacher_pronunciation_ratings WHERE audio_record_id = 'rec-pilot-1'"
        ).fetchone()
    assert row["participant_id"] == "participant-p001"
    assert row["session_id"] == "session-abc"
    assert row["item_id"] == "lesson-1:0"
    assert row["attempt_id"] == "attempt-1"


def test_review_queue_hides_system_prediction_before_stage1(client):
    _seed_audio_record(client)
    queue = client.get("/api/teacher-review/queue", params={"teacher_id": "Ms. Chen"}).json()
    entry = next(e for e in queue if e["audio_record_id"] == "rec-pilot-1")
    assert entry["review_status"] == "NOT_STARTED"
    assert "assistive_state" not in entry
    assert "e2_diagnostic_category" not in entry
    assert set(entry.keys()) == {
        "audio_record_id", "participant_id", "item_id", "session_id",
        "attempt_id", "attempt_number", "attempt_type", "review_status",
    }


def test_recording_without_pilot_identity_cannot_be_reviewed(client):
    _seed_audio_record(client, overrides={
        "id": "rec-legacy-1",
        "sessionId": None,
        "attemptId": None,
        "attemptNumber": None,
        "attemptType": None,
    })
    response = client.get("/api/teacher-review/attempt/rec-legacy-1/stage1")
    assert response.status_code == 400


def test_recording_without_participant_id_cannot_be_reviewed(client):
    _seed_audio_record(client, overrides={"id": "rec-no-participant", "studentId": None})
    response = client.get("/api/teacher-review/attempt/rec-no-participant/stage1")
    assert response.status_code == 400
