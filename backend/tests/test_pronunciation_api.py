"""POST /api/pronunciation/evaluate: target and reference come from the server."""

import os

import pytest
from psycopg.types.json import Jsonb

import db
from pron_audio import synth_wav
from services.pronunciation import evaluator as evaluator_module
from services.pronunciation.config import FeedbackConfig
from services.pronunciation.feedback import OpenAICompatibleFeedbackProvider
from services.pronunciation.reference_cache import InMemoryReferenceStore

URL = "/api/pronunciation/evaluate"
TEXT = "媽麻罵"
STORY_ID = "pron-story"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No network, a private reference store and a private upload directory."""
    # Every test logs in as the same teacher; the login limiter (10 per minute
    # per account) would otherwise start rejecting the fixture's login.
    import security.auth as auth

    auth._login_attempts.clear()
    for name in ("OPENAI_API_KEY", "PRONUNCIATION_FEEDBACK_API_KEY", "PRONUNCIATION_SCORE_STUDENT_VISIBLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(evaluator_module, "default_reference_store", InMemoryReferenceStore())
    import services.pronunciation.reference_source as reference_source

    monkeypatch.setattr(reference_source, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "story_audio").mkdir()
    return tmp_path


def _publish_story(reference_url="/uploads/story_audio/ref.wav", *, published=True, turns=None):
    frame = {
        "imageUrl": "/scene.png", "prompt": "Say it", "vocabulary": "",
        "suggestedAnswer": TEXT, "listenScript": TEXT,
    }
    if reference_url:
        frame["listenAudioUrl"] = reference_url
    with db.connect_db() as conn:
        conn.execute(
            "INSERT INTO custom_stories (id, title, frames, published, conversation_turns) VALUES (%s, %s, %s, %s, %s)",
            (STORY_ID, "Pron story", Jsonb([frame]), published, Jsonb(turns) if turns else None),
        )


def _reference(isolated, shapes=("flat", "rise", "fall")):
    return synth_wav(isolated / "story_audio" / "ref.wav", list(shapes))


def _wav(isolated, shapes=("flat", "rise", "fall"), **kwargs) -> bytes:
    with open(synth_wav(isolated / "student.wav", list(shapes), **kwargs), "rb") as handle:
        return handle.read()


def _post(client, audio: bytes, **data):
    payload = {"story_id": STORY_ID, "scene_index": "0", **data}
    return client.post(URL, files={"file": ("a.wav", audio, "audio/wav")}, data=payload)


def test_a_teacher_gets_the_score_feedback_and_full_debug_evidence(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    body = _post(client, _wav(isolated, base_hz=200)).json()
    assert body["status"] == "scored"
    assert body["score"]["total"] == 100
    by_key = {d["key"]: d for d in body["score"]["dimensions"]}
    assert by_key["tone"]["basis"] == "measured" and by_key["segmental"]["basis"] == "unavailable"
    assert body["feedback"]["summary"]
    assert body["model"]["scoring_version"] == "pronunciation-score-v1"
    debug = body["debug"]
    assert debug["provenance"]["expected_text"] == TEXT  # resolved server-side
    assert debug["reference_features"]["syllables"][0]["f0_points"]
    assert debug["student_features"]["syllables"][2]["direction"] == "fall"
    assert debug["policy"]["weights"]["tone"] == 0.4


def test_a_flat_tone_is_reported_per_word_with_its_flag(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    body = _post(client, _wav(isolated, ("flat", "rise", "flat"))).json()
    assert body["score"]["total"] < 100
    word = next(w for w in body["words"] if w["word"] == "罵")
    assert word["flags"] == ["tone_contour_too_flat"]
    assert (word["reference_shape"], word["student_shape"]) == ("fall", "flat")
    assert body["feedback"]["focus_words"][0]["word"] == "罵"


def test_students_do_not_see_the_score_until_it_is_enabled(isolated, logged_in_student):
    client, _ = logged_in_student
    _publish_story()
    _reference(isolated)
    response = _post(client, _wav(isolated))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "pronunciation_score_not_enabled"


def test_an_enabled_student_gets_no_debug_or_raw_pitch_data(isolated, logged_in_student, monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_SCORE_STUDENT_VISIBLE", "true")
    client, _ = logged_in_student
    _publish_story()
    _reference(isolated)
    response = _post(client, _wav(isolated))
    assert response.status_code == 200
    body = response.json()
    assert body["score"]["total"] == 100
    assert "debug" not in body
    assert "f0_points" not in response.text
    assert set(body["feedback"]) == {"summary", "focus_words", "practice_tip"}


def test_an_anonymous_caller_is_rejected(isolated, anonymous_client):
    _publish_story()
    assert _post(anonymous_client, b"x").status_code == 401


def test_a_story_without_a_reference_recording_says_so(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story(reference_url=None)
    response = _post(client, _wav(isolated))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reference_audio_missing"


def test_a_reference_path_outside_the_upload_directory_is_refused(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story(reference_url="/uploads/../../etc/passwd")
    response = _post(client, _wav(isolated))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reference_audio_missing"


def test_an_unknown_or_unpublished_story_is_not_found(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    assert _post(client, _wav(isolated), story_id="nope").status_code == 404
    _publish_story(published=False)
    assert _post(client, _wav(isolated)).status_code == 404


def test_empty_audio_is_a_bad_request(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    response = _post(client, b"")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_audio"


def test_audio_praat_cannot_read_gives_an_unscorable_result_not_an_error(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    response = _post(client, b"definitely not a wav file")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unscorable"
    assert body["score"]["total"] is None
    assert "again" in body["feedback"]["summary"].lower()


def test_an_unreadable_reference_recording_is_a_server_side_problem_with_a_code(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    (isolated / "story_audio" / "ref.wav").write_bytes(b"corrupt")
    response = _post(client, _wav(isolated))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "reference_unreadable"


def test_the_score_survives_the_feedback_model_being_down(isolated, logged_in_teacher, monkeypatch):
    async def failing_http(url, headers, body, timeout):
        raise RuntimeError("503 upstream")

    provider = OpenAICompatibleFeedbackProvider(
        FeedbackConfig(api_key="sk-test", model="gpt-6-luna", base_url="https://llm.test/v1"), failing_http
    )
    monkeypatch.setattr(evaluator_module, "build_feedback_provider", lambda config=None: provider)
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    body = _post(client, _wav(isolated, ("flat", "rise", "flat"))).json()
    assert body["status"] == "scored" and body["score"]["total"] is not None
    assert body["model"]["feedback_source"] == "local"
    assert body["debug"]["provenance"]["feedback_fallback_reason"].startswith("llm_error")
    assert body["words"]


def test_the_reference_is_analysed_once_across_requests(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    first = _post(client, _wav(isolated)).json()
    second = _post(client, _wav(isolated, ("flat", "rise", "flat"))).json()
    assert first["reference"]["cache_hit"] is False
    assert second["reference"]["cache_hit"] is True


def test_a_conversation_turn_is_scored_against_its_own_target_recording(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    turns = [
        {"id": "sys-1", "speaker": "system", "text": "你好嗎"},
        {"id": "stu-1", "speaker": "student", "text": TEXT, "targetText": TEXT,
         "targetAudioUrl": "/uploads/story_audio/turn.wav"},
    ]
    _publish_story(reference_url=None, turns=turns)
    synth_wav(isolated / "story_audio" / "turn.wav", ["flat", "rise", "fall"])
    response = _post(client, _wav(isolated), conversation_id="c1", turn_id="stu-1", turn_index="1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "scored"
    assert body["reference"]["key"] == f"story:{STORY_ID}:turn:stu-1"
