"""Unit tests for OMPAL corpus parsing and system/corpus character alignment.

These run without network access or audio: a miniature corpus is written to a
temp directory in the same shape as the real one.
"""
import json
import os
import sys
import wave

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import (
    OmpalWord,
    align_system_characters,
    corpus_status,
    load_utterances,
)


def _write_silent_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)


@pytest.fixture
def mini_corpus(tmp_path):
    """A two-utterance corpus mirroring the real files' differing shapes:
    native ratings are scalars, non-native ratings are per-rater arrays."""
    _write_silent_wav(tmp_path / "wav" / "SPEAKER01001" / "00100101.wav")
    _write_silent_wav(tmp_path / "wav" / "SPEAKER02001" / "00200101.wav")

    (tmp_path / "native_scores.json").write_text(
        json.dumps({
            "00100101": {
                "accuracy": 5, "fluency": 5, "prosody": 5,
                "text": "他很忙",
                "words": [
                    {"tone": 1, "text": ["他"]},
                    {"tone": 1, "text": ["很"]},
                    {"tone": 1, "text": ["忙"]},
                ],
            }
        }),
        encoding="utf-8",
    )
    (tmp_path / "non-native_scores-detail.json").write_text(
        json.dumps({
            "00200101": {
                "accuracy": [4, 5, 4], "fluency": [5, 4, 5], "prosody": [4, 4, 4],
                "text": "他很忙",
                "words": [
                    {"tone": ["1", "1", "1"], "text": ["他"]},
                    {"tone": ["0", "1", "1"], "text": ["很"]},
                    {"tone": ["1", "1", "1"], "text": ["忙"]},
                ],
            }
        }),
        encoding="utf-8",
    )
    return tmp_path


class TestCorpusStatus:
    def test_reports_not_downloaded_for_an_empty_directory(self, tmp_path):
        status = corpus_status(tmp_path)
        assert status["downloaded"] is False
        assert status["wav_count"] == 0

    def test_reports_downloaded_when_audio_and_scores_are_present(self, mini_corpus):
        status = corpus_status(mini_corpus)
        assert status["downloaded"] is True
        assert status["wav_count"] == 2
        assert "CC BY 4.0" in status["citation"]


class TestLoadUtterances:
    def test_loads_both_populations_and_marks_them(self, mini_corpus):
        utterances = load_utterances(mini_corpus)
        assert len(utterances) == 2
        by_id = {item.utterance_id: item for item in utterances}
        assert by_id["00100101"].is_native is True
        assert by_id["00200101"].is_native is False

    def test_takes_speaker_identity_from_the_wav_tree(self, mini_corpus):
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        assert by_id["00200101"].speaker_id == "SPEAKER02001"

    def test_normalizes_scalar_native_ratings_into_a_panel_of_one(self, mini_corpus):
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        native = by_id["00100101"]
        assert native.rater_accuracy == (5.0,)
        assert native.words[0].rater_tone_labels == (True,)

    def test_preserves_per_rater_disagreement_for_learners(self, mini_corpus):
        """The whole human-ceiling analysis depends on this not being averaged
        away: rater 1 marked 很 wrong while raters 2 and 3 marked it correct."""
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        learner = by_id["00200101"]
        assert learner.words[1].rater_tone_labels == (False, True, True)
        assert learner.rater_accuracy == (4.0, 5.0, 4.0)

    def test_mean_rating_averages_the_panel(self, mini_corpus):
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        assert by_id["00200101"].mean_rating("accuracy") == pytest.approx(13 / 3)

    def test_skips_utterances_whose_audio_is_missing(self, mini_corpus):
        (mini_corpus / "wav" / "SPEAKER02001" / "00200101.wav").unlink()
        utterances = load_utterances(mini_corpus)
        assert [item.utterance_id for item in utterances] == ["00100101"]

    def test_falls_back_to_averaged_scores_where_per_rater_detail_is_absent(
        self, mini_corpus
    ):
        """In the real corpus the per-rater detail file covers only 1,112 of
        1,768 learner WAVs while the averaged file covers all of them. Using
        detail alone silently discarded a third of the corpus."""
        _write_silent_wav(mini_corpus / "wav" / "SPEAKER02002" / "00200201.wav")
        (mini_corpus / "non-native_scores.json").write_text(
            json.dumps({
                "00200201": {
                    "accuracy": 3.67, "fluency": 4.0, "prosody": 3.33,
                    "text": "他很忙",
                    "words": [
                        {"tone": 1, "text": ["他"]},
                        {"tone": 0, "text": ["很"]},
                        {"tone": 1, "text": ["忙"]},
                    ],
                }
            }),
            encoding="utf-8",
        )
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        assert "00200201" in by_id
        fallback = by_id["00200201"]
        assert fallback.is_native is False
        # An averaged entry is a one-rater panel, which the ceiling calculation
        # excludes on its own because it uses the modal panel size.
        assert fallback.words[1].rater_tone_labels == (False,)

    def test_per_rater_detail_wins_over_the_averaged_file(self, mini_corpus):
        (mini_corpus / "non-native_scores.json").write_text(
            json.dumps({
                "00200101": {
                    "accuracy": 4.33, "fluency": 4.67, "prosody": 4.0,
                    "text": "他很忙",
                    "words": [
                        {"tone": 1, "text": ["他"]},
                        {"tone": 1, "text": ["很"]},
                        {"tone": 1, "text": ["忙"]},
                    ],
                }
            }),
            encoding="utf-8",
        )
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        # The detail file's 3-rater split survives rather than the averaged 1.
        assert by_id["00200101"].words[1].rater_tone_labels == (False, True, True)

    def test_derives_expected_tones_for_neutral_tone_detection(self, mini_corpus):
        by_id = {item.utterance_id: item for item in load_utterances(mini_corpus)}
        words = by_id["00100101"].words
        assert all(len(word.expected_tones) == len(word.text) for word in words)
        assert not words[0].has_neutral_tone  # 他 is tone 1


class TestNeutralToneFlag:
    def test_flags_a_word_containing_a_neutral_tone_character(self):
        word = OmpalWord(text="他們", expected_tones=(1, 5), rater_tone_labels=(True,))
        assert word.has_neutral_tone is True

    def test_does_not_flag_fully_toned_words(self):
        word = OmpalWord(text="很忙", expected_tones=(3, 2), rater_tone_labels=(True,))
        assert word.has_neutral_tone is False


class TestAlignSystemCharacters:
    def test_regroups_per_character_verdicts_onto_corpus_word_spans(self):
        words = (
            OmpalWord("他們", (1, 5), (True,)),
            OmpalWord("忙", (2,), (True,)),
        )
        system = [("他", True), ("們", False), ("忙", True)]
        assert align_system_characters(words, system) == [False, True]

    def test_a_multi_character_word_passes_only_when_every_character_passes(self):
        words = (OmpalWord("他們", (1, 5), (True,)),)
        assert align_system_characters(words, [("他", True), ("們", True)]) == [True]
        assert align_system_characters(words, [("他", True), ("們", False)]) == [False]

    def test_returns_none_when_the_character_sequences_disagree(self):
        """A silent misalignment would shift every label and corrupt every
        metric downstream, so a mismatch must drop the utterance loudly."""
        words = (OmpalWord("他很忙", (1, 3, 2), (True,)),)
        assert align_system_characters(words, [("他", True), ("忙", True)]) is None

    def test_returns_none_when_the_system_produced_nothing(self):
        words = (OmpalWord("他", (1,), (True,)),)
        assert align_system_characters(words, []) is None
