"""ASR content-recognition test against real human speech.

Every other ASR test (test_asr_unit.py, test_asr_performance.py) mocks the
provider call directly — `patch("main.transcribe_with_groq", ...)` returning
a fixed string — so none of them ever check whether the ASR actually
recognizes real speech content. The only "audio" fixture that exists
elsewhere (`fixtures.py:SPEECH_WAV`) is a pure sine tone; no provider can
transcribe that into words.

This test calls a real ASR provider (no mocking) on real recorded human
speech — the same vendored OMPAL subset test_tone_scorer_ompal_regression.py
uses — and compares the recognized transcript to the utterance's known
correct text. Skipped entirely when no provider API key is configured, so it
never fails a run that simply has no credentials (matches the pattern in
test_deployment_inference_api.py).

Deliberately does NOT pass `vocab_hint` (the scene-vocabulary prompt bias +
`correct_homophones()` post-processing the production request path uses —
see main.py:2325, main.py:3581). That mechanism nudges a transcript toward
expected words and was never itself tested against real, potentially-wrong
speech; skipping it here measures the ASR provider's raw recognition
ability, which is the more fundamental thing to have any coverage of at all.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402 — import loads .env via main.py's own load_dotenv()

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "ompal_sample")
METADATA_PATH = os.path.join(FIXTURE_DIR, "metadata.json")

HAS_ASR_PROVIDER = bool(main.GROQ_API_KEY or main.OPENAI_API_KEY or main.GEMINI_API_KEY)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not HAS_ASR_PROVIDER,
        reason="no ASR provider API key configured (GROQ/OPENAI/GEMINI)",
    ),
]


def _load_metadata():
    with open(METADATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _char_overlap_ratio(expected: str, recognized: str) -> float:
    """Fraction of expected's characters also present in recognized, order-
    insensitive and allowing repeats up to expected's own count. Simple and
    tolerant of minor ASR punctuation/spacing quirks, while still requiring
    the actual content to be there — this is a content-recognition sanity
    check, not a precise WER measurement."""
    if not expected:
        return 1.0
    from collections import Counter

    expected_counts = Counter(expected)
    recognized_counts = Counter(recognized)
    matched = sum(min(count, recognized_counts[ch]) for ch, count in expected_counts.items())
    return matched / len(expected)


@pytest.mark.asyncio
async def test_asr_recognizes_most_real_speech_content():
    """Aggregate content-accuracy sanity check across the vendored real-
    speech sample. Not a claim of measured WER — a regression guard: if ASR
    routing breaks (wrong provider, wrong audio format, silence gate firing
    on real speech), the aggregate ratio collapses and this fails loudly.
    Per-utterance detail is printed so a real drop is diagnosable, not just
    "average went down"."""
    metadata = _load_metadata()
    ratios = []
    for utterance in metadata:
        wav_path = os.path.join(FIXTURE_DIR, utterance["wav_file"])
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        result = await main.transcribe_audio_content(audio_bytes, "auto")
        ratio = _char_overlap_ratio(utterance["text"], result.text)
        ratios.append(ratio)
        print(
            f"{utterance['utterance_id']} expected={utterance['text']!r} "
            f"got={result.text!r} model={result.model} ratio={ratio:.2f}"
        )

    assert ratios, "no utterances were transcribed"
    average_ratio = sum(ratios) / len(ratios)
    # Real ASR on real (if careful, prompted) speech should recognize most
    # of the target characters most of the time. 0.6 leaves real headroom
    # for accent/disfluency/homophone substitutions without masking a
    # genuine break (e.g. silence-gate misfiring, wrong audio format sent).
    assert average_ratio >= 0.6, (
        f"average character-overlap ratio {average_ratio:.2f} across "
        f"{len(ratios)} real recordings is far below what real ASR should "
        "achieve on prompted speech — check provider routing/audio format"
    )
