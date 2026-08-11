"""STEP 8 — Candidate E2 context-routing regression tests, plus structural
guards that Candidate E V1 and `tone_context.py` are only ever imported
read-only, and that no OMPAL data is referenced.
"""
import os
import sys

import jieba
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.candidates.context_aware_contour_scorer import (
    HALF_THIRD_RISE_CEILING,
    HALF_THIRD_RISE_REJECT_SLOPE,
    _score_half_third,
    score_segment_e2,
)
from benchmarking.candidates.contour_scorer_v2 import _score_t1, _score_t2, _score_t3, _score_t4, score_segment_v2
from tone_context import han_break_flags, plan_expected_tones

# Canonical-ish synthetic contours, reused from the earlier candidate work.
FLAT = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
RISING = np.array([0.1, 0.2, 0.35, 0.5, 0.6, 0.7, 0.8, 0.9])
FALLING = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.35, 0.2, 0.1])
DIP = np.array([0.6, 0.5, 0.4, 0.25, 0.2, 0.25, 0.45, 0.65])


def _plan(chars, underlying, token_indices=None, breaks_after=None):
    text = "".join(chars)
    if token_indices is None:
        token_indices = [0] * len(chars)
    if breaks_after is None:
        breaks_after = han_break_flags(text)
    return plan_expected_tones(list(chars), underlying, token_indices, breaks_after)


class TestT3T3RoutesToT2Realization:
    def test_first_t3_in_t3_t3_gets_accepted_tone_2(self):
        plan = _plan(["馬", "好"], [3, 3])
        assert plan[0].accepted_surface_tones == (2,)
        assert plan[0].rule == "T3_T3"

    def test_score_segment_e2_matches_score_t2_exactly_for_that_case(self):
        plan = _plan(["馬", "好"], [3, 3])
        expected = plan[0]
        score, provenance, matched_tone = score_segment_e2(RISING, expected)
        assert matched_tone == 2
        assert score == pytest.approx(_score_t2(RISING))
        assert provenance == "measured"

    def test_a_falling_contour_is_scored_low_via_the_t2_branch_not_accepted_as_t3(self):
        """A first-T3-in-T3+T3 that was actually produced as a falling
        shape (wrong -- should have risen) must be scored against T2's
        rise formula, not quietly re-scored as a valid (full or half) T3."""
        plan = _plan(["馬", "好"], [3, 3])
        score, _prov, matched_tone = score_segment_e2(FALLING, plan[0])
        assert matched_tone == 2
        assert score == pytest.approx(_score_t2(FALLING))
        assert score < 50  # a falling contour scores poorly against T2's rise formula


class TestT3BeforeNonT3RoutesToHalfThird:
    @pytest.mark.parametrize("following_tone,following_char", [(1, "天"), (2, "人"), (4, "是")])
    def test_realization_is_half_third(self, following_tone, following_char):
        plan = _plan(["馬", following_char], [3, following_tone])
        assert plan[0].realization == "half_third"
        assert plan[0].accepted_surface_tones == (3,)

    def test_score_segment_e2_uses_the_half_third_formula_not_full_dip(self):
        plan = _plan(["馬", "天"], [3, 1])
        expected = plan[0]
        score, provenance, matched_tone = score_segment_e2(FALLING, expected)
        assert matched_tone == 3
        assert provenance == "measured_half_third"
        assert score == pytest.approx(_score_half_third(FALLING))
        # And explicitly NOT the full-dip formula's score for the same input.
        assert score != pytest.approx(_score_t3(FALLING))

    def test_a_clear_rise_is_rejected_by_the_half_third_gate(self):
        plan = _plan(["馬", "天"], [3, 1])
        score, _prov, _matched = score_segment_e2(RISING, plan[0])
        assert score <= HALF_THIRD_RISE_CEILING


class TestIsolatedAndPhraseFinalRouteToFullThird:
    def test_isolated_t3_gets_full_third_realization(self):
        plan = _plan(["馬"], [3])
        assert plan[0].realization == "full_third"
        assert plan[0].accepted_surface_tones == (3,)

    def test_isolated_t3_score_matches_candidate_e_v1s_full_dip_formula_exactly(self):
        plan = _plan(["馬"], [3])
        score, provenance, matched_tone = score_segment_e2(DIP, plan[0])
        assert matched_tone == 3
        assert provenance == "measured_full_third"
        assert score == pytest.approx(_score_t3(DIP))

    def test_phrase_final_t3_also_gets_full_third(self):
        plan = _plan(["三", "馬"], [1, 3])
        t3_entry = plan[1]
        assert t3_entry.realization == "full_third"


class TestT1T2T4UnaffectedByT3Machinery:
    @pytest.mark.parametrize("tone,contour,formula", [(1, FLAT, _score_t1), (2, RISING, _score_t2), (4, FALLING, _score_t4)])
    def test_matches_candidate_e_v1_exactly(self, tone, contour, formula):
        plan = _plan(["测"[:0] or {1: "他", 2: "麻", 4: "罵"}[tone]], [tone])
        expected = plan[0]
        assert expected.realization == "canonical"
        e2_score, _prov, matched_tone = score_segment_e2(contour, expected)
        e_v1_score, _e_v1_prov = score_segment_v2(contour, tone)
        assert matched_tone == tone
        assert e2_score == pytest.approx(e_v1_score)
        assert e2_score == pytest.approx(formula(contour))

    def test_t1_t2_t4_are_never_routed_through_half_third_or_full_third(self):
        for tone, char in ((1, "他"), (2, "麻"), (4, "罵")):
            plan = _plan([char], [tone])
            assert plan[0].realization not in ("half_third", "full_third", "third_tone_sandhi")


class TestContextAcrossWordBoundaries:
    """T3 sandhi must still apply across a jieba word boundary -- the
    documented gap `apply_tone_sandhi` (Candidate E V1's inherited legacy
    path) has and `plan_expected_tones` fixes."""

    def test_t3_t3_sandhi_fires_even_with_different_token_indices(self):
        # token_indices=[0, 1] simulates jieba splitting the pair into two
        # separate single-character tokens, as it would for e.g. 很/好.
        plan = _plan(["馬", "好"], [3, 3], token_indices=[0, 1])
        assert plan[0].rule == "T3_T3"
        assert plan[0].accepted_surface_tones == (2,)

    def test_a_real_two_word_t3_t3_sequence_via_actual_jieba_segmentation(self):
        text = "很好"  # hen3 hao3 -- genuinely two separate jieba tokens
        tokens = jieba.lcut(text)
        assert len(tokens) >= 2  # confirms this really does cross a token boundary
        token_indices = []
        for i, tok in enumerate(tokens):
            token_indices.extend([i] * len(tok))
        plan = plan_expected_tones(list(text), [3, 3], token_indices, han_break_flags(text))
        assert plan[0].rule == "T3_T3"
        assert plan[0].accepted_surface_tones == (2,)

        score, _prov, matched_tone = score_segment_e2(RISING, plan[0])
        assert matched_tone == 2
        assert score == pytest.approx(_score_t2(RISING))

    def test_a_strong_prosodic_boundary_blocks_the_sandhi(self):
        # 馬，好 (with a comma) -- a strong boundary should prevent T3+T3
        # sandhi from crossing it, per han_break_flags/plan_expected_tones.
        text = "馬，好"
        han_chars = [c for c in text if "一" <= c <= "鿿"]
        plan = plan_expected_tones(han_chars, [3, 3], [0, 0], han_break_flags(text))
        assert plan[0].rule != "T3_T3"
        assert plan[0].accepted_surface_tones == (3,)


class TestMaxOverAcceptedAlternatives:
    def test_third_tone_chain_scores_the_max_of_its_two_accepted_tones(self):
        # 3+ consecutive T3s -> ambiguous grouping -> accepted_surface_tones
        # = (2, 3) for the non-final members, per tone_context.py Pass 2.
        plan = _plan(["馬", "馬", "好"], [3, 3, 3])
        middle = plan[1]
        assert set(middle.accepted_surface_tones) >= {2, 3} or middle.accepted_surface_tones in ((2, 3),)

        score, _prov, matched_tone = score_segment_e2(RISING, middle)
        expected_t2_score = _score_t2(RISING)
        expected_t3_score = _score_t3(RISING) if middle.realization == "full_third" else None
        # RISING should favor the T2 branch; matched_tone should reflect
        # whichever branch actually won.
        assert score == pytest.approx(max(
            c for c in [expected_t2_score, expected_t3_score] if c is not None
        ))

    def test_never_averages_the_alternatives(self):
        """Structural guard against the exact mistake the task warned
        against: averaging would produce a DIFFERENT (lower) number than
        either individual candidate for a contour that matches one
        alternative well and the other poorly."""
        plan = _plan(["馬", "馬", "好"], [3, 3, 3])
        middle = plan[1]
        score, _prov, _matched = score_segment_e2(RISING, middle)
        t2_score = _score_t2(RISING)
        t3_score = _score_t3(RISING)
        average = (t2_score + t3_score) / 2
        assert score >= max(t2_score, t3_score) - 1e-6
        assert score != pytest.approx(average, abs=1.0) or max(t2_score, t3_score) == pytest.approx(average)


class TestReadOnlyDependencies:
    def test_module_never_writes_to_candidate_e_v1_or_tone_context(self):
        import ast
        from pathlib import Path

        from benchmarking.candidates import context_aware_contour_scorer as e2

        tree = ast.parse(Path(e2.__file__).read_text(encoding="utf-8"))
        # Every docstring (module, class, AND function/method) explains
        # this exact guarantee in prose using these filenames -- collect
        # all of them (not just the module's) so the scan below checks
        # real code, not documentation.
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in docstrings:
                assert "contour_scorer_v2.py" not in node.value
                assert "tone_context.py" not in node.value

    def test_module_never_references_ompal_loaders(self):
        import ast
        from pathlib import Path

        from benchmarking.candidates import context_aware_contour_scorer as e2

        tree = ast.parse(Path(e2.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "ompal" not in node.module.lower()
            if isinstance(node, ast.Name):
                assert node.id not in {"load_utterances", "load_split_rows"}
