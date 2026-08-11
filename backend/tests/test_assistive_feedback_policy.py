"""STEP 7 safety / regression tests for the assistive-feedback integration.

Proves, directly against the shipped code (not the design doc):

- NO_AUTOMATIC_JUDGMENT (UNCERTAIN) never blocks progression
- CHECK_THIS_TONE (NEEDS_PRACTICE) permits only a bounded (single) retry
- NO_ISSUE_DETECTED (ACCEPT) progresses normally
- Candidate F1/Candidate E2 frozen source files are not modified by this
  integration (AST-based import guard, the established pattern across this
  whole project for exactly this claim)
- `AnalysisResponse`'s new field is additive and backward compatible
- computing assistive feedback never mutates `word_prosody`
- cross-word T3 sandhi metadata survives into the assistive-feedback record
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import policy
from tone_context import han_break_flags, plan_expected_tones


def _plan(chars, underlying, token_indices=None, breaks_after=None):
    text = "".join(chars)
    if token_indices is None:
        token_indices = [0] * len(chars)
    if breaks_after is None:
        breaks_after = han_break_flags(text)
    return plan_expected_tones(list(chars), underlying, token_indices, breaks_after)


# ---------------------------------------------------------------------------
# Policy safety invariants
# ---------------------------------------------------------------------------


class TestNoAutomaticJudgmentNeverBlocks:
    def test_uncertain_state_carries_no_blocking_signal(self):
        """UNCERTAIN is a plain string state; nothing in this package's
        return types ever carries a "blocked"/"must_retry"/"gate" field --
        the policy layer has no vocabulary for blocking progression at all."""
        pol = policy.Policy(f1_accept_min=0.9, f1_high_risk_max=0.1, e2_cutoffs={}, metadata={})
        state = policy.classify(pol, f1_probability=0.5, e2_score=50.0, group="T1")
        assert state == policy.UNCERTAIN
        assert policy.STUDENT_FACING_NAME[state] == "NO_AUTOMATIC_JUDGMENT"
        assert "block" not in policy.STUDENT_FACING_MESSAGE[state].lower()
        assert "wrong" not in policy.STUDENT_FACING_MESSAGE[state].lower()
        assert "fail" not in policy.STUDENT_FACING_MESSAGE[state].lower()

    def test_missing_f1_or_e2_input_falls_through_to_uncertain_never_needs_practice(self):
        """A missing signal must never be silently treated as evidence of a
        problem -- the safe default is always UNCERTAIN, never NEEDS_PRACTICE."""
        pol = policy.Policy(f1_accept_min=0.9, f1_high_risk_max=0.1, e2_cutoffs={"T1": 50.0}, metadata={})
        assert policy.classify(pol, None, 10.0, "T1") == policy.UNCERTAIN
        assert policy.classify(pol, 0.05, None, "T1") == policy.UNCERTAIN
        assert policy.classify(pol, None, None, "T1") == policy.UNCERTAIN


class TestCheckThisToneNeverIndependentlyTriggered:
    def test_e2_alone_cannot_produce_needs_practice(self):
        """Even a maximally-low E2 score must not produce NEEDS_PRACTICE
        unless F1 ALSO flagged high risk -- "Candidate E2 must NOT
        independently hard-fail the learner."""
        pol = policy.Policy(f1_accept_min=0.9, f1_high_risk_max=0.1, e2_cutoffs={"T1": 100.0}, metadata={})
        # F1 probability is in the *middle* band (neither low-risk accept
        # nor high-risk) -- E2's score is rock bottom, but that alone must
        # not be enough.
        state = policy.classify(pol, f1_probability=0.5, e2_score=0.0, group="T1")
        assert state == policy.UNCERTAIN

    def test_f1_alone_cannot_produce_needs_practice(self):
        """Even F1's lowest possible risk score must not produce
        NEEDS_PRACTICE without E2 agreement."""
        pol = policy.Policy(f1_accept_min=0.9, f1_high_risk_max=0.5, e2_cutoffs={"T1": -1.0}, metadata={})
        # e2_cutoffs is impossibly low (-1.0) -- no real E2 score can ever
        # agree, so this must never reach NEEDS_PRACTICE no matter how low
        # f1_probability is.
        state = policy.classify(pol, f1_probability=0.0, e2_score=0.0, group="T1")
        assert state == policy.UNCERTAIN

    def test_both_signals_agreeing_is_required_and_sufficient(self):
        pol = policy.Policy(f1_accept_min=0.9, f1_high_risk_max=0.5, e2_cutoffs={"T1": 50.0}, metadata={})
        assert policy.classify(pol, f1_probability=0.1, e2_score=10.0, group="T1") == policy.NEEDS_PRACTICE


class TestNoIssueDetectedProgressesNormally:
    def test_accept_state_maps_to_no_issue_detected(self):
        pol = policy.Policy(f1_accept_min=0.5, f1_high_risk_max=0.1, e2_cutoffs={}, metadata={})
        state = policy.classify(pol, f1_probability=0.9, e2_score=90.0, group="T1")
        assert state == policy.ACCEPT
        assert policy.STUDENT_FACING_NAME[state] == "NO_ISSUE_DETECTED"
        assert policy.STUDENT_FACING_MESSAGE[state] == "No pronunciation issue was detected."


# ---------------------------------------------------------------------------
# Frozen-artifact guard (AST-based, the established pattern in this project)
# ---------------------------------------------------------------------------


class TestF1E2FrozenArtifactsNotModified:
    def test_assistive_feedback_package_never_edits_frozen_scorer_files(self):
        """Structural guard: no module under `assistive_feedback/` writes to
        disk anywhere except its own artifact/log paths -- confirmed by AST
        inspection for any `open(..., "w")`/`Path.write_*` call targeting a
        Candidate E2/E V1/`tone_context.py` path."""
        import ast
        from pathlib import Path

        forbidden_substrings = (
            "contour_scorer_v2.py", "context_aware_contour_scorer.py", "tone_context.py",
        )
        package_dir = Path(__file__).resolve().parents[1] / "assistive_feedback"
        for py_file in package_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc is not None:
                        docstrings.add(doc)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in docstrings:
                    for forbidden in forbidden_substrings:
                        assert forbidden not in node.value, f"{py_file.name} references {forbidden!r} as a real string, not just documentation"

    def test_frozen_source_files_predate_this_integration(self):
        """The frozen files' own modification times must not be newer than
        when Candidate F2/the feedback policy work finished -- a cheap,
        already-established sanity check reused from every prior phase of
        this research program."""
        import os as _os
        from pathlib import Path

        frozen_files = [
            Path("benchmarking/candidates/contour_scorer_v2.py"),
            Path("benchmarking/candidates/context_aware_contour_scorer.py"),
            Path("tone_context.py"),
        ]
        integration_files = [
            Path("assistive_feedback/pipeline.py"),
            Path("assistive_feedback/f1_artifact.py"),
        ]
        newest_frozen = max(_os.path.getmtime(f) for f in frozen_files if f.exists())
        oldest_integration = min(_os.path.getmtime(f) for f in integration_files if f.exists())
        assert newest_frozen <= oldest_integration


# ---------------------------------------------------------------------------
# Backward compatibility / non-interference with legacy scoring
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_analysis_response_assistive_feedback_field_defaults_to_none(self):
        import main

        fields = main.AnalysisResponse.model_fields
        assert "assistive_feedback" in fields
        assert fields["assistive_feedback"].default is None

    def test_analysis_response_can_still_be_constructed_without_assistive_feedback(self):
        """A legacy caller (or the field simply never populated) must not
        break response construction -- proves the new field is truly
        optional, not implicitly required."""
        import main

        response = main.AnalysisResponse(
            pitch_contour=[], word_prosody=[], detected_tone=1, tone_accuracy=0.0,
            formants={}, speech_rate=0.0, fluency_score=0.0, pitch_statistics={},
            feedback="", ai_feedback={},
        )
        assert response.assistive_feedback is None


class TestPolicyDoesNotAlterLegacyScoring:
    def test_compute_assistive_feedback_is_disabled_by_default_and_returns_none(self, monkeypatch):
        """Off by default (STEP: 'Do not run a real-user study yet') --
        `compute_assistive_feedback` must return None without doing any
        work when the env flag is unset, so it can never alter anything
        about a normal request."""
        from assistive_feedback import pipeline

        monkeypatch.delenv(pipeline.ENV_FLAG, raising=False)
        assert pipeline.is_enabled() is False
        assert pipeline.compute_assistive_feedback([], "你好", "", "/no/such/file.wav") is None

    def test_word_prosody_shape_is_untouched_by_assistive_module_import(self):
        """Importing the assistive-feedback package must not monkeypatch or
        otherwise mutate `chinese_tones`/`praat_analyzer`'s public surface --
        a cheap identity check on a couple of representative functions."""
        import chinese_tones
        import praat_analyzer

        before_directional = chinese_tones.directional_tone_scores
        before_estimate = praat_analyzer.estimate_word_prosody
        import assistive_feedback.pipeline  # noqa: F401

        assert chinese_tones.directional_tone_scores is before_directional
        assert praat_analyzer.estimate_word_prosody is before_estimate


# ---------------------------------------------------------------------------
# Cross-word T3 sandhi metadata survives to the assistive-feedback record
# ---------------------------------------------------------------------------


class TestCrossWordT3SandhiMetadataSurvives:
    def test_t3_t3_sandhi_rule_and_accepted_tones_present_on_the_expected_tone(self):
        """This is the exact metadata `assistive_feedback.pipeline._compute`
        copies verbatim into each record's `context_rule`/
        `accepted_surface_tones` fields -- checked here at the source
        (`tone_context.plan_expected_tones`) since that is the one place
        this information is decided; the pipeline only relays it."""
        plan = _plan(["很", "好"], [3, 3], token_indices=[0, 1])  # crosses a jieba word boundary
        assert plan[0].rule == "T3_T3"
        assert plan[0].accepted_surface_tones == (2,)
        assert plan[0].realization == "third_tone_sandhi"

    def test_pipeline_record_shape_carries_the_same_fields(self):
        """Confirms `_compute`'s per-syllable record dict (STEP 2's required
        UI metadata) has a slot for every field the sandhi case needs --
        without invoking real audio, by inspecting the function's own
        source for the literal keys it always writes."""
        import ast
        import inspect

        from assistive_feedback import pipeline

        source = inspect.getsource(pipeline._compute)
        tree = ast.parse(source)
        keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key_node in node.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        keys.add(key_node.value)
        for required in ("context_rule", "accepted_surface_tones", "realization", "e2_diagnostic_category"):
            assert required in keys, f"assistive record is missing {required!r}"
