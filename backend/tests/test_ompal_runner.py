"""Unit tests for the OMPAL scoring job.

A fake analyzer stands in for Praat so these run in milliseconds without audio.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from benchmarking.ompal_runner import (
    flatten_characters,
    load_scored,
    run_scoring,
    score_utterance,
)


def make_utterance(utterance_id="00200101", text="他很忙"):
    return OmpalUtterance(
        utterance_id=utterance_id,
        speaker_id="SPEAKER02001",
        is_native=False,
        text=text,
        wav_path=Path("/nonexistent") / f"{utterance_id}.wav",
        words=tuple(OmpalWord(char, (1,), (True,)) for char in text),
        rater_accuracy=(4.0,),
        rater_fluency=(4.0,),
        rater_prosody=(4.0,),
    )


def fake_analyzer(scores=(80.0, 50.0, 90.0), text="他很忙", tone_accuracy=73.0, fluency=68.0):
    """Build an analyzer returning the same 10-tuple shape as analyze_all."""

    def analyzer(_path, _transcription):
        word_prosody = [
            {
                "token": text,
                "syllables": [
                    {"char": char, "score": score}
                    for char, score in zip(text, scores)
                ],
            }
        ]
        return (
            [], {}, 3.0, fluency, {}, word_prosody, 2, tone_accuracy, "", {},
        )

    return analyzer


class TestFlattenCharacters:
    def test_flattens_syllables_across_words(self):
        word_prosody = [
            {"syllables": [{"char": "他", "score": 80}, {"char": "們", "score": 40}]},
            {"syllables": [{"char": "忙", "score": 90}]},
        ]
        assert flatten_characters(word_prosody) == [
            {"char": "他", "score": 80.0},
            {"char": "們", "score": 40.0},
            {"char": "忙", "score": 90.0},
        ]

    def test_returns_empty_when_no_syllables_were_produced(self):
        assert flatten_characters([{"token": "abc", "syllables": []}]) == []

    def test_tolerates_missing_syllable_fields(self):
        assert flatten_characters([{}]) == []


class TestScoreUtterance:
    def test_records_scores_not_pass_fail_so_thresholds_stay_adjustable(self):
        """Storing raw scores is what lets the report threshold move without
        re-running Praat over the whole corpus."""
        record = score_utterance(make_utterance(), fake_analyzer())
        assert [c["score"] for c in record["characters"]] == [80.0, 50.0, 90.0]
        assert record["system_tone_accuracy"] == 73.0
        assert record["system_fluency"] == 68.0
        assert record["error"] is None

    def test_passes_the_reference_text_so_no_asr_is_involved(self):
        seen = {}

        def analyzer(path, transcription):
            seen["path"] = path
            seen["transcription"] = transcription
            return fake_analyzer()(path, transcription)

        score_utterance(make_utterance(text="他很忙"), analyzer)
        assert seen["transcription"] == "他很忙"

    def test_records_an_analyzer_failure_instead_of_raising(self):
        def broken(_path, _transcription):
            raise RuntimeError("could not read wav")

        record = score_utterance(make_utterance(), broken)
        assert record["error"] == "could not read wav"
        assert record["characters"] == []

    def test_flags_an_utterance_that_produced_no_character_scores(self):
        """A data failure must never become a zero pronunciation score."""

        def empty(_path, _transcription):
            return ([], {}, 0.0, 0.0, {}, [], 0, 0.0, "", {})

        record = score_utterance(make_utterance(), empty)
        assert "no per-character tone scores" in record["error"]


class TestRunScoring:
    def test_writes_one_json_line_per_utterance(self, tmp_path):
        results = tmp_path / "scored.jsonl"
        utterances = [make_utterance("001"), make_utterance("002")]
        summary = run_scoring(utterances, results, analyzer=fake_analyzer())
        assert summary["scored"] == 2
        assert len(results.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_resumes_instead_of_rescoring_completed_utterances(self, tmp_path):
        results = tmp_path / "scored.jsonl"
        run_scoring([make_utterance("001")], results, analyzer=fake_analyzer())
        summary = run_scoring(
            [make_utterance("001"), make_utterance("002")],
            results,
            analyzer=fake_analyzer(),
        )
        assert summary["skipped"] == 1
        assert summary["scored"] == 1

    def test_stops_promptly_when_cancellation_is_requested(self, tmp_path):
        results = tmp_path / "scored.jsonl"
        utterances = [make_utterance(f"{index:03d}") for index in range(10)]
        summary = run_scoring(
            utterances, results, analyzer=fake_analyzer(), should_cancel=lambda: True
        )
        assert summary["scored"] == 0

    def test_reports_progress_as_it_goes(self, tmp_path):
        results = tmp_path / "scored.jsonl"
        seen = []
        run_scoring(
            [make_utterance("001"), make_utterance("002")],
            results,
            analyzer=fake_analyzer(),
            on_progress=lambda done, total, failed: seen.append((done, total)),
        )
        assert seen == [(1, 2), (2, 2)]

    def test_counts_failures_separately_from_successes(self, tmp_path):
        results = tmp_path / "scored.jsonl"

        def sometimes_broken(path, transcription):
            if "002" in str(path):
                raise RuntimeError("bad file")
            return fake_analyzer()(path, transcription)

        summary = run_scoring(
            [make_utterance("001"), make_utterance("002")],
            results,
            analyzer=sometimes_broken,
        )
        assert summary == {"scored": 1, "failed": 1, "skipped": 0, "total": 2}


class TestLoadScored:
    def test_returns_empty_for_a_missing_file(self, tmp_path):
        assert load_scored(tmp_path / "absent.jsonl") == []

    def test_discards_only_a_truncated_trailing_line(self, tmp_path):
        """A crash mid-write leaves one partial line; the completed rows before
        it are still valid and must survive."""
        results = tmp_path / "scored.jsonl"
        results.write_text(
            json.dumps({"utterance_id": "001"}) + "\n" + '{"utterance_id": "00',
            encoding="utf-8",
        )
        assert load_scored(results) == [{"utterance_id": "001"}]
