"""File upload utilities: save audio, images, clean up."""
import base64
import os
from typing import Optional
from urllib.parse import unquote_to_bytes

from fastapi import UploadFile

from config import AUDIO_UPLOAD_DIR, IMAGE_UPLOAD_DIR, UPLOAD_DIR


async def save_uploaded_audio(file: UploadFile, record_id: str) -> str:
    extension = extension_from_upload(file.filename, file.content_type, default=".wav")
    filename = f"{safe_file_stem(record_id)}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = await file.read()
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/audio/{filename}"


def persist_story_frame_images(story_id: str, frames: list[dict]) -> list[dict]:
    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        image_url = frame.get("imageUrl", "")
        if image_url.startswith("data:image/"):
            frame = {**frame, "imageUrl": save_data_url_image(image_url, story_id, index)}
        stored_frames.append(frame)
    return stored_frames


def save_data_url_image(data_url: str, story_id: str, index: int) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url
    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".png")
    filename = f"{safe_file_stem(story_id)}-frame-{index}{extension}"
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
        ext = os.path.splitext(filename)[1].lower()
        if ext:
            return ext
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
        c if c.isalnum() or c in ("-", "_") else "-"
        for c in value
    ).strip("-") or "upload"


def remove_uploaded_file(url: str) -> None:
    if not url.startswith("/uploads/"):
        return
    relative = url.removeprefix("/uploads/").replace("/", os.sep)
    path = os.path.abspath(os.path.join(UPLOAD_DIR, relative))
    upload_root = os.path.abspath(UPLOAD_DIR)
    if path.startswith(upload_root) and os.path.exists(path):
        os.remove(path)
