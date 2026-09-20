"""Vowel-quality readout for a student's own recording.

What this module reports, and what it deliberately refuses to.

`praat_analyzer` already measures each syllable's real time span (energy
aligner, see `tone_scoring.alignment`) and can measure real formants inside an
arbitrary slice of the audio. Together those give a genuine per-syllable F1/F2
reading — the first pronunciation signal in this app below the level of the
tone.

The obvious next step, turning that reading into a right/wrong verdict, is the
one thing not done here. Formant frequencies scale with vocal-tract length, so
a fixed table of adult vowel formants judges a child's perfectly good /a/ as
some other vowel. Normalising that away needs an estimate of the speaker's own
vowel space, and a short beginner sentence does not contain enough distinct
vowels to estimate one: with two vowels to fit, a single noisy measurement
drags the fit far enough to accuse the other, correct, vowel. That was not a
hypothetical — it is what the first implementation did to a synthesised /a/
placed exactly on target.

So the contract is: **measure, report, do not grade.**

* F1/F2 come back as measured. Those numbers are real.
* The articulatory reading (`vowel_zone`) is expressed *relative to the same
  recording's own centre*, so it is meaningful for any voice and makes no
  appeal to a canonical table.
* The vowel the character is supposed to carry is reported alongside, from the
  pinyin. The student sees target and measurement side by side; neither this
  module nor the UI claims a score for the pair.
* Only the tone gate can pass or fail anything. Nothing here reaches it.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# The nucleus vowel of every Mandarin final, with where that nucleus actually
# sits in the mouth.
#
# The articulation has to hang off the *final*, not off the vowel letter,
# because the letter lies. Written "e" is three different vowels: the back
# unrounded [ɤ] of 這 zhè, the front [e] of 美 měi and 姐 jiě, and the central
# [ə] of 什 shén. An earlier version of this table keyed on the letter and so
# told a student that 美 targets a *back* vowel, which is simply false — and
# false in the one direction that matters, since the whole column exists to
# tell them where to put their tongue.
#
# For a monophthong the final *is* the nucleus. For the rest this is the vowel
# the middle of the syllable is closest to, which is what makes a single
# median interpretable at all — but it remains the nucleus of a moving target,
# hence the `nucleus_only` status.
FINAL_NUCLEUS: Dict[str, Dict[str, str]] = {}


def _final(final: str, vowel: str, height: str, backness: str) -> None:
    FINAL_NUCLEUS[final] = {"vowel": vowel, "height": height, "backness": backness}


# Open central [a] — the nucleus of every a-final.
for _f in ("a", "ai", "ao", "an", "ang", "ia", "iao", "ian", "iang",
           "ua", "uai", "uan", "uang", "van"):
    _final(_f, "a", "low", "central")
# Mid back rounded [o].
for _f in ("o", "ou", "uo", "iou", "iu", "ong", "iong"):
    _final(_f, "o", "mid", "back")
# Mid back unrounded [ɤ] — only "e" standing on its own.
_final("e", "e", "mid", "back")
# Mid FRONT [e] — the e of ei/ie/üe/uei, and the [ɛ] of üan.
for _f in ("ei", "ie", "ve", "uei", "ui"):
    _final(_f, "e", "mid", "front")
# Central [ə] — the e of the -n/-ng finals.
for _f in ("en", "eng", "uen", "un", "ueng"):
    _final(_f, "e", "mid", "central")
# High front [i].
for _f in ("i", "in", "ing"):
    _final(_f, "i", "high", "front")
# High back rounded [u].
_final("u", "u", "high", "back")
# High front rounded [y] — ü, as pypinyin spells it.
for _f in ("v", "vn"):
    _final(_f, "v", "high", "front")

MONOPHTHONGS = frozenset({"a", "o", "e", "i", "u", "v"})

# Bounds a human vowel's formants have to respect. Outside them the LPC
# tracker has locked onto the wrong pole — which happens on retroflex onsets
# (zh/ch/sh) and nasals — and the number it produced is not a measurement of
# anything. Values here come from the standard range of adult and child vowel
# formants, widened generously so only genuine tracker failures are caught.
_F1_RANGE = (180.0, 1100.0)
_F2_RANGE = (600.0, 3400.0)


def is_plausible(f1: float, f2: float) -> bool:
    """Whether a formant pair could have come from a human vowel at all.

    F2 always sits above F1 in a vowel; a pair that violates that, or that
    lands outside the physiological range, is a tracking failure. Showing it
    would be worse than showing nothing, because it looks like data.
    """
    if f1 <= 0 or f2 <= 0:
        return False
    if not (_F1_RANGE[0] <= f1 <= _F1_RANGE[1]):
        return False
    if not (_F2_RANGE[0] <= f2 <= _F2_RANGE[1]):
        return False
    return f2 > f1

# Initials after which a written "i" is the syllabic apical vowel, not /i/.
_APICAL_INITIALS = frozenset({"zh", "ch", "sh", "r", "z", "c", "s"})

# Statuses, in the order they are decided.
NOT_MEASURED = "not_measured"      # no audio was handed in
NOT_APPLICABLE = "not_applicable"  # syllabic -i, er, or an unrecognised final
NO_FORMANTS = "no_formants"        # the nucleus was too short or unvoiced
NUCLEUS_ONLY = "nucleus_only"      # measured, but the final is not a single vowel
MEASURED = "measured"              # measured, and the final is one steady vowel


def expected_vowel(
    initial: str, final: str, neutral: bool = False
) -> Tuple[Optional[str], Optional[Dict[str, str]], str]:
    """Return ``(nucleus vowel, its articulation, status)`` for one syllable.

    The status is the best this syllable can reach: `not_applicable` when
    there is no single vowel to point at, `nucleus_only` when the final moves
    through more than one, and `measured` when it is a plain monophthong.

    ``neutral`` marks a toneless syllable. The "e" of 的 de, 了 le, 麼 me and
    呢 ne is not the back [ɤ] of 這 zhè — an unstressed syllable centralises
    to [ə]. Same class of mistake as keying articulation off the vowel letter:
    the spelling is identical, the target is not.
    """
    final = (final or "").strip().lower()
    if not final or final == "er":
        return None, None, NOT_APPLICABLE
    if final == "i" and initial in _APICAL_INITIALS:
        return None, None, NOT_APPLICABLE
    nucleus = FINAL_NUCLEUS.get(final)
    if nucleus is None:
        return None, None, NOT_APPLICABLE
    zone = {"height": nucleus["height"], "backness": nucleus["backness"]}
    if neutral and nucleus["vowel"] == "e":
        zone = {"height": "mid", "backness": "central"}
    return nucleus["vowel"], zone, MEASURED if final in MONOPHTHONGS else NUCLEUS_ONLY


def vowel_zone(
    f1: float,
    f2: float,
    ref: Optional[Tuple[float, float]] = None,
) -> Optional[Dict[str, str]]:
    """Describe a formant pair as mouth height and tongue backness.

    ``ref`` is the speaker's own (F1, F2) centre for this recording. With it,
    the reading is relative to that speaker and therefore means the same thing
    for an adult and a child — "more open than the rest of what you just said"
    rather than "open by an adult's yardstick".

    Without ``ref`` the absolute Hz bands are used. Those are adult-shaped and
    only good enough for the single coarse sentence-level label the AI feedback
    has always printed; per-syllable callers should always pass ``ref``.
    """
    if not f1 or not f2 or f1 <= 0 or f2 <= 0:
        return None
    if ref and ref[0] > 0 and ref[1] > 0:
        # A tight band on purpose. At ±15 % almost every vowel of an ordinary
        # sentence landed inside it and the column read "mid" eleven times in
        # a row — technically true, and useless. Real vowel spaces separate by
        # far more than 8 %, so this keeps the reading informative without
        # inventing distinctions.
        height_ratio = f1 / ref[0]
        back_ratio = f2 / ref[1]
        height = "high" if height_ratio < 0.92 else "low" if height_ratio > 1.08 else "mid"
        backness = "back" if back_ratio < 0.92 else "front" if back_ratio > 1.08 else "central"
        return {"height": height, "backness": backness}
    height = "high" if f1 < 400 else "mid" if f1 < 650 else "low"
    if height == "low":
        # An open vowel's F2 says little about backness once the jaw is down,
        # so the absolute path does not pretend to read one.
        backness = "central"
    elif height == "high":
        backness = "front" if f2 > 2000 else "back"
    else:
        backness = "front" if f2 > 1800 else "central" if f2 > 1200 else "back"
    return {"height": height, "backness": backness}


