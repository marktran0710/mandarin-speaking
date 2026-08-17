"""Real-human-speech regression test for the production tone scorer.

Everything else that exercises `chinese_tones.py`/`tone_decision.py`
(test_syllable_gate.py, test_word_tone_decision.py, ...) does so on
hand-crafted synthetic pitch contours. This is the first test that runs the
actual production pipeline (`praat_analyzer.analyze_all`, no mocking, no
API key needed — pure local Parselmouth) on **real recorded human speech**
with **expert-labeled correct/incorrect tone judgments**: a small, vendored
subset of the OMPAL corpus (see `fixtures/ompal_sample/ATTRIBUTION.md`).

What this test is and is not:

* It IS a regression guard: if a future change to the scoring pipeline
  causes a mass verdict flip (e.g. everything becomes CORRECT, or
  everything becomes INCORRECT, or the pipeline starts crashing on real
  WAV files), these tests will fail loudly.
* It is NOT a claim of scientific accuracy. 16 utterances cannot support
  that claim, and the production scorer has a documented, known bias
  (T1 over-acceptance / T2-4 over-rejection — see
  backend/benchmarking/report_controlled_tone_test.py) that this test
  does not try to fix. The baseline thresholds below were measured against
  the current scorer and given generous headroom specifically so this test
  does not fail on that already-known, already-documented gap.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import analyze_all

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "ompal_sample")
METADATA_PATH = os.path.join(FIXTURE_DIR, "metadata.json")


def _load_metadata():
    with open(METADATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ompal_results():
    """Run the real production pipeline once per vendored utterance.

    Returns a list of (metadata, word_prosody) pairs. Module-scoped so the
    ~1.7s total Praat processing cost is paid once, not once per test.
    """
    metadata = _load_metadata()
    results = []
    for utterance in metadata:
        wav_path = os.path.join(FIXTURE_DIR, utterance["wav_file"])
        analysis = analyze_all(wav_path, utterance["text"])
        word_prosody = analysis[5]
        results.append((utterance, word_prosody))
    return results


def _syllables_by_char(word_prosody):
    """Flatten word_prosody into {char: syllable_dict}, first match wins."""
    by_char = {}
    for word in word_prosody:
        for syllable in word.get("syllables") or []:
            by_char.setdefault(syllable["char"], syllable)
    return by_char


def test_fixture_covers_all_four_tones_and_both_populations():
    """Sanity check on the fixture itself, not the scorer — catches an
    accidentally-corrupted or -truncated metadata.json before it produces
    confusing failures below."""
    metadata = _load_metadata()
    assert len(metadata) >= 15
    tones = {t for u in metadata for w in u["words"] for t in w["expected_tones"]}
    assert {1, 2, 3, 4} <= tones
    assert any(u["is_native"] for u in metadata)
    assert any(not u["is_native"] for u in metadata)


def test_pipeline_runs_on_every_real_recording_without_error(ompal_results):
    """Basic pipeline-integrity regression: the production Praat pipeline
    must run to completion on real (non-synthetic) WAV files and return a
    non-empty, well-shaped word_prosody for every one of them. Nothing here
    depends on getting the tone judgment right — only on not crashing and
    not silently returning nothing."""
    assert len(ompal_results) >= 15
    for utterance, word_prosody in ompal_results:
        assert word_prosody, f"empty word_prosody for {utterance['utterance_id']}"
        for word in word_prosody:
            assert "syllables" in word
            assert "verdict" in word
            assert "passed" in word


def test_syllable_passed_matches_diagnostic_status_on_real_audio(ompal_results):
    """Two one-directional invariants from the tone-verdict refactor, now
    confirmed on real recorded speech rather than only hand-crafted
    contours (test_word_prosody_verdict_wiring.py):

    * diagnostic_status == CORRECT  =>  passed is True   (always)
    * diagnostic_status == INCORRECT => passed is False  (always — the
      word-level combiner never reaches a CORRECT word verdict, the only
      thing that promotes a syllable's `passed`, while an INCORRECT
      syllable is present)

    NOT asserted: UNCERTAIN => passed is False. A real, intended case
    (word-level promotion — see praat_analyzer.py's combiner) sets
    passed=True for a measured-UNCERTAIN syllable when the whole-word
    shape+direction evidence is strong; `diagnostic_status` deliberately
    stays UNCERTAIN so the row still displays △ honestly. This test hit
    that exact case on 00100102's 我 (word 我家: shape=85.1 dir=96.5 =>
    word verdict CORRECT => 我's passed promoted to True while its own
    diagnostic_status stays UNCERTAIN) while it was first written — proof
    real audio exercises paths synthetic fixtures had not."""
    for utterance, word_prosody in ompal_results:
        for word in word_prosody:
            for syllable in word.get("syllables") or []:
                diag = syllable.get("diagnostic_status")
                passed = syllable.get("passed")
                if diag == "CORRECT":
                    assert passed is True, (
                        f"{utterance['utterance_id']} char={syllable['char']} "
                        f"diagnostic_status=CORRECT but passed={passed}"
                    )
                elif diag == "INCORRECT":
                    assert passed is False, (
                        f"{utterance['utterance_id']} char={syllable['char']} "
                        f"diagnostic_status=INCORRECT but passed={passed}"
                    )


# Measured against the current production scorer on this fixture (see
# module docstring): 9/86 known-correct words are currently scored
# INCORRECT (~10%), and 2/6 known-incorrect words are currently scored
# CORRECT (~33%). Both bounds below are set with generous headroom above
# that baseline — they exist to catch a GROSS regression (the rate roughly
# doubling or worse), not to hold the scorer to today's already-imperfect
# baseline.
MAX_FALSE_REJECT_RATE = 0.35
MAX_FALSE_ACCEPT_RATE = 0.75


def test_false_reject_rate_on_expert_confirmed_correct_words(ompal_results):
    """Words every OMPAL rater agreed were pronounced correctly must not be
    confidently called INCORRECT (the strongest ✗ state) at anywhere near a
    majority rate. A known baseline miss rate exists (see module docstring)
    — this only guards against it getting much worse."""
    total = 0
    false_rejects = 0
    for utterance, word_prosody in ompal_results:
        by_char = _syllables_by_char(word_prosody)
        for word_meta in utterance["words"]:
            if word_meta["consensus"] != "correct":
                continue
            syllable = by_char.get(word_meta["text"])
            if syllable is None:
                continue
            total += 1
            if syllable.get("diagnostic_status") == "INCORRECT":
                false_rejects += 1

    assert total >= 50, "fixture should provide enough known-correct words to be meaningful"
    rate = false_rejects / total
    assert rate <= MAX_FALSE_REJECT_RATE, (
        f"false-reject rate {rate:.2f} ({false_rejects}/{total}) exceeds "
        f"{MAX_FALSE_REJECT_RATE} — the scorer is calling confirmed-correct "
        "tones wrong far more than the measured baseline"
    )


def test_false_accept_rate_on_expert_confirmed_incorrect_words(ompal_results):
    """Words every OMPAL rater agreed were pronounced incorrectly must not
    be confidently called CORRECT at anywhere near a total rate. Sample is
    small (single digits) by construction — see module docstring for why
    this bound is deliberately loose rather than a precision claim."""
    total = 0
    false_accepts = 0
    for utterance, word_prosody in ompal_results:
        by_char = _syllables_by_char(word_prosody)
        for word_meta in utterance["words"]:
            if word_meta["consensus"] != "incorrect":
                continue
            syllable = by_char.get(word_meta["text"])
            if syllable is None:
                continue
            total += 1
            if syllable.get("diagnostic_status") == "CORRECT":
                false_accepts += 1

    assert total >= 4, "fixture should provide at least a few known-incorrect words"
    rate = false_accepts / total
    assert rate <= MAX_FALSE_ACCEPT_RATE, (
        f"false-accept rate {rate:.2f} ({false_accepts}/{total}) exceeds "
        f"{MAX_FALSE_ACCEPT_RATE} — the scorer is rubber-stamping confirmed-"
        "incorrect tones far more than the measured baseline"
    )
