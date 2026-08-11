"""Error-analysis exports and the validation CLI.

These cover the parts a research reader depends on: that the exported tables
agree with the report they accompany, that false acceptance and false rejection
are counted from the stated denominators, and that criteria the system cannot
assess are never given a fabricated value.
"""
import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.error_analysis import (
    FALSE_ACCEPTANCE,
    FALSE_REJECTION,
    FIELDNAMES,
    NA,
    build_rows,
    export,
    summarize,
)
from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from benchmarking.stats import binary_agreement, error_rates


def _utterance(utterance_id, words, tone_panels):
    return OmpalUtterance(
        utterance_id=utterance_id,
        speaker_id="SPEAKER02001",
        is_native=False,
        text="".join(words),
        wav_path=Path(f"/corpus/{utterance_id}.wav"),
        words=tuple(
            OmpalWord(
                text=char,
                expected_tones=(tone,),
                rater_tone_labels=panel,
                rater_consonant_labels=(True, True, True),
                rater_vowel_labels=(True, True, True),
            )
            for char, tone, panel in zip(words, (1, 2), tone_panels)
        ),
        rater_accuracy=(4.0, 4.0, 5.0),
        rater_fluency=(4.0, 4.0, 4.0),
        rater_prosody=(4.0, 4.0, 4.0),
    )


def _scored(utterance_id, scores):
    return {
        "utterance_id": utterance_id,
        "speaker_id": "SPEAKER02001",
        "is_native": False,
        "system_tone_accuracy": 60.0,
        "system_fluency": 70.0,
        "characters": [
            {"char": char, "score": score, "judged": True}
            for char, score in scores
        ],
        "error": None,
    }


# 媽: humans say correct, system scores 20 -> false rejection.
# 好: humans say incorrect, system scores 90 -> false acceptance.
UTTERANCES = [
    _utterance(
        "00200101",
        ("媽", "好"),
        [(True, True, True), (False, False, True)],
    )
]
SCORED = [_scored("00200101", [("媽", 20.0), ("好", 90.0)])]


class TestErrorRates:
    def test_denominators_are_the_human_labels_not_the_total(self):
        rates = error_rates(true_positive=4, true_negative=1, false_positive=3, false_negative=2)
        # False acceptance is out of everything humans marked incorrect.
        assert rates["false_acceptance_denominator"] == 4
        assert rates["false_acceptance_rate"] == pytest.approx(3 / 4)
        # False rejection is out of everything humans marked correct.
        assert rates["false_rejection_denominator"] == 6
        assert rates["false_rejection_rate"] == pytest.approx(2 / 6)

    def test_specificity_is_reported_alongside_recall(self):
        metrics = binary_agreement([True, False, True, False], [True, True, False, False])
        assert metrics["recall"] == pytest.approx(0.5)
        assert metrics["specificity"] == pytest.approx(0.5)


class TestRows:
    def test_classifies_the_two_error_directions(self):
        rows = build_rows(UTTERANCES, SCORED, threshold=58.0)
        by_word = {row["word"]: row for row in rows}
        assert by_word["媽"]["error_type"] == FALSE_REJECTION
        assert by_word["媽"]["human_majority_tone_correct"] == 1
        assert by_word["媽"]["system_tone_correct"] == 0
        assert by_word["好"]["error_type"] == FALSE_ACCEPTANCE
        assert by_word["好"]["human_majority_tone_correct"] == 0
        assert by_word["好"]["system_tone_correct"] == 1

    def test_individual_rater_labels_are_preserved(self):
        rows = build_rows(UTTERANCES, SCORED, threshold=58.0)
        by_word = {row["word"]: row for row in rows}
        assert by_word["媽"]["individual_rater_labels"] == "111"
        assert by_word["好"]["individual_rater_labels"] == "001"

    def test_unavailable_features_are_na_not_zero(self):
        """A zero would be read as a measurement. These are simply not stored
        by the cached scoring and must say so."""
        row = build_rows(UTTERANCES, SCORED, threshold=58.0)[0]
        for field in ("duration_seconds", "f0_mean", "f0_slope", "alignment_score"):
            assert row[field] == NA, field

    def test_neutral_tone_words_are_excluded(self):
        neutral = _utterance("00200102", ("的", "好"), [(True,) * 3, (True,) * 3])
        object.__setattr__(
            neutral.words[0], "expected_tones", (5,)
        )
        rows = build_rows([neutral], [_scored("00200102", [("的", 90.0), ("好", 90.0)])],
                          threshold=58.0)
        assert [row["word"] for row in rows] == ["好"]


class TestSummary:
    def test_breaks_errors_down_by_tone_and_score_distance(self):
        rows = build_rows(UTTERANCES, SCORED, threshold=58.0)
        summary = summarize(rows, 58.0)
        assert summary["n"] == 2
        assert summary["error_counts"][FALSE_REJECTION] == 1
        assert summary["error_counts"][FALSE_ACCEPTANCE] == 1
        assert sum(summary["false_rejection_by_score_distance"].values()) == 1
        assert summary["most_false_rejected_words"][0][0] == "媽"

    def test_names_the_dimensions_it_cannot_break_down_by(self):
        summary = summarize(build_rows(UTTERANCES, SCORED, threshold=58.0), 58.0)
        assert "duration_bin" in summary["unavailable_dimensions"]
        assert "alignment_quality" in summary["unavailable_dimensions"]


class TestExport:
    def test_writes_the_three_tables_with_a_stable_schema(self, tmp_path):
        rows = build_rows(UTTERANCES, SCORED, threshold=58.0)
        written = export(rows, tmp_path)
        assert written == {
            "human_vs_system.csv": 2,
            "tone_false_acceptance.csv": 1,
            "tone_false_rejection.csv": 1,
        }
        with (tmp_path / "human_vs_system.csv").open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == FIELDNAMES
            exported = list(reader)
        assert {row["word"] for row in exported} == {"媽", "好"}

    def test_the_disagreement_tables_are_subsets_of_the_full_table(self, tmp_path):
        rows = build_rows(UTTERANCES, SCORED, threshold=58.0)
        export(rows, tmp_path)
        with (tmp_path / "tone_false_rejection.csv").open(encoding="utf-8") as handle:
            rejected = list(csv.DictReader(handle))
        assert [row["error_type"] for row in rejected] == [FALSE_REJECTION]


class TestCli:
    def test_refuses_to_score_implicitly_when_no_cache_exists(self, tmp_path):
        """Scoring 1,850 files is minutes of Praat. A validation run that
        silently triggered it would be a trap, so it fails with instructions."""
        from benchmarking import validation_cli

        corpus = tmp_path / "ompal"
        (corpus / "wav").mkdir(parents=True)
        with pytest.raises(SystemExit, match="No cached scoring"):
            validation_cli.run(
                corpus_root=corpus,
                scored_path=tmp_path / "missing.jsonl",
                results_dir=tmp_path / "results",
            )

    def test_summary_never_claims_the_system_is_validated(self):
        from benchmarking.validation_cli import render_summary

        empty = {"n": 0}
        text = render_summary(
            report_a={"pass_fail_agreement": empty},
            report_b={
                "pass_fail_agreement": empty,
                "benchmark_protocol": {
                    "citation": "c", "speaker_count": 0, "recording_count": 0,
                    "rated_word_count": 0, "population_caveat": "p",
                    "threshold_warning": "w",
                },
                "human_ceiling": {},
                "score_agreement": {
                    "accuracy": {"n": 0}, "fluency": {"n": 0},
                    "prosody": {"n": 0, "human_label_count": 0, "reason": "r"},
                    "note": "n",
                },
                "segmental_support": {
                    "consonant": {"human_label_count": 0, "reason": "r"},
                    "vowel": {"human_label_count": 0, "system_output": "s", "reason": "r"},
                },
                "exclusions": {},
            },
            provenance={"total": 0, "by_join_source": {}},
            error_summary={
                "by_expected_tone": {},
                "false_rejection_by_score_distance": {},
                "most_false_rejected_words": [],
                "unavailable_dimensions": {},
            },
            exports={},
            threshold=58.0,
        )
        # The disclaimer must be present, and no affirmative claim may be.
        # Compared on collapsed whitespace, since the template wraps lines.
        flat = " ".join(text.split())
        assert "not a statement that the system is validated" in flat
        for claim in (
            "The system is validated",
            "the system is validated.",
            "results validate the system",
        ):
            assert claim not in flat, claim
        assert "showed low agreement with OMPAL expert annotations" in flat
