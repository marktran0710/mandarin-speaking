import asyncio

import httpx
import pytest

from services.pronunciation.ompal import assess_ompal
from services.pronunciation.presenter import present_evaluation
from services.pronunciation.rubric_evaluator import RubricEvaluation

BODY = {"results": {"accuracy": 4.5, "fluency": 4.4, "prosody": 4.3, "feedback": "很好"},
        "duration_seconds": 1.9, "model_version": "v2"}


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_OMPAL_ENABLED", "true")
    monkeypatch.setenv("PRONUNCIATION_OMPAL_TIMEOUT_SECONDS", "30")


@pytest.mark.asyncio
async def test_request_and_response():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/assess"
        assert b'name="file"' in request.content
        assert "他們都很忙".encode() in request.content
        assert b"audio-fixture" in request.content
        return httpx.Response(200, json=BODY)
    result = await assess_ompal(b"audio-fixture", "他們都很忙", transport=httpx.MockTransport(handler))
    assert result["status"] == "scored"
    assert result["scores"]["accuracy"] == 4.5
    assert result["model_version"] == "v2"
    assert "average_score" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429, 500])
async def test_http_failures(status):
    result = await assess_ompal(b"audio", "你好", transport=httpx.MockTransport(lambda req: httpx.Response(status)))
    assert result == {"status": "unavailable", "source": "ompal_api", "reason": f"http_{status}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 6, True, "4", None])
async def test_invalid_score(value):
    body = BODY | {"results": BODY["results"] | {"accuracy": value}}
    result = await assess_ompal(b"audio", "你好", transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    assert result["reason"] == "invalid_response"


@pytest.mark.asyncio
async def test_deadline(monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_OMPAL_TIMEOUT_SECONDS", ".01")
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=BODY)
    assert (await assess_ompal(b"audio", "你好", transport=httpx.MockTransport(handler)))["reason"] == "timeout"


@pytest.mark.asyncio
async def test_disabled_makes_no_request(monkeypatch):
    monkeypatch.setenv("PRONUNCIATION_OMPAL_ENABLED", "false")
    def handler(request):
        pytest.fail("disabled provider must not upload audio")
    assert (await assess_ompal(b"audio", "你好", transport=httpx.MockTransport(handler)))["reason"] == "disabled"


def test_comparison_visible_without_debug():
    comparison = {"status": "scored", "scores": {"accuracy": 4.5}}
    body = present_evaluation(RubricEvaluation({"ompal_comparison": comparison, "debug": {"private": True}}), include_debug=False)
    assert body["ompal_comparison"] == comparison
    assert "debug" not in body
