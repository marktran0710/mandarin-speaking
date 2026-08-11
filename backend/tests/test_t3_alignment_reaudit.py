"""Tests for the T3 alignment re-audit and tone-context-planner audit:
correctness of the boundary/shape comparison logic, and structural guards
that Candidate E V1 and OMPAL are never touched, and that no new alignment
model was introduced (only the existing EnergyAligner).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.t3_alignment_reaudit import (
    TARGET_CONTEXTS,
    _old_5050_boundary_seconds,
    measure_aligned,
)
from benchmarking.tone_context_planner_audit import (
    CONTEXT_TEXT,
    UNDERLYING_TONE,
    run_planner_for_context,
)


class TestOldBoundaryReproducesOriginalHeuristic:
    def test_matches_frame_count_half_split(self):
        contour = [(float(i) * 0.01, 100.0 + i) for i in range(20)]
        boundary = _old_5050_boundary_seconds(contour)
        assert boundary == contour[10][0]

    def test_odd_length_contour_does_not_crash(self):
        contour = [(float(i) * 0.01, 100.0) for i in range(7)]
        boundary = _old_5050_boundary_seconds(contour)
        assert boundary == contour[3][0]


class TestMeasureAlignedOnRealAudio:
    """Exercises the real pipeline (EnergyAligner + normalize + smooth +
    classify) against the actual generated controlled audio -- skipped if
    that audio hasn't been generated in this environment."""

    def _has_audio(self):
        from pathlib import Path

        return (Path("benchmarking/external/t3_context_audio") / "zh-TW-HsiaoChenNeural_3_plus_t1.wav").exists()

    def test_returns_two_distinct_syllable_durations(self):
        if not self._has_audio():
            import pytest

            pytest.skip("controlled T3 context audio not generated in this environment")
        result = measure_aligned("zh-TW-HsiaoChenNeural", "plus_t1")
        assert result.error == ""
        assert result.first_syllable_duration_s > 0
        assert result.second_syllable_duration_s > 0

    def test_shape_category_is_one_of_the_documented_labels(self):
        if not self._has_audio():
            import pytest

            pytest.skip("controlled T3 context audio not generated in this environment")
        result = measure_aligned("zh-TW-HsiaoChenNeural", "plus_t3")
        assert result.shape_category in (
            "fall-rise", "rise-fall", "low-flat", "mostly-falling", "mostly-rising", "other", "unmeasured",
        )

    def test_all_four_target_contexts_are_measurable(self):
        if not self._has_audio():
            import pytest

            pytest.skip("controlled T3 context audio not generated in this environment")
        for context in TARGET_CONTEXTS:
            result = measure_aligned("zh-TW-HsiaoChenNeural", context)
            assert result.error == "", f"{context}: {result.error}"


class TestPlannerAuditUsesRealPlanner:
    def test_isolated_t3_gets_no_sandhi_rule(self):
        rows = run_planner_for_context("isolated")
        assert rows[0]["underlying_tone"] == 3
        assert rows[0]["rule"] == "none"

    def test_t3_before_t3_gets_the_t3_t3_sandhi_rule(self):
        rows = run_planner_for_context("plus_t3")
        first = rows[0]
        assert first["underlying_tone"] == 3
        assert first["rule"] == "T3_T3"
        assert first["accepted_surface_tones"] == "(2,)"

    def test_t3_before_non_t3_gets_half_third_realization(self):
        for context in ("plus_t1", "plus_t2", "plus_t4"):
            rows = run_planner_for_context(context)
            first = rows[0]
            assert first["underlying_tone"] == 3
            assert first["realization"] == "half_third"

    def test_phrase_final_t3_is_the_second_character(self):
        rows = run_planner_for_context("phrase_final")
        t3_row = next(r for r in rows if r["underlying_tone"] == 3)
        assert t3_row["position"] == 1

    def test_every_context_text_matches_its_underlying_tone_table(self):
        for context, chars in CONTEXT_TEXT.items():
            for char in chars:
                assert char in UNDERLYING_TONE


class TestNoCandidateEOrOmpalReference:
    def _assert_module_clean(self, module):
        import ast
        from pathlib import Path

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "contour_scorer_v2" not in node.module
                assert "ompal" not in node.module.lower()
            if isinstance(node, ast.Name):
                assert node.id not in {"load_utterances", "load_split_rows"}

    def test_alignment_reaudit_module_is_clean(self):
        from benchmarking import t3_alignment_reaudit

        self._assert_module_clean(t3_alignment_reaudit)

    def test_planner_audit_module_is_clean(self):
        from benchmarking import tone_context_planner_audit

        self._assert_module_clean(tone_context_planner_audit)


class TestNoNewAlignmentModel:
    def test_alignment_reaudit_only_imports_energy_aligner(self):
        import ast
        from pathlib import Path

        from benchmarking import t3_alignment_reaudit

        tree = ast.parse(Path(t3_alignment_reaudit.__file__).read_text(encoding="utf-8"))
        aligner_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "tone_scoring.alignment":
                aligner_imports.update(alias.name for alias in node.names)
        assert aligner_imports == {"EnergyAligner"}
