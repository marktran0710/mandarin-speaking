"""Speaker-adaptive (two-pass) pitch tracking for the teacher model contour."""
import numpy as np
import pytest

from domain.speech.acoustics import extract_pitch_two_pass, speaker_pitch_range
from helpers.audio_io import write_wav

SAMPLE_RATE = 24000


def _glide_wav(path, f_start, f_end, duration=1.0, harmonics=4):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freq = f_start + (f_end - f_start) * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    pcm = sum(np.sin(h * phase) / h for h in range(1, harmonics + 1)) * 0.2
    write_wav(str(path), pcm.astype(np.float32), SAMPLE_RATE)
    return freq, t


def test_range_follows_the_speakers_own_quartiles():
    floor, ceiling = speaker_pitch_range(np.array([200.0] * 50 + [260.0] * 50))
    assert floor == pytest.approx(0.75 * 200.0)
    assert ceiling == pytest.approx(2.5 * 260.0)


def test_range_is_clamped_to_sane_bounds():
    low_floor, _ = speaker_pitch_range(np.array([70.0] * 10))
    _, high_ceiling = speaker_pitch_range(np.array([600.0] * 10))
    assert low_floor == 60.0
    assert high_ceiling == 900.0


def test_tracks_a_voiced_glide_accurately(tmp_path):
    path = tmp_path / "glide.wav"
    freq, t = _glide_wav(path, 180, 260)
    contour = extract_pitch_two_pass(str(path))

    assert len(contour) > 50
    times = np.array([point[0] for point in contour])
    tracked = np.array([point[1] for point in contour])
    truth = np.interp(times, t, freq)
    inner = (times > 0.1) & (times < 0.9)
    assert np.median(np.abs(tracked[inner] - truth[inner]) / truth[inner]) < 0.03


def test_returns_nothing_for_silence_instead_of_raising(tmp_path):
    path = tmp_path / "silence.wav"
    write_wav(str(path), np.zeros(SAMPLE_RATE // 2, dtype=np.float32), SAMPLE_RATE)
    assert extract_pitch_two_pass(str(path)) == []


def test_model_contour_uses_the_adaptive_tracker(tmp_path, monkeypatch):
    """The stored model contour is the one place a wrong octave shows up on
    screen and in the score, so it must come from the two-pass tracker."""
    import services.speech.reference_voice as reference_voice

    path = tmp_path / "teacher.wav"
    _glide_wav(path, 200, 280, duration=1.6)
    calls = []
    real = reference_voice.extract_pitch_two_pass
    monkeypatch.setattr(reference_voice, "extract_pitch_two_pass", lambda *a, **k: calls.append(1) or real(*a, **k))

    contour = reference_voice.extract_sentence_model_contour(str(path), "我想喝水。")

    assert calls, "the model contour did not go through extract_pitch_two_pass"
    assert contour["tokens"]
