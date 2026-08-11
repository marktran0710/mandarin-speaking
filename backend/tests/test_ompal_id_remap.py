"""The OMPAL per-rater ID remap, and the guards that keep it honest.

656 of 1,768 learner utterances carry their per-rater annotations under an ID
that addresses no audio, because the detail file was written per annotation
session rather than per speaker. Joining literally drops a third of the corpus
from every inter-rater statistic.

The remap is derived from the data and verified against the averaged file, so
these tests cover both halves: that it recovers the right pairs, and that it
refuses rather than guesses when the relation does not hold.
"""
import json
import os
import sys
import wave

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import (
    JOIN_EXACT,
    JOIN_NATIVE_SCALAR,
    JOIN_REMAP,
    join_summary,
    load_utterances,
    remap_detail_ids,
)


def _entry(text, words, accuracy, fluency, prosody, per_rater=True):
    """One score entry, in either the per-rater or the averaged shape."""
    def value(values):
        return list(values) if per_rater else round(sum(values) / len(values), 2)

    def label(values):
        if per_rater:
            return [str(v) for v in values]
        return 1 if sum(values) * 2 > len(values) else 0

    return {
        "text": text,
        "accuracy": value(accuracy),
        "fluency": value(fluency),
        "prosody": value(prosody),
        "words": [
            {
                "text": [char],
                "phoneme_consonant": label(consonant),
                "phoneme_vowel": label(vowel),
                "tone": label(tone),
            }
            for char, consonant, vowel, tone in words
        ],
    }


WORDS = [("媽", [1, 1, 1], [1, 1, 0], [1, 0, 1]), ("好", [1, 1, 1], [1, 1, 1], [0, 0, 1])]
RATINGS = ([4, 5, 4], [5, 4, 5], [4, 4, 4])


@pytest.fixture
def corpus(tmp_path):
    """A miniature corpus with the same session-split shape as the real one.

    Speaker 001 has 31 recordings. The per-rater file annotates the first 29
    under speaker 001 and the remaining 2 under a phantom speaker 002.
    """
    root = tmp_path / "ompal"
    wav_dir = root / "wav" / "SPEAKER02001"
    wav_dir.mkdir(parents=True)
    for index in range(1, 32):
        path = wav_dir / f"002001{index:02d}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 100)

    averaged = {
        f"002001{index:02d}": _entry(f"媽好{index}", WORDS, *RATINGS, per_rater=False)
        for index in range(1, 32)
    }
    detail = {
        f"002001{index:02d}": _entry(f"媽好{index}", WORDS, *RATINGS)
        for index in range(1, 30)
    }
    # The overflow block: annotated as speaker 002, utterances 01-02, which are
    # really speaker 001's utterances 30-31.
    for offset, index in enumerate((30, 31), start=1):
        detail[f"002002{offset:02d}"] = _entry(f"媽好{index}", WORDS, *RATINGS)

    (root / "native_scores.json").write_text("{}", encoding="utf-8")
    (root / "non-native_scores.json").write_text(
        json.dumps(averaged, ensure_ascii=False), encoding="utf-8"
    )
    (root / "non-native_scores-detail.json").write_text(
        json.dumps(detail, ensure_ascii=False), encoding="utf-8"
    )
    return root, averaged, detail


class TestRemap:
    def test_recovers_the_overflow_block(self, corpus):
        _root, averaged, detail = corpus
        mapping = remap_detail_ids(detail, averaged, averaged.keys())
        assert mapping == {"00200201": "00200130", "00200202": "00200131"}

    def test_directly_addressed_annotations_are_left_alone(self, corpus):
        _root, averaged, detail = corpus
        mapping = remap_detail_ids(detail, averaged, averaged.keys())
        assert not any(key.startswith("002001") for key in mapping)

    def test_missing_audio_alone_is_not_an_error(self, corpus):
        """An annotation whose audio simply is not published, with no
        unannotated audio anywhere to pair it against, is missing data — which
        the loader has always skipped rather than treated as a join failure."""
        _root, averaged, detail = corpus
        # Every recording directly annotated, plus one annotation with no audio.
        detail = {
            key: value for key, value in detail.items() if key.startswith("002001")
        }
        averaged = {
            key: value for key, value in averaged.items() if key in detail
        }
        detail["00299901"] = _entry("孤", WORDS, *RATINGS)
        assert remap_detail_ids(detail, averaged, averaged.keys()) == {}

    def test_refuses_when_missing_audio_and_a_remap_are_mixed(self, corpus):
        """Ambiguous on purpose. With both an unpairable annotation and a real
        overflow block present, there is no way to tell which is which, so the
        join refuses instead of picking one reading."""
        _root, averaged, detail = corpus
        detail = {**detail, "00299901": _entry("孤", WORDS, *RATINGS)}
        with pytest.raises(ValueError, match="cannot pair annotation speakers"):
            remap_detail_ids(detail, averaged, averaged.keys())

    def test_refuses_when_the_annotations_disagree(self, corpus):
        """The load-bearing guard. If a corpus revision renumbers the audio,
        the remap must fail loudly rather than join the wrong ratings."""
        _root, averaged, detail = corpus
        detail = dict(detail)
        detail["00200201"] = _entry("完全不同", WORDS, *RATINGS)
        with pytest.raises(ValueError, match="disagrees with the averaged annotation"):
            remap_detail_ids(detail, averaged, averaged.keys())

    def test_refuses_when_the_speaker_blocks_do_not_line_up(self, corpus):
        _root, averaged, detail = corpus
        detail = dict(detail)
        detail["00200301"] = _entry("媽好30", WORDS, *RATINGS)
        with pytest.raises(ValueError, match="cannot pair annotation speakers"):
            remap_detail_ids(detail, averaged, averaged.keys())


class TestLoaderProvenance:
    def test_every_utterance_records_how_it_was_joined(self, corpus):
        root, _averaged, _detail = corpus
        utterances = load_utterances(root)
        summary = join_summary(utterances)
        assert summary["total"] == 31
        assert summary["by_join_source"] == {JOIN_EXACT: 29, JOIN_REMAP: 2}
        assert summary["with_per_rater_labels"] == 31

    def test_remapped_utterances_keep_the_annotation_id(self, corpus):
        root, _averaged, _detail = corpus
        by_id = {u.utterance_id: u for u in load_utterances(root)}
        remapped = by_id["00200130"]
        assert remapped.join_source == JOIN_REMAP
        assert remapped.annotation_id == "00200201"
        # And it carries a real panel, which is the whole point.
        assert len(remapped.words[0].rater_tone_labels) == 3

    def test_all_three_word_criteria_are_preserved(self, corpus):
        """Only tone has a machine counterpart, but dropping the other two
        would make the report unable to say how many human labels exist for
        criteria the system cannot assess."""
        root, _averaged, _detail = corpus
        word = load_utterances(root)[0].words[0]
        assert word.rater_tone_labels == (True, False, True)
        assert word.rater_consonant_labels == (True, True, True)
        assert word.rater_vowel_labels == (True, True, False)

    def test_native_utterances_are_marked_as_lacking_a_panel(self, tmp_path):
        root = tmp_path / "ompal"
        wav_dir = root / "wav" / "SPEAKER01001"
        wav_dir.mkdir(parents=True)
        with wave.open(str(wav_dir / "00100101.wav"), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 100)
        (root / "native_scores.json").write_text(
            json.dumps(
                {"00100101": _entry("媽好", WORDS, *RATINGS, per_rater=False)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "non-native_scores.json").write_text("{}", encoding="utf-8")
        (root / "non-native_scores-detail.json").write_text("{}", encoding="utf-8")

        utterance = load_utterances(root)[0]
        assert utterance.join_source == JOIN_NATIVE_SCALAR
        assert utterance.has_per_rater_labels is False
