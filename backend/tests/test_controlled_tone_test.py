"""Candidate D's controlled synthetic smoke test: the crossed test-case
design, the confusion-metrics math, the A/B/C/D error categorization, and
-- most importantly -- a guard proving this module never touches OMPAL data,
since the whole point of this test is that it must not.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.controlled_tone_test import (
    TEST_FAMILIES,
    AudioProvenance,
    build_test_cases,
    confusion_metrics,
    error_category,
)


def _provenance_for(family: str) -> list[AudioProvenance]:
    characters = TEST_FAMILIES[family]
    return [
        AudioProvenance(
            audio_file=f"{family}{tone}.wav", source="edge-tts (test)",
            generated_or_recorded="generated", text=char, pinyin=f"{family}{tone}", produced_tone=tone,
        )
        for tone, char in enumerate(characters, start=1)
    ]


class TestNeverTouchesOmpal:
    """AST-based, not a text search -- the module's own docstring explains
    this exact guarantee using the words "ompal_corpus", "load_utterances",
    and "final_test" as prose, which would make a plain substring search
    trip on the documentation instead of on real imports/identifiers. This
    checks actual import statements and actual Name/Attribute references,
    which docstring text can never produce."""

    def _module_tree(self):
        import ast
        from pathlib import Path

        from benchmarking import controlled_tone_test

        return ast.parse(Path(controlled_tone_test.__file__).read_text(encoding="utf-8"))

    def test_no_import_references_the_ompal_corpus_loader(self):
        """`benchmarking.ompal_corpus` is specifically the module that reads
        OMPAL audio/annotation files -- forbidden here. A generic helper
        like `benchmarking.ompal_runner.flatten_characters` (used to reshape
        `analyze_all`'s own output, unrelated to loading OMPAL data) is
        fine, so this checks the specific loader module, not any module
        whose name happens to contain "ompal"."""
        import ast

        tree = self._module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module != "benchmarking.ompal_corpus"
                assert not node.module.endswith(".ompal_corpus")

    def test_no_identifier_references_ompal_loading_functions(self):
        """Covers both `load_utterances` (the OMPAL corpus loader) and
        `load_split_rows` (the OMPAL speaker-split loader Candidates B/C/D's
        real validation code uses) -- neither should ever be referenced as
        an actual name in this module's code."""
        import ast

        tree = self._module_tree()
        forbidden = {"load_utterances", "load_split_rows"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden

    def test_no_identifier_references_the_final_test_lock_machinery(self):
        """No OMPAL split loading happens here at all, so there is nothing
        for a FinalTestLockedError guard to guard -- confirming that, rather
        than importing a guard this module has no use for, is itself the
        safety property that matters."""
        import ast

        tree = self._module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "FinalTestLockedError"
            if isinstance(node, ast.Attribute):
                assert node.attr != "FinalTestLockedError"


class TestBuildTestCases:
    def test_produces_a_fully_crossed_4x4_design_per_family(self):
        provenance = _provenance_for("ma")
        cases = build_test_cases(provenance)
        assert len(cases) == 16  # 4 produced x 4 reference

    def test_two_families_together_give_32_cases(self):
        provenance = _provenance_for("ma") + _provenance_for("shi")
        cases = build_test_cases(provenance)
        assert len(cases) == 32

    def test_diagonal_cases_are_matched_and_expected_correct(self):
        cases = build_test_cases(_provenance_for("ma"))
        matched = [c for c in cases if c.audio_tone == c.reference_tone]
        assert len(matched) == 4
        assert all(c.expected_tone_correct == 1 for c in matched)

    def test_off_diagonal_cases_are_mismatched_and_expected_incorrect(self):
        cases = build_test_cases(_provenance_for("ma"))
        mismatched = [c for c in cases if c.audio_tone != c.reference_tone]
        assert len(mismatched) == 12
        assert all(c.expected_tone_correct == 0 for c in mismatched)

    def test_every_reference_tone_appears_the_same_number_of_times(self):
        cases = build_test_cases(_provenance_for("ma") + _provenance_for("shi"))
        counts = {tone: sum(1 for c in cases if c.reference_tone == tone) for tone in (1, 2, 3, 4)}
        assert len(set(counts.values())) == 1  # all equal
        assert counts[1] == 8

    def test_case_ids_are_unique(self):
        cases = build_test_cases(_provenance_for("ma") + _provenance_for("shi"))
        assert len({c.case_id for c in cases}) == len(cases)


class TestConfusionMetrics:
    def test_perfect_agreement_gives_accuracy_one(self):
        metrics = confusion_metrics([1, 0, 1, 0], [1, 0, 1, 0])
        assert metrics["accuracy"] == 1.0
        assert metrics["balanced_accuracy"] == 1.0

    def test_perfect_disagreement_gives_accuracy_zero(self):
        metrics = confusion_metrics([1, 0], [0, 1])
        assert metrics["accuracy"] == 0.0
        assert metrics["sensitivity"] == 0.0
        assert metrics["specificity"] == 0.0

    def test_none_predictions_are_excluded_not_counted_as_wrong(self):
        """A None entry means NA (not judged / not run) -- it must reduce N,
        not silently count as a wrong prediction."""
        metrics = confusion_metrics([1, 0, 1], [1, None, 1])
        assert metrics["n"] == 2
        assert metrics["accuracy"] == 1.0

    def test_all_none_returns_none_metrics_not_a_fabricated_zero(self):
        metrics = confusion_metrics([1, 0], [None, None])
        assert metrics["n"] == 0
        assert metrics["accuracy"] is None

    def test_false_rejection_and_acceptance_rates_match_definitions(self):
        # expected=1 (should be accepted): predicted 0,1 -> one false rejection
        # expected=0 (should be rejected): predicted 1,0 -> one false acceptance
        metrics = confusion_metrics([1, 1, 0, 0], [0, 1, 1, 0])
        assert metrics["false_rejection_rate"] == 0.5
        assert metrics["false_acceptance_rate"] == 0.5


class TestErrorCategory:
    def test_iflytek_not_run_takes_precedence(self):
        assert error_category(1, 1, None) == "IFLYTEK_NOT_RUN"

    def test_current_not_judged_when_iflytek_is_available(self):
        assert error_category(1, None, 1) == "CURRENT_NOT_JUDGED"

    def test_category_a_current_wrong_iflytek_correct(self):
        assert error_category(1, 0, 1) == "A_current_wrong_iflytek_correct"

    def test_category_b_current_correct_iflytek_wrong(self):
        assert error_category(1, 1, 0) == "B_current_correct_iflytek_wrong"

    def test_category_c_both_wrong(self):
        assert error_category(1, 0, 0) == "C_both_wrong"

    def test_category_d_both_correct(self):
        assert error_category(1, 1, 1) == "D_both_correct"

    def test_category_d_both_correct_on_a_negative_case(self):
        assert error_category(0, 0, 0) == "D_both_correct"
