"""Unit tests for caf_metrics.classify_pauses and speech_rate_verdict.

classify_pauses judges whether each detected pause landed at a natural
boundary in the reference script (after punctuation, or before a connective)
versus mid-phrase ("choppy"). speech_rate_verdict turns a measured
articulation rate into a plain-language too-slow/good/too-fast judgment using
the thresholds already established in praat_analyzer.analyze_fluency and
caf_metrics.fluency_metrics (2.5 / 6.5 syl/s cutoffs, 3-5 syl/s good band).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from caf_metrics import classify_pauses, speech_rate_verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word(token, start, end):
    return {"token": token, "start_time": start, "end_time": end}


def _pause(start, end):
    return {"start": start, "end": end, "duration": round(end - start, 3)}


# ---------------------------------------------------------------------------
# classify_pauses
# ---------------------------------------------------------------------------

class TestClassifyPauses:
    def test_pause_after_comma_is_natural(self):
        # Reference: 我喜歡貓，因為牠很可愛。
        # Student paused right where the comma is.
        reference = "我喜歡貓，因為牠很可愛。"
        word_prosody = [
            _word("我喜歡貓", 0.0, 0.8),
            _word("因為", 1.2, 1.6),
            _word("牠很可愛", 1.6, 2.4),
        ]
        pause_analysis = {"pauses": [_pause(0.8, 1.2)]}

        result = classify_pauses(reference, pause_analysis, word_prosody)

        assert result["natural"] == [
            {"before": "我喜歡貓", "after": "因為", "duration": 0.4}
        ]
        assert result["choppy"] == []

    def test_pause_mid_phrase_is_choppy(self):
        # Reference: 我喜歡貓。 (no punctuation between 我喜歡 and 貓)
        reference = "我喜歡貓。"
        word_prosody = [
            _word("我喜歡", 0.0, 0.6),
            _word("貓", 1.0, 1.3),
        ]
        pause_analysis = {"pauses": [_pause(0.6, 1.0)]}

        result = classify_pauses(reference, pause_analysis, word_prosody)

        assert result["choppy"] == [
            {"before": "我喜歡", "after": "貓", "duration": 0.4}
        ]
        assert result["natural"] == []

    def test_pause_before_connective_is_natural(self):
        # Reference: 我很累，所以我想睡覺。ish, but written without comma
        # to isolate the connective rule: 我很累所以我想睡覺。
        reference = "我很累所以我想睡覺。"
        word_prosody = [
            _word("我很累", 0.0, 0.6),
            _word("所以", 1.0, 1.3),
            _word("我想睡覺", 1.3, 2.0),
        ]
        pause_analysis = {"pauses": [_pause(0.6, 1.0)]}

        result = classify_pauses(reference, pause_analysis, word_prosody)

        assert result["natural"] == [
            {"before": "我很累", "after": "所以", "duration": 0.4}
        ]

    def test_word_count_mismatch_returns_empty_unjudged_result(self):
        # Student's transcription segmented into a different number of words
        # than the reference (misread/ASR error) — too unreliable to align,
        # so no pause should be judged either way.
        reference = "我喜歡貓，因為牠很可愛。"
        word_prosody = [_word("我喜歡貓好可愛啊", 0.0, 1.0)]
        pause_analysis = {"pauses": [_pause(0.4, 0.7)]}

        result = classify_pauses(reference, pause_analysis, word_prosody)

        assert result == {"natural": [], "choppy": [], "judged": False}

    def test_no_pauses_returns_empty_result(self):
        reference = "我喜歡貓。"
        word_prosody = [_word("我喜歡貓", 0.0, 1.0)]
        pause_analysis = {"pauses": []}

        result = classify_pauses(reference, pause_analysis, word_prosody)

        assert result["natural"] == []
        assert result["choppy"] == []
        assert result["judged"] is True


# ---------------------------------------------------------------------------
# speech_rate_verdict
# ---------------------------------------------------------------------------

class TestSpeechRateVerdict:
    def test_slow_rate_below_threshold(self):
        result = speech_rate_verdict(1.8)
        assert result["verdict"] == "slow"
        assert "1.8" in result["text"]

    def test_fast_rate_above_threshold(self):
        result = speech_rate_verdict(7.2)
        assert result["verdict"] == "fast"
        assert "7.2" in result["text"]

    def test_good_rate_within_beginner_band(self):
        result = speech_rate_verdict(4.0)
        assert result["verdict"] == "good"

    def test_zero_rate_is_slow(self):
        result = speech_rate_verdict(0.0)
        assert result["verdict"] == "slow"
