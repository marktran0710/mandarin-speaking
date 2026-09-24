"""Conversation Practice data contract (Dual Speaking Modes plan, Epic 1):
conversationTurns round-trips through POST/GET /api/custom-stories,
including the optional student-only targetAudioUrl field, kept distinct
from the system turn's own audioUrl (the character's line, never reused
as a stand-in for the student's model response audio)."""

STORY = {
    "id": "conv-story-1",
    "title": "Conversation story",
    "frames": [{"imageUrl": "", "prompt": "友美，妳這個週末要做什麼？", "vocabulary": ""}],
    "conversationTurns": [
        {
            "id": "system-1",
            "speaker": "system",
            "text": "友美，妳這個週末要做什麼？",
            "pinyin": "Yǒuměi, nǐ zhège zhōumò yào zuò shénme?",
            "translation": "What are you doing this weekend?",
            "audioUrl": "/uploads/story_audio/character-turn-01.mp3",
        },
        {
            "id": "student-1",
            "speaker": "student",
            "text": "我想跟朋友去喝下午茶。",
            "targetText": "我想跟朋友去喝下午茶。",
            "targetAudioUrl": "/uploads/story_audio/student-model-01.mp3",
            "pinyin": "Wǒ xiǎng gēn péngyǒu qù hē xiàwǔchá.",
            "translation": "I want to have afternoon tea with my friends.",
        },
    ],
    "published": True,
    "lessonNumber": 5,
}


def test_conversation_turns_round_trip_including_target_audio_url(admin_client):
    assert admin_client.post("/api/custom-stories", json=STORY).status_code == 200

    stories = admin_client.get("/api/custom-stories").json()
    saved = next(s for s in stories if s["id"] == "conv-story-1")
    turns = saved["conversationTurns"]
    assert len(turns) == 2

    system_turn, student_turn = turns
    assert system_turn["audioUrl"] == "/uploads/story_audio/character-turn-01.mp3"
    assert "targetAudioUrl" not in system_turn or system_turn["targetAudioUrl"] is None

    assert student_turn["targetText"] == "我想跟朋友去喝下午茶。"
    assert student_turn["targetAudioUrl"] == "/uploads/story_audio/student-model-01.mp3"
    # The character's audio and the student's model audio must never collapse
    # onto the same field/value.
    assert student_turn.get("audioUrl") != system_turn["audioUrl"]


def test_conversation_turns_are_optional_and_default_to_none(admin_client):
    story = {**STORY, "id": "conv-story-2", "conversationTurns": None}
    assert admin_client.post("/api/custom-stories", json=story).status_code == 200

    stories = admin_client.get("/api/custom-stories").json()
    saved = next(s for s in stories if s["id"] == "conv-story-2")
    assert saved["conversationTurns"] is None
