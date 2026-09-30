"""Find the teacher's reference recording for a published scene or conversation turn.

The reference comes from story data the server owns, never from the client: a
scene uses its ``listenAudioUrl``; a conversation turn uses that turn's own
``targetAudioUrl`` (a turn must not borrow the scene's recording, which is of a
different sentence).
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


def _turn_audio_url(story_id: str, turn_id: str) -> Optional[str]:
    with connect_db() as db:
        row = repo.find_published_conversation_turns(db, story_id)
    for turn in (row or {}).get("conversation_turns") or []:
        if isinstance(turn, dict) and turn.get("id") == turn_id:
            return turn.get("targetAudioUrl") or None
    return None


def _scene_audio_url(story_id: str, scene_index: int) -> Optional[str]:
    with connect_db() as db:
        row = repo.find_published_scene(db, story_id)
    frames: list[Any] = (row or {}).get("frames") or []
    if scene_index >= len(frames) or not isinstance(frames[scene_index], dict):
        return None
    return frames[scene_index].get("listenAudioUrl") or None


def resolve_reference_source(
    story_id: str,
    scene_index: int,
    *,
    conversation_id: str = "",
    turn_id: str = "",
) -> ReferenceSource:
    if conversation_id or turn_id:
        audio_url = _turn_audio_url(story_id, turn_id)
        key = f"story:{story_id}:turn:{turn_id}"
    else:
        audio_url = _scene_audio_url(story_id, scene_index)
        key = f"story:{story_id}:scene:{scene_index}"
    if not audio_url:
        raise EvaluationError(_MISSING, "This exercise has no teacher recording to compare against.")
    return ReferenceSource(reference_key=key, audio_url=audio_url, audio_path=_path_for_upload_url(audio_url))
