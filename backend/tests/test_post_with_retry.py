"""services.asr._post_with_retry: short exponential backoff for calls to
external AI provider APIs (OpenAI/Groq/Gemini). A classroom of ~50 students
hitting the same provider around the same moment makes a rate-limit blip or a
dropped connection common, not exceptional - see services/asr.py's own
comment above the helper. It's re-exported into main's namespace for
part_007/part_008's vocab/phrase/distractor/cloze/synonym/image-generation
callers, which is a separate, general-purpose use of the same helper.
"""
import os
import sys

import httpx
import pytest
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import services.asr as asr_service


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", "https://example.com"))


@pytest.mark.asyncio
async def test_returns_immediately_on_success(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 3)
    client = AsyncMock()
    client.post = AsyncMock(return_value=_response(200))

    response = await asr_service._post_with_retry(client, "https://example.com")

    assert response.status_code == 200
    assert client.post.call_count == 1


@pytest.mark.asyncio
async def test_returns_immediately_on_a_non_retryable_status(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 3)
    client = AsyncMock()
    client.post = AsyncMock(return_value=_response(401))

    response = await asr_service._post_with_retry(client, "https://example.com")

    assert response.status_code == 401
    assert client.post.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_a_retryable_status_then_succeeds(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(asr_service.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[_response(429), _response(200)])

    response = await asr_service._post_with_retry(client, "https://example.com")

    assert response.status_code == 200
    assert client.post.call_count == 2


@pytest.mark.asyncio
async def test_returns_the_final_response_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(asr_service.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.post = AsyncMock(return_value=_response(503))

    response = await asr_service._post_with_retry(client, "https://example.com")

    assert response.status_code == 503
    assert client.post.call_count == 3


@pytest.mark.asyncio
async def test_retries_on_timeout_then_succeeds(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(asr_service.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[httpx.ConnectTimeout("timed out"), _response(200)])

    response = await asr_service._post_with_retry(client, "https://example.com")

    assert response.status_code == 200
    assert client.post.call_count == 2


@pytest.mark.asyncio
async def test_raises_after_exhausting_retries_on_repeated_timeouts(monkeypatch):
    monkeypatch.setattr(asr_service, "_ASR_PROVIDER_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(asr_service.asyncio, "sleep", AsyncMock())
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))

    with pytest.raises(httpx.ConnectTimeout):
        await asr_service._post_with_retry(client, "https://example.com")

    assert client.post.call_count == 2
