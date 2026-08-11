"""The label/methodological audit's load-bearing mechanics: the positional
row-alignment guard between the diagnostics table and the two prediction
CSVs (a silent misalignment would attribute the wrong prediction to the
wrong syllable everywhere downstream), the sandhi-status mapping from
`tone_context`'s rule identifiers, and the HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET
filter's conjunction of criteria.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.label_audit import (
    SANDHI_STATUS_MAP,
    _utterance_plan,
    is_unanimous,
    meets_high_confidence_criteria,
)
from tone_context import RULE_BU, RULE_NEUTRAL_LEXICAL, RULE_T3_T3, RULE_YI


class TestSandhiStatusMapping:
    def test_t3_t3_maps_to_t3_candidate(self):
        # 我很好: 我(3) 很(3) 好(3) -- a T3 chain, but the simple 2-in-a-row
        # case is easiest to construct directly: 很好 in isolation.
        chars, lengths, plan = _utterance_plan("很好")
        assert chars == ["很", "好"]
        assert SANDHI_STATUS_MAP.get(plan[0].rule) == "T3_sandhi_candidate"

    def test_yi_maps_to_yi_candidate(self):
        chars, lengths, plan = _utterance_plan("一個人")
        yi_index = chars.index("一")
        assert SANDHI_STATUS_MAP.get(plan[yi_index].rule) == "yi_sandhi_candidate"

    def test_bu_maps_to_bu_candidate(self):
        chars, lengths, plan = _utterance_plan("不去")
        bu_index = chars.index("不")
        assert SANDHI_STATUS_MAP.get(plan[bu_index].rule) == "bu_sandhi_candidate"

    def test_ordinary_tone1_word_is_stable(self):
        # 他 (tā, T1) in isolation triggers no rule.
        chars, lengths, plan = _utterance_plan("他來了")
        ta_index = chars.index("他")
        assert SANDHI_STATUS_MAP.get(plan[ta_index].rule) == "stable"

    def test_every_known_rule_constant_is_mapped(self):
        """Guards against a future new RULE_* constant in tone_context.py
        silently falling through to "unknown" without a deliberate mapping
        decision."""
        for rule in (RULE_T3_T3, RULE_YI, RULE_BU, RULE_NEUTRAL_LEXICAL):
            assert rule in SANDHI_STATUS_MAP


class TestLexicalWordLength:
    def test_two_character_word_gets_length_two(self):
        chars, lengths, plan = _utterance_plan("朋友來了")
        # 朋友 should segment as one 2-character token.
        peng_index = chars.index("朋")
        you_index = chars.index("友")
        assert lengths[peng_index] == 2
        assert lengths[you_index] == 2

    def test_punctuation_is_excluded_from_the_han_sequence(self):
        chars, lengths, plan = _utterance_plan("你好，我很好。")
        assert all(0x4E00 <= ord(c) <= 0x9FFF for c in chars)
        assert len(chars) == len(lengths) == len(plan)


class TestUnanimity:
    def test_all_zeros_is_unanimous(self):
        assert is_unanimous({"individual_rater_labels": "000"}) is True

    def test_all_ones_is_unanimous(self):
        assert is_unanimous({"individual_rater_labels": "111"}) is True

    def test_mixed_is_not_unanimous(self):
        assert is_unanimous({"individual_rater_labels": "010"}) is False

    def test_empty_is_not_unanimous(self):
        assert is_unanimous({"individual_rater_labels": ""}) is False


class TestHighConfidenceCriteria:
    """Q8's revised definition, per the follow-up instruction: unanimous +
    valid single-character annotation + context-stable + non-neutral --
    deliberately NOT gated on lexical (jieba) word length, since Q1
    established label duplication isn't plausible in this validation set."""

    def _base_row(self, **overrides):
        row = {
            "individual_rater_labels": "111",
            "word_character_count": "1",
            "sandhi_status": "stable",
            "expected_tone": "1",
            "lexical_word_length": 1,
        }
        row.update(overrides)
        return row

    def test_a_clean_row_qualifies(self):
        assert meets_high_confidence_criteria(self._base_row()) is True

    def test_multisyllabic_lexical_word_still_qualifies(self):
        """The load-bearing behavior change: a row belonging to a
        2-character jieba word must NOT be excluded from the primary
        high-confidence subset -- that's now auxiliary-only (Q2/Q3)."""
        row = self._base_row(lexical_word_length=2)
        assert meets_high_confidence_criteria(row) is True

    def test_non_unanimous_is_excluded(self):
        row = self._base_row(individual_rater_labels="011")
        assert meets_high_confidence_criteria(row) is False

    def test_sandhi_candidate_is_excluded(self):
        row = self._base_row(sandhi_status="T3_sandhi_candidate")
        assert meets_high_confidence_criteria(row) is False

    def test_neutral_tone_is_excluded(self):
        row = self._base_row(expected_tone="5")
        assert meets_high_confidence_criteria(row) is False

    def test_multi_character_annotation_span_is_excluded(self):
        row = self._base_row(word_character_count="2")
        assert meets_high_confidence_criteria(row) is False


class TestBuildMasterRowsAlignmentGuard:
    def test_raises_on_row_count_mismatch(self, tmp_path, monkeypatch):
        import csv

        from benchmarking import label_audit

        short_csv = tmp_path / "short.csv"
        with short_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["audio_id", "expected_tone", "candidate_b_probability", "candidate_b_predicted_correct"],
            )
            writer.writeheader()
            writer.writerow({"audio_id": "x", "expected_tone": "1", "candidate_b_probability": "0.5", "candidate_b_predicted_correct": "1"})

        monkeypatch.setattr(label_audit, "B_PREDICTIONS_CSV", short_csv)
        # C_PREDICTIONS_CSV left pointing at the real, full-length file, so
        # the two prediction files now have different lengths -- the guard
        # must refuse to proceed rather than zip() silently truncating.
        try:
            label_audit.build_master_rows()
        except RuntimeError as error:
            assert "mismatch" in str(error).lower()
        else:
            raise AssertionError("expected a RuntimeError for mismatched row counts")
