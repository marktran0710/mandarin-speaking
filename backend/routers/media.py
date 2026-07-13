from fastapi import APIRouter, HTTPException, Query, Request

import main
from main import StoryImageGenerationRequest, StoryImageGenerationResponse

router = APIRouter()


@router.get("/api/inline-media")
async def inline_media(url: str = Query(..., max_length=2000)):
    """Resolve an image/audio reference (local /uploads/... path or a remote
    http(s) URL, e.g. a DALL-E/Pollinations.ai-hosted story image) to a
    base64 data URL. Used by story export so the browser never has to
    fetch() a third-party host directly, which CORS would otherwise block.
    """
    result = await main.resolve_media_b64(url)
    if result is None:
        raise HTTPException(status_code=404, detail="Could not resolve that media reference.")
    data, mime = result
    return {"dataUrl": f"data:{mime};base64,{data}"}


@router.post("/api/generate-story-images", response_model=StoryImageGenerationResponse)
async def generate_story_images(request: StoryImageGenerationRequest, req: Request):
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

    if main.GEMINI_API_KEY:
        try:
            return await main.generate_story_images_with_gemini(request)
        except Exception as exc:
            main.logger.warning("Gemini story image planning failed, using local fallback: %s", exc)

    fallback = main.build_story_image_fallback(request, provider="local")
    return await main.normalize_story_image_response(
        {"title": fallback.title, "learning_goal": fallback.learning_goal,
         "frames": [{"title": f.title, "student_prompt": f.student_prompt,
                     "vocabulary": f.vocabulary, "image_prompt": f.image_prompt}
                    for f in fallback.frames]},
        request,
        provider="local",
    )
