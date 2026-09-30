"""Find the teacher's reference recording for a published scene or conversation turn.

The reference comes from story data the server owns, never from the client: a
scene uses its ``listenAudioUrl``; a conversation turn uses that turn's own
``targetAudioUrl`` (a turn must not borrow the scene's recording, which is of a
different sentence). A turn linked to a scene may reuse that scene recording
only when their scripts match.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from db import connect_db
from repositories import verified_speech_repository as repo
from services.media import UPLOAD_DIR
from services.pronunciation.evaluator import EvaluationError

_MISSING = "reference_audio_missing"


@dataclass(frozen=True)
class ReferenceSource:
    reference_key: str
    audio_url: str
    audio_path: str


def _path_for_upload_url(audio_url: str) -> str:
    """Map an /uploads/ URL to a file inside the upload directory, and nothing else."""
    if not isinstance(audio_url, str) or not audio_url.startswith("/uploads/"):
        raise EvaluationError(_MISSING, "The reference recording is not stored on this server.")
    root = os.path.abspath(UPLOAD_DIR)
    path = os.path.abspath(os.path.join(root, audio_url.removeprefix("/uploads/").replace("/", os.sep)))
    if os.path.commonpath([root, path]) != root:
        raise EvaluationError(_MISSING, "The reference recording path is not valid.")
    return path


def _same_script(left: str, right: str) -> bool:
    from services.pronunciation.script import build_expected_syllables
    return [s.hanzi for s in build_expected_syllables(left)] == [s.hanzi for s in build_expected_syllables(right)]


def _scene_audio_url(story_id: str, scene_index: int, difficulty_level: str, expected_text: str) -> Optional[str]:
    with connect_db() as db:
        row = repo.find_published_scene(db, story_id)
    frames: list[Any] = (row or {}).get("frames") or []
    if scene_index >= len(frames) or not isinstance(frames[scene_index], dict):
        return None
    frame = frames[scene_index]
    suffix = {"easy": "", "medium": "Medium", "hard": "Hard"}.get(difficulty_level, "")
    tier_audio = frame.get(f"listenAudioUrl{suffix}") if suffix else None
    if tier_audio:
        return tier_audio
    # A base recording may only be reused when the requested script matches it.
    recorded_script = str(frame.get("listenScript") or frame.get("suggestedAnswer") or "")
    if expected_text and not _same_script(expected_text, recorded_script):
        raise EvaluationError("reference_mismatch", "The teacher recording is for a different sentence. Add a recording for this target.")
    return frame.get("listenAudioUrl") or None


def _turn_audio_url(story_id: str, turn_id: str, scene_index: int, difficulty_level: str, expected_text: str) -> Optional[str]:
    with connect_db() as db:
        row = repo.find_published_conversation_turns(db, story_id)
    turns = (row or {}).get("conversation_turns") or []
    for turn in turns:
        if isinstance(turn, dict) and turn.get("id") == turn_id:
            if turn.get("targetAudioUrl"):
                return turn["targetAudioUrl"]
            # Only an explicit scene link with the same target can reuse a sample.
            if turn.get("sceneIndex") == scene_index and expected_text:
                return _scene_audio_url(story_id, scene_index, difficulty_level, expected_text)
            return None
    if not turns and turn_id == f"student-scene-{scene_index}" and expected_text:
        return _scene_audio_url(story_id, scene_index, difficulty_level, expected_text)
    return None


def resolve_reference_source(
    story_id: str,
    scene_index: int,
    *,
    conversation_id: str = "",
    turn_id: str = "",
    difficulty_level: str = "easy",
    expected_text: str = "",
) -> ReferenceSource:
    if conversation_id or turn_id:
        audio_url = _turn_audio_url(story_id, turn_id, scene_index, difficulty_level, expected_text)
        key = f"story:{story_id}:turn:{turn_id}"
    else:
        audio_url = _scene_audio_url(story_id, scene_index, difficulty_level, expected_text)
        key = f"story:{story_id}:scene:{scene_index}"
    if not audio_url:
        raise EvaluationError(_MISSING, "This exercise has no teacher recording to compare against.")
    return ReferenceSource(reference_key=key, audio_url=audio_url, audio_path=_path_for_upload_url(audio_url))
