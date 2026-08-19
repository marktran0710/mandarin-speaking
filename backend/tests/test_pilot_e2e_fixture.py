"""PART 17: deterministic end-to-end fixture for the small-teacher-validated
pilot architecture.

Builds the exact fixture the spec names -- Participant P001, Session S001,
Item ITEM001, Attempt A001, AudioRecord R001, system output, Teacher T01
Stage 1 + Stage 2, Teacher T02 Stage 1 + Stage 2, then Attempt A002
(FOCUSED_RETRY) / AudioRecord R002 -- and proves every system and human
record joins using explicit ID fields only (`participant_id`, `session_id`,
`item_id`, `attempt_id`, `syllable_index`). No test here ever reads
`created_at`/timestamp to link or order anything; `attempt_number` is the
only ordering field used, exactly as `assistive_feedback/research_log.py`'s
own `reconstruct_sequence` already establishes as the pattern.

Item identity deliberately reuses the existing `topic_id` + `image_index`
composite (PART 5: "do not invent duplicate identity systems") -- `ITEM001`
below is realized as `topicId="ITEM001", imageIndex=0`, giving
`item_id == "ITEM001:0"`.
"""

PARTICIPANT_ID = "P001"
SESSION_ID = "S001"
TOPIC_ID = "ITEM001"
IMAGE_INDEX = 0
ITEM_ID = f"{TOPIC_ID}:{IMAGE_INDEX}"


def _system_output_for(attempt_id: str, check_this_tone: bool):
    return [{
        "syllable_index": 0,
        "character": "你",
        "expected_underlying_tone": 3,
        "accepted_surface_tones": [2] if check_this_tone else [3],
        "context_rule": "third_sandhi" if check_this_tone else None,
        "realization": "third_sandhi" if check_this_tone else "full_third",
        "assistive_state": "NEEDS_PRACTICE" if check_this_tone else "ACCEPT",
        "assistive_state_label": "CHECK_THIS_TONE" if check_this_tone else "NO_ISSUE_DETECTED",
        "assistive_message": (
            "This tone may be worth checking." if check_this_tone
            else "No pronunciation issue was detected."
        ),
        "e2_diagnostic_category": "C_t3_t3_to_t2" if check_this_tone else "A_full_third",
        "explanation": {
            "e2_provenance": "measured",
            "e2_matched_tone": 2 if check_this_tone else 3,
            "boundary_before": False,
            "boundary_after": False,
        },
    }]


def _seed_audio_record(client, audio_record_id, attempt_id, attempt_number, attempt_type, check_this_tone):
    payload = {
        "id": audio_record_id,
        "timestamp": "2026-08-09T08:00:00Z",
        "duration": 1200,
        "transcription": "你好",
        "model": "whisper",
        "topicId": TOPIC_ID,
        "imageIndex": IMAGE_INDEX,
        "studentId": PARTICIPANT_ID,
        "audioUrl": f"/uploads/audio/{audio_record_id}.wav",
        "praatMetrics": {
            "pitch_contour": [[0.0, 220.0], [0.1, 210.0]],
            "word_prosody": [{"word": "你好", "passed": not check_this_tone, "accuracy": 40}],
            "assistive_feedback": _system_output_for(attempt_id, check_this_tone),
        },
        "sessionId": SESSION_ID,
        "attemptId": attempt_id,
        "attemptNumber": attempt_number,
        "attemptType": attempt_type,
    }
    response = client.post("/api/pilot/audio-records", json=payload)
    assert response.status_code == 200
    return payload


def test_full_pilot_fixture_joins_by_id_fields_only(client):
    # ── Attempt A001 / AudioRecord R001 ─────────────────────────────────
    _seed_audio_record(client, "R001", "A001", 1, "WHOLE_SENTENCE_INITIAL", check_this_tone=True)

    stage1_view = client.get("/api/teacher-review/attempt/R001/stage1").json()
    assert stage1_view["participant_id"] == PARTICIPANT_ID
    assert stage1_view["session_id"] == SESSION_ID
    assert stage1_view["item_id"] == ITEM_ID
    assert stage1_view["attempt_id"] == "A001"
    # Blind: no system judgment reaches Stage 1.
    assert "assistive_state" not in str(stage1_view["targets"])

    for teacher_id, tone_score in (("T01", 0), ("T02", 1)):
        rating = client.post(
            "/api/teacher-review/ratings/stage1",
            json={
                "teacher_id": teacher_id,
                "audio_record_id": "R001",
                "syllable_index": 0,
                "consonant_score": 1,
                "vowel_score": 1,
                "tone_score": tone_score,
            },
        )
        assert rating.status_code == 200
        sentence_rating = client.post(
            "/api/teacher-review/ratings/stage1",
            json={
                "teacher_id": teacher_id,
                "audio_record_id": "R001",
                "syllable_index": None,
                "accuracy_score": 4,
                "fluency_score": 4,
                "prosody_score": 3,
            },
        )
        assert sentence_rating.status_code == 200

    for teacher_id, feedback_verdict in (
        ("T01", "APPROPRIATE"), ("T02", "PARTIALLY_APPROPRIATE"),
    ):
        stage2_view = client.get(
            "/api/teacher-review/attempt/R001/stage2", params={"teacher_id": teacher_id}
        )
        assert stage2_view.status_code == 200
        assert stage2_view.json()["system_output"][0]["assistive_state_label"] == "CHECK_THIS_TONE"

        stage2_rating = client.post(
            "/api/teacher-review/ratings/stage2",
            json={
                "teacher_id": teacher_id,
                "audio_record_id": "R001",
                "syllable_index": 0,
                "retry_recommended": True,
                "feedback_appropriateness": feedback_verdict,
            },
        )
        assert stage2_rating.status_code == 200

    # ── Attempt A002 (FOCUSED_RETRY) / AudioRecord R002 ─────────────────
    # Same participant/session/item, a NEW attempt_id -- a retry is its own
    # attempt, never a mutation of A001's rows.
    _seed_audio_record(client, "R002", "A002", 2, "FOCUSED_RETRY", check_this_tone=False)
    retry_stage1 = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "T01",
            "audio_record_id": "R002",
            "syllable_index": 0,
            "consonant_score": 1,
            "vowel_score": 1,
            "tone_score": 1,
        },
    )
    assert retry_stage1.status_code == 200

    # ── Verify every join is by explicit ID fields, never by timestamp ──
    import database

    with database.connect_db() as db:
        audio_rows = db.execute(
            "SELECT id, student_id, session_id, topic_id, image_index, attempt_id, "
            "attempt_number, attempt_type FROM audio_records ORDER BY id"
        ).fetchall()
        rating_rows = db.execute(
            "SELECT rating_id, teacher_id, audio_record_id, participant_id, session_id, "
            "item_id, attempt_id, syllable_index, rating_stage, tone_score, "
            "retry_recommended, feedback_appropriateness "
            "FROM teacher_pronunciation_ratings ORDER BY attempt_id, teacher_id, rating_stage, "
            "COALESCE(syllable_index, -1)"
        ).fetchall()

    assert {r["id"]: r["attempt_id"] for r in audio_rows} == {"R001": "A001", "R002": "A002"}
    for row in audio_rows:
        assert row["student_id"] == PARTICIPANT_ID
        assert row["session_id"] == SESSION_ID
        assert row["topic_id"] == TOPIC_ID
        assert row["image_index"] == IMAGE_INDEX

    # A001 carries 6 rows (T01+T02 x {syllable stage1, sentence stage1, syllable stage2}).
    a001_rows = [r for r in rating_rows if r["attempt_id"] == "A001"]
    assert len(a001_rows) == 6
    assert {(r["teacher_id"], r["rating_stage"], r["syllable_index"]) for r in a001_rows} == {
        ("T01", "stage_1_blind", 0), ("T01", "stage_1_blind", None), ("T01", "stage_2_feedback_review", 0),
        ("T02", "stage_1_blind", 0), ("T02", "stage_1_blind", None), ("T02", "stage_2_feedback_review", 0),
    }
    for row in a001_rows:
        assert row["participant_id"] == PARTICIPANT_ID
        assert row["session_id"] == SESSION_ID
        assert row["item_id"] == ITEM_ID

    # A002 carries exactly the one retry-attempt rating, distinct from A001's.
    a002_rows = [r for r in rating_rows if r["attempt_id"] == "A002"]
    assert len(a002_rows) == 1
    assert a002_rows[0]["teacher_id"] == "T01"
    assert a002_rows[0]["rating_stage"] == "stage_1_blind"

    # Two independent teachers' Stage-1 tone judgments for the SAME syllable
    # were both preserved, never overwritten into one row.
    t01_tone = next(r for r in a001_rows if r["teacher_id"] == "T01" and r["rating_stage"] == "stage_1_blind" and r["syllable_index"] == 0)
    t02_tone = next(r for r in a001_rows if r["teacher_id"] == "T02" and r["rating_stage"] == "stage_1_blind" and r["syllable_index"] == 0)
    assert t01_tone["tone_score"] == 0
    assert t02_tone["tone_score"] == 1

    # Stage-2 feedback-appropriateness judgments differ per teacher, both kept.
    t01_stage2 = next(r for r in a001_rows if r["teacher_id"] == "T01" and r["rating_stage"] == "stage_2_feedback_review")
    t02_stage2 = next(r for r in a001_rows if r["teacher_id"] == "T02" and r["rating_stage"] == "stage_2_feedback_review")
    assert t01_stage2["feedback_appropriateness"] == "APPROPRIATE"
    assert t02_stage2["feedback_appropriateness"] == "PARTIALLY_APPROPRIATE"

    # Review queue reconstructs the same two attempts purely from IDs, with
    # correct per-teacher stage status and no system prediction leaked.
    queue_t01 = client.get("/api/teacher-review/queue", params={"teacher_id": "T01"}).json()
    statuses = {row["audio_record_id"]: row["review_status"] for row in queue_t01}
    assert statuses["R001"] == "STAGE_2_COMPLETE"
    assert statuses["R002"] == "STAGE_1_COMPLETE"
