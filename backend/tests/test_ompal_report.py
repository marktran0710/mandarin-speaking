"""Unit tests for the OMPAL agreement report."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from benchmarking.ompal_report import PRODUCTION_THRESHOLD, build_report


def utterance(
    utterance_id="00200101",
    speaker_id="SPEAKER02001",
    is_native=False,
    words=(("他", 1, (True,)), ("忙", 2, (True,))),
    accuracy=(4.0,),
    fluency=(4.0,),
):
    return OmpalUtterance(
        utterance_id=utterance_id,
        speaker_id=speaker_id,
        is_native=is_native,
        text="".join(word[0] for word in words),
        wav_path=Path(f"/tmp/{utterance_id}.wav"),
        words=tuple(
            OmpalWord(text=text, expected_tones=(tone,), rater_tone_labels=labels)
            for text, tone, labels in words
        ),
        rater_accuracy=accuracy,
        rater_fluency=fluency,
        rater_prosody=(4.0,),
    )


def scored(
    utterance_id="00200101",
    scores=(80.0, 80.0),
    tone_accuracy=75.0,
    fluency=70.0,
    error=None,
    chars="他忙",
):
    return {
        "utterance_id": utterance_id,
        "speaker_id": "SPEAKER02001",
        "is_native": False,
        "system_tone_accuracy": tone_accuracy,
        "system_fluency": fluency,
        "characters": [
            {"char": char, "score": score} for char, score in zip(chars, scores)
        ],
        "error": error,
    }


class TestThresholdSensitivity:
    def test_threshold_changes_the_verdict_without_rescoring(self):
        """Storing raw scores means the slider recomputes from the same data."""
        items = [utterance()]
        rows = [scored(scores=(60.0, 60.0))]

        lenient = build_report(items, rows, threshold=50.0)
        strict = build_report(items, rows, threshold=70.0)

        assert lenient["pass_fail_agreement"]["true_positive"] == 2
        assert strict["pass_fail_agreement"]["false_negative"] == 2

    def test_defaults_to_the_shipped_production_threshold(self):
        report = build_report([utterance()], [scored()])
        assert report["benchmark_protocol"]["threshold"] == PRODUCTION_THRESHOLD


class TestExclusions:
    def test_excludes_and_counts_neutral_tone_words(self):
        """Our scorer has no T1-T4 shape for neutral tone, so those words
        cannot be fairly judged and must be reported as excluded, not hidden."""
        items = [utterance(words=(("他", 1, (True,)), ("們", 5, (True,))))]
        rows = [scored(chars="他們")]
        report = build_report(items, rows)
        assert report["exclusions"]["neutral_tone"] == 1
        assert report["pass_fail_agreement"]["n"] == 1

    def test_excludes_and_counts_analyzer_errors(self):
        report = build_report([utterance()], [scored(error="unreadable wav")])
        assert report["exclusions"]["analyzer_error"] == 1
        assert report["pass_fail_agreement"] == {"n": 0}

    def test_excludes_and_counts_alignment_mismatches(self):
        """A misalignment would shift every label, so the utterance is dropped
        and counted rather than silently corrupting the metrics."""
        mismatched = scored()
        mismatched["characters"] = [{"char": "很", "score": 80.0}]
        report = build_report([utterance()], [mismatched])
        assert report["exclusions"]["alignment_mismatch"] == 1


class TestHumanCeilingAndVerdict:
    def test_reports_the_ceiling_from_learner_rater_panels(self):
        items = [
            utterance(
                utterance_id="001",
                words=(("他", 1, (True, True, False)), ("忙", 2, (True, True, True))),
            ),
            utterance(
                utterance_id="002",
                words=(("他", 1, (False, False, False)), ("忙", 2, (True, False, True))),
            ),
        ]
        rows = [scored("001"), scored("002")]
        report = build_report(items, rows)
        assert report["human_ceiling"]["rater_count"] == 3
        assert report["human_ceiling"]["item_count"] == 4

    def test_verdict_compares_system_against_the_ceiling(self):
        """Raters mostly agree (one dissent on 他), giving a positive ceiling;
        the system tracks them, so a real ratio can be formed."""
        items = [
            utterance(
                utterance_id=f"{index:03d}",
                words=(("他", 1, (True, True, False)), ("忙", 2, (False, False, False))),
            )
            for index in range(6)
        ]
        rows = [scored(f"{index:03d}", scores=(80.0, 20.0)) for index in range(6)]
        report = build_report(items, rows)
        verdict = report["verdict"]
        assert verdict["human_ceiling_kappa"] > 0
        assert verdict["ratio"] is not None
        assert verdict["level"] in {"at_human_level", "approaching_human", "below_human"}
        assert "kappa" in verdict["summary"]

    def test_a_non_positive_ceiling_is_reported_as_measured_not_missing(self):
        """Systematically opposed raters produce a negative ceiling. That is a
        finding about the panel, not a tooling failure, and saying "could not
        be computed" would blame the tool for what the data actually shows."""
        items = [
            utterance(
                utterance_id=f"{index:03d}",
                words=(("他", 1, (True, True, False)), ("忙", 2, (False, False, True))),
            )
            for index in range(6)
        ]
        rows = [scored(f"{index:03d}", scores=(80.0, 20.0)) for index in range(6)]
        verdict = build_report(items, rows)["verdict"]
        assert verdict["level"] == "no_reliable_ceiling"
        assert verdict["human_ceiling_kappa"] < 0
        assert verdict["ratio"] is None
        assert "did not agree with each other beyond chance" in verdict["summary"]

    def test_verdict_is_unknown_when_the_ceiling_cannot_be_computed(self):
        """A single-rater panel has no inter-rater agreement to measure."""
        report = build_report([utterance()], [scored()])
        assert report["verdict"]["level"] == "unknown"


class TestPopulationSplit:
    def test_separates_natives_from_learners(self):
        items = [
            utterance(utterance_id="001", is_native=False),
            utterance(utterance_id="002", speaker_id="SPEAKER01001", is_native=True),
        ]
        rows = [scored("001"), scored("002")]
        report = build_report(items, rows)
        assert report["by_population"]["learners"]["n"] == 2
        assert report["by_population"]["natives"]["n"] == 2


class TestSentenceCorrelation:
    def test_reports_rank_correlation_but_never_a_fabricated_error(self):
        """A 1-5 rubric and a 0-100 score share no unit; an "average error"
        between them would look precise while meaning nothing."""
        items = [
            utterance(utterance_id=f"{i:03d}", accuracy=(float(i),), fluency=(float(i),))
            for i in range(1, 6)
        ]
        rows = [
            scored(f"{i:03d}", tone_accuracy=i * 20.0, fluency=i * 20.0)
            for i in range(1, 6)
        ]
        report = build_report(items, rows)
        assert report["score_agreement"]["accuracy"]["spearman_correlation"] == pytest.approx(1.0)
        assert report["score_agreement"]["mean_absolute_error"] is None
        assert "1-5" in report["score_agreement"]["note"]


class TestReleaseGate:
    def test_marks_mean_absolute_error_not_applicable_rather_than_failing_silently(self):
        report = build_report([utterance()], [scored()])
        gate = report["release_gate"]
        mae = next(c for c in gate["checks"] if c["name"] == "mean_absolute_error")
        assert mae["applicable"] is False
        assert "Not applicable" in mae["detail"]
        assert gate["complete"] is False

    def test_reports_the_other_criteria_as_normal_checks(self):
        report = build_report([utterance()], [scored()])
        names = {check["name"] for check in report["release_gate"]["checks"]}
        assert {"accuracy", "cohen_kappa", "speaker_count", "tone_1_f1"} <= names


class TestProvenance:
    def test_carries_citation_caveat_and_threshold_warning(self):
        protocol = build_report([utterance()], [scored()])["benchmark_protocol"]
        assert "CC BY 4.0" in protocol["citation"]
        assert "French-L1" in protocol["population_caveat"]
        assert "leakage" in protocol["threshold_warning"]

    def test_counts_recordings_and_speakers_actually_scored(self):
        items = [
            utterance(utterance_id="001", speaker_id="SPEAKER02001"),
            utterance(utterance_id="002", speaker_id="SPEAKER02002"),
        ]
        report = build_report(items, [scored("001"), scored("002")])
        assert report["benchmark_protocol"]["recording_count"] == 2
        assert report["benchmark_protocol"]["speaker_count"] == 2


class TestAudit:
    def test_lists_disagreements_for_teacher_review(self):
        items = [utterance()]
        rows = [scored(scores=(80.0, 10.0))]
        report = build_report(items, rows)
        assert report["audit"]["disagreement_count"] == 1
        assert report["audit"]["disagreements"][0]["word"] == "忙"

    def test_truncates_a_long_disagreement_list(self):
        items = [utterance(utterance_id=f"{i:03d}") for i in range(10)]
        rows = [scored(f"{i:03d}", scores=(10.0, 10.0)) for i in range(10)]
        report = build_report(items, rows, audit_limit=5)
        assert report["audit"]["disagreement_count"] == 20
        assert len(report["audit"]["disagreements"]) == 5
        assert report["audit"]["truncated"] is True
