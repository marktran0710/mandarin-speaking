"""POST /api/pronunciation/evaluate: target and reference come from the server."""

import json
import os

import pytest
from psycopg.types.json import Jsonb

import db
from pron_audio import synth_wav
from services.pronunciation import rubric_evaluator as evaluator_module
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
    monkeypatch.setenv("PRONUNCIATION_FEEDBACK_API_KEY", "sk-test")
    async def successful_http(url, headers, body, timeout):
        evidence = json.loads(body["messages"][1]["content"])
        reply = {
            "summary": "Compare the recording with the reference.",
            "fluency_feedback": "Keep the sentence flowing between phrase boundaries.",
            "prosody_feedback": "Follow the reference sentence pitch and relative timing.",
            "practice_tip": "Practise the whole sentence slowly.",
        }
        return {"choices": [{"message": {"content": json.dumps(reply)}}]}
    monkeypatch.setattr(evaluator_module, "build_feedback_provider", lambda config=None: OpenAICompatibleFeedbackProvider(config, successful_http))
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
    assert "score" not in body
    assert body["dimensions"]["accuracy"]["score"] is None
    assert body["dimensions"]["fluency"]["score"] == 5
    assert body["dimensions"]["prosody"]["score"] == 5
    assert body["dimensions"]["fluency"]["measurements"]["speech_rate"] > 0
    assert body["feedback"]["summary"]
    assert body["model"]["scoring_version"] == "pronunciation-rubric-v1"
    debug = body["debug"]
    assert debug["provenance"]["expected_text"] == TEXT  # resolved server-side
    assert debug["reference_features"]["syllables"][0]["f0_points"]
    assert debug["student_features"]["syllables"][2]["direction"] == "fall"
    assert debug["policy"]["validation_status"] == "uncalibrated_engineering_defaults"


def test_a_flat_tone_is_reported_per_word_with_its_flag(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    body = _post(client, _wav(isolated, ("flat", "rise", "flat"))).json()
    assert "score" not in body
    assert body["words"] == []  # diagnostic tone flags do not claim Accuracy
    assert body["dimensions"]["accuracy"]["ai_result"] is None
    assert body["dimensions"]["prosody"]["score"] < 5
    assert body["feedback"]["focus_words"] == []


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
    assert "score" not in body
    assert body["dimensions"]["accuracy"]["score"] is None
    assert body["dimensions"]["fluency"]["score"] == 5
    assert body["dimensions"]["prosody"]["score"] == 5
    assert "debug" not in body
    assert "f0_points" not in response.text
    assert body["feedback"]["dimension_feedback"]["fluency"]


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


def test_unreadable_audio_is_reported_without_local_feedback(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    response = _post(client, b"definitely not a wav file")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "recording_unscorable"


def test_an_unreadable_reference_recording_is_a_server_side_problem_with_a_code(isolated, logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_story()
    (isolated / "story_audio" / "ref.wav").write_bytes(b"corrupt")
    response = _post(client, _wav(isolated))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "reference_unreadable"


def test_model_failure_is_reported_without_local_feedback(isolated, logged_in_teacher, monkeypatch):
    async def failing_http(url, headers, body, timeout):
        raise RuntimeError("503 upstream")

    provider = OpenAICompatibleFeedbackProvider(
        FeedbackConfig(api_key="sk-test", model="gpt-6-luna", base_url="https://llm.test/v1"), failing_http
    )
    monkeypatch.setattr(evaluator_module, "build_feedback_provider", lambda config=None: provider)
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    response = _post(client, _wav(isolated, ("flat", "rise", "flat")))
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "llm_error_RuntimeError"
    assert "No local feedback" in response.json()["detail"]["message"]


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


def test_missing_model_key_is_reported_without_local_feedback(isolated, logged_in_teacher, monkeypatch):
    from services.pronunciation.feedback import LocalFeedbackProvider
    monkeypatch.setattr(evaluator_module, "build_feedback_provider", lambda config=None: LocalFeedbackProvider())
    client, _ = logged_in_teacher
    _publish_story()
    _reference(isolated)
    response = _post(client, _wav(isolated))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"


@pytest.fixture
def stable_speaking_analysis(monkeypatch):
    from unittest.mock import AsyncMock
    from api.schemas.models import AnalysisResponse
    import main
    analysis = AnalysisResponse(
        transcription=TEXT, pitch_contour=[], word_prosody=[], detected_tone=1,
        tone_accuracy=80, formants={}, speech_rate=3, fluency_score=80,
        pitch_statistics={}, feedback="Old feedback", ai_feedback={},
        content_match=True, pronunciation_mastery={"passed": True},
    )
    analyzer = AsyncMock(return_value=analysis)
    monkeypatch.setattr(main, "_do_analyze", analyzer)
    monkeypatch.setattr(main, "save_uploaded_audio", AsyncMock(return_value="/uploads/audio/attempt.wav"))
    return analyzer


@pytest.mark.parametrize("verified,conversation", [(True, False), (True, True), (False, False), (False, True)])
def test_speaking_flows_return_and_save_gpt_feedback(
    isolated, logged_in_student, stable_speaking_analysis, verified, conversation,
):
    client, _ = logged_in_student
    turns = [{"id": "student-1", "speaker": "student", "text": TEXT, "targetText": TEXT,
              "targetAudioUrl": "/uploads/story_audio/ref.wav"}] if conversation else None
    _publish_story(turns=turns)
    _reference(isolated)
    data = {"base_story_id": STORY_ID, "scene_index": "0", "pronunciation_feedback": "true",
            "attempt_id": "new-feedback-attempt"}
    if conversation:
        data.update(conversation_id="conv-1", turn_id="student-1", turn_index="0")
    endpoint = "/api/analyze/verified" if verified else "/api/analyze"
    audio = _wav(isolated)
    response = client.post(endpoint, files={"file": ("recording.wav", audio, "audio/wav")}, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    analysis = body["analysis"] if verified else body
    assert "score" not in analysis["pronunciation_evaluation"]
    assert analysis["pronunciation_evaluation"]["dimensions"]["accuracy"]["score"] is None
    assert analysis["pronunciation_evaluation"]["dimensions"]["prosody"]["score"] == 5
    assert analysis["pronunciation_evaluation"]["model"]["feedback_model"] == "gpt-6-luna"
    assert analysis["pronunciation_evaluation"]["reference"]["audio_url"] == "/uploads/story_audio/ref.wav"
    assert "debug" not in analysis["pronunciation_evaluation"]
    assert analysis["feedback_provenance"]["fallback_used"] is False
    assert analysis["processing_trace"]["stages"][-1]["model"] == "gpt-6-luna"
    assert analysis["content_match"] is True
    assert stable_speaking_analysis.call_args.kwargs["skip_language_feedback"] is True
    if verified:
        with db.connect_db() as conn:
            saved = conn.execute("SELECT praat_metrics FROM audio_records WHERE attempt_id = %s", (data["attempt_id"],)).fetchone()
        assert saved["praat_metrics"]["pronunciation_evaluation"] == analysis["pronunciation_evaluation"]
        replay = client.post(endpoint, files={"file": ("recording.wav", audio, "audio/wav")}, data=data)
        assert replay.status_code == 200, replay.text
        assert replay.json()["analysis"]["pronunciation_evaluation"] == analysis["pronunciation_evaluation"]
        assert stable_speaking_analysis.await_count == 1


def test_gpt_failure_does_not_persist_a_successful_speaking_attempt(
    isolated, logged_in_student, stable_speaking_analysis, monkeypatch,
):
    from services.pronunciation.feedback import FeedbackRejected
    async def failed_http(*args):
        raise FeedbackRejected("llm_http_401")
    monkeypatch.setattr(evaluator_module, "build_feedback_provider", lambda config=None: OpenAICompatibleFeedbackProvider(config, failed_http))
    client, _ = logged_in_student
    _publish_story()
    _reference(isolated)
    response = client.post("/api/analyze/verified", files={"file": ("recording.wav", _wav(isolated), "audio/wav")},
                           data={"base_story_id": STORY_ID, "scene_index": "0", "pronunciation_feedback": "true", "attempt_id": "failed-feedback"})
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "llm_http_401"
    with db.connect_db() as conn:
        assert conn.execute("SELECT id FROM audio_records WHERE attempt_id = %s", ("failed-feedback",)).fetchone() is None


@pytest.mark.parametrize("matches", [True, False])
def test_generated_conversation_reuses_only_a_matching_scene_sample(isolated, matches):
    from services.pronunciation.reference_source import resolve_reference_source
    from services.pronunciation.evaluator import EvaluationError
    _publish_story()
    _reference(isolated)
    if matches:
        reference = resolve_reference_source(STORY_ID, 0, conversation_id="conv", turn_id="student-scene-0", expected_text=TEXT)
        assert reference.audio_url == "/uploads/story_audio/ref.wav"
    else:
        with pytest.raises(EvaluationError, match="different sentence"):
            resolve_reference_source(STORY_ID, 0, conversation_id="conv", turn_id="student-scene-0", expected_text="你好")
