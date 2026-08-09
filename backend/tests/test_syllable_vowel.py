"""Per-syllable vowel readout.

The tone gate tells a student which way to move their pitch; nothing below the
tone told them anything about the sounds themselves. These tests pin the vowel
*measurement* that now rides alongside each syllable — and, just as much, pin
the places it must stay silent.

The silences matter because the first version of this code did grade vowels,
and got it wrong in the most damaging direction: a synthesised /a/ sitting
exactly on its canonical formants was marked incorrect, because the two-vowel
speaker normalisation it depended on had been dragged off by the other
syllable's noisy reading. Hence `test_no_verdict_is_ever_attached`, which is
the load-bearing test in this file.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import estimate_word_prosody
from vowel_analysis import (
    FINAL_NUCLEUS,
    MEASURED,
    NO_FORMANTS,
    NOT_APPLICABLE,
    NOT_MEASURED,
    NUCLEUS_ONLY,
    expected_vowel,
    is_plausible,
    vowel_zone,
)

try:
    import parselmouth
except ImportError:  # pragma: no cover - exercised only where Praat is absent
    parselmouth = None


# ── The F1/F2 → articulatory zone read ────────────────────────────────────


@pytest.mark.parametrize(
    "f1,f2,height,backness",
    [
        (300, 2200, "high", "front"),   # 你 nǐ
        (300, 1500, "high", "back"),    # 書 shū
        (500, 1900, "mid", "front"),    # 姐 jiě
        (500, 1500, "mid", "central"),  # 的 de
        (500, 1000, "mid", "back"),     # 我 wǒ
        (800, 1300, "low", "central"),  # 啊 ā
    ],
)
def test_vowel_zone_absolute_bands(f1, f2, height, backness):
    """The absolute path must keep reproducing the sentence-level label that
    classify_vowel_quality has always printed — it now shares this function."""
    assert vowel_zone(f1, f2) == {"height": height, "backness": backness}


def test_vowel_zone_is_empty_without_formants():
    assert vowel_zone(0, 0) is None
    assert vowel_zone(500, 0) is None


def test_vowel_zone_reads_relative_to_the_speaker():
    """The same absolute formants mean different things for different voices.

    600/1500 Hz is a mid-central vowel by the adult bands, but for a speaker
    whose own centre sits at 900/2000 it is high and back. The per-syllable
    readout follows the speaker, which is what makes it usable for a child.
    """
    assert vowel_zone(600, 1500) == {"height": "mid", "backness": "central"}
    assert vowel_zone(600, 1500, ref=(900.0, 2000.0)) == {
        "height": "high",
        "backness": "back",
    }


# ── Which syllables have a vowel to point at ──────────────────────────────


@pytest.mark.parametrize(
    "initial,final,vowel,status",
    [
        ("m", "a", "a", MEASURED),       # 媽
        ("n", "i", "i", MEASURED),       # 你
        ("sh", "u", "u", MEASURED),      # 書
        ("n", "v", "v", MEASURED),       # 女
        ("h", "ao", "a", NUCLEUS_ONLY),  # 好 — the target moves
        ("z", "ai", "a", NUCLEUS_ONLY),  # 在
        ("f", "an", "a", NUCLEUS_ONLY),  # 飯
        ("ch", "i", None, NOT_APPLICABLE),  # 吃 — apical -i, not the vowel /i/
        ("zh", "i", None, NOT_APPLICABLE),
        ("", "er", None, NOT_APPLICABLE),   # 兒 — rhotic
    ],
)
def test_expected_vowel_marks_what_can_be_read(initial, final, vowel, status):
    assert expected_vowel(initial, final)[0] == vowel
    assert expected_vowel(initial, final)[2] == status


@pytest.mark.parametrize(
    "initial,final,height,backness",
    [
        # Written "e" is three different vowels, and an earlier version of the
        # table called all of them back — telling a learner to pull their
        # tongue back for 美, which is the opposite of correct.
        ("zh", "e", "mid", "back"),      # 這 — [ɤ], genuinely back
        ("m", "ei", "mid", "front"),     # 美 — [e], front
        ("j", "ie", "mid", "front"),     # 姐
        ("sh", "en", "mid", "central"),  # 什 — [ə]
        ("h", "en", "mid", "central"),   # 很
        ("n", "i", "high", "front"),     # 你
        ("m", "a", "low", "central"),    # 媽
        ("sh", "u", "high", "back"),     # 書
    ],
)
def test_expected_zone_follows_the_final_not_the_letter(initial, final, height, backness):
    _, zone, _ = expected_vowel(initial, final)
    assert zone == {"height": height, "backness": backness}


def test_a_neutral_tone_e_centralises():
    """麼 / 的 / 了 are unstressed: their "e" is [ə], not 這's back [ɤ]."""
    _, stressed, _ = expected_vowel("m", "e")
    _, unstressed, _ = expected_vowel("m", "e", neutral=True)
    assert stressed == {"height": "mid", "backness": "back"}
    assert unstressed == {"height": "mid", "backness": "central"}


@pytest.mark.parametrize(
    "f1,f2,plausible",
    [
        (520.0, 1053.0, True),
        (338.9, 2885.7, True),
        # The real failure this guard was written for: 這 in a student
        # recording measured F1 = 1754 Hz, 3.6x that speaker's own median.
        # No human vowel has an F1 that high; the tracker had locked onto the
        # wrong pole behind the retroflex zh-.
        (1754.3, 2361.7, False),
        (1200.0, 900.0, False),   # F2 below F1 — impossible in a vowel
        (0.0, 1500.0, False),
        (500.0, 0.0, False),
        (100.0, 1500.0, False),   # below any human F1
        (500.0, 5000.0, False),   # beyond any human F2
    ],
)
def test_is_plausible_rejects_tracker_failures(f1, f2, plausible):
    assert is_plausible(f1, f2) is plausible


def test_every_pypinyin_final_is_covered():
    """A final missing from the table would silently become not_applicable,
    quietly blanking the column for whole classes of characters."""
    from pypinyin import Style, pinyin
    from pypinyin.constants import PINYIN_DICT

    unhandled = set()
    for code in PINYIN_DICT:
        final = pinyin(chr(code), style=Style.FINALS, strict=True)[0][0]
        if not final or final == "er":
            continue
        if expected_vowel("m", final)[2] == NOT_APPLICABLE:
            unhandled.add(final)
    assert unhandled == set()


def test_every_final_carries_a_full_articulation():
    for final, nucleus in FINAL_NUCLEUS.items():
        assert nucleus["vowel"] in {"a", "o", "e", "i", "u", "v"}, final
        assert nucleus["height"] in {"high", "mid", "low"}, final
        assert nucleus["backness"] in {"front", "central", "back"}, final


# ── Wiring into estimate_word_prosody ─────────────────────────────────────


def _contour(pitch_pattern, base_hz=220.0, spread_hz=160.0, num_points=60, duration=0.8):
    x = np.linspace(0, 1, len(pitch_pattern))
    shape = np.interp(np.linspace(0, 1, num_points), x, pitch_pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), freqs.tolist()))


_ZAIJIA = [0.95, 0.75, 0.55, 0.35, 0.79, 0.75, 0.78, 0.74]


def test_no_audio_means_no_vowel_claim():
    """Callers that hand in only a pitch contour get an honest blank.

    The word-drill path and every existing test call estimate_word_prosody
    without audio; none of them may start seeing invented vowel data.
    """
    segments = estimate_word_prosody(_contour(_ZAIJIA), "在家")
    syllables = segments[0]["syllables"]
    assert [s["vowel_status"] for s in syllables] == [NOT_MEASURED, NOT_MEASURED]
    assert all("f1" not in s for s in syllables)
    # The tone verdict is untouched by any of this.
    assert [s["char"] for s in syllables] == ["在", "家"]
    assert all(s["passed"] is not None for s in syllables)


# ── End-to-end against synthesised speech ─────────────────────────────────


def _vowel_segment(f1, f2, duration, sample_rate=16000, f0=120.0):
    """A source-filter vowel: a glottal pulse train through two resonances.

    Real enough for Praat's Burg LPC to recover formants, which is exactly the
    measurement path under test — synthesising a plain sine would test
    nothing, because a sine has no formants to find.
    """
    samples = int(duration * sample_rate)
    signal = np.zeros(samples)
    period = int(sample_rate / f0)
    time = np.arange(samples) / sample_rate
    for formant, amplitude in ((f1, 1.0), (f2, 0.4)):
        resonance = amplitude * np.exp(-math.pi * 90.0 * time) * np.cos(
            2 * math.pi * formant * time
        )
        pulses = np.zeros(samples)
        pulses[::period] = 1.0
        signal += np.convolve(pulses, resonance)[:samples]
    peak = np.max(np.abs(signal)) or 1.0
    return signal / peak * 0.8


def _two_syllable_sound(first, second, sample_rate=16000, duration=0.4):
    gap = np.zeros(int(0.05 * sample_rate))
    audio = np.concatenate(
        [
            _vowel_segment(*first, duration, sample_rate),
            gap,
            _vowel_segment(*second, duration, sample_rate),
        ]
    )
    return parselmouth.Sound(audio, sampling_frequency=sample_rate)


@pytest.mark.skipif(parselmouth is None, reason="Parselmouth not installed")
def test_measures_each_syllable_against_its_own_audio():
    """你媽 — a close front vowel then an open one — must read as two
    different vowels, because they were spoken as two different vowels."""
    sound = _two_syllable_sound((300.0, 2300.0), (850.0, 1300.0))
    segments = estimate_word_prosody(
        _contour([0.6, 0.4, 0.3, 0.7, 0.8, 0.8], duration=float(sound.get_total_duration())),
        "你媽",
        sound=sound,
    )
    syllables = [s for segment in segments for s in segment["syllables"]]
    assert [s["char"] for s in syllables] == ["你", "媽"]
    assert [s["expected_vowel"] for s in syllables] == ["i", "a"]
    assert [s["vowel_status"] for s in syllables] == [MEASURED, MEASURED]

    for syllable in syllables:
        assert syllable["f1"] > 0 and syllable["f2"] > 0
        assert syllable["measured_zone"] is not None

    # The open vowel must measure the higher F1 and the lower F2. This is the
    # one acoustic claim the whole feature rests on: if it fails, the slicing
    # is measuring the wrong part of the audio and every number shown to a
    # student is noise.
    close, open_ = syllables
    assert open_["f1"] > close["f1"]
    assert open_["f2"] < close["f2"]

    # And the relative reading has to follow: open where the jaw drops.
    assert close["measured_zone"]["height"] == "high"
    assert open_["measured_zone"]["height"] == "low"


@pytest.mark.skipif(parselmouth is None, reason="Parselmouth not installed")
def test_no_verdict_is_ever_attached():
    """A vowel produced exactly on target must not be graded — because the
    grade cannot be trusted, in either direction, from an utterance this
    short. Reporting the measurement is the whole promise.
    """
    sound = _two_syllable_sound((300.0, 2300.0), (850.0, 1300.0))
    segments = estimate_word_prosody(
        _contour([0.6, 0.4, 0.3, 0.7, 0.8, 0.8], duration=float(sound.get_total_duration())),
        "你媽",
        sound=sound,
    )
    for segment in segments:
        for syllable in segment["syllables"]:
            assert "vowel_match" not in syllable
            assert "measured_vowel" not in syllable
        # The word-level pass verdict still comes from the tone alone.
        assert segment["passed"] in (True, False, None)


@pytest.mark.skipif(parselmouth is None, reason="Parselmouth not installed")
def test_silence_reports_no_formants_rather_than_a_number():
    """Nothing to measure has to say so. Whatever the tracker returns for
    silence is not a description of a vowel the student produced."""
    sample_rate = 16000
    sound = parselmouth.Sound(
        np.zeros(int(0.9 * sample_rate)), sampling_frequency=sample_rate
    )
    segments = estimate_word_prosody(
        _contour([0.6, 0.4, 0.3, 0.7, 0.8, 0.8], duration=0.9),
        "你媽",
        sound=sound,
    )
    syllables = [s for segment in segments for s in segment["syllables"]]
    for syllable in syllables:
        assert syllable["vowel_status"] == NO_FORMANTS
        assert syllable["measured_zone"] is None
        assert syllable["f1"] == 0.0
        # The target is still worth showing — it comes from the pinyin, not
        # from the audio.
        assert syllable["expected_zone"] is not None


@pytest.mark.skipif(parselmouth is None, reason="Parselmouth not installed")
def test_apical_i_is_never_read_as_the_vowel_i():
    """吃 is written chi but holds no /i/. Measuring it would produce a real
    number attached to a target that does not exist."""
    sound = _two_syllable_sound((500.0, 1400.0), (850.0, 1300.0))
    segments = estimate_word_prosody(
        _contour([0.8, 0.8, 0.7, 0.5, 0.4, 0.3], duration=float(sound.get_total_duration())),
        "吃飯",
        sound=sound,
    )
    syllables = [s for segment in segments for s in segment["syllables"]]
    chi, fan = syllables
    assert chi["char"] == "吃"
    assert chi["vowel_status"] == NOT_APPLICABLE
    assert chi["expected_vowel"] is None
    assert chi["measured_zone"] is None
    # 飯 is a nasal final: measured, but reported as a nucleus only.
    assert fan["vowel_status"] == NUCLEUS_ONLY
    assert fan["expected_vowel"] == "a"
