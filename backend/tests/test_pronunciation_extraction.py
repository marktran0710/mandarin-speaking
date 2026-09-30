"""Praat-backed feature extraction, run on synthetic voiced audio."""

import pytest

from domain.pronunciation.compare import compare_utterances
from pron_audio import silent_wav, synth_wav
from services.pronunciation.extraction import (
    PIPELINE_VERSION,
    FeatureExtractionError,
    extract_utterance_features,
)

TEXT = "媽麻罵"  # three syllables: ma1 ma2 ma4


def test_one_syllable_per_script_character_with_the_measured_pitch_direction(tmp_path):
    path = synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"])
    features = extract_utterance_features(path, TEXT)
    assert [s.expected.hanzi for s in features.syllables] == list(TEXT)
    assert [s.direction for s in features.syllables] == ["flat", "rise", "fall"]
    assert all(s.voiced_ratio > 0.6 for s in features.syllables)
    assert features.alignment.fallback_used is False


def test_syllable_spans_are_ordered_contiguous_and_inside_the_recording(tmp_path):
    features = extract_utterance_features(synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"]), TEXT)
    spans = [(s.start_ms, s.end_ms) for s in features.syllables]
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
    assert 0 <= spans[0][0] and spans[-1][1] <= features.duration_ms


def test_pitch_is_stored_relative_to_the_speaker_not_in_hz(tmp_path):
    features = extract_utterance_features(synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"]), TEXT)
    values = [v for s in features.syllables for _, v in s.f0_points]
    assert all(abs(v) < 12 for v in values)
    assert abs(sorted(values)[len(values) // 2]) < 3  # centred on the speaker's median


def test_the_same_audio_always_gives_identical_features(tmp_path):
    path = synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"])
    assert extract_utterance_features(path, TEXT).to_dict() == extract_utterance_features(path, TEXT).to_dict()


def test_a_deep_voice_and_a_high_voice_compare_as_the_same_tones(tmp_path):
    low = extract_utterance_features(synth_wav(tmp_path / "lo.wav", ["flat", "rise", "fall"], base_hz=110), TEXT)
    high = extract_utterance_features(synth_wav(tmp_path / "hi.wav", ["flat", "rise", "fall"], base_hz=230), TEXT)
    comparison = compare_utterances(high, low)
    assert comparison.tone_similarity > 0.9
    assert all(not s.flags for s in comparison.syllables)


def test_a_flat_attempt_at_a_falling_tone_is_detected_end_to_end(tmp_path):
    reference = extract_utterance_features(synth_wav(tmp_path / "r.wav", ["flat", "rise", "fall"]), TEXT)
    student = extract_utterance_features(synth_wav(tmp_path / "s.wav", ["flat", "rise", "flat"]), TEXT)
    comparison = compare_utterances(student, reference)
    assert "tone_contour_too_flat" in comparison.syllables[2].flags
    assert comparison.syllables[0].flags == ()


def test_a_long_gap_is_recorded_as_a_pause_at_the_right_place(tmp_path):
    path = synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"], gaps_ms=[400, 120])
    features = extract_utterance_features(path, TEXT)
    assert [p.after_syllable for p in features.pauses] == [0]
    assert features.pauses[0].duration_ms >= 200
    assert features.articulation_ms < features.syllables[-1].end_ms - features.syllables[0].start_ms


def test_provenance_records_how_the_features_were_made(tmp_path):
    features = extract_utterance_features(synth_wav(tmp_path / "a.wav", ["flat", "rise", "fall"]), TEXT)
    assert features.provenance["pipeline_version"] == PIPELINE_VERSION
    assert features.provenance["praat_version"]
    assert features.provenance["pitch_tracker"] == "two_pass_adaptive"
    assert features.provenance["aligner"] == "energy_landmarks"


def test_silence_has_no_voiced_speech_to_measure(tmp_path):
    with pytest.raises(FeatureExtractionError) as caught:
        extract_utterance_features(silent_wav(tmp_path / "s.wav"), TEXT)
    assert caught.value.code == "no_voiced_speech"


def test_a_file_praat_cannot_read_is_reported_not_crashed(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"this is not audio")
    with pytest.raises(FeatureExtractionError) as caught:
        extract_utterance_features(str(bad), TEXT)
    assert caught.value.code == "audio_unreadable"


def test_text_with_no_han_characters_cannot_be_evaluated(tmp_path):
    with pytest.raises(FeatureExtractionError) as caught:
        extract_utterance_features(synth_wav(tmp_path / "a.wav", ["flat"]), "abc")
    assert caught.value.code == "no_syllables"
