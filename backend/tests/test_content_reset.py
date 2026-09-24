from services.content_reset import clean_story_content, story_preservation_snapshot


def test_cleanup_preserves_story_frames_images_and_scripts():
    story = {
        "id": "story-1",
        "title": "Story",
        "lesson_number": 5,
        "lesson_sub_order": 2,
        "published": True,
        "frames": [
            {
                "imageUrl": "/uploads/images/story-1.jpg",
                "prompt": "Describe the scene.",
                "listenScript": "這是故事腳本。",
                "suggestedAnswer": "這是答案。",
                "vocabulary": "茶",
                "listenAudioUrl": "/uploads/audio/scene.wav",
                "vocabularyAudioUrls": '["/uploads/audio/word.wav"]',
                "vocabularyReferenceCurves": "old-curves",
                "wordId": "old-word-id",
            }
        ],
        "conversation_turns": [
            {
                "id": "system-1",
                "speaker": "system",
                "text": "你好。",
                "audioUrl": "/uploads/story_audio/character.wav",
            },
            {
                "id": "student-1",
                "speaker": "student",
                "text": "你好。",
                "targetText": "你好。",
                "targetAudioUrl": "/uploads/story_audio/model.wav",
            },
        ],
        "story_vocabulary": {"easy": {"word": "茶", "wordId": "old-word-id"}},
        "story_phrases": {"easy": {"phrase": "喝茶"}},
    }

    cleaned = clean_story_content(story, remove_quiz=True, remove_audio=True)
    frame = cleaned["frames"][0]

    assert len(cleaned["frames"]) == 1
    assert frame["imageUrl"] == story["frames"][0]["imageUrl"]
    assert frame["prompt"] == story["frames"][0]["prompt"]
    assert frame["listenScript"] == story["frames"][0]["listenScript"]
    assert frame["suggestedAnswer"] == story["frames"][0]["suggestedAnswer"]
    assert "listenAudioUrl" not in frame
    assert "vocabularyAudioUrls" not in frame
    assert "vocabularyReferenceCurves" not in frame
    assert "wordId" not in frame
    assert cleaned["conversation_turns"] == [
        {"id": "system-1", "speaker": "system", "text": "你好。"},
        {"id": "student-1", "speaker": "student", "text": "你好。", "targetText": "你好。"},
    ]
    assert cleaned["story_vocabulary"] == {"easy": {"word": "茶"}}


def test_story_snapshot_compares_only_fields_expected_to_survive():
    before = {
        "id": "story-1",
        "title": "Story",
        "lesson_number": 5,
        "lesson_sub_order": 1,
        "published": False,
        "frames": [{"imageUrl": "/uploads/images/story.jpg", "prompt": "Prompt", "listenAudioUrl": "/uploads/audio/x.wav"}],
        "conversation_turns": None,
        "story_vocabulary": None,
        "story_phrases": None,
    }
    after = clean_story_content(before, remove_quiz=True, remove_audio=True)
    assert story_preservation_snapshot([before], remove_quiz=True, remove_audio=True) == story_preservation_snapshot([after], remove_quiz=True, remove_audio=True)


def test_database_reset_preserves_story_skeleton_and_clears_learning_evidence(monkeypatch):
    import scripts.reset_learning_content as reset
    from db import connect_db
    from psycopg.types.json import Jsonb

    monkeypatch.setattr(reset, "_audio_files", lambda: [])
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO custom_stories
                (id, title, frames, published, vocab_assessment, conversation_turns)
            VALUES (%s, %s, %s, TRUE, %s, %s)
            """,
            (
                "reset-story",
                "Reset story",
                Jsonb([{
                    "imageUrl": "https://example.test/story.png",
                    "prompt": "Keep this prompt",
                    "listenScript": "Keep this script",
                    "listenAudioUrl": "/uploads/audio/old.wav",
                    "vocabularyDistractors": ["old"],
                }]),
                Jsonb([{"wordId": "old-word", "level": "easy"}]),
                Jsonb([{
                    "id": "turn-1",
                    "speaker": "system",
                    "text": "Keep this line",
                    "audioUrl": "/uploads/story_audio/old.wav",
                }]),
            ),
        )
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, completed_at, total_questions,
                 correct_count, total_time_ms, question_results)
            VALUES ('reset-attempt', 'reset-story', 'Student', '2026-01-01T00:00:00Z', 1, 0, 10, '[]'::jsonb)
            """
        )
        db.execute(
            """
            INSERT INTO vocab_quiz_responses
                (student_id, word_id, word, quiz_id, attempt_id, item_id,
                 question_type, correct, response_time_ms, attempt_order)
            VALUES ('student-1', 'old-word', '舊詞', 'quiz-1', 'reset-attempt',
                    'old-item', 'basic_meaning_mcq', FALSE, 10, 0)
            """
        )
        db.execute(
            """
            INSERT INTO student_vocab_mastery
                (student_id, word_id, p_learned, observation_count, correct_count,
                 incorrect_count, created_at, updated_at)
            VALUES ('student-1', 'old-word', .9, 3, 2, 1, '2026-01-01', '2026-01-01')
            """
        )
        db.execute(
            """
            INSERT INTO audio_records
                (id, timestamp, duration, transcription, model, audio_url)
            VALUES ('old-audio', '2026-01-01T00:00:00Z', 1, '', 'test', '/uploads/audio/old.wav')
            """
        )
        if db.execute("SELECT to_regclass('public.media_assets') AS name").fetchone()["name"]:
            db.execute(
                """
                INSERT INTO media_assets
                    (id, kind, source_type, source_id, storage_key, mime_type)
                VALUES ('audio:old-audio', 'student_recording', 'audio_record',
                        'old-audio', '/uploads/audio/old.wav', 'audio/wav')
                """
            )

    result = reset.reset_learning_content(
        remove_quiz=True,
        remove_audio=True,
        remove_dependent_state=True,
        execute=True,
    )

    assert result["after"]["stories"] == 1
    assert result["after"]["frames"] == 1
    assert result["after"]["quiz_questions"] == 0
    assert result["after"]["quiz_attempts"] == 0
    assert result["after"]["quiz_responses"] == 0
    assert result["after"]["audio_records"] == 0
    assert result["after"]["audio_media_assets"] == 0
    assert result["after"]["bkt_mastery"] == 0

    with connect_db() as db:
        story = db.execute(
            "SELECT frames, conversation_turns FROM custom_stories WHERE id = 'reset-story'"
        ).fetchone()
    assert story["frames"] == [{
        "imageUrl": "https://example.test/story.png",
        "prompt": "Keep this prompt",
        "listenScript": "Keep this script",
    }]
    assert story["conversation_turns"] == [{
        "id": "turn-1",
        "speaker": "system",
        "text": "Keep this line",
    }]
