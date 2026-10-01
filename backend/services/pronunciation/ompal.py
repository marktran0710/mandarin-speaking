"""Optional external OMPAL comparison; never changes the local rubric."""
import asyncio
import math
import os

import httpx

ENDPOINT = "https://ompal.ntuompal.workers.dev/api/assess"


def unavailable(reason):
    return {"status": "unavailable", "source": "ompal_api", "reason": reason}


def _normalize(body):
    results = body["results"]
    scores = {}
    for key in ("accuracy", "fluency", "prosody"):
        value = results[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 5:
            raise ValueError("invalid score")
        scores[key] = value
    duration = body["duration_seconds"]
    version = body["model_version"]
    feedback = results.get("feedback", "")
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
            or duration <= 0 or not isinstance(version, str) or not version or len(version) > 100
            or not isinstance(feedback, str) or len(feedback) > 4000):
        raise ValueError("invalid metadata")
    return {"status": "scored", "source": "ompal_api", "scores": scores, "out_of": 5,
            "model_version": version, "duration_seconds": duration, "feedback": feedback,
            "validation_status": "external_comparison_not_calibrated"}


async def assess_ompal(audio: bytes, text: str, *, transport=None):
    if os.getenv("PRONUNCIATION_OMPAL_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return unavailable("disabled")
    if not audio or not text.strip():
        return unavailable("missing_input")
    try:
        timeout = float(os.getenv("PRONUNCIATION_OMPAL_TIMEOUT_SECONDS", "30"))
        if not math.isfinite(timeout) or not 0 < timeout <= 40:
            return unavailable("invalid_configuration")
        # Overall deadline also bounds servers that trickle response bytes.
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False) as client:
                response = await client.post(ENDPOINT, files={"file": ("recording.wav", audio, "audio/wav")}, data={"text": text})
                if not response.is_success:
                    return unavailable(f"http_{response.status_code}")
                return _normalize(response.json())
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return unavailable("timeout")
    except httpx.RequestError:
        return unavailable("connection_failed")
    except (ValueError, TypeError, KeyError):
        return unavailable("invalid_response")
