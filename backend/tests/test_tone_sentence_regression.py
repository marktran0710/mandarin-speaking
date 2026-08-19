"""Regression: 友美，妳這個週末要做什麼？

The sentence that started this work. The app returned ✗ for six of its eleven
syllables, and for most of them the only thing that had gone wrong was that a
heuristic contour score landed under 58.

Two kinds of test here:

* end-to-end through `estimate_word_prosody`, checking that the contextual
  targets and the diagnostic fields are actually produced and that the legacy
  progression fields are untouched;
* a decision-layer replay of the exact scores the real recording produced, so
  the four-state outcome for each syllable is pinned and reviewable.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import SYLLABLE_PASS_THRESHOLD, estimate_word_prosody
from tone_decision import (
    PROVENANCE_MEASURED,
    PROVENANCE_NEUTRAL_CONSTANT,
    DiagnosticStatus,
    QcEvidence,
    decide_tone,
    summarize_sentence,
)

SENTENCE = "友美, 妳這個週末要做什麼?"


def _contour(num_points=260, duration=3.2):
    """A plausible speech-shaped contour. The exact numbers do not matter for
    these assertions — what is under test is the plumbing and the contextual
    targets, not one particular recording's scores."""
    rng = np.random.default_rng(11)
    base = 210 + 30 * np.sin(np.linspace(0, 9 * np.pi, num_points))
    jitter = rng.normal(0, 4, num_points)
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), (base + jitter).tolist()))


@pytest.fixture(scope="module")
def segments():
    return estimate_word_prosody(_contour(), SENTENCE)


@pytest.fixture(scope="module")
def syllables(segments):
    return [s for segment in segments for s in segment.get("syllables", [])]


def by_char(syllables, char):
    return next(s for s in syllables if s["char"] == char)


def test_every_syllable_is_diagnosed(syllables):
    assert [s["char"] for s in syllables] == list("友美妳這個週末要做什麼")
    for syllable in syllables:
        assert syllable["diagnostic_status"] in {
            "CORRECT",
            "UNCERTAIN",
            "INCORRECT",
            "INVALID_AUDIO",
        }
        assert syllable["diagnostic_reason"]
        assert "underlying_tone" in syllable
        assert syllable["accepted_surface_tones"]


def test_the_comma_splits_the_third_tone_run(syllables):
    """友美，| 妳 — three T3s on paper, but not one chain.

    Sandhi is phrase-internal, so the comma cuts the run in two: 友美 is a
    clean T3+T3 pair (友 → rising), and 妳 starts a fresh phrase. An earlier
    version grouped all three because segmentation discarded the punctuation,
    which loosened 友 to "either T2 or T3" — a weaker and wronger target.
    """
    you, mei, ni = (by_char(syllables, c) for c in ("友", "美", "妳"))

    assert you["underlying_tone"] == 3
    assert you["accepted_surface_tones"] == [2], "友 is the first of a clean pair"
    assert you["context_rule"] == "T3_T3"
    assert you["tone_realization"] == "third_tone_sandhi"

    assert mei["accepted_surface_tones"] == [3], "美 is phrase-final before the comma"
    assert mei["boundary_after"] is True
    assert mei["tone_realization"] == "full_third"

    assert ni["accepted_surface_tones"] == [3], "妳 opens a new phrase"
    assert ni["context_rule"] is None, "no sandhi reaches across the comma"


def test_ni_before_a_fourth_tone_is_half_third(syllables):
    entry = by_char(syllables, "妳")
    assert entry["underlying_tone"] == 3
    assert entry["accepted_surface_tones"] == [3]
    assert entry["tone_realization"] == "half_third"


def test_ge_accepts_the_neutral_realization(syllables):
    """這個's 個 is normally destressed; insisting on a full T4 fall would
    fail a learner who said it the ordinary way."""
    entry = by_char(syllables, "個")
    assert set(entry["accepted_surface_tones"]) == {4, 5}


def test_the_neutral_syllable_is_never_reported_as_measured(syllables):
    """麼 used to come back as a flat 75 % ✓ for every learner alive. There is
    no neutral-tone evaluator, so the honest answer is "not judged"."""
    entry = by_char(syllables, "麼")
    assert entry["underlying_tone"] == 5
    assert entry["diagnostic_status"] == "UNCERTAIN"
    assert entry["diagnostic_reason"] == "neutral_tone_has_no_contour_target"
    assert entry["contour_match_score"] is None


# ── H: progression must be untouched by all of the above ─────────────────


def test_legacy_threshold_is_unchanged():
    assert SYLLABLE_PASS_THRESHOLD == 58.0


def test_legacy_score_and_threshold_still_travel_with_the_syllable(syllables):
    """After the verdict refactor, `passed` follows the canonical verdict
    rather than the raw score bar — but the raw score and the legacy
    threshold-only verdict must still ride alongside so research exports
    and A/B ablation can see what the old gate would have said."""
    for syllable in syllables:
        assert isinstance(syllable["score"], float)
        assert syllable["legacy"]["threshold"] == 58.0
        assert syllable["legacy"]["passed"] == (
            syllable["score"] >= SYLLABLE_PASS_THRESHOLD
        )


def test_canonical_passed_follows_the_verdict_not_the_raw_threshold(segments):
    """The refactor's central invariant, verified end-to-end: `passed` is
    True IFF the diagnostic verdict is CORRECT — OR the syllable's word
    verdict was itself promoted to CORRECT by combined shape+direction
    evidence (e.g. strong_shape_direction_overridden), which is allowed to
    carry non-placeholder syllables along with it (see the promotion loop
    in estimate_word_prosody). Placeholder syllables (neutral tone / too
    short to measure) are exempt from that promotion and must still follow
    their own diagnostic verdict.
    """
    placeholder_provenances = {"constant_short_segment", "neutral_not_measured"}
    for segment in segments:
        word_promoted = segment.get("passed") is True
        for syllable in segment.get("syllables", []):
            canonical = syllable["diagnostic_status"] == "CORRECT"
            if (
                word_promoted
                and syllable.get("score_provenance") not in placeholder_provenances
            ):
                assert syllable["passed"] is True, syllable
            else:
                assert syllable["passed"] is canonical, syllable


def test_placeholder_syllables_never_pass_under_the_new_gate(syllables):
    """Direct assertion of the bug the refactor closes: neutral-tone and
    short-segment placeholders — which the legacy gate silently passed
    because their constants (75, 65) sit above the 58 bar — must now
    resolve to passed=False via the UNCERTAIN verdict."""
    placeholders = [
        s
        for s in syllables
        if s["diagnostic_status"] == "UNCERTAIN"
        and s.get("diagnostic_reason")
        in {"neutral_tone_has_no_contour_target", "segment_too_short_to_measure"}
    ]
    assert placeholders, (
        "expected at least one placeholder syllable in this recording "
        "(the neutral-tone 麼 is one)"
    )
    for syllable in placeholders:
        assert syllable["passed"] is False, syllable


# ── Decision replay of the real recording's scores ───────────────────────

#: What the production scorer actually produced for this recording, together
#: with the contextual target each syllable was measured against. Recorded
#: from a real learner attempt so the table is not invented.
OBSERVED = [
    ("友", 55.0, PROVENANCE_MEASURED),
    ("美", 53.0, PROVENANCE_MEASURED),
    ("妳", 50.0, PROVENANCE_MEASURED),
    ("這", 94.0, PROVENANCE_MEASURED),
    ("個", 56.0, PROVENANCE_MEASURED),
    ("週", 100.0, PROVENANCE_MEASURED),
    ("末", 69.0, PROVENANCE_MEASURED),
    ("要", 51.0, PROVENANCE_MEASURED),
    ("做", 68.0, PROVENANCE_MEASURED),
    ("什", 37.0, PROVENANCE_MEASURED),
    ("麼", 75.0, PROVENANCE_NEUTRAL_CONSTANT),
]

GOOD_QC = QcEvidence(judged=True, pitch_points=40, minimum_pitch_points=8)


def _replay():
    return {
        char: decide_tone(
            score,
            provenance,
            GOOD_QC,
            measurable_by_contour=provenance != PROVENANCE_NEUTRAL_CONSTANT,
        ).status
        for char, score, provenance in OBSERVED
    }


@pytest.mark.parametrize("char", ["友", "美", "妳", "個", "要"])
def test_the_originally_misreported_syllables_are_no_longer_errors(char):
    """The core complaint: every one of these was shown as ✗ purely because a
    heuristic score sat between 50 and 57.

    A later calibration pass (2026-08-19) lowered TONE_CONFIRM_THRESHOLD from
    58 to 50 specifically to shrink the "not clear enough to judge" band, so
    these scores (50-56) now clear the confirm bar outright instead of
    landing in UNCERTAIN — the intended outcome, not a regression."""
    assert _replay()[char] is DiagnosticStatus.CORRECT


@pytest.mark.parametrize("char", ["這", "週", "末", "做"])
def test_the_clear_matches_stay_correct(char):
    assert _replay()[char] is DiagnosticStatus.CORRECT


def test_shen_is_reported_as_an_error_and_this_is_a_known_divergence():
    """什 scores 37 against a rising target, meaning its pitch fell where it
    should have risen. Under the corrected reading of this pipeline that is
    evidence of a tone error, so it is reported as one.

    This DIVERGES from the original specification, which listed 什 as
    UNCERTAIN. That expectation assumed 0.37 was a model confidence — "the
    classifier is unsure". It is not: there is no classifier, and 37 is a
    contour mismatch. Forcing this one syllable back to UNCERTAIN would mean
    tuning the error threshold to a single example, so the divergence is
    recorded here instead and left for calibration against human raters.
    """
    assert _replay()["什"] is DiagnosticStatus.INCORRECT


def test_the_neutral_syllable_is_not_a_free_pass():
    assert _replay()["麼"] is DiagnosticStatus.UNCERTAIN


def test_the_sentence_is_mostly_correct_not_uncertain():
    """The headline result after the 2026-08-19 calibration pass: what used to
    read as six pronunciation failures, then six "could not tell"s, is now one
    candidate error and a single genuine unmeasured syllable (麼, neutral
    tone). 友/美/妳/個/要 all clear the lowered confirm bar."""
    summary = summarize_sentence(list(_replay().values()))
    assert summary["counts"]["incorrect"] == 1
    assert summary["counts"]["uncertain"] == 1
    assert summary["counts"]["correct"] == 9
    # And a single error asks the learner to drill that syllable, not to
    # re-record the whole sentence.
    assert summary["recommended_action"] == "targeted_practice"
