import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv


load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))


def clean_api_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY"))
GEMINI_API_KEY = clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY"))
OPENAI_FEEDBACK_MODEL = os.getenv("OPENAI_FEEDBACK_MODEL", "gpt-4o-mini")
GEMINI_FEEDBACK_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-2.0-flash")
AI_FEEDBACK_PROVIDER = os.getenv("AI_FEEDBACK_PROVIDER", "local").lower()


def fallback_language_feedback(transcription: str) -> Dict:
    text = transcription.strip()
    character_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")

    if not text:
        return {
            "provider": "local",
            "fluency": {
                "score": 0,
                "feedback": "No transcription was available. Try one short sentence and speak clearly.",
            },
            "grammar": {
                "score": 0,
                "feedback": "Grammar feedback needs a transcription.",
                "corrections": [],
            },
            "vocabulary": {
                "score": 0,
                "feedback": "Vocabulary feedback needs a transcription.",
                "suggestions": [],
            },
            "improved_version": "",
            "practice_prompt": "Record one simple Mandarin sentence about the picture.",
        }

    if character_count < 6:
        fluency_feedback = "Good start. Try making this into a complete sentence."
        fluency_score = 55
    elif character_count < 18:
        fluency_feedback = "The sentence length is good for focused tone practice."
        fluency_score = 72
    else:
        fluency_feedback = "Nice extended response. Keep the rhythm steady across phrases."
        fluency_score = 82

    return {
        "provider": "local",
        "fluency": {
            "score": fluency_score,
            "feedback": fluency_feedback,
        },
        "grammar": {
            "score": 70 if character_count >= 6 else 55,
            "feedback": "Check that the sentence has a clear subject, action, and ending particle when needed.",
            "corrections": [],
        },
        "vocabulary": {
            "score": 70 if character_count >= 6 else 50,
            "feedback": "Use one specific noun and one descriptive word from the picture vocabulary.",
            "suggestions": ["Add a place word", "Add an emotion word", "Add a time word"],
        },
        "improved_version": text,
        "practice_prompt": "Say the same idea again with one extra detail about who, where, or how.",
    }


async def generate_language_feedback(transcription: str) -> Dict:
    text = transcription.strip()
    if not text:
        return fallback_language_feedback(text)

    if AI_FEEDBACK_PROVIDER == "local":
        return fallback_language_feedback(text)

    if AI_FEEDBACK_PROVIDER == "openai" and OPENAI_API_KEY:
        try:
            return await _feedback_with_openai(text)
        except Exception as exc:
            print(f"OpenAI feedback failed, using local fallback: {exc}")

    if GEMINI_API_KEY:
        try:
            return await _feedback_with_gemini(text)
        except Exception as exc:
            print(f"Gemini feedback failed, using local fallback: {exc}")

    if OPENAI_API_KEY:
        try:
            return await _feedback_with_openai(text)
        except Exception as exc:
            print(f"OpenAI feedback failed, using local fallback: {exc}")

    return fallback_language_feedback(text)


async def _feedback_with_openai(transcription: str) -> Dict:
    payload = {
        "model": OPENAI_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin learning coach. Return only valid JSON with "
                    "provider, fluency, grammar, vocabulary, improved_version, and practice_prompt. "
                    "Keep feedback short, specific, and encouraging. Use Traditional Chinese examples when useful."
                ),
            },
            {
                "role": "user",
                "content": _feedback_prompt(transcription),
            },
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    data["provider"] = "openai"
    return _normalize_feedback(data)


async def _feedback_with_gemini(transcription: str) -> Dict:
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Return only valid JSON. "
                            f"{_feedback_prompt(transcription)}"
                        )
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(_strip_json_fence(content))
    data["provider"] = GEMINI_FEEDBACK_MODEL
    return _normalize_feedback(data)


def _feedback_prompt(transcription: str) -> str:
    return f"""
Analyze this Mandarin learner transcription:

{transcription}

Return JSON shaped exactly like:
{{
  "provider": "ai",
  "fluency": {{"score": 0-100, "feedback": "one short sentence"}},
  "grammar": {{"score": 0-100, "feedback": "one short sentence", "corrections": ["short correction"]}},
  "vocabulary": {{"score": 0-100, "feedback": "one short sentence", "suggestions": ["better word or phrase"]}},
  "improved_version": "a natural improved Mandarin version",
  "practice_prompt": "one sentence practice task"
}}
"""


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _normalize_feedback(data: Dict) -> Dict:
    fallback = fallback_language_feedback("")
    normalized = {
        "provider": data.get("provider", "ai"),
        "fluency": _normalize_score_block(data.get("fluency", {}), fallback["fluency"]),
        "grammar": _normalize_list_block(data.get("grammar", {}), fallback["grammar"], "corrections"),
        "vocabulary": _normalize_list_block(data.get("vocabulary", {}), fallback["vocabulary"], "suggestions"),
        "improved_version": str(data.get("improved_version", "")),
        "practice_prompt": str(data.get("practice_prompt", fallback["practice_prompt"])),
    }
    return normalized


def _normalize_score_block(data: Dict, fallback: Dict) -> Dict:
    return {
        "score": _score(data.get("score", fallback["score"])),
        "feedback": str(data.get("feedback", fallback["feedback"])),
    }


def _normalize_list_block(data: Dict, fallback: Dict, list_key: str) -> Dict:
    items = data.get(list_key, fallback[list_key])
    if not isinstance(items, list):
        items = fallback[list_key]

    return {
        "score": _score(data.get("score", fallback["score"])),
        "feedback": str(data.get("feedback", fallback["feedback"])),
        list_key: [str(item) for item in items[:4]],
    }


def _score(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
