"""The row_to_* helpers used to json.loads() TEXT columns. With JSONB,
psycopg hands back already-parsed Python objects — these tests pin that the
helpers pass them through instead of double-parsing (which raises TypeError
on a dict), and that the API-facing shape is unchanged."""
import pytest

import database


def test_row_to_custom_story_passes_through_parsed_jsonb():
    row = {
        "id": "s1",
        "title": "我的房間",
        "learning_goal": "describe a room",
        "frames": [{"prompt": "這是我的房間。", "vocabulary": "房間"}],
        "published": True,
        "linear": False,
        "lesson_number": 5,
        "narrative_mode": "story",
        "first_frame_is_example": False,
        "quiz_exclusions": [{"word": "房間", "kind": "cloze"}],
    }
    result = database.row_to_custom_story(row)
    assert result["frames"] == [{"prompt": "這是我的房間。", "vocabulary": "房間"}]
    assert result["published"] is True
    assert result["linear"] is False
    assert result["lessonNumber"] == 5
    assert result["quizExclusions"] == [{"word": "房間", "kind": "cloze"}]


def test_row_to_custom_story_handles_null_jsonb():
    row = {
        "id": "s2",
        "title": "t",
        "learning_goal": "g",
        "frames": None,
        "published": False,
        "linear": False,
        "lesson_number": None,
        "narrative_mode": "story",
        "first_frame_is_example": False,
        "quiz_exclusions": None,
    }
    result = database.row_to_custom_story(row)
    assert result["frames"] == []
    assert result["quizExclusions"] == []


def test_row_to_story_submission_shape():
    row = {
        "id": "sub1",
        "story_id": "teacher-s1",
        "story_title": "我的房間",
        "student_name": "Mai",
        "submitted_at": "2026-07-26T08:00:00Z",
        "scenes": [{"sceneIndex": 0, "transcription": "你好"}],
        "concatenated_audio_url": "/uploads/story_audio/sub1.wav",
        "story_feedback": {"overall": 7},
    }
    result = database.row_to_story_submission(row)
    assert result["scenes"] == [{"sceneIndex": 0, "transcription": "你好"}]
    assert result["storyFeedback"] == {"overall": 7}
    assert result["concatenatedAudioUrl"] == "/uploads/story_audio/sub1.wav"
    assert result["reviewStatus"] == "pending"
    assert result["teacherNote"] is None

    row["review_status"] = "reviewed"
    row["teacher_note"] = "Strong scene transitions."
    reviewed = database.row_to_story_submission(row)
    assert reviewed["reviewStatus"] == "reviewed"
    assert reviewed["teacherNote"] == "Strong scene transitions."


def test_row_to_vocab_quiz_attempt_shape():
    row = {
        "id": "a1",
        "story_id": "teacher-s1",
        "student_name": "Mai",
        "student_id": "stu-1",
        "mode": "tier2",
        "completed_at": "2026-07-26T08:00:00Z",
        "total_questions": 10,
        "correct_count": 8,
        "total_time_ms": 42000,
        "question_results": [{"word": "房間", "correct": True, "timeMs": 1200}],
    }
    result = database.row_to_vocab_quiz_attempt(row)
    assert result["questionResults"] == [{"word": "房間", "correct": True, "timeMs": 1200}]
    assert result["totalQuestions"] == 10


def test_row_to_audio_record_shape():
    row = {
        "id": "r1",
        "timestamp": "2026-07-26T08:00:00Z",
        "duration": 3000,
        "transcription": "你好",
        "model": "whisper",
        "topic_id": "teacher-s1",
        "image_url": "/uploads/images/a.png",
        "image_index": 0,
        "audio_url": "/uploads/audio/r1.wav",
        "praat_metrics": {"toneAccuracy": 0.8},
        "student_id": None,
    }
    result = database.row_to_audio_record(row)
    assert result["praatMetrics"] == {"toneAccuracy": 0.8}
    assert result["topicId"] == "teacher-s1"
    assert result["studentId"] is None


def test_ensure_column_helpers_are_gone():
    """Alembic owns the schema now — a leftover ensure_column() would create
    a second, silent migration path that Alembic doesn't know about."""
    assert not hasattr(database, "ensure_column")
    assert not hasattr(database, "ensure_column_dropped")
