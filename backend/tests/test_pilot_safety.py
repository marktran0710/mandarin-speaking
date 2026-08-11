"""PART 18: the 12 safety tests for the small-teacher-validated pilot
architecture. Some are exercised elsewhere and only cross-referenced here in
one place for the final report; the ones with no existing coverage are
implemented directly in this file.

  1. Pilot student sees only Speaking Practice.
     -> src/components/StoryRecorder.test.tsx, describe("pilot mode hides
        the Stable/Experimental selector (PART 1)") -- this app's "mode" IS
        the Stable/Experimental analysis-version selector (see the audit's
        own CONFIRMED CURRENT STATE #4), so hiding it hides the only other
        student-visible mode choice.
  2. Stable/Experimental remains hidden from pilot UI.
     -> same test file/describe block as #1.
  3. Candidate E2 is the only public E-family diagnostic scorer.
     -> test_e2_is_the_only_public_e_family_scorer below (structural guard).
  4. Candidate E V1 has no independent production call path.
     -> test_e_v1_has_no_independent_production_call_path below.
  5. Legacy FAIL cannot block pilot progression.
     -> StoryRecorder.test.tsx, "does not block progression on a legacy
        fail for a pilot session with active assistive feedback".
  6. CHECK_THIS_TONE cannot cause endless retries.
     -> src/utils/retryPolicy.test.ts (MAX_AUTOMATIC_RETRIES = 1, capped).
  7. Stage-1 teacher API contains no system judgments.
     -> test_teacher_review.py::test_stage1_view_excludes_all_system_judgment_fields.
  8. Stage 2 remains locked until Stage 1 is submitted.
     -> test_teacher_review.py::test_stage2_locked_until_stage1_submitted.
  9. Two teachers can rate the same attempt independently.
     -> test_teacher_review.py::test_two_teachers_rate_independently_without_overwriting.
 10. Teacher ratings are never prefilled from machine values.
     -> test_teacher_rating_is_never_prefilled_from_machine_values below.
 11. Sentence-level and syllable-level ratings remain distinct.
     -> test_teacher_review.py::test_sentence_and_syllable_level_ratings_stay_distinct
        and ::test_mixed_syllable_and_sentence_fields_rejected.
 12. attempt_id deterministically links research log / audio_record /
     system output / teacher rating.
     -> test_attempt_id_links_research_log_audio_record_and_teacher_rating below.
"""

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _imports_e2_or_f1_directly(py_file: Path) -> bool:
    """True if `py_file` imports assistive_feedback.e2_scoring or
    assistive_feedback.f1_artifact -- the only two modules that can reach
    Candidate E2/F1. Parsed via `ast`, not a text grep, so a comment or a
    string mentioning the module name can't produce a false positive."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("assistive_feedback.e2_scoring") or \
               node.module.startswith("assistive_feedback.f1_artifact"):
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("assistive_feedback.e2_scoring", "assistive_feedback.f1_artifact"):
                    return True
    return False


def test_e2_is_the_only_public_e_family_scorer():
    """No router and no request-path module other than
    `assistive_feedback/pipeline.py` may import the E2 scorer directly --
    that would open a second, ungoverned path to a diagnostic score."""
    request_path_files = [
        *((BACKEND_ROOT / "routers").glob("*.py")),
        BACKEND_ROOT / "main.py",
    ]
    offenders = [f for f in request_path_files if _imports_e2_or_f1_directly(f)]
    assert offenders == [], (
        f"These request-path files import Candidate E2/F1 directly, bypassing "
        f"assistive_feedback/pipeline.py: {[f.name for f in offenders]}"
    )


def test_e_v1_has_no_independent_production_call_path():
    """`routers/analysis_v2.py` (the "Experimental V2" endpoint) must not
    call Candidate E V1/E2 -- it only wraps the legacy
    `chinese_tones.detect_tone` path (per the prior runtime-scorer audit).
    A regression here would silently give Candidate E V1 a second,
    independent production decision path."""
    analysis_v2 = (BACKEND_ROOT / "routers" / "analysis_v2.py").read_text(encoding="utf-8")
    for forbidden in ("e2_scoring", "f1_artifact", "context_aware_contour_scorer", "score_segment_e2"):
        assert forbidden not in analysis_v2, (
            f"routers/analysis_v2.py references {forbidden!r} -- Candidate E V1/E2 "
            "must only be reachable through assistive_feedback/pipeline.py."
        )


AUDIO_RECORD = {
    "id": "rec-prefill-1",
    "timestamp": "2026-08-09T08:00:00Z",
    "duration": 1200,
    "transcription": "你好",
    "model": "whisper",
    "topicId": "lesson-1",
    "studentId": "participant-p001",
    "imageIndex": 0,
    "praatMetrics": {
        "assistive_feedback": [{
            "syllable_index": 0,
            "character": "你",
            "expected_underlying_tone": 3,
            "accepted_surface_tones": [2],
            "context_rule": "third_sandhi",
            "realization": "third_sandhi",
            # The SYSTEM says NEEDS_PRACTICE / CHECK_THIS_TONE for this syllable.
            "assistive_state": "NEEDS_PRACTICE",
            "assistive_state_label": "CHECK_THIS_TONE",
            "assistive_message": "This tone may be worth checking.",
            "e2_diagnostic_category": "C_t3_t3_to_t2",
            "explanation": {"e2_provenance": "measured", "e2_matched_tone": 2, "boundary_before": False, "boundary_after": False},
        }],
    },
    "sessionId": "session-abc",
    "attemptId": "attempt-prefill-1",
    "attemptNumber": 1,
    "attemptType": "WHOLE_SENTENCE_INITIAL",
}


def test_teacher_rating_is_never_prefilled_from_machine_values(client):
    """The system's own judgment for this syllable is NEEDS_PRACTICE
    (tone_score would be 0 if derived from it). A teacher submitting the
    OPPOSITE human judgment (tone_score=1, "acceptable") must be stored
    exactly as submitted -- proving no server-side code path derives or
    overrides a rubric score from `assistive_state`/`e2_diagnostic_category`/
    F1/legacy `passed`."""
    assert client.post("/api/audio-records", json=AUDIO_RECORD).status_code == 200

    response = client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-prefill-1",
            "syllable_index": 0,
            "consonant_score": 1,
            "vowel_score": 1,
            "tone_score": 1,  # Disagrees with the system's CHECK_THIS_TONE verdict.
        },
    )
    assert response.status_code == 200

    import database
    with database.connect_db() as db:
        row = db.execute(
            "SELECT tone_score FROM teacher_pronunciation_ratings WHERE audio_record_id = 'rec-prefill-1'"
        ).fetchone()
    assert row["tone_score"] == 1  # Exactly what the teacher submitted, not what the system said.


def test_attempt_id_links_research_log_audio_record_and_teacher_rating(client, tmp_path, monkeypatch):
    """Three independently-written data stores -- the JSONL research log
    (`assistive_feedback/research_log.py`), the `audio_records` table, and
    `teacher_pronunciation_ratings` -- must all resolve to the SAME
    participant/session/item when queried by the SAME `attempt_id`, with no
    timestamp-based reconciliation anywhere in the lookup."""
    from assistive_feedback import research_log

    log_path = tmp_path / "research_log.jsonl"
    attempt_id = "attempt-join-1"

    research_log.log_attempt(
        research_log.AttemptLogRecord(
            attempt_id=attempt_id,
            participant_id="participant-p001",
            item_id="lesson-1:0",
            syllable_index=0,
            character="你",
            policy_state="NEEDS_PRACTICE",
            f1_risk_score=0.82,
            e2_diagnostic_category="C_t3_t3_to_t2",
            e2_score=0.1,
            expected_tone=3,
            accepted_surface_tones=[2],
            session_id="session-abc",
            attempt_number=1,
            attempt_type="WHOLE_SENTENCE_INITIAL",
            study_phase="pilot",
            feedback_enabled=True,
        ),
        path=log_path,
    )

    audio_record = {**AUDIO_RECORD, "id": "rec-join-1", "attemptId": attempt_id}
    assert client.post("/api/audio-records", json=audio_record).status_code == 200
    assert client.post(
        "/api/teacher-review/ratings/stage1",
        json={
            "teacher_id": "Ms. Chen",
            "audio_record_id": "rec-join-1",
            "syllable_index": 0,
            "consonant_score": 1,
            "vowel_score": 1,
            "tone_score": 0,
        },
    ).status_code == 200

    log_rows = [r for r in research_log.read_records(log_path) if r["attempt_id"] == attempt_id]
    import database
    with database.connect_db() as db:
        audio_row = db.execute(
            "SELECT * FROM audio_records WHERE attempt_id = %s", (attempt_id,)
        ).fetchone()
        rating_row = db.execute(
            "SELECT * FROM teacher_pronunciation_ratings WHERE attempt_id = %s", (attempt_id,)
        ).fetchone()

    assert len(log_rows) == 1
    assert audio_row is not None and rating_row is not None

    # The join key (attempt_id) is the only thing used to find these three
    # rows above -- now confirm they genuinely describe the same event.
    assert log_rows[0]["participant_id"] == audio_row["student_id"] == rating_row["participant_id"]
    assert log_rows[0]["session_id"] == audio_row["session_id"] == rating_row["session_id"]
    assert log_rows[0]["item_id"] == rating_row["item_id"]
