from pinyin_service import canonical_pinyin, canonical_pinyin_tone3


def test_canonical_taiwan_pinyin_uses_backend_dictionary():
    assert canonical_pinyin("聽音樂") == "tīng yīn yuè"
    assert canonical_pinyin("什麼") == "shén me"
    assert canonical_pinyin("妳這個週末要做什麼") == (
        "nǐ zhè gè zhōu mò yào zuò shén me"
    )


def test_canonical_taiwan_pinyin_exposes_tone_numbers_for_scoring():
    assert canonical_pinyin_tone3("什麼") == "shen2 me5"
