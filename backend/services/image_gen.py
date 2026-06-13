"""Story image generation: Gemini plan → real images or SVG fallback."""
import asyncio
import json
import os
from urllib.parse import quote

import httpx

from config import GEMINI_API_KEY, IMAGE_UPLOAD_DIR, OPENAI_API_KEY, logger
from models import (
    StoryImageFrame,
    StoryImageGenerationRequest,
    StoryImageGenerationResponse,
)


async def generate_story_images_with_gemini(
    request: StoryImageGenerationRequest,
) -> StoryImageGenerationResponse:
    prompt = f"""
You are helping a Mandarin teacher create a six-picture speaking story.

Situation context:
{request.situation}

Student level:
{request.level}

Visual style:
{request.style}

Language focus:
{request.language_focus}

Return only valid JSON shaped exactly like:
{{
  "title": "short activity title",
  "learning_goal": "one sentence learning goal",
  "frames": [
    {{
      "title": "scene title",
      "student_prompt": "student speaking prompt",
      "vocabulary": ["word", "word", "word"],
      "image_prompt": "specific image generation prompt for one coherent story scene"
    }}
  ]
}}

Rules:
- Return exactly 6 frames.
- The 6 frames must tell one connected real-life story with clear narrative progression.
- Each frame shows ONE specific visible action — not just a place or object.
- image_prompt must be highly specific: describe the exact people (age, clothing, expression),
  their action (gesture, body language), the precise setting (specific location details,
  background objects), and the mood/lighting. Write it as a detailed scene description
  for a photorealistic image generator. Minimum 30 words per image_prompt.
  Example: "Photorealistic photo of a teenage Taiwanese girl in school uniform looking
  at her empty hands with a worried expression, standing on a Taipei MRT platform,
  other commuters visible in background, bright fluorescent station lighting."
- Do NOT use vague words like "scene", "illustration", "image of", "depicts".
- Use safe, real-life content appropriate for middle school students.
- Use Traditional Chinese vocabulary when useful, but keep JSON keys in English.
"""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
    if response.status_code != 200:
        raise RuntimeError(response.text)
    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(_strip_json_fence(content))
    return await normalize_story_image_response(data, request, provider="gemini-2.0-flash")


def build_story_image_fallback(
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    situation = request.situation.strip()
    title = _title_from_situation(situation)
    scene_templates = [
        ("Set the scene", "Describe who is there and where the story begins.", ["who", "where", "today"]),
        ("First action", "Tell what the main person does first.", ["first", "go", "meet"]),
        ("Small problem", "Explain the problem or surprise in the situation.", ["problem", "because", "need"]),
        ("Ask for help", "Say how someone asks, answers, or helps.", ["ask", "help", "together"]),
        ("Solve it", "Describe what changes and how the problem is solved.", ["then", "finish", "better"]),
        ("Ending feeling", "Finish the story with a feeling or lesson.", ["finally", "feel", "next time"]),
    ]
    frames = []
    for index, (scene_title, prompt, vocab) in enumerate(scene_templates, start=1):
        image_prompt = (
            f"{request.style}, frame {index} of 6, {scene_title.lower()} for "
            f"the situation: {situation}. Show people doing a clear classroom-safe "
            "real-life action, consistent characters, soft colors, storybook composition."
        )
        frames.append(StoryImageFrame(
            index=index,
            title=scene_title,
            student_prompt=prompt,
            vocabulary=vocab,
            image_prompt=image_prompt,
            image_url=build_scene_svg_data_url(index, scene_title, situation),
        ))
    return StoryImageGenerationResponse(
        provider=provider,
        title=title,
        learning_goal=(
            "Students build a six-part Mandarin story by describing the scene, "
            "event, problem, help, solution, and feeling."
        ),
        frames=frames,
    )


async def generate_real_image(image_prompt: str, seed: int) -> str:
    """Download a generated image; returns /uploads/images/... path or '' on failure."""
    try:
        if OPENAI_API_KEY:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": "dall-e-3", "prompt": image_prompt, "n": 1,
                          "size": "1024x1024", "quality": "standard", "response_format": "url"},
                )
            if resp.status_code != 200:
                raise RuntimeError(resp.text)
            img_url = resp.json()["data"][0]["url"]
        else:
            from urllib.parse import quote as url_quote
            img_url = (
                f"https://image.pollinations.ai/prompt/{url_quote(image_prompt)}"
                f"?width=800&height=600&seed={seed}&model=flux&nologo=true"
            )

        async with httpx.AsyncClient(timeout=60) as client:
            img_resp = await client.get(img_url, follow_redirects=True)
        if img_resp.status_code != 200:
            return ""

        content_type = img_resp.headers.get("content-type", "image/jpeg")
        ext = ".jpg" if "jpeg" in content_type else ".png"
        filename = f"gen-{seed}{ext}"
        path = os.path.join(IMAGE_UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(img_resp.content)
        return f"/uploads/images/{filename}"
    except Exception as exc:
        logger.warning("Image generation failed (seed=%s): %s", seed, exc)
        return ""


async def normalize_story_image_response(
    data: dict,
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    fallback = build_story_image_fallback(request, provider=provider)
    raw_frames = data.get("frames", [])

    frame_meta = []
    for index in range(6):
        fb = fallback.frames[index]
        raw = raw_frames[index] if index < len(raw_frames) and isinstance(raw_frames[index], dict) else {}
        title = str(raw.get("title") or fb.title).strip()
        student_prompt = str(raw.get("student_prompt") or fb.student_prompt).strip()
        vocabulary = raw.get("vocabulary") or fb.vocabulary
        if not isinstance(vocabulary, list):
            vocabulary = fb.vocabulary
        raw_image_prompt = str(raw.get("image_prompt") or fb.image_prompt).strip()
        image_prompt = (
            f"Photorealistic scene, natural lighting, Taiwan setting. {raw_image_prompt} "
            f"No text overlays. Real people, real environment. Frame {index + 1} of a connected story."
        )
        frame_meta.append((index, title, student_prompt, vocabulary, image_prompt))

    base_seed = abs(hash(request.situation)) % 100000
    image_urls = await asyncio.gather(*[
        generate_real_image(meta[4], base_seed + meta[0])
        for meta in frame_meta
    ])

    frames = []
    for (index, title, student_prompt, vocabulary, image_prompt), img_url in zip(frame_meta, image_urls):
        url = img_url or build_scene_svg_data_url(index + 1, title, request.situation)
        frames.append(StoryImageFrame(
            index=index + 1,
            title=title,
            student_prompt=student_prompt,
            vocabulary=[str(w) for w in vocabulary[:5]],
            image_prompt=image_prompt,
            image_url=url,
        ))

    return StoryImageGenerationResponse(
        provider=provider,
        title=str(data.get("title") or fallback.title).strip(),
        learning_goal=str(data.get("learning_goal") or fallback.learning_goal).strip(),
        frames=frames,
    )


def build_scene_svg_data_url(index: int, title: str, situation: str) -> str:
    palettes = [
        ("#dff7ef", "#2f9e83", "#f7c948"),
        ("#e9f0ff", "#5778c7", "#f4a261"),
        ("#fff3df", "#d9822b", "#59a14f"),
        ("#f0ecff", "#7c65d1", "#ffb703"),
        ("#e8f6ff", "#2786a5", "#f77f00"),
        ("#f8efe6", "#8f6b4a", "#4cc9f0"),
    ]
    bg, primary, accent = palettes[(index - 1) % len(palettes)]
    safe_title = _escape_svg(title[:36])
    safe_ctx = _escape_svg(situation[:64])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 640">
<rect width="960" height="640" fill="{bg}"/>
<rect x="48" y="52" width="864" height="536" rx="30" fill="#fffaf3" stroke="#263238" stroke-width="5"/>
<path d="M82 455 C170 395 250 430 322 382 C430 310 545 390 642 326 C722 274 800 298 878 244 L878 588 L82 588 Z" fill="{accent}" opacity="0.28"/>
<rect x="96" y="116" width="230" height="168" rx="20" fill="#ffffff" stroke="{primary}" stroke-width="5"/>
<rect x="642" y="112" width="220" height="172" rx="20" fill="#ffffff" stroke="{primary}" stroke-width="5"/>
<circle cx="440" cy="246" r="58" fill="{primary}"/>
<circle cx="560" cy="246" r="58" fill="{accent}"/>
<path d="M408 340 C436 296 468 296 496 340 L496 458 L370 458 Z" fill="{primary}"/>
<path d="M530 340 C558 296 590 296 618 340 L652 458 L496 458 Z" fill="{accent}"/>
<path d="M365 492 L662 492" stroke="#263238" stroke-width="8" stroke-linecap="round"/>
<circle cx="130" cy="150" r="16" fill="{accent}"/>
<circle cx="178" cy="150" r="16" fill="{primary}"/>
<circle cx="690" cy="150" r="16" fill="{accent}"/>
<circle cx="738" cy="150" r="16" fill="{primary}"/>
<text x="96" y="82" fill="#263238" font-family="Arial, sans-serif" font-size="30" font-weight="800">Frame {index}</text>
<text x="96" y="540" fill="#263238" font-family="Arial, sans-serif" font-size="34" font-weight="800">{safe_title}</text>
<text x="96" y="574" fill="#455a64" font-family="Arial, sans-serif" font-size="20">{safe_ctx}</text>
</svg>"""
    return "data:image/svg+xml;charset=utf-8," + quote(svg.replace("\n", ""))


def _strip_json_fence(content: str) -> str:
    s = content.strip()
    if s.startswith("```json"):
        return s.removeprefix("```json").removesuffix("```").strip()
    if s.startswith("```"):
        return s.removeprefix("```").removesuffix("```").strip()
    return s


def _title_from_situation(situation: str) -> str:
    words = " ".join(situation.split()[:8])
    return f"{words} Story" if words else "Six Picture Story"


def _escape_svg(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
