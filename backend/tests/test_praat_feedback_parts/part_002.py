

# ---------------------------------------------------------------------------
# get_tone_feedback — single-tone grading
# ---------------------------------------------------------------------------

class TestGetToneFeedback:
    _rising = _make_contour([0.2, 0.5, 0.8])

    def test_empty_contour_returns_fallback(self):
        fb = get_tone_feedback(1, 80.0, [])
        assert "No clear tone" in fb

    def test_invalid_tone_returns_fallback(self):
        fb = get_tone_feedback(99, 80.0, self._rising)
        assert "No clear tone" in fb

    @pytest.mark.parametrize("accuracy,expected", [
        (86.0, "Excellent"),
        (85.1, "Excellent"),
        (85.0, "Good"),      # boundary
        (71.0, "Good"),
        (70.1, "Good"),
        (70.0, "recognizable"),  # boundary
        (56.0, "recognizable"),
        (55.1, "recognizable"),
        (55.0, "needs more contrast"),  # boundary
        (0.0,  "needs more contrast"),
    ])
    def test_accuracy_bands(self, accuracy, expected):
        fb = get_tone_feedback(2, accuracy, self._rising)
        assert expected.lower() in fb.lower(), (
            f"accuracy={accuracy}: expected {expected!r} in {fb!r}"
        )

    def test_tone2_rising_direction_praised(self):
        rising = _make_contour([0.1, 0.5, 0.9])   # clearly rising
        fb = get_tone_feedback(2, 80.0, rising)
        assert "upward" in fb.lower() or "rise" in fb.lower() or "rising" in fb.lower()

    def test_tone2_wrong_direction_noted(self):
        falling = _make_contour([0.9, 0.5, 0.1])   # falling instead of rising
        fb = get_tone_feedback(2, 40.0, falling)
        assert "rise" in fb.lower() or "higher" in fb.lower()

    def test_tone3_clear_dip_praised(self):
        dip = _make_contour([0.8, 0.3, 0.1, 0.4, 0.8])
        fb = get_tone_feedback(3, 80.0, dip)
        assert "dip" in fb.lower()

    def test_tone4_falling_praised(self):
        falling = _make_contour([0.9, 0.6, 0.2])
        fb = get_tone_feedback(4, 80.0, falling)
        assert "falling" in fb.lower() or "fall" in fb.lower()

    def test_tone1_flat_praised(self):
        flat = _make_contour([0.8, 0.8, 0.8, 0.8], spread_hz=5.0)
        fb = get_tone_feedback(1, 80.0, flat)
        assert "steady" in fb.lower() or "level" in fb.lower() or "flat" in fb.lower()


# ---------------------------------------------------------------------------
# _classify_content_word
# ---------------------------------------------------------------------------

class TestClassifyContentWord:
    def test_non_chinese_returns_false(self):
        assert _classify_content_word("hello") is False

    def test_empty_returns_false(self):
        assert _classify_content_word("") is False

    def test_pure_punctuation_returns_false(self):
        assert _classify_content_word("。！") is False

    def test_common_noun_returns_true(self):
        # 學校 (school) — a noun
        assert _classify_content_word("學校") is True

    def test_common_verb_returns_true(self):
        # 游泳 (swim) — a verb not in the custom jieba word list.
        assert _classify_content_word("游泳") is True

    def test_custom_dictionary_verb_returns_true(self):
        # 吃飯 is registered via jieba.add_word in caf_metrics with an
        # explicit tag="v". Regression guard: add_word() without a tag
        # resets the word's POS to 'x' (unknown), which used to make this
        # return False even though "eat" is clearly a content word.
        import caf_metrics  # noqa: F401 — registers jieba's custom TC dictionary
        assert _classify_content_word("吃飯") is True

    def test_custom_dictionary_location_noun_returns_true(self):
        # 家裡 is already tagged 's' in jieba's own dictionary, but the old
        # untagged jieba.add_word("家裡", freq=200000) call reset it to 'x'.
        import caf_metrics  # noqa: F401
        assert _classify_content_word("家裡") is True

    def test_custom_dictionary_pronoun_returns_false(self):
        # 這裡 is a demonstrative pronoun (tag "r"), not in the content
        # POS-prefix set — should stay classified as a function word.
        import caf_metrics  # noqa: F401
        assert _classify_content_word("這裡") is False


# ---------------------------------------------------------------------------
# Cross-function consistency invariants
# ---------------------------------------------------------------------------

class TestFeedbackConsistency:
    """These tests guard that no two feedback functions contradict each other
    for the same input, and that numeric scores align with feedback text."""

    def test_phrase_feedback_lead_matches_score_for_many_accuracies(self):
        """Parametric sweep: the lead word in phrase feedback always matches
        the accuracy band, even at boundary values."""
        cases = [
            (100.0, "Excellent"),
            (76.0,  "Excellent"),
            (75.0,  "Good"),
            (59.0,  "Good"),
            (58.0,  "recognizable"),
            (45.0,  "recognizable"),
            (44.0,  "contrast"),
            (1.0,   "contrast"),
        ]
        for accuracy, kw in cases:
            words = [_word("媽", [1], accuracy)]
            fb = generate_phrase_tone_feedback(words, accuracy)
            assert kw.lower() in fb.lower(), (
                f"accuracy={accuracy}: expected {kw!r} in lead, got: {fb!r}"
            )

    def test_word_feedback_good_match_never_appears_below_68(self):
        """'Good match' in feedback text must imply score >= 68 — the frontend
        relies on this to decide whether to show the improvement tip."""
        for score in [0.0, 20.0, 47.9, 67.9]:
            fb = _word_prosody_feedback("rising", 50.0, [2], score)
            assert not fb.startswith("Good match"), (
                f"score={score}: 'Good match' must not appear below 68, got: {fb!r}"
            )

    def test_word_feedback_good_match_always_appears_at_or_above_68(self):
        for score in [68.0, 70.0, 90.0, 100.0]:
            fb = _word_prosody_feedback("falling", 50.0, [4], score)
            assert fb.startswith("Good match"), (
                f"score={score}: 'Good match' must appear at/above 68, got: {fb!r}"
            )

    def test_tone_sandhi_does_not_crash_feedback(self):
        """T3+T3 → sandhi makes it T2+T3; feedback should still work."""
        words = [_word("你好", [3, 3], 65.0)]
        fb = generate_phrase_tone_feedback(words, 65.0)
        assert isinstance(fb, str) and len(fb) > 0

    def test_all_neutral_tones_handled_gracefully(self):
        """A word whose every syllable is neutral (T5) is scored but not
        graded for shape — feedback must still be coherent."""
        words = [_word("嗎", [5], 75.0), _word("呢", [5], 80.0)]
        fb = generate_phrase_tone_feedback(words, 77.5)
        assert isinstance(fb, str) and "Excellent" in fb


class TestWordProsodyFeedbackDiagnosis:
    """Below 48 the feedback must say what the student's pitch DID and give
    a concrete vocal action — not just restate that the shape was wrong."""

    def test_rose_when_tone4_expected_names_the_error_and_fix(self):
        fb = _word_prosody_feedback("rising", 60.0, [4], 30.0)
        assert "doesn't match yet" in fb
        assert "rose" in fb and "fall" in fb.lower()

    def test_fell_when_tone2_expected_names_the_error_and_fix(self):
        fb = _word_prosody_feedback("falling", 60.0, [2], 30.0)
        assert "fell" in fb and "rise" in fb.lower()

    def test_rose_when_tone3_expected_explains_dip_order(self):
        fb = _word_prosody_feedback("rising", 60.0, [3], 30.0)
        assert "dips first" in fb

    def test_flat_when_tone4_expected_calls_out_flatness(self):
        fb = _word_prosody_feedback("level", 5.0, [4], 30.0)
        assert "Too flat" in fb

    def test_moving_when_tone1_expected_asks_for_steady_note(self):
        fb = _word_prosody_feedback("dip", 70.0, [1], 30.0)
        assert "steady" in fb

    def test_mid_tier_appends_exaggeration_tip(self):
        fb = _word_prosody_feedback("rising", 40.0, [2], 55.0)
        assert fb.startswith("Recognizable")
        assert "Exaggerate" in fb

    def test_neutral_only_word_keeps_generic_message(self):
        fb = _word_prosody_feedback("level", 5.0, [5], 30.0)
        assert "doesn't match yet" in fb
        # No tones 1-4 to anchor a diagnosis — must not invent one.
        assert "Too flat" not in fb and "steady" not in fb
