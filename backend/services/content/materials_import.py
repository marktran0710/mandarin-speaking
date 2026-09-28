"""Bulk image and script imports for lesson 5-8 story materials.

The preview functions only parse and inspect the database. Confirm reparses the
uploaded bytes, locks the matched stories, writes media once per story, and
updates the existing JSONB rows without touching unrelated story fields.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import secrets
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Iterable

from psycopg.types.json import Jsonb

import services.media as media_service


LESSON_MIN = 5
LESSON_MAX = 8
STORIES_PER_LESSON = 3
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_SCRIPT_LENGTH = 4000
IMAGE_NAME_RE = re.compile(r"^(?P<lesson>[5-8])-(?P<story>[1-3])(?P<extension>\.png|\.jpe?g|\.webp)$", re.IGNORECASE)
SCRIPT_COLUMNS = ("lesson", "story", "scene", "script")


def expected_image_names() -> list[str]:
    return [f"{lesson}-{story}.png" for lesson in range(LESSON_MIN, LESSON_MAX + 1) for story in range(1, STORIES_PER_LESSON + 1)]


def _story_key(lesson: int, story: int) -> str:
    return f"{lesson}-{story}"


def _story_locations(db: Any) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        "SELECT id, title, lesson_number, lesson_sub_order, frames, conversation_turns "
        "FROM custom_stories WHERE lesson_number BETWEEN %s AND %s",
        (LESSON_MIN, LESSON_MAX),
    ).fetchall()
    locations: dict[str, dict[str, Any]] = {}
    for row in rows:
        lesson = row.get("lesson_number")
        story = row.get("lesson_sub_order")
        if isinstance(lesson, int) and isinstance(story, int):
            locations[_story_key(lesson, story)] = row
    return locations


def _filename(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).name


def _parse_image_assets(files: Iterable[tuple[str, bytes]], _seen: set[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    assets: list[dict[str, Any]] = []
    issues: list[str] = []
    seen = _seen if _seen is not None else set()
    for original_name, content in files:
        name = _filename(original_name)
        extension = os.path.splitext(name)[1].lower()
        if extension == ".zip" or content[:4] == b"PK\x03\x04":
            if len(content) > MAX_ARCHIVE_BYTES:
                issues.append(f"{name}: ZIP is too large (maximum {MAX_ARCHIVE_BYTES} bytes).")
                continue
            try:
                archive = zipfile.ZipFile(io.BytesIO(content))
            except zipfile.BadZipFile:
                issues.append(f"{name}: image import must be a valid ZIP file.")
                continue
            try:
                nested: list[tuple[str, bytes]] = []
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    nested_name = _filename(info.filename)
                    if nested_name.startswith(".") or nested_name.startswith("__MACOSX"):
                        continue
                    nested_extension = os.path.splitext(nested_name)[1].lower()
                    if nested_extension in IMAGE_EXTENSIONS:
                        data = archive.read(info)
                        nested.append((nested_name, data))
                    elif nested_extension and nested_extension not in {".txt", ".md", ".csv"}:
                        issues.append(f"{nested_name}: unsupported image type; use PNG, JPG, or WebP.")
                nested_assets, nested_issues = _parse_image_assets(nested, seen)
                assets.extend(nested_assets)
                issues.extend(nested_issues)
            finally:
                archive.close()
            continue

        if extension not in IMAGE_EXTENSIONS:
            issues.append(f"{name}: unsupported image type; use PNG, JPG, or WebP.")
            continue
        match = IMAGE_NAME_RE.fullmatch(name)
        if not match:
            issues.append(f"{name}: filename must be lesson-story.ext, for example 5-1.png.")
            continue
        if len(content) > MAX_IMAGE_BYTES:
            issues.append(f"{name}: image is too large (maximum {MAX_IMAGE_BYTES} bytes).")
            continue
        key = _story_key(int(match.group("lesson")), int(match.group("story")))
        if key in seen:
            issues.append(f"{name}: duplicate image for story {key}.")
            continue
        seen.add(key)
        assets.append({
            "filename": name,
            "storyKey": key,
            "lesson": int(match.group("lesson")),
            "story": int(match.group("story")),
            "extension": extension,
            "data": content,
        })
    if not assets and not issues:
        issues.append("No supported image files were selected.")
    return assets, issues


def _dedupe_image_assets(assets: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for asset in assets:
        key = asset["storyKey"]
        if key in seen:
            issues.append(f"{asset['filename']}: duplicate image for story {key}.")
            continue
        seen.add(key)
        unique.append(asset)
    return unique


def _parse_int(value: Any, label: str, row_number: int) -> int:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d+", text):
        raise ValueError(f"Row {row_number}: {label} must be an integer.")
    return int(text)


def _parse_script_rows(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Scripts CSV must be UTF-8 (UTF-8 with BOM is supported).") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    except csv.Error as exc:
        raise ValueError(f"Scripts CSV could not be read: {exc}") from exc
    fieldnames = [str(field or "").strip().lower() for field in (reader.fieldnames or [])]
    missing = [column for column in SCRIPT_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"Scripts CSV is missing required columns: {', '.join(missing)}.")

    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: set[tuple[int, int, int]] = set()
    for row_number, raw in enumerate(reader, start=2):
        values = {str(key or "").strip().lower(): (value or "") for key, value in raw.items() if key is not None}
        if not any(str(value).strip() for value in values.values()):
            continue
        try:
            lesson = _parse_int(values.get("lesson"), "lesson", row_number)
            story = _parse_int(values.get("story"), "story", row_number)
            scene = _parse_int(values.get("scene"), "scene", row_number)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        script = str(values.get("script") or "").strip()
        key = (lesson, story, scene)
        if lesson < LESSON_MIN or lesson > LESSON_MAX or story < 1 or story > STORIES_PER_LESSON:
            issues.append(f"Row {row_number}: lesson/story must be one of 5-1 through 8-3.")
        if scene < 1:
            issues.append(f"Row {row_number}: scene must be at least 1.")
        if not script:
            issues.append(f"Row {row_number}: script cannot be empty.")
        elif len(script) > MAX_SCRIPT_LENGTH:
            issues.append(f"Row {row_number}: script is too long (maximum {MAX_SCRIPT_LENGTH} characters).")
        if key in seen:
            issues.append(f"Row {row_number}: duplicate target {lesson}-{story} scene {scene}.")
        seen.add(key)
        rows.append({"row": row_number, "lesson": lesson, "story": story, "scene": scene, "script": script, "storyKey": _story_key(lesson, story)})
    if not rows and not issues:
        issues.append("Scripts CSV does not contain any data rows.")
    return rows, issues


def _script_preview(locations: dict[str, dict[str, Any]], rows: list[dict[str, Any]], issues: list[str]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    for item in rows:
        location = locations.get(item["storyKey"])
        if not location:
            issues.append(f"{item['storyKey']}: no existing story matches this lesson/story.")
            continue
        frames = location.get("frames") or []
        index = item["scene"] - 1
        if index >= len(frames):
            issues.append(f"{item['storyKey']} scene {item['scene']}: scene is outside the existing story range ({len(frames)} scenes).")
            continue
        frame = frames[index] if isinstance(frames[index], dict) else {}
        before = str(frame.get("listenScript") or frame.get("suggestedAnswer") or "")
        changes.append({
            "lesson": item["lesson"], "story": item["story"], "scene": item["scene"],
            "storyId": location["id"], "storyTitle": location["title"], "before": before,
            "after": item["script"],
        })
    return {"kind": "scripts", "rows": len(rows), "changes": changes, "issues": issues, "valid": not issues}


def preview_materials(db: Any, kind: str, files: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
    locations = _story_locations(db)
    if kind == "images":
        assets, issues = _parse_image_assets(files)
        assets = _dedupe_image_assets(assets, issues)
        changes: list[dict[str, Any]] = []
        for asset in assets:
            location = locations.get(asset["storyKey"])
            if not location:
                issues.append(f"{asset['filename']}: no existing story matches {asset['storyKey']}.")
                continue
            frames = location.get("frames") or []
            before = next((frame.get("imageUrl") for frame in frames if isinstance(frame, dict) and frame.get("imageUrl")), "")
            changes.append({
                "filename": asset["filename"], "storyKey": asset["storyKey"], "storyId": location["id"],
                "storyTitle": location["title"], "scenes": len(frames), "before": before,
                "after": asset["filename"], "bytes": len(asset["data"]),
            })
        return {"kind": "images", "files": len(assets), "changes": changes, "issues": issues, "valid": not issues}
    if kind == "scripts":
        file_list = list(files)
        if len(file_list) != 1:
            return {"kind": "scripts", "rows": 0, "changes": [], "issues": ["Scripts import accepts exactly one CSV file."], "valid": False}
        rows, issues = _parse_script_rows(file_list[0][1])
        return _script_preview(locations, rows, issues)
    raise ValueError("Materials import kind must be images or scripts.")


def _write_image(asset: dict[str, Any]) -> str:
    digest = hashlib.sha256(asset["data"]).hexdigest()[:12]
    filename = f"materials-{asset['storyKey']}-{digest}-{secrets.token_hex(5)}{asset['extension']}"
    os.makedirs(media_service.IMAGE_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(media_service.IMAGE_UPLOAD_DIR, filename)
    temp_path = f"{path}.tmp-{secrets.token_hex(8)}"
    try:
        with open(temp_path, "wb") as output:
            output.write(asset["data"])
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return f"/uploads/images/{filename}"


def _remove_unreferenced_images(db: Any, candidates: set[str]) -> None:
    if not candidates:
        return
    referenced: set[str] = set()
    for row in db.execute("SELECT frames FROM custom_stories").fetchall():
        for frame in row.get("frames") or []:
            if isinstance(frame, dict):
                url = frame.get("imageUrl")
                if isinstance(url, str) and url.startswith("/uploads/"):
                    referenced.add(url)
    for url in candidates - referenced:
        media_service.remove_uploaded_file(url)


def _apply_scripts(db: Any, rows: list[dict[str, Any]]) -> tuple[dict[str, Any], set[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        grouped[item["storyKey"]].append(item)
    updated: list[dict[str, Any]] = []
    cleared_conversation: list[str] = []
    for story_key, story_rows in grouped.items():
        location = _story_locations(db).get(story_key)
        if not location:
            raise ValueError(f"{story_key}: no existing story matches this lesson/story.")
        locked = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (location["id"],)).fetchone()
        if locked is None:
            raise ValueError(f"{story_key}: story changed before import.")
        frames = [dict(frame) if isinstance(frame, dict) else {} for frame in (locked.get("frames") or [])]
        for item in story_rows:
            index = item["scene"] - 1
            if index >= len(frames):
                raise ValueError(f"{story_key} scene {item['scene']}: scene is outside the existing story range.")
            old_frame = dict(frames[index])
            frame = dict(old_frame)
            frame["suggestedAnswer"] = item["script"]
            frame["listenScript"] = item["script"]
            audio_url = str(frame.get("listenAudioUrl") or "")
            refreshed = False
            if audio_url.startswith("/uploads/"):
                refreshed = media_service._refresh_scene_reference_curves(
                    locked["id"], index, frame, old_frame, "", audio_url
                ) is not False
            if not refreshed:
                media_service._clear_scene_reference_curves(old_frame, frame, "")
            frames[index] = frame
            updated.append({
                "lesson": item["lesson"], "story": item["story"], "scene": item["scene"],
                "storyId": locked["id"], "storyTitle": locked["title"], "script": item["script"],
                "alignment": "refreshed" if refreshed else "cleared",
            })
        db.execute(
            "UPDATE custom_stories SET frames = %s::jsonb, conversation_turns = NULL WHERE id = %s",
            (Jsonb(frames), locked["id"]),
        )
        cleared_conversation.append(locked["id"])
    return {"kind": "scripts", "updated": updated, "stories": sorted(set(cleared_conversation))}, set()


def apply_materials(db: Any, kind: str, files: Iterable[tuple[str, bytes]]) -> dict[str, Any]:
    file_list = list(files)
    report = preview_materials(db, kind, file_list)
    if report["issues"]:
        raise ValueError("Materials import failed validation: " + " ".join(report["issues"][:8]))
    if kind == "scripts":
        rows, _ = _parse_script_rows(file_list[0][1])
        result, _ = _apply_scripts(db, rows)
        refreshed = sum(1 for item in result["updated"] if item["alignment"] == "refreshed")
        cleared = len(result["updated"]) - refreshed
        return {**result, "alignmentRefreshed": refreshed, "alignmentCleared": cleared}
    assets, issues = _parse_image_assets(file_list)
    assets = _dedupe_image_assets(assets, issues)
    written: list[str] = []
    old_urls: set[str] = set()
    stories: list[dict[str, Any]] = []
    try:
        for asset in assets:
            location = _story_locations(db).get(asset["storyKey"])
            if not location:
                raise ValueError(f"{asset['storyKey']}: no existing story matches this lesson/story.")
            locked = db.execute("SELECT * FROM custom_stories WHERE id = %s FOR UPDATE", (location["id"],)).fetchone()
            if locked is None:
                raise ValueError(f"{asset['storyKey']}: story changed before import.")
            frames = [dict(frame) if isinstance(frame, dict) else {} for frame in (locked.get("frames") or [])]
            old_urls.update(
                frame.get("imageUrl") for frame in frames
                if isinstance(frame.get("imageUrl"), str) and frame.get("imageUrl", "").startswith("/uploads/")
            )
            url = _write_image(asset)
            written.append(url)
            for frame in frames:
                frame["imageUrl"] = url
            db.execute("UPDATE custom_stories SET frames = %s::jsonb WHERE id = %s", (Jsonb(frames), locked["id"]))
            stories.append({"storyKey": asset["storyKey"], "storyId": locked["id"], "storyTitle": locked["title"], "imageUrl": url, "scenes": len(frames)})
    except Exception:
        for url in written:
            media_service.remove_uploaded_file(url)
        raise
    _remove_unreferenced_images(db, old_urls)
    return {"kind": "images", "updated": stories, "files": len(assets), "stories": [item["storyId"] for item in stories]}


def build_scripts_template(db: Any) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(SCRIPT_COLUMNS)
    for row in sorted(_story_locations(db).values(), key=lambda item: (item["lesson_number"], item["lesson_sub_order"], item["id"])):
        for scene, frame in enumerate(row.get("frames") or [], start=1):
            if not isinstance(frame, dict):
                continue
            writer.writerow([
                row["lesson_number"], row["lesson_sub_order"], scene,
                str(frame.get("listenScript") or frame.get("suggestedAnswer") or ""),
            ])
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def build_images_template() -> bytes:
    readme = (
        "Lesson 5-8 image template\r\n\r\n"
        "Replace each filename with one complete PNG, JPG, or WebP image.\r\n"
        "One image is reused for every scene in that small story; do not crop it into panels.\r\n\r\n"
        "Expected filenames:\r\n" + "".join(f"- {name}\r\n" for name in expected_image_names())
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", readme.encode("utf-8"))
    return buffer.getvalue()
