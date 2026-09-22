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
