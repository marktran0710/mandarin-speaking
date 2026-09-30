"""The known script -> expected syllables (tone, sandhi, word grouping)."""

from services.pronunciation.script import build_expected_syllables

SENTENCE = "友美，妳這個週末要做什麼？"


def test_each_han_character_becomes_one_syllable_in_order():
    syllables = build_expected_syllables(SENTENCE)
    assert "".join(s.hanzi for s in syllables) == "友美妳這個週末要做什麼"
    assert [s.index for s in syllables] == list(range(11))


def test_pinyin_is_tone_numbered_and_tone_fields_follow_the_sandhi_plan():
    first, second = build_expected_syllables(SENTENCE)[:2]
    assert (first.pinyin, second.pinyin) == ("you3", "mei3")
    # 友美 is a third-tone pair: the first surfaces as tone 2 but is citation tone 3.
    assert first.citation_tone == 3 and first.expected_tone == 2
    assert first.accepted_tones == (2,)
    assert second.expected_tone == 3


def test_a_lexical_neutral_tone_has_no_contour_target():
    last = build_expected_syllables(SENTENCE)[-1]
    assert last.hanzi == "麼"
    assert last.expected_tone == 5
    assert last.measurable_by_contour is False


def test_syllables_of_one_word_share_a_word_index():
    syllables = build_expected_syllables(SENTENCE)
    assert syllables[0].word_index == syllables[1].word_index  # 友美
    assert syllables[1].word_index != syllables[2].word_index  # 美 | 妳


def test_text_without_han_characters_yields_no_syllables():
    assert build_expected_syllables("？！ abc") == ()
