"""Unit tests for segment_words() in caf_metrics.py.

Covers Traditional Chinese compound words that jieba's Simplified-Chinese
dictionary splits incorrectly, plus punctuation-boundary behaviour (the
enumeration comma 、 must act as a word boundary, not be silently joined).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from caf_metrics import segment_words


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_contains_all(result: list, required: list, sentence: str) -> None:
    """Assert every required token appears in result (order-insensitive)."""
    missing = [w for w in required if w not in result]
    assert not missing, (
        f"Missing tokens {missing} in segmentation of {sentence!r}.\n"
        f"Got: {result}"
    )


# ---------------------------------------------------------------------------
# Exact-output tests — three target sentences
# ---------------------------------------------------------------------------

class TestTargetSentences:
    """Exact expected output for the three CFL lesson sentences."""

    def test_campus_photo_sentence(self):
        """在校園裡 must not split as 在校 + 園裡 (SC compound interference)."""
        sentence = "下課以後，風景很好，他們在校園裡高興地照相"
        result = segment_words(sentence)
        assert result == [
            "下課", "以後", "風景", "很", "好",
            "他們", "在校園裡", "高興", "地", "照相",
        ], f"Got: {result}"

    def test_class_return_sentence(self):
        """吃飽, 大樓裡, 中文課 must each be single tokens.

        The enumeration comma 、 between 中文課 and 學中文 must create a
        segmentation boundary so 課 and 學 are never fused into 課學.
        """
        sentence = "吃飽以後，他們回到大樓裡上中文課、學中文"
        result = segment_words(sentence)
        assert result == [
            "吃飽", "以後", "他們", "回到", "大樓裡",
            "上", "中文課", "學", "中文",
        ], f"Got: {result}"

    def test_noodle_shop_sentence(self):
        """麵店 must not split as 麵 + 店."""
        sentence = "中午的時候，弟弟和同學一起去外面的麵店吃午餐"
        result = segment_words(sentence)
        assert result == [
            "中午", "的", "時候", "弟弟", "和", "同學",
            "一起", "去", "外面", "的", "麵店", "吃", "午餐",
        ], f"Got: {result}"


# ---------------------------------------------------------------------------
# Key-compound regression tests
# ---------------------------------------------------------------------------

class TestTCCompoundWords:
    """Each test guards a single Traditional Chinese compound that jieba's
    built-in Simplified Chinese dictionary splits incorrectly."""

    # ---- location words with TC suffix 裡 ----

    def test_zai_jia_li(self):
        """在家裡 — 在家 (SC) must not steal 家 from 家裡."""
        assert segment_words("姐姐在家裡做飯") == ["姐姐", "在家裡", "做飯"]

    def test_zai_jiaoyuan_li(self):
        """在校園裡 — isolated check."""
        assert segment_words("他們在校園裡") == ["他們", "在校園裡"]

    def test_zai_dalou_li(self):
        """大樓裡 — inside a building."""
        result = segment_words("他們回到大樓裡")
        _assert_contains_all(result, ["大樓裡"], "他們回到大樓裡")

    def test_jiaoshi_li(self):
        """教室裡."""
        result = segment_words("學生在教室裡寫字")
        _assert_contains_all(result, ["教室裡"], "學生在教室裡寫字")

    # ---- verb compounds ----

    def test_chi_bao(self):
        """吃飽 — eat until full."""
        result = segment_words("吃飽以後")
        _assert_contains_all(result, ["吃飽", "以後"], "吃飽以後")

    def test_zuo_fan(self):
        """做飯 — cook a meal."""
        assert segment_words("媽媽在廚房做飯") == ["媽媽", "在", "廚房", "做飯"]

    def test_chi_fan(self):
        """吃飯 — eat a meal."""
        assert segment_words("我們去吃飯") == ["我們", "去", "吃飯"]

    def test_zuo_zuoye(self):
        """做作業 — do homework."""
        assert segment_words("我在家裡做作業") == ["我", "在家裡", "做作業"]

    # ---- lesson / course words ----

    def test_zhongwen_ke(self):
        """中文課 — Chinese class."""
        result = segment_words("上中文課")
        _assert_contains_all(result, ["中文課"], "上中文課")

    # ---- place names ----

    def test_mian_dian(self):
        """麵店 — noodle shop."""
        result = segment_words("去麵店吃午餐")
        _assert_contains_all(result, ["麵店"], "去麵店吃午餐")


# ---------------------------------------------------------------------------
# Punctuation boundary tests
# ---------------------------------------------------------------------------

class TestPunctuationBoundaries:
    """Punctuation (，、。) must act as segmentation boundaries so adjacent
    Han characters across a punctuation mark are never fused into one token."""

    def test_enumeration_comma_boundary(self):
        """、 between two clauses must not fuse the flanking characters."""
        result = segment_words("上中文課、學中文")
        # 課 and 學 must be separate tokens — never 課學
        assert "課學" not in result, f"課學 was fused; got: {result}"
        _assert_contains_all(result, ["中文課", "學", "中文"], "上中文課、學中文")

    def test_fullwidth_comma_boundary(self):
        """，between two clauses must produce separate token runs."""
        result = segment_words("他們在校園裡，高興地照相")
        # 裡 and 高 must not be fused
        fused = [t for t in result if "裡高" in t]
        assert not fused, f"裡高 fused into {fused}; got: {result}"

    def test_period_boundary(self):
        """。acts as a boundary between sentences."""
        result = segment_words("吃飯了。睡覺了。")
        assert "飯睡" not in " ".join(result), f"Cross-sentence fusion; got: {result}"

    def test_empty_string(self):
        assert segment_words("") == []

    def test_no_han_characters(self):
        assert segment_words("Hello, world! 123") == []

    def test_pure_punctuation(self):
        assert segment_words("，。、！？") == []
