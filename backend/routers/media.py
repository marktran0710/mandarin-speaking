import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

import security.auth as auth
import main
import services.media as media_service
import services.media_access_service as media_access_service
import services.content.images as story_images_service
from db import connect_db
from services.content.images import StoryImageGenerationRequest, StoryImageGenerationResponse

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


@router.get("/uploads/{relative_path:path}")
def serve_upload(
    relative_path: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Serve uploaded media only to an authenticated session."""
    upload_root = Path(media_service.UPLOAD_DIR).resolve()
    requested = (upload_root / unquote_to_bytes(relative_path).decode("utf-8")).resolve()
    if requested != upload_root and upload_root not in requested.parents:
        raise HTTPException(status_code=404, detail="Media not found.")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    if identity.role == "student":
        stored_url = f"/uploads/{relative_path.replace(os.sep, '/')}"
        with connect_db() as db:
            allowed = media_access_service.is_media_access_allowed(db, identity.id, stored_url)
        if not allowed:
            raise HTTPException(status_code=403, detail="Media access is not allowed.")
    media_type, _ = mimetypes.guess_type(str(requested))
    # Uploaded media is immutable (its URL is content/id-addressed), and it is
    # the highest-volume request type, so let the browser cache it and skip the
    # round-trip (and this authorization check) when a student reopens a story.
    # `private`, never a shared/CDN cache, because the media is auth-gated.
    return FileResponse(
        requested,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/api/inline-media")
async def inline_media(
    url: str = Query(..., max_length=2000),
    identity: auth.Identity = Depends(auth.require_admin),
):
    """Resolve an image/audio reference (local /uploads/... path or a remote
    http(s) URL, e.g. a DALL-E/Pollinations.ai-hosted story image) to a
    base64 data URL. Used by story export so the browser never has to
    fetch() a third-party host directly, which CORS would otherwise block.
    """
    result = await media_service.resolve_media_b64(url)
    if result is None:
        raise HTTPException(status_code=404, detail="Could not resolve that media reference.")
    data, mime = result
    return {"dataUrl": f"data:{mime};base64,{data}"}


@router.post("/api/generate-story-images", response_model=StoryImageGenerationResponse)
async def generate_story_images(
    request: StoryImageGenerationRequest,
    req: Request,
    identity: auth.Identity = Depends(auth.require_admin),
):
    """
    Generate a six-image story sequence plan from a classroom situation.
    Gemini creates the scene plan when configured; deterministic local fallback
    keeps the teacher workflow usable offline.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"gen-images:{client_ip}", max_requests=10, window_seconds=60)

    situation = request.situation.strip()
    if len(situation) < 8:
        raise HTTPException(
            status_code=400,
            detail="Describe the situation context with at least 8 characters.",
        )

    if story_images_service.GEMINI_API_KEY:
        try:
            return await story_images_service.generate_story_images_with_gemini(request)
        except Exception as exc:
            main.logger.warning("Gemini story image planning failed, using local fallback: %s", exc)

    fallback = story_images_service.build_story_image_fallback(request, provider="local")
    return await story_images_service.normalize_story_image_response(
        {"title": fallback.title, "learning_goal": fallback.learning_goal,
         "frames": [{"title": f.title, "student_prompt": f.student_prompt,
                     "vocabulary": f.vocabulary, "image_prompt": f.image_prompt}
                    for f in fallback.frames]},
        request,
        provider="local",
    )
