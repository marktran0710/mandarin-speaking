import scripts.purge_custom_stories as purge

from scripts.purge_custom_stories import TARGET_STORY_IDS, deletion_order, target_ids_with_aliases


def test_manifest_is_exactly_the_reviewed_lesson_5_to_8_scope():
    expected = {
        "custom-story-1785137028726", "custom-story-1785204635939", "custom-story-1785205277637",
        "custom-story-1785235297869", "custom-story-1785310310407", "custom-story-1784770916021",
        "custom-story-1783739495489", "custom-story-1782894133778", "custom-story-1783556771524",
        "custom-story-1784207590772", "lesson-wo-de-fangjian", "lesson-vv-kan",
        "modern-chinese-l6-dialogue-1", "modern-chinese-l6-dialogue-2", "modern-chinese-l6-reading",
        "modern-chinese-l7-dialogue-1", "modern-chinese-l7-dialogue-2", "modern-chinese-l7-reading",
        "modern-chinese-l8-dialogue-1", "modern-chinese-l8-dialogue-2", "modern-chinese-l8-reading",
    }
    assert len(TARGET_STORY_IDS) == 21
    assert set(TARGET_STORY_IDS) == expected
    assert "custom-story-1785065694751" not in TARGET_STORY_IDS


def test_target_ids_include_teacher_aliases_without_losing_canonical_ids():
    target_ids = target_ids_with_aliases(("story-a", "story-b"))
    assert target_ids == (
        "story-a", "story-a-medium", "story-a-hard",
        "story-b", "story-b-medium", "story-b-hard",
        "teacher-story-a", "teacher-story-a-medium", "teacher-story-a-hard",
        "teacher-story-b", "teacher-story-b-medium", "teacher-story-b-hard",
    )
    assert "teacher-story-a-medium" in target_ids


def test_deletion_order_removes_dependents_before_story_rows():
    order = deletion_order()
    assert order[-1] == "custom_stories"
    assert order.index("audio_records") < order.index("custom_stories")
    assert order.index("vocab_quiz_attempts") < order.index("custom_stories")
    assert order.index("vocab_quiz_responses") < order.index("custom_stories")


def test_pronunciation_rating_scope_uses_audio_and_item_id_only(monkeypatch):
    sql = []
    monkeypatch.setattr(purge, "_table_exists", lambda _db, table: table == "teacher_pronunciation_ratings")
    monkeypatch.setattr(purge, "_column_exists", lambda _db, _table, column: column in {"audio_record_id", "attempt_id", "item_id"})
    monkeypatch.setattr(purge, "_audio_ids", lambda _db, _ids: ["audio-1"])
    monkeypatch.setattr(purge, "_count", lambda _db, statement, _params: sql.append(statement) or 0)
    counts = purge.count_candidates(object())
    assert counts["teacher_pronunciation_ratings"] == 0
    assert "audio_record_id = ANY" in sql[0]
    assert "item_id LIKE ANY" in sql[0]
    assert "attempt_id" not in sql[0]


def test_mastery_rebuild_is_scoped_to_students_with_deleted_responses(monkeypatch):
    rebuilt = []
    monkeypatch.setattr(purge, "_table_exists", lambda _db, table: table == "student_vocab_mastery")
    monkeypatch.setattr(purge, "rebuild_student_vocabulary_mastery", lambda _db, student: rebuilt.append(student))
    assert purge._rebuild_affected_mastery(object(), ["s1", "s2", "s1"]) == 3
    assert rebuilt == ["s1", "s2", "s1"]


def test_upload_path_stays_inside_persistent_upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(purge, "UPLOAD_ROOT", tmp_path.resolve())
    assert purge._upload_path("/uploads/story_audio/clip.wav") == (tmp_path / "story_audio" / "clip.wav").resolve()
    assert purge._upload_path("/uploads/../secret.txt") is None
    assert purge._upload_path("https://example.com/clip.wav") is None


def test_execute_purge_deletes_dependents_before_custom_stories(monkeypatch):
    calls = []
    rebuilt = []

    class Database:
        def execute(self, sql, _params):
            calls.append(("query", sql))
            return self

        def fetchall(self):
            return []

    tables = {
        "teacher_pronunciation_ratings", "media_assets", "learning_measurement_events",
        "speaking_progress", "audio_records", "story_submissions", "vocab_quiz_attempts",
        "vocab_quiz_responses", "custom_stories",
    }
    monkeypatch.setattr(purge, "_table_exists", lambda _db, table: table in tables)
    monkeypatch.setattr(purge, "_column_exists", lambda _db, _table, column: column in {"audio_record_id", "item_id"})
    monkeypatch.setattr(purge, "_audio_ids", lambda _db, _ids: ["audio-1"])
    monkeypatch.setattr(purge, "_affected_response_students", lambda _db, _ids: ["student-1"])
    monkeypatch.setattr(purge, "_delete", lambda _db, table, where, _params: calls.append((table, where)) or 0)
    monkeypatch.setattr(purge, "_rebuild_affected_mastery", lambda _db, students: rebuilt.extend(students) or len(students))

    deleted = purge.execute_purge(Database())
    assert deleted["custom_stories"] == 0
    delete_tables = [name for name, _ in calls if name != "query"]
    assert delete_tables[-1] == "custom_stories"
    assert delete_tables.index("vocab_quiz_responses") < delete_tables.index("custom_stories")
    rating_where = next(where for name, where in calls if name == "teacher_pronunciation_ratings")
    assert "audio_record_id = ANY" in rating_where
    assert "item_id LIKE ANY" in rating_where
    assert "attempt_id" not in rating_where
    assert rebuilt == ["student-1"]
