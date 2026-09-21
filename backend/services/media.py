"""Media/file-storage domain: persisting audio records, story frame images
and audio, and resolving media references (local /uploads/... path, data:
URL, or a remote http(s) URL) to base64 for server-side use (inline export,
vision-model prompts).

Kept separate from ai_feedback/asr/story_images: this module owns *where
files live and how they're addressed*, not any AI provider call.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import socket
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote_to_bytes, urlparse

import httpx
from fastapi import HTTPException, UploadFile
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from config import settings
from db import connect_db
from services.speech.reference_voice import (
    extract_scene_reference_curves,
    extract_scene_reference_from_audio,
)

logger = logging.getLogger("speaking_app")

REMOTE_MEDIA_ALLOWED_HOSTS = settings.remote_media_allowed_hosts
UPLOAD_DIR = settings.upload_dir
AUDIO_UPLOAD_DIR = settings.audio_upload_dir
IMAGE_UPLOAD_DIR = settings.image_upload_dir
STORY_AUDIO_UPLOAD_DIR = settings.story_audio_upload_dir
_MAX_AUDIO_BYTES = settings.max_audio_bytes

os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)
os.makedirs(STORY_AUDIO_UPLOAD_DIR, exist_ok=True)


class AudioRecordRequest(BaseModel):
    id: str
    timestamp: str
    duration: int
    transcription: str = ""
    model: str
    topicId: Optional[str] = None
    studentId: Optional[str] = None
    imageUrl: Optional[str] = None
    imageIndex: Optional[int] = None
    audioUrl: Optional[str] = None
    audioName: Optional[str] = None
    praatMetrics: Optional[dict] = None
    analysisVersion: Optional[str] = None
    analysisSchemaVersion: Optional[str] = None
    modelVersion: Optional[str] = None
    comparisonGroupId: Optional[str] = None
    sessionId: Optional[str] = None
    attemptId: Optional[str] = None
    attemptNumber: Optional[int] = None
    attemptType: Optional[str] = None


def save_audio_record(record: AudioRecordRequest, owner_id: Optional[str] = None):
    metrics = dict(record.praatMetrics or {})
    if record.analysisVersion:
        metrics.setdefault("analysis_version", record.analysisVersion)
    if record.analysisSchemaVersion:
        metrics.setdefault("analysis_schema_version", record.analysisSchemaVersion)
    if record.modelVersion:
        metrics.setdefault("model_version", record.modelVersion)
    if record.comparisonGroupId:
        metrics.setdefault("comparison_group_id", record.comparisonGroupId)
    with connect_db() as db:
        if owner_id is not None:
            existing = db.execute(
                "SELECT student_id FROM audio_records WHERE id = %s",
                (record.id,),
            ).fetchone()
            if existing is not None and existing.get("student_id") != owner_id:
                raise HTTPException(status_code=409, detail="Audio record already belongs to another student.")
        db.execute(
            """
            INSERT INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id, student_id,
                image_url, image_index, audio_url, audio_name, praat_metrics,
                session_id, attempt_id, attempt_number, attempt_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                duration = EXCLUDED.duration,
                transcription = EXCLUDED.transcription,
                model = EXCLUDED.model,
                topic_id = EXCLUDED.topic_id,
                student_id = EXCLUDED.student_id,
                image_url = EXCLUDED.image_url,
                image_index = EXCLUDED.image_index,
                audio_url = EXCLUDED.audio_url,
                audio_name = EXCLUDED.audio_name,
                praat_metrics = EXCLUDED.praat_metrics,
                session_id = EXCLUDED.session_id,
                attempt_id = EXCLUDED.attempt_id,
                attempt_number = EXCLUDED.attempt_number,
                attempt_type = EXCLUDED.attempt_type
            """,
            (
                record.id,
                record.timestamp,
                record.duration,
                record.transcription,
                record.model,
                record.topicId,
                record.studentId,
                record.imageUrl,
                record.imageIndex,
                record.audioUrl,
                record.audioName,
                Jsonb(metrics),
                record.sessionId,
                record.attemptId,
                record.attemptNumber,
                record.attemptType,
            ),
        )


def save_verified_audio_record(
    *,
    record_id: str,
    student_id: str,
    attempt_id: str,
    audio_sha256: str,
    verification_version: str,
    topic_id: str,
    scene_index: int,
    audio_url: str,
    audio_name: str,
    image_url: str,
    transcription: str,
    model: str,
    praat_metrics: dict,
) -> dict:
    """Persist a server-owned stable-analysis result.

    This is intentionally separate from ``save_audio_record``: browser
    clients may still save legacy practice records, but cannot set this
    route's verification provenance fields.
    """
    with connect_db() as db:
        # ``attempt_id`` has no database uniqueness constraint.  The advisory
        # lock makes a same-student retry atomic without broadening schema
        # scope, including when the first request has not inserted a row yet.
        # Lock by the idempotency key alone, not by student, so two different
        # identities cannot race to claim the same attempt id.
        lock_key = f"verified-audio:{attempt_id}"
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
        attempts = db.execute(
            """
            SELECT id, student_id, audio_sha256, server_verified_at, audio_url, praat_metrics
            FROM audio_records
            WHERE attempt_id = %s
            ORDER BY server_verified_at DESC NULLS LAST, created_at DESC, id DESC
            FOR UPDATE
            """,
            (attempt_id,),
        ).fetchall()
        if any(row.get("student_id") != student_id for row in attempts):
            raise HTTPException(status_code=409, detail="Attempt already belongs to another student.")

        existing = next((row for row in attempts if row.get("server_verified_at") is not None), None)
        if existing is not None:
            if existing.get("audio_sha256") != audio_sha256:
                raise HTTPException(status_code=409, detail="Attempt ID was already used with different audio.")
            return existing
        if attempts:
            # A legacy browser write already claimed this idempotency key, but
            # its client-supplied metrics are not evidence. Do not append a
            # second row under the same attempt or silently upgrade the old one.
            raise HTTPException(status_code=409, detail="Attempt ID already exists without server verification.")

        db.execute(
            """
            INSERT INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id, student_id,
                image_url, image_index, audio_url, audio_name, praat_metrics,
                attempt_id, server_verified_at, audio_sha256,
                server_verification_version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, NOW(), %s, %s
            )
            """,
            (
                record_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), 0,
                transcription, model, topic_id, student_id, image_url, scene_index,
                audio_url, audio_name, Jsonb(praat_metrics), attempt_id,
                audio_sha256, verification_version,
            ),
        )
        return {
            "id": record_id,
            "audio_sha256": audio_sha256,
            "server_verified_at": datetime.datetime.now(datetime.timezone.utc),
            "audio_url": audio_url,
            "praat_metrics": praat_metrics,
        }


async def save_uploaded_audio(file: UploadFile, record_id: str, owner_id: str = "") -> str:
    extension = extension_from_upload(file.filename, file.content_type, default=".wav")
    owner_stem = safe_file_stem(owner_id) if owner_id else "legacy"
    filename = f"{owner_stem}-{safe_file_stem(record_id)}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = await file.read()
    if len(content) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {_MAX_AUDIO_BYTES} bytes.",
        )
    # Write beside the target and replace atomically. A failed/interrupted
    # upload must never leave a truncated file under a URL already persisted
    # in audio_records.
    temp_path = f"{path}.tmp-{secrets.token_hex(8)}"
    with open(temp_path, "wb") as output:
        output.write(content)
    os.replace(temp_path, path)
    return f"/uploads/audio/{filename}"


def persist_story_frame_images(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced image files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
        ).fetchone()
    old_frames = (row["frames"] or []) if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        frame = dict(frame)
        # Stories carry a single image per frame.
        for field, suffix in (("imageUrl", ""),):
            image_url = frame.get(field) or ""
            if image_url.startswith("data:image/"):
                new_url = save_data_url_image(image_url, story_id, f"{index}{suffix}")
                old_url = (
                    old_frames[index - 1].get(field, "")
                    if index - 1 < len(old_frames)
                    else ""
                )
                if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                    remove_uploaded_file(old_url)
                frame[field] = new_url
        stored_frames.append(frame)
    return stored_frames


# Stories carry a single audio track per frame (listenAudioUrl).
_AUDIO_TIER_SUFFIXES = ("",)


def persist_story_frame_audio(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced audio files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
        ).fetchone()
    old_frames = (row["frames"] or []) if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        frame = dict(frame)
        old_frame = old_frames[index - 1] if index - 1 < len(old_frames) else {}
        for suffix in _AUDIO_TIER_SUFFIXES:
            field = f"listenAudioUrl{suffix}"
            audio_url = frame.get(field) or ""
            old_url = old_frame.get(field, "") or ""

            if audio_url.startswith("data:audio/"):
                new_url = save_data_url_audio(audio_url, story_id, f"{index}{suffix.lower()}")
                if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                    remove_uploaded_file(old_url)
                frame[field] = new_url

                if new_url != old_url:
                    _refresh_scene_reference_curves(
                        story_id, index - 1, frame, old_frame, suffix, new_url
                    )
            elif not audio_url and old_url.startswith("/uploads/"):
                # The teacher cleared this scene's audio (not replaced it) —
                # without this, the old file stays orphaned on disk and the
                # curves derived from it keep silently scoring students
                # against a recording the UI no longer shows as present.
                remove_uploaded_file(old_url)
                _clear_scene_reference_curves(old_frame, frame, suffix)
        stored_frames.append(frame)
    return stored_frames


def _refresh_scene_reference_curves(
    story_id: str, frame_index: int, frame: dict, old_frame: dict, suffix: str, audio_url: str
) -> None:
    """Re-derives a scene's per-word target pitch curves from its real model
    recording whenever a teacher uploads or re-records one, so the "target
    shape" a student practices against always reflects the actual final
    model audio (teacher voice or TTS) rather than going stale after a
    manual upload that bypasses the TTS generation endpoint.

    Best-effort: a scene with no suggested-answer/listen-script text, or an
    audio file the pitch tracker can't read, just keeps whatever reference
    curves (if any) it already had — it doesn't block saving the story.
    """
    sentence_text = (
        frame.get(f"listenScript{suffix}") or frame.get(f"suggestedAnswer{suffix}") or ""
    ).strip()
    if not sentence_text:
        return

    vocab_text = frame.get(f"vocabulary{suffix}") or ""
    words = [word.strip() for word in vocab_text.split(",") if word.strip()]

    relative_path = audio_url.removeprefix("/uploads/").replace("/", os.sep)
    audio_path = os.path.abspath(os.path.join(UPLOAD_DIR, relative_path))
    if not os.path.exists(audio_path):
        return

    try:
        word_results = (
            extract_scene_reference_from_audio(
                story_id=story_id,
                frame_index=frame_index,
                sentence_text=sentence_text,
                words=words,
                sentence_audio_path=audio_path,
                audio_dir=STORY_AUDIO_UPLOAD_DIR,
            )
            if words
            else []
        )
        sentence_curves = extract_scene_reference_curves(audio_path, sentence_text)
    except Exception:
        logger.warning(
            "Reference-curve extraction failed for story=%s frame=%s tier=%s",
            story_id, frame_index, suffix or "easy", exc_info=True,
        )
        return

    try:
        old_word_urls = json.loads(old_frame.get(f"vocabularyAudioUrls{suffix}") or "[]")
    except (json.JSONDecodeError, TypeError):
        old_word_urls = []
    for old_word_url in old_word_urls:
        if isinstance(old_word_url, str):
            remove_uploaded_file(old_word_url)

    frame[f"vocabularyAudioUrls{suffix}"] = json.dumps(
        [w["audio_url"] for w in word_results], ensure_ascii=False
    )
    frame[f"vocabularyReferenceCurves{suffix}"] = json.dumps([w["curve"] for w in word_results])
    frame[f"sentenceReferenceCurves{suffix}"] = json.dumps(
        sentence_curves, ensure_ascii=False
    )


def _clear_scene_reference_curves(old_frame: dict, frame: dict, suffix: str) -> None:
    """Drops a scene's cached per-word audio/curves when its model audio is
    cleared rather than replaced — mirrors the cleanup half of
    _refresh_scene_reference_curves, minus the re-derive step since there is
    no new recording to derive from."""
    try:
        old_word_urls = json.loads(old_frame.get(f"vocabularyAudioUrls{suffix}") or "[]")
    except (json.JSONDecodeError, TypeError):
        old_word_urls = []
    for old_word_url in old_word_urls:
        if isinstance(old_word_url, str):
            remove_uploaded_file(old_word_url)

    frame[f"vocabularyAudioUrls{suffix}"] = "[]"
    frame[f"vocabularyReferenceCurves{suffix}"] = "[]"
    frame[f"sentenceReferenceCurves{suffix}"] = "{}"


def save_data_url_audio(data_url: str, story_id: str, index: int) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url

    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".webm")
    ts = int(time.time() * 1000) % 1_000_000
    filename = f"{safe_file_stem(story_id)}-frame-{index}-audio-{ts}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = (
        base64.b64decode(data)
        if ";base64" in header
        else unquote_to_bytes(data)
    )
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/audio/{filename}"


def save_data_url_image(data_url: str, story_id: str, index) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url

    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".png")
    ts = int(time.time() * 1000) % 1_000_000  # 6-digit ms suffix busts cache on replace
    filename = f"{safe_file_stem(story_id)}-frame-{index}-{ts}{extension}"
    path = os.path.join(IMAGE_UPLOAD_DIR, filename)
    content = (
        base64.b64decode(data)
        if ";base64" in header
        else unquote_to_bytes(data)
    )
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/images/{filename}"


def extension_from_upload(
    filename: Optional[str],
    content_type: Optional[str],
    default: str,
) -> str:
    if filename:
        extension = os.path.splitext(filename)[1].lower()
        if extension:
            return extension
    return extension_from_mime(content_type or "", default)


def extension_from_mime(mime: str, default: str) -> str:
    return {
        "audio/wav": ".wav",
        "audio/wave": ".wav",
        "audio/webm": ".webm",
        "audio/mpeg": ".mp3",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }.get(mime.lower(), default)


def safe_file_stem(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in ("-", "_") else "-"
        for character in value
    ).strip("-") or "upload"


def remove_uploaded_file(url: str) -> None:
    if not url or not url.startswith("/uploads/"):
        return
    relative_path = url.removeprefix("/uploads/").replace("/", os.sep)
    path = os.path.abspath(os.path.join(UPLOAD_DIR, relative_path))
    upload_root = os.path.abspath(UPLOAD_DIR)
    if path.startswith(upload_root) and os.path.exists(path):
        os.remove(path)


_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


async def resolve_media_b64(ref: str) -> Optional[Tuple[str, str]]:
    """Resolve a data:, local /uploads/..., or remote http(s) reference to
    (base64_data, mime_type), fetching remote URLs from the server rather
    than the browser.

    This matters because story frames built via AI image generation
    (DALL-E / Pollinations.ai) keep their original third-party URL, and
    those hosts don't grant CORS permission for arbitrary origins — a
    browser-side fetch() of them is blocked. A server-to-server request has
    no CORS restriction at all, so resolving here sidesteps the problem.
    """
    ref = (ref or "").strip()
    if not ref:
        return None

    if ref.startswith("data:"):
        header, _, data = ref.partition(",")
        mime = header.removeprefix("data:").split(";")[0] or "application/octet-stream"
        if len(data) > 7 * 1024 * 1024 or mime.lower() == "image/svg+xml":
            return None
        return data, mime

    if ref.startswith("/uploads/"):
        relative_path = ref.removeprefix("/uploads/").replace("/", os.sep)
        upload_root = Path(UPLOAD_DIR).resolve()
        path = (upload_root / relative_path).resolve()
        try:
            path.relative_to(upload_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        mime = (
            _IMAGE_MIME_BY_EXT.get(path.suffix.lower())
            or mimetypes.guess_type(str(path))[0]
            or "application/octet-stream"
        )
        if mime == "image/svg+xml":
            return None
        with path.open("rb") as fh:
            return base64.b64encode(fh.read()).decode(), mime

    if ref.startswith("http://") or ref.startswith("https://"):
        parsed = urlparse(ref)
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.hostname.lower() not in REMOTE_MEDIA_ALLOWED_HOSTS:
            return None
        if parsed.port not in (None, 80, 443):
            return None
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                return None
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                async with client.stream("GET", ref) as response:
                    if response.status_code != 200:
                        return None
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > 5 * 1024 * 1024:
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > 5 * 1024 * 1024:
                            return None
                        chunks.append(chunk)
            mime = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return base64.b64encode(b"".join(chunks)).decode(), mime
        except Exception:
            return None

    return None


async def resolve_image_b64(image_ref: str) -> Optional[Tuple[str, str]]:
    """Resolve a scene image reference to (base64_data, mime_type) for vision
    prompts. SVG is excluded since vision models (Gemini, OpenAI) don't
    support it."""
    result = await resolve_media_b64(image_ref)
    if result and result[1] == "image/svg+xml":
        return None
    return result
