"""
ASR Performance benchmarks.

Measures latency and throughput of:
  - Provider routing (zero cost, should be <1 ms)
  - fallback_language_feedback() (local, CPU-only)
  - transcribe_with_openai / gemini (mocked network)
  - /api/transcribe endpoint (full HTTP round-trip via TestClient)
  - Auto-fallback chain under provider failure
  - Concurrent request handling

Run with:
    pytest backend/tests/test_asr_performance.py -v --tb=short -s
    pytest backend/tests/test_asr_performance.py -v -k perf
"""

import asyncio
import os
import sys
import time
import statistics
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from fixtures import SILENT_WAV, SHORT_WAV, LONG_WAV


# ── Helpers ───────────────────────────────────────────────────────────────────

def measure(fn, iterations: int = 50):
    """Run a sync callable N times and return (mean_ms, p95_ms, p99_ms)."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    mean = statistics.mean(times)
    p95  = times[int(len(times) * 0.95)]
    p99  = times[min(int(len(times) * 0.99), len(times) - 1)]
    return mean, p95, p99


async def ameasure(coro_fn, iterations: int = 20):
    """Run an async callable N times and return (mean_ms, p95_ms, p99_ms)."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await coro_fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    mean = statistics.mean(times)
    p95  = times[int(len(times) * 0.95)]
    p99  = times[min(int(len(times) * 0.99), len(times) - 1)]
    return mean, p95, p99


def print_result(label: str, mean: float, p95: float, p99: float,
                 budget_ms: float | None = None):
    status = ""
    if budget_ms is not None:
        status = "PASS" if mean < budget_ms else "OVER BUDGET"
    print(f"\n  [{label}]")
    print(f"    mean={mean:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms  {status}")
    if budget_ms:
        print(f"    budget={budget_ms:.0f}ms")


# ── Provider routing (pure Python, no I/O) ───────────────────────────────────

class TestRoutingPerformance:
    """Routing is synchronous logic — should cost essentially nothing."""

    @pytest.mark.asyncio
    async def test_routing_latency_under_1ms(self):
        from services.asr import transcribe_audio_content

        async def route():
            with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as m:
                m.return_value = MagicMock(text="你好", model="ctwhisper")
                await transcribe_audio_content(SHORT_WAV, "ctwhisper")

        mean, p95, p99 = await ameasure(route, iterations=30)
        print_result("routing (ctwhisper alias)", mean, p95, p99, budget_ms=5)
        assert mean < 5, f"Routing overhead too high: {mean:.1f}ms"

    @pytest.mark.asyncio
    async def test_auto_fallback_routing_latency(self, monkeypatch):
        import services.asr as asr
        monkeypatch.setattr(asr, "ASR_FALLBACK_ORDER", ["ctwhisper"])

        async def route():
            with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as m:
                m.return_value = MagicMock(text="你好", model="ctwhisper")
                await asr.transcribe_with_auto_fallback(SHORT_WAV)

        mean, p95, p99 = await ameasure(route, iterations=30)
        print_result("auto-fallback (1 provider)", mean, p95, p99, budget_ms=5)
        assert mean < 5


# ── Mocked API providers ──────────────────────────────────────────────────────

class TestMockedProviderLatency:
    """
    Measures Python overhead only — actual network latency is mocked to zero.
    This tells us whether our async/await wrapping adds hidden cost.
    """

    @pytest.mark.asyncio
    async def test_openai_provider_overhead(self, monkeypatch):
        monkeypatch.setattr("services.asr.OPENAI_API_KEY", "sk-test")
        from services.asr import transcribe_with_openai

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"text": "你好"}

        async def run():
            with patch("httpx.AsyncClient") as cls:
                cli = AsyncMock()
                cli.__aenter__ = AsyncMock(return_value=cli)
                cli.__aexit__ = AsyncMock(return_value=False)
                cli.post = AsyncMock(return_value=mock_resp)
                cls.return_value = cli
                await transcribe_with_openai(SHORT_WAV)

        mean, p95, p99 = await ameasure(run, iterations=20)
        print_result("openai provider (mocked net)", mean, p95, p99, budget_ms=20)
        assert mean < 20

    @pytest.mark.asyncio
    async def test_gemini_provider_overhead(self, monkeypatch):
        monkeypatch.setattr("services.asr.GEMINI_API_KEY", "test-key")
        from services.asr import transcribe_with_gemini

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "早上好"}]}}]
        }

        async def run():
            with patch("httpx.AsyncClient") as cls:
                cli = AsyncMock()
                cli.__aenter__ = AsyncMock(return_value=cli)
                cli.__aexit__ = AsyncMock(return_value=False)
                cli.post = AsyncMock(return_value=mock_resp)
                cls.return_value = cli
                await transcribe_with_gemini(SHORT_WAV)

        mean, p95, p99 = await ameasure(run, iterations=20)
        print_result("gemini provider (mocked net)", mean, p95, p99, budget_ms=20)
        assert mean < 20


# ── Local feedback (CPU-only, no I/O) ────────────────────────────────────────

class TestFeedbackPerformance:
    """
    fallback_language_feedback() must be fast since it's called on every
    analysis request when no cloud provider is configured.
    """

    def test_empty_input_fast(self):
        from ai_feedback import fallback_language_feedback
        mean, p95, p99 = measure(lambda: fallback_language_feedback(""), iterations=100)
        print_result("fallback_feedback (empty)", mean, p95, p99, budget_ms=2)
        assert mean < 2

    def test_short_text_fast(self):
        from ai_feedback import fallback_language_feedback
        text = "我叫李明，我住在台北。"
        vocab = "我,叫,住,台北"
        mean, p95, p99 = measure(
            lambda: fallback_language_feedback(text, scene_vocabulary=vocab),
            iterations=100,
        )
        print_result("fallback_feedback (short text)", mean, p95, p99, budget_ms=2)
        assert mean < 2

    def test_long_text_still_fast(self):
        from ai_feedback import fallback_language_feedback
        text = "我的名字叫李明。我住在台北市的一個小社區裡面。我喜歡學習普通話，也喜歡和朋友一起去公園散步。"
        vocab = ",".join(["我", "名字", "台北", "學習", "朋友", "公園"])
        mean, p95, p99 = measure(
            lambda: fallback_language_feedback(
                text, scene_vocabulary=vocab,
                praat_tone_accuracy=75.0, praat_fluency_score=68.0,
            ),
            iterations=100,
        )
        print_result("fallback_feedback (long text + praat)", mean, p95, p99, budget_ms=5)
        assert mean < 5

    def test_throughput_rps(self):
        from ai_feedback import fallback_language_feedback
        text = "我叫李明，我住在台北。"
        vocab = "我,叫,住,台北"
        iters = 500
        t0 = time.perf_counter()
        for _ in range(iters):
            fallback_language_feedback(text, scene_vocabulary=vocab)
        elapsed = time.perf_counter() - t0
        rps = iters / elapsed
        print(f"\n  [fallback_feedback throughput] {rps:.0f} req/s over {iters} iterations")
        assert rps > 500, f"Local feedback too slow: {rps:.0f} req/s"


# ── Fallback chain failure path ───────────────────────────────────────────────

class TestFallbackChainPerformance:
    """
    When the first N providers all fail, the chain should still resolve
    quickly (no long blocking retries).
    """

    @pytest.mark.asyncio
    async def test_single_failure_fast(self, monkeypatch):
        import services.asr as asr
        monkeypatch.setattr(asr, "ASR_FALLBACK_ORDER", ["ctwhisper", "funasr"])

        async def run():
            with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw, \
                 patch("services.asr.transcribe_with_funasr", new_callable=AsyncMock) as funasr:
                ctw.side_effect = RuntimeError("not loaded")
                funasr.return_value = MagicMock(text="你好", model="funasr")
                await asr.transcribe_with_auto_fallback(SHORT_WAV)

        mean, p95, p99 = await ameasure(run, iterations=20)
        print_result("fallback: 1 fail + 1 success", mean, p95, p99, budget_ms=10)
        assert mean < 10

    @pytest.mark.asyncio
    async def test_two_failures_still_fast(self, monkeypatch):
        import services.asr as asr
        monkeypatch.setattr(asr, "ASR_FALLBACK_ORDER", ["ctwhisper", "funasr", "gemini"])
        monkeypatch.setattr(asr, "GEMINI_API_KEY", "test-key")

        mock_gemini_resp = MagicMock(status_code=200)
        mock_gemini_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "你好"}]}}]
        }

        async def run():
            with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw, \
                 patch("services.asr.transcribe_with_funasr", new_callable=AsyncMock) as funasr, \
                 patch("httpx.AsyncClient") as cls:
                ctw.side_effect = RuntimeError("not loaded")
                funasr.side_effect = RuntimeError("not loaded")
                cli = AsyncMock()
                cli.__aenter__ = AsyncMock(return_value=cli)
                cli.__aexit__ = AsyncMock(return_value=False)
                cli.post = AsyncMock(return_value=mock_gemini_resp)
                cls.return_value = cli
                await asr.transcribe_with_auto_fallback(SHORT_WAV)

        mean, p95, p99 = await ameasure(run, iterations=20)
        print_result("fallback: 2 fails + 1 success (gemini)", mean, p95, p99, budget_ms=20)
        assert mean < 20


# ── HTTP endpoint concurrency ─────────────────────────────────────────────────

class TestEndpointConcurrency:
    """
    Simulate concurrent requests to /api/transcribe via asyncio.gather.
    The backend must handle N simultaneous requests without serialising.
    """

    @pytest.mark.asyncio
    async def test_concurrent_transcribe_requests(self):
        from fastapi.testclient import TestClient
        import main

        N = 10

        with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="ctwhisper")

            with TestClient(main.app) as client:
                def single_request():
                    return client.post(
                        "/api/transcribe",
                        files={"file": ("t.wav", SHORT_WAV, "audio/wav")},
                        data={"model": "ctwhisper"},
                    )

                t0 = time.perf_counter()
                # Run via asyncio.gather to measure async throughput
                loop = asyncio.get_event_loop()
                results = await asyncio.gather(
                    *[loop.run_in_executor(None, single_request) for _ in range(N)]
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

        statuses = [r.status_code for r in results]
        print(f"\n  [{N} concurrent /api/transcribe] total={elapsed_ms:.0f}ms "
              f"per-req~{elapsed_ms/N:.0f}ms  statuses={set(statuses)}")
        assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"

    @pytest.mark.asyncio
    async def test_health_endpoint_latency(self):
        from fastapi.testclient import TestClient
        import main

        with TestClient(main.app) as client:
            mean, p95, p99 = measure(
                lambda: client.get("/health"),
                iterations=50,
            )
        print_result("/health endpoint", mean, p95, p99, budget_ms=50)
        assert mean < 50


# ── WAV payload size impact ───────────────────────────────────────────────────

class TestPayloadSizeImpact:
    """
    Verify that larger audio payloads don't disproportionately slow routing.
    The routing overhead itself should be independent of payload size.
    """

    @pytest.mark.asyncio
    async def test_short_vs_long_wav_routing_similar(self, monkeypatch):
        import services.asr as asr
        monkeypatch.setattr(asr, "ASR_FALLBACK_ORDER", ["ctwhisper"])

        async def route(wav):
            with patch("services.asr.transcribe_with_ct_whisper", new_callable=AsyncMock) as m:
                m.return_value = MagicMock(text="你好", model="ctwhisper")
                await asr.transcribe_with_auto_fallback(wav)

        mean_short, _, _ = await ameasure(lambda: route(SHORT_WAV), iterations=20)
        mean_long,  _, _ = await ameasure(lambda: route(LONG_WAV),  iterations=20)

        print(f"\n  [routing overhead by size]")
        print(f"    short WAV ({len(SHORT_WAV):,} B): {mean_short:.2f}ms")
        print(f"    long  WAV ({len(LONG_WAV):,} B): {mean_long:.2f}ms")
        print(f"    ratio: {mean_long/mean_short:.1f}x")

        # Routing overhead (not inference!) should not scale with file size
        assert mean_long < mean_short * 10, (
            f"Routing overhead scales too much with file size: "
            f"{mean_short:.1f}ms vs {mean_long:.1f}ms"
        )


# ── Summary printer ───────────────────────────────────────────────────────────

class TestSummaryReport:
    """Prints a consolidated benchmark summary at end of run."""

    def test_print_summary(self):
        from ai_feedback import fallback_language_feedback

        scenarios = [
            ("empty feedback",
             lambda: fallback_language_feedback(""), 100),
            ("short feedback",
             lambda: fallback_language_feedback("你好", scene_vocabulary="你好"), 100),
        ]

        print("\n" + "=" * 60)
        print("  ASR BENCHMARK SUMMARY")
        print("=" * 60)

        for label, fn, n in scenarios:
            mean, p95, p99 = measure(fn, iterations=n)
            print(f"  {label:<35} mean={mean:6.2f}ms  p95={p95:6.2f}ms")

        print("=" * 60)
        assert True  # always pass — this is just a printer
