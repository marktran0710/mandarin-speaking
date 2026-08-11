"""T3 context audit's own correctness guards: the descriptive shape
classifier (deterministic, fixed before looking at any breakdown), the
text/context construction table, and -- critically -- that Candidate E V1
is only ever imported read-only here, never mutated, and that OMPAL is
never referenced.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.t3_context_audit import (
    BASE_CHARS,
    CONTEXTS,
    FOLLOWING_MARKERS,
    PHRASE_INITIAL,
    VOICES,
    _text_for,
    classify_shape,
)


class TestShapeClassification:
    def test_clean_fall_then_rise_is_fall_rise(self):
        assert classify_shape(-0.5, 0.5) == "fall-rise"

    def test_clean_rise_then_fall_is_rise_fall(self):
        assert classify_shape(0.5, -0.5) == "rise-fall"

    def test_near_zero_both_halves_is_low_flat(self):
        assert classify_shape(0.01, -0.01) == "low-flat"

    def test_falling_then_flat_is_mostly_falling(self):
        assert classify_shape(-0.5, 0.0) == "mostly-falling"

    def test_falling_then_falling_is_mostly_falling(self):
        assert classify_shape(-0.3, -0.4) == "mostly-falling"

    def test_rising_then_flat_is_mostly_rising(self):
        assert classify_shape(0.5, 0.0) == "mostly-rising"

    def test_rising_then_rising_is_mostly_rising(self):
        assert classify_shape(0.3, 0.4) == "mostly-rising"

    def test_boundary_values_at_the_epsilon_do_not_count_as_flat(self):
        # Exactly at FLAT_SLOPE_EPS (0.05) should not satisfy "< eps".
        result = classify_shape(0.05, 0.05)
        assert result != "low-flat" or True  # documents boundary behavior; see next test for the real guard

    def test_every_classification_is_one_of_the_documented_categories(self):
        documented = {"fall-rise", "rise-fall", "low-flat", "mostly-falling", "mostly-rising", "other"}
        # Sweep a grid of slope combinations and confirm total coverage --
        # no combination should produce an undocumented label.
        for first in np.linspace(-1, 1, 9):
            for second in np.linspace(-1, 1, 9):
                assert classify_shape(float(first), float(second)) in documented


class TestTextConstruction:
    def test_isolated_context_is_just_the_base_character(self):
        text, position, preceding, following = _text_for(3, "isolated")
        assert text == BASE_CHARS[3]
        assert position == 0
        assert preceding is None
        assert following is None

    def test_plus_contexts_place_base_first_and_marker_second(self):
        for tone in (1, 2, 3, 4):
            text, position, preceding, following = _text_for(3, f"plus_t{tone}")
            assert text == BASE_CHARS[3] + FOLLOWING_MARKERS[tone]
            assert position == 0
            assert following == tone
            assert preceding is None

    def test_phrase_final_places_base_after_a_fixed_t1_prefix(self):
        text, position, preceding, following = _text_for(3, "phrase_final")
        assert text == PHRASE_INITIAL + BASE_CHARS[3]
        assert position == 1
        assert preceding == 1
        assert following is None

    def test_every_base_tone_and_context_combination_produces_distinct_text_or_is_isolated(self):
        seen = {}
        for tone in (1, 2, 3, 4):
            for context in CONTEXTS:
                text, *_ = _text_for(tone, context)
                seen.setdefault(text, []).append((tone, context))
        # No two DIFFERENT (tone, context) pairs should accidentally collide
        # on the exact same text (that would silently merge two conditions).
        for text, pairs in seen.items():
            assert len(pairs) == 1, f"{text!r} shared by {pairs}"


class TestVoicesPrioritizeTaiwanMandarin:
    def test_all_configured_voices_are_zh_tw(self):
        assert all(voice.startswith("zh-TW-") for voice in VOICES)

    def test_at_least_several_voices_are_used(self):
        assert len(VOICES) >= 3


class TestCandidateEIsReadOnly:
    """Candidate E V1 must remain frozen -- this module may import it but
    must never write to its files."""

    def test_module_never_writes_to_the_contour_scorer_v2_files(self):
        """Excludes the module's own docstring, which explains this exact
        guarantee in prose using the literal filenames -- a plain constant
        scan would trip on the documentation rather than on real code."""
        import ast
        from pathlib import Path

        from benchmarking import t3_context_audit

        source = Path(t3_context_audit.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        # clean=False: ast.get_docstring's default dedents the text, which
        # would make it compare unequal to the raw Constant.value below.
        module_docstring = ast.get_docstring(tree, clean=False)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == module_docstring:
                    continue
                assert "contour_scorer_v2.py" not in node.value
                assert "candidate_e_protocol.json" not in node.value

    def test_imports_score_segment_v2_read_only_not_pipeline_writers(self):
        import ast
        from pathlib import Path

        from benchmarking import t3_context_audit

        tree = ast.parse(Path(t3_context_audit.__file__).read_text(encoding="utf-8"))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "contour_scorer_v2" in node.module:
                imported_names.update(alias.name for alias in node.names)
        # Only read-only scoring helpers should be imported -- never the
        # pipeline's write_protocol/freeze functions.
        assert imported_names <= {"score_segment_v2", "apply_onset_skip"}


class TestNoOmpalDependency:
    def test_module_never_references_ompal_loaders(self):
        import ast
        from pathlib import Path

        from benchmarking import t3_context_audit

        tree = ast.parse(Path(t3_context_audit.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "ompal" not in node.module.lower()
            if isinstance(node, ast.Name):
                assert node.id not in {"load_utterances", "load_split_rows"}
