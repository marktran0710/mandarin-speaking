"""The known script -> expected syllables.

Tone, sandhi and word grouping come from the existing validated tone planner
(``helpers.tone_context.plan_for_tokens``: third-tone sandhi, half-third, 一/不,
lexical neutral tones) rather than a second lookup, so the evaluator can never
disagree with the coaching pipeline about what a syllable should sound like.
"""

from __future__ import annotations

from helpers.caf_metrics import segment_words
from helpers.pinyin_service import canonical_pinyin_tone3
from helpers.tone_context import plan_for_tokens

from domain.pronunciation.types import ExpectedSyllable


def build_expected_syllables(text: str) -> tuple[ExpectedSyllable, ...]:
    tokens = segment_words(text or "")
    if not tokens:
        return ()
    plan = plan_for_tokens(tokens, None, text=text)

    pinyin: list[str] = []
    for token in tokens:
        pinyin.extend(canonical_pinyin_tone3(token).split())
    if len(pinyin) != len(plan):
        # A reading the dictionary could not split one-to-one: fall back to the
        # planned tone digit so the syllable is still labelled consistently.
        pinyin = [f"{item.char}{item.underlying_tone}" for item in plan]

    return tuple(
        ExpectedSyllable(
            index=index,
            hanzi=item.char,
            pinyin=pinyin[index],
            citation_tone=item.underlying_tone,
            expected_tone=item.accepted_surface_tones[0],
            accepted_tones=tuple(item.accepted_surface_tones),
            word_index=item.token_index,
            realization=item.realization,
        )
        for index, item in enumerate(plan)
    )
