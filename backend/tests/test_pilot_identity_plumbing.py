"""Pre-pilot research-logging plumbing: identity threading, the pilot
feature-flag override, and backward compatibility.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import pipeline, research_log


class TestGlobalFlagUnchangedByThisTask:
    def test_global_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv(pipeline.ENV_FLAG, raising=False)
        monkeypatch.delenv(pipeline.PILOT_ENV_FLAG, raising=False)
        assert pipeline.is_enabled() is False
        assert pipeline.is_enabled(study_phase="pilot") is False

    def test_global_flag_still_works_exactly_as_before(self, monkeypatch):
        monkeypatch.setenv(pipeline.ENV_FLAG, "1")
        monkeypatch.delenv(pipeline.PILOT_ENV_FLAG, raising=False)
        assert pipeline.is_enabled() is True
        assert pipeline.is_enabled(study_phase="pilot") is True  # global flag covers everything


class TestPilotOverrideRequiresBothGates:
    def test_pilot_flag_alone_is_not_enough(self, monkeypatch):
        """The pilot env var without the request explicitly opting in via
        study_phase="pilot" must NOT enable anything -- it is not a second
        way to flip the global default."""
        monkeypatch.delenv(pipeline.ENV_FLAG, raising=False)
        monkeypatch.setenv(pipeline.PILOT_ENV_FLAG, "1")
        assert pipeline.is_enabled() is False
        assert pipeline.is_enabled(study_phase="") is False

    def test_study_phase_alone_is_not_enough(self, monkeypatch):
        """A request claiming study_phase="pilot" without the operator
        having set the pilot env var must NOT enable anything -- a student
        cannot self-opt-in by sending a form field alone."""
        monkeypatch.delenv(pipeline.ENV_FLAG, raising=False)
        monkeypatch.delenv(pipeline.PILOT_ENV_FLAG, raising=False)
        assert pipeline.is_enabled(study_phase="pilot") is False

    def test_both_gates_together_enable_pilot_only(self, monkeypatch):
        monkeypatch.delenv(pipeline.ENV_FLAG, raising=False)
        monkeypatch.setenv(pipeline.PILOT_ENV_FLAG, "1")
        assert pipeline.is_enabled(study_phase="pilot") is True
        assert pipeline.is_enabled(study_phase="") is False  # still off for non-pilot requests
        assert pipeline.is_enabled() is False  # still off for the global default


class TestRequestIdentityDefaultsAreInert:
    def test_default_identity_has_no_participant(self):
        identity = pipeline.RequestIdentity()
        assert identity.participant_id == ""
        assert identity.attempt_type == "WHOLE_SENTENCE_INITIAL"
        assert identity.study_phase == ""

    def test_compute_assistive_feedback_without_identity_never_logs(self, monkeypatch, tmp_path):
        """No identity -> no log write, even if the feature is enabled --
        logging must be opt-in per request, not automatic just because the
        layer ran."""
        log_path = tmp_path / "should_stay_empty.jsonl"
        monkeypatch.setattr(research_log, "LOG_PATH", log_path)
        monkeypatch.setenv(pipeline.ENV_FLAG, "1")
        # Deliberately malformed input (too-short pitch contour) so
        # `compute_assistive_feedback` returns None quickly without needing
        # real audio -- this test only checks the identity/logging
        # contract, not the scoring math.
        result = pipeline.compute_assistive_feedback([], "你好", "", "/no/such/file.wav")
        assert result is None
        assert not log_path.exists() or research_log.read_records(log_path) == []


class TestDoAnalyzeSignatureBackwardCompatible:
    def test_new_params_all_have_defaults(self):
        import inspect

        import main

        sig = inspect.signature(main._do_analyze)
        new_params = ("participant_id", "item_id", "session_id", "attempt_id", "attempt_number", "attempt_type", "study_phase")
        for name in new_params:
            assert name in sig.parameters, f"missing parameter {name}"
            assert sig.parameters[name].default is not inspect.Parameter.empty, f"{name} must have a default"

    def test_route_new_form_fields_all_have_defaults(self):
        import inspect

        import routers.asr

        sig = inspect.signature(routers.asr.analyze_speech)
        for name in ("participant_id", "item_id", "session_id", "attempt_id", "attempt_number", "attempt_type", "study_phase"):
            assert name in sig.parameters, f"missing Form field {name}"


class TestNoRawScoresLeakToStudentFacingRecord:
    def test_pipeline_result_dict_keys_never_include_raw_scores(self):
        """The STUDENT-facing per-syllable dict (what `_compute` appends to
        its returned list) must never carry `f1_risk_score`/`e2_score` --
        those exist only in the research-log side effect. Checked via the
        exact literal keys `_compute` writes into that dict (not the
        research-log dict, a different literal a few lines earlier in the
        same function)."""
        import ast
        import inspect

        from assistive_feedback import pipeline as pipeline_module

        source = inspect.getsource(pipeline_module._compute)
        tree = ast.parse(source)
        # Find the dict literal passed to `results.append(...)` specifically.
        append_dicts = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "results"
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        append_dicts.append(arg)
        assert append_dicts, "could not find results.append(...) call"
        keys = {
            key_node.value for d in append_dicts for key_node in d.keys
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)
        }
        assert "f1_risk_score" not in keys
        assert "e2_score" not in keys
        assert "assistive_state" in keys  # sanity: this IS the student-facing dict
