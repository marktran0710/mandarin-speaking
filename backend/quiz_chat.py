"""The Chat adapter quiz_pipeline.py's validate_candidates needs, wired to
the same Groq-first/Gemini-fallback chain the quiz generators in main.py
already use. Ported from scripts/eval-quiz-pipeline.py (which validated the
pipeline offline against the labelled audit) so the live /quiz/validate
endpoint runs the exact same call shape that was scored there.
"""

from __future__ import annotations

import asyncio
import os

import httpx

GROQ_MODEL = os.getenv("GROQ_FEEDBACK_MODEL", "openai/gpt-oss-120b")
GEMINI_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-3.6-flash")

# Groq's free tier throttles on tokens-per-minute; two in flight plus
# Retry-After backoff clears a story-sized batch without tripping it.
CONCURRENCY = 2
_semaphore = asyncio.Semaphore(CONCURRENCY)


async def _groq(system: str, user: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": GROQ_MODEL,
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def _gemini(system: str, user: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
                # See ai_feedback.py's identical note: gemini-3.6-flash
                # thinks by default, which is pure overhead for a JSON-only
                # validation call.
                "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
            },
        )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def make_chat(groq_api_key: str | None, gemini_api_key: str | None):
    """Binds a Chat callable to the app's actual API keys (main.py already
    cleans/reads them from env) rather than reading os.getenv again here."""

    async def chat(system: str, user: str) -> str:
        async with _semaphore:
            last: Exception | None = None
            for attempt in range(6):
                try:
                    if groq_api_key:
                        return await _groq(system, user, groq_api_key)
                    if gemini_api_key:
                        return await _gemini(system, user, gemini_api_key)
                    raise RuntimeError("Set GROQ_API_KEY or GEMINI_API_KEY to validate quiz questions.")
                except httpx.HTTPStatusError as exc:
                    last = exc
                    if exc.response.status_code not in (429, 503):
                        raise
                    wait = exc.response.headers.get("retry-after")
                    try:
                        delay = float(wait) if wait else 0.0
                    except ValueError:
                        delay = 0.0
                    await asyncio.sleep(max(delay, 3 * (attempt + 1)))
                except Exception as exc:  # noqa: BLE001 - retried below, not swallowed
                    last = exc
                    await asyncio.sleep(2 + attempt)
            raise RuntimeError(f"chat failed after retries: {last}")

    return chat
