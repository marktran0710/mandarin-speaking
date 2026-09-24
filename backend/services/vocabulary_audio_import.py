"""Admin import of canonical per-word vocabulary audio.

Audio used by the learner's vocabulary preview and quiz belongs to the same
canonical ``vocab_assessment`` record as the word and its three questions.
This module accepts a ZIP whose audio filenames are the assessment ``wordId``
plus an audio extension, for example ``C5-5-1-I1-W001.mp3``.

The preview path is read-only. The confirm path re-parses and re-matches the
archive before writing, so a stale browser preview cannot publish against a
changed content bank.
"""

from __future__ import annotations

import hashlib
import io
import os
import secrets
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from psycopg.types.json import Jsonb

import services.media as media_service


AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".webm", ".ogg"})
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024


def _archive_assets(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Audio ZIP is too large. Maximum size is {MAX_ARCHIVE_BYTES} bytes.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("Audio import must be a valid ZIP file.") from exc

    assets: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_keys: set[str] = set()
    try:
        for info in archive.infolist():
            if info.is_dir():
                continue
            filename = PurePosixPath(info.filename.replace("\\", "/")).name
            if not filename or filename.startswith(".") or filename.startswith("__MACOSX"):
                continue
            extension = os.path.splitext(filename)[1].lower()
            if extension not in AUDIO_EXTENSIONS:
                continue
            word_key = os.path.splitext(filename)[0].strip()
            if not word_key:
                issues.append(f"{filename}: filename must contain a Word Key.")
                continue
            if word_key in seen_keys:
                issues.append(f"{word_key}: duplicate audio files in the ZIP.")
                continue
            seen_keys.add(word_key)
            if info.file_size > media_service._MAX_AUDIO_BYTES:
                issues.append(
                    f"{filename}: audio file is too large (maximum {media_service._MAX_AUDIO_BYTES} bytes)."
                )
                continue
            data = archive.read(info)
            if len(data) > media_service._MAX_AUDIO_BYTES:
                issues.append(
                    f"{filename}: audio file is too large (maximum {media_service._MAX_AUDIO_BYTES} bytes)."
                )
                continue
            assets.append({"filename": filename, "wordKey": word_key, "extension": extension, "data": data})
    finally:
        archive.close()
    if not assets and not issues:
        issues.append("The ZIP contains no supported audio files (.mp3, .wav, .m4a, .webm, or .ogg).")
    return assets, issues


def _word_locations(db: Any) -> dict[str, list[dict[str, Any]]]:
    locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = db.execute(
        "SELECT id, title, vocab_assessment FROM custom_stories "
        "WHERE vocab_assessment IS NOT NULL"
    ).fetchall()
    for row in rows:
        assessment = row.get("vocab_assessment")
        if not isinstance(assessment, list):
            continue
        for index, question in enumerate(assessment):
            if not isinstance(question, dict):
                continue
            word_key = str(question.get("wordId") or "").strip()
            if not word_key:
                continue
            locations[word_key].append({
                "storyId": row["id"],
                "storyTitle": row["title"],
                "questionIndex": index,
            })
    return locations


def _match_assets(db: Any, assets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    locations = _word_locations(db)
    matched: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for asset in assets:
        candidates = locations.get(asset["wordKey"], [])
        if not candidates:
            unmatched.append(asset["filename"])
            continue
        if len({candidate["storyId"] for candidate in candidates}) > 1:
            unmatched.append(f"{asset['filename']} (Word Key exists in multiple stories)")
            continue
        matched.append({**asset, **candidates[0]})
    return matched, unmatched


def preview_vocabulary_audio_import(db: Any, content: bytes) -> dict[str, Any]:
    assets, issues = _archive_assets(content)
    matched, unmatched = _match_assets(db, assets)
    return {
        "files": len(assets),
        "matched": [
            {
                "filename": asset["filename"],
                "wordKey": asset["wordKey"],
                "storyId": asset["storyId"],
                "storyTitle": asset["storyTitle"],
                "bytes": len(asset["data"]),
            }
            for asset in matched
        ],
        "unmatched": unmatched,
        "issues": issues,
    }


def _stored_filename(word_key: str, extension: str) -> str:
    digest = hashlib.sha256(word_key.encode("utf-8")).hexdigest()[:10]
    return f"vocab-{media_service.safe_file_stem(word_key)}-{digest}-{secrets.token_hex(6)}{extension}"


def _write_asset(asset: dict[str, Any]) -> str:
    filename = _stored_filename(asset["wordKey"], asset["extension"])
    os.makedirs(media_service.AUDIO_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(media_service.AUDIO_UPLOAD_DIR, filename)
    temp_path = f"{path}.tmp-{secrets.token_hex(8)}"
    try:
        with open(temp_path, "wb") as output:
            output.write(asset["data"])
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return f"/uploads/audio/{filename}"


def apply_vocabulary_audio_import(db: Any, content: bytes) -> dict[str, Any]:
    """Write one ZIP import after rebuilding its match set from the database."""
    assets, issues = _archive_assets(content)
    if issues:
        raise ValueError("Audio import failed validation: " + " ".join(issues[:8]))
    matched, unmatched = _match_assets(db, assets)
    if not matched:
        raise ValueError("No ZIP audio filename matched a canonical vocabulary Word Key.")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in matched:
        grouped[asset["storyId"]].append(asset)

    written_urls: list[str] = []
    old_urls: list[str] = []
    try:
        for story_id, story_assets in grouped.items():
            row = db.execute(
                "SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (story_id,)
            ).fetchone()
            if row is None or not isinstance(row.get("vocab_assessment"), list):
                raise ValueError(f"Story {story_id} no longer has a canonical vocabulary bank.")
            assessment = [dict(question) for question in row["vocab_assessment"]]
            by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for question in assessment:
                if isinstance(question, dict) and question.get("wordId"):
                    by_word[str(question["wordId"])].append(question)
            for asset in story_assets:
                questions = by_word.get(asset["wordKey"], [])
                if not questions:
                    raise ValueError(f"{asset['wordKey']}: vocabulary changed before import.")
                url = _write_asset(asset)
                written_urls.append(url)
                for question in questions:
                    old_url = question.get("audioUrl")
                    if isinstance(old_url, str) and old_url.startswith("/uploads/"):
                        old_urls.append(old_url)
                    question["audioUrl"] = url
            db.execute(
                "UPDATE custom_stories SET vocab_assessment = %s::jsonb WHERE id = %s",
                (Jsonb(assessment), story_id),
            )
    except Exception:
        for url in written_urls:
            media_service.remove_uploaded_file(url)
        raise

    for old_url in old_urls:
        if old_url not in written_urls:
            media_service.remove_uploaded_file(old_url)

    return {
        "files": len(assets),
        "updated": len(matched),
        "unmatched": unmatched,
        "stories": sorted({asset["storyTitle"] for asset in matched}),
    }
