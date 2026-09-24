"""Pure field-level cleanup helpers for the learning-content reset command.

These helpers deliberately operate on copied JSON values.  The reset command
uses them to remove quiz/audio-owned fields while retaining the story/frame
shape and all authored text and images.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


QUIZ_FRAME_FIELDS = frozenset(
    {
        "vocabularyDistractors",
        "vocabularyCloze",
        "vocabularySynonym",
    }
)


QUIZ_REFERENCE_KEYS = frozenset(
    {
        "questionid",
        "quizid",
        "quizquestionid",
        "wordid",
        "vocabularyitemid",
    }
)


def _key_token(key: object) -> str:
    return "".join(character for character in str(key).casefold() if character.isalnum())


def is_audio_key(key: object) -> bool:
    """Return whether a JSON key owns or points at uploaded/derived audio."""

    token = _key_token(key)
    return (
        "audio" in token
        or "referencecurve" in token
        or "pronunciationreference" in token
    )


def is_quiz_key(key: object) -> bool:
    """Return whether a JSON key is obsolete quiz material or an old ID link."""

    quiz_frame_tokens = {_key_token(field) for field in QUIZ_FRAME_FIELDS}
    return _key_token(key) in quiz_frame_tokens or _key_token(key) in QUIZ_REFERENCE_KEYS


def clean_json_value(
    value: Any,
    *,
    remove_quiz: bool = False,
    remove_audio: bool = False,
) -> Any:
    """Copy JSON-compatible data, dropping only owned stale references."""

    if isinstance(value, Mapping):
        cleaned: dict[Any, Any] = {}
        for key, child in value.items():
            if remove_audio and is_audio_key(key):
                continue
            if remove_quiz and is_quiz_key(key):
                continue
            cleaned[key] = clean_json_value(
                child,
                remove_quiz=remove_quiz,
                remove_audio=remove_audio,
            )
        return cleaned
    if isinstance(value, list):
        return [
            clean_json_value(item, remove_quiz=remove_quiz, remove_audio=remove_audio)
            for item in value
        ]
    return value


def clean_story_content(
    story: Mapping[str, Any],
    *,
    remove_quiz: bool,
    remove_audio: bool,
) -> dict[str, Any]:
    """Return a safe copy of authored story JSON with stale owned fields removed.

    ``frames`` and ``conversation_turns`` are validated because silently
    replacing malformed authored content would be more dangerous than
    stopping the reset.
    """

    frames = story.get("frames")
    if not isinstance(frames, list) or any(not isinstance(frame, Mapping) for frame in frames):
        raise ValueError(f"Story {story.get('id')!r} has a malformed frames array")

    conversation_turns = story.get("conversation_turns")
    if conversation_turns is not None and (
        not isinstance(conversation_turns, list)
        or any(not isinstance(turn, Mapping) for turn in conversation_turns)
    ):
        raise ValueError(f"Story {story.get('id')!r} has malformed conversation_turns")

    cleaned = dict(story)
    cleaned["frames"] = [
        clean_json_value(frame, remove_quiz=remove_quiz, remove_audio=remove_audio)
        for frame in frames
    ]
    if conversation_turns is not None:
        cleaned["conversation_turns"] = [
            clean_json_value(turn, remove_quiz=remove_quiz, remove_audio=remove_audio)
            for turn in conversation_turns
        ]
    if remove_quiz or remove_audio:
        for field in ("story_vocabulary", "story_phrases"):
            if field in cleaned:
                cleaned[field] = clean_json_value(
                    cleaned[field],
                    remove_quiz=remove_quiz,
                    remove_audio=remove_audio,
                )
    return cleaned


def contains_nonempty_audio_reference(value: Any) -> bool:
    """Detect an actual audio URL/value, ignoring empty compatibility keys."""

    if isinstance(value, str):
        text = value.strip().casefold()
        return text.startswith(("/uploads/audio/", "/uploads/story_audio/", "data:audio/"))
    if isinstance(value, Mapping):
        for key, child in value.items():
            if is_audio_key(key) and isinstance(child, str) and child.strip():
                return True
            if contains_nonempty_audio_reference(child):
                return True
        return False
    if isinstance(value, list):
        return any(contains_nonempty_audio_reference(item) for item in value)
    return False


def story_preservation_snapshot(
    stories: list[Mapping[str, Any]],
    *,
    remove_quiz: bool,
    remove_audio: bool,
) -> dict[str, Any]:
    """Capture authored identity/content that must remain unchanged."""

    snapshot: dict[str, Any] = {}
    for story in stories:
        cleaned = clean_story_content(
            story,
            remove_quiz=remove_quiz,
            remove_audio=remove_audio,
        )
        snapshot[str(story["id"])] = {
            field: story.get(field)
            for field in ("id", "title", "lesson_number", "lesson_sub_order", "published")
        }
        snapshot[str(story["id"])] |= {
            "frames": cleaned["frames"],
            "conversation_turns": cleaned.get("conversation_turns"),
            "story_vocabulary": cleaned.get("story_vocabulary"),
            "story_phrases": cleaned.get("story_phrases"),
        }
    return snapshot
