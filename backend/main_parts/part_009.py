

def correct_homophones(text: str, vocab_hint: str) -> str:
    """Replace homophones in transcript with vocab words that share the same tone-aware pinyin."""
    vocab_words = [w.strip() for w in vocab_hint.split(",") if w.strip()]
    # Build mapping: pinyin-with-tones -> vocab word (longest match wins)
    vocab_words.sort(key=len, reverse=True)
    pinyin_to_vocab: dict[str, str] = {}
    for word in vocab_words:
        py = canonical_pinyin_tone3(word)
        pinyin_to_vocab[py] = word

    if not pinyin_to_vocab:
        return text

    # Slide a window over the transcript characters and replace matching runs
    chars = list(text)
    max_len = max(len(w) for w in vocab_words)
    i = 0
    result: list[str] = []
    while i < len(chars):
        replaced = False
        for length in range(min(max_len, len(chars) - i), 0, -1):
            segment = "".join(chars[i : i + length])
            py = canonical_pinyin_tone3(segment)
            if py in pinyin_to_vocab and segment != pinyin_to_vocab[py]:
                result.append(pinyin_to_vocab[py])
                i += length
                replaced = True
                break
        if not replaced:
            result.append(chars[i])
            i += 1
    return "".join(result)


def convert_to_traditional_chinese(text: str) -> str:
    try:
        from opencc import OpenCC

        return OpenCC("s2twp").convert(text)
    except Exception:
        return text
