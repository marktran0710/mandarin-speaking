"""Unit tests for the OMPAL agreement report."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from benchmarking.ompal_report import PRODUCTION_THRESHOLD, build_report


FULL = (True, True, True)      # a unanimous 3-rater panel
SPLIT = (False, True, True)    # raters disagree, majority passes


def utterance(
    utterance_id="00200101",
    speaker_id="SPEAKER02001",
    is_native=False,
    words=(("他", 1, FULL), ("忙", 2, FULL)),
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
    judged=True,
):
    return {
        "utterance_id": utterance_id,
        "speaker_id": "SPEAKER02001",
        "is_native": False,
        "system_tone_accuracy": tone_accuracy,
        "system_fluency": fluency,
        "characters": [
            {"char": char, "score": score, "judged": judged}
            for char, score in zip(chars, scores)
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
        items = [utterance(words=(("他", 1, FULL), ("們", 5, FULL)))]
        rows = [scored(chars="他們")]
        report = build_report(items, rows)
        assert report["exclusions"]["neutral_tone"] == 1
        assert report["pass_fail_agreement"]["n"] == 1

    def test_excludes_and_counts_analyzer_errors(self):
        report = build_report([utterance()], [scored(error="unreadable wav")])
        assert report["exclusions"]["analyzer_error"] == 1
        assert report["pass_fail_agreement"] == {"n": 0}

    def test_excludes_syllables_the_analyzer_declined_to_judge(self):
        """The analyzer writes a placeholder 0.0 with passed=None when a
        segment had too few pitch frames. Scoring that as a failure blamed the
        system for ~19% of syllables it never actually judged -- and teachers
        passed 86% of them, so it was pure injected noise."""
        report = build_report([utterance()], [scored(scores=(0.0, 0.0), judged=False)])
        assert report["exclusions"]["unjudged_by_analyzer"] == 2
        assert report["per_rater_agreement"]["n"] == 0

    def test_a_judged_zero_score_still_counts_as_a_failure(self):
        """Only the placeholder is excluded; a genuinely measured 0.0 is a
        real failing score and must still be held against the system."""
        report = build_report([utterance()], [scored(scores=(0.0, 0.0), judged=True)])
        assert "unjudged_by_analyzer" not in report["exclusions"]
        assert report["per_rater_agreement"]["n"] == 2

    def test_rejects_legacy_records_that_predate_the_judged_flag(self):
        """Without the flag, placeholder zeros are indistinguishable from real
        failures, so such a record cannot be interpreted safely at all."""
        legacy = scored()
        for entry in legacy["characters"]:
            del entry["judged"]
        report = build_report([utterance()], [legacy])
        assert report["exclusions"]["legacy_record_without_judged_flag"] == 1
        assert report["per_rater_agreement"]["n"] == 0

    def test_excludes_words_without_a_full_rater_panel(self):
        """Averaging kappa over differently-sized panels is not a single
        interpretable quantity, so partial panels are dropped and counted."""
        items = [utterance(words=(("他", 1, (True,)), ("忙", 2, FULL)))]
        report = build_report(items, [scored()])
        assert report["exclusions"]["incomplete_rater_panel"] == 1
        assert report["per_rater_agreement"]["n"] == 1

    def test_excludes_and_counts_alignment_mismatches(self):
        """A misalignment would shift every label, so the utterance is dropped
        and counted rather than silently corrupting the metrics."""
        mismatched = scored()
        mismatched["characters"] = [{"char": "很", "score": 80.0}]
        report = build_report([utterance()], [mismatched])
        assert report["exclusions"]["alignment_mismatch"] == 1


class TestHumanCeilingAndVerdict:
    def test_reports_the_ceiling_from_rater_panels(self):
        items = [
            utterance(utterance_id="001", words=(("他", 1, SPLIT), ("忙", 2, FULL))),
            utterance(utterance_id="002", words=(("他", 1, FULL), ("忙", 2, SPLIT))),
        ]
        report = build_report(items, [scored("001"), scored("002")])
        assert report["human_ceiling"]["rater_count"] == 3
        assert report["human_ceiling"]["item_count"] == 4

    def test_headline_is_agreement_with_the_rater_majority(self):
        """Protocol change 2026-08-06: the headline compares against the
        3-rater majority. A perfect system scores 1.0 against that label, so
        the target is reachable rather than bounded away as it was when
        measured against noisy individuals."""
        items = [utterance(utterance_id=f"{i:03d}", words=(("他", 1, SPLIT), ("忙", 2, FULL)))
                 for i in range(5)]
        rows = [scored(f"{i:03d}") for i in range(5)]
        report = build_report(items, rows)
        assert report["verdict"]["compared_against"] == "majority"
        assert report["verdict"]["target"] == 0.70
        # Per-rater agreement survives as context, without a target of its own:
        # applying the majority target to the harder per-rater task would
        # report a failure the contract never asked for.
        primary = report["per_rater_agreement"]
        assert primary["rater_count"] == 3
        assert len(primary["per_rater"]) == 3
        assert "target" not in primary
        assert report["verdict"]["per_rater_kappa"] is not None

    def test_verdict_reports_the_shortfall_against_the_committed_target(self):
        items = [utterance(utterance_id=f"{i:03d}", words=(("他", 1, FULL), ("忙", 2, SPLIT)))
                 for i in range(6)]
        rows = [scored(f"{i:03d}", scores=(80.0, 20.0)) for i in range(6)]
        verdict = build_report(items, rows)["verdict"]
        assert verdict["target"] == 0.70
        assert verdict["meets_target"] is False
        assert verdict["level"] in {"below_target", "near_target"}
        assert "target" in verdict["summary"]

    def test_the_oracle_bound_no_longer_gates_the_majority_headline(self):
        """The 0.606-0.744 oracle bound is a property of the per-rater task.
        Against the majority label a perfect system scores 1.0, so that warning
        must not fire and imply the new target is unreachable."""
        items = [utterance(utterance_id=f"{i:03d}", words=(("他", 1, SPLIT), ("忙", 2, SPLIT)))
                 for i in range(8)]
        rows = [scored(f"{i:03d}", scores=(80.0, 20.0)) for i in range(8)]
        report = build_report(items, rows)
        # Still reported, because it is what the per-rater context must be read
        # against -- it just no longer bounds the headline.
        assert report["oracle_bound"]["uncontaminated"] is not None
        assert "attainable maximum" not in report["verdict"]["summary"]

    def test_oracle_bound_reports_both_variants_and_the_tie_cost(self):
        items = [utterance(utterance_id=f"{i:03d}", words=(("他", 1, SPLIT), ("忙", 2, FULL)))
                 for i in range(6)]
        rows = [scored(f"{i:03d}") for i in range(6)]
        bound = build_report(items, rows)["oracle_bound"]
        assert bound["contaminated"] is not None
        assert bound["dropped_for_ties"] is not None


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
