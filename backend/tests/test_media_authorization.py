"""Media authorization regressions for student-facing story assets."""

from psycopg.types.json import Jsonb


def test_student_can_read_audio_referenced_by_published_conversation_turn(
    logged_in_student, tmp_path, monkeypatch
):
    import db
    import services.media as media_service

    upload_root = tmp_path / "uploads"
    audio_path = upload_root / "story_audio" / "conversation-model.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"conversation model audio")
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_root))

    stored_url = "/uploads/story_audio/conversation-model.mp3"
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories
                (id, title, frames, published, conversation_turns)
            VALUES (%s, %s, %s, TRUE, %s)
            """,
            (
                "conversation-media-story",
                "Conversation media story",
                Jsonb([]),
                Jsonb([{"id": "system-1", "speaker": "system", "audioUrl": stored_url}]),
            ),
        )

    client, _student = logged_in_student
    response = client.get(stored_url)

    assert response.status_code == 200
    assert response.content == b"conversation model audio"


def _story_with_vocab_audio(conn, story_id, stored_url, *, published):
    conn.execute(
        """
        INSERT INTO custom_stories
            (id, title, frames, published, vocab_assessment)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            story_id,
            story_id,
            Jsonb([]),
            published,
            Jsonb([{"wordId": "W001", "targetWord": "錢包", "audioUrl": stored_url}]),
        ),
    )


def test_student_can_read_vocabulary_audio_of_a_published_story(
    logged_in_student, tmp_path, monkeypatch
):
    import db
    import services.media as media_service

    upload_root = tmp_path / "uploads"
    audio_path = upload_root / "audio" / "vocab-published.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"vocab model audio")
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_root))

    stored_url = "/uploads/audio/vocab-published.mp3"
    with db.connect_db() as conn:
        _story_with_vocab_audio(conn, "vocab-audio-published", stored_url, published=True)

    client, _student = logged_in_student
    response = client.get(stored_url)

    assert response.status_code == 200
    assert response.content == b"vocab model audio"


def test_student_cannot_read_vocabulary_audio_of_an_unpublished_story(
    logged_in_student, tmp_path, monkeypatch
):
    import db
    import services.media as media_service

    upload_root = tmp_path / "uploads"
    audio_path = upload_root / "audio" / "vocab-draft.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"draft vocab audio")
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_root))

    stored_url = "/uploads/audio/vocab-draft.mp3"
    with db.connect_db() as conn:
        _story_with_vocab_audio(conn, "vocab-audio-draft", stored_url, published=False)

    client, _student = logged_in_student
    response = client.get(stored_url)

    assert response.status_code == 403
