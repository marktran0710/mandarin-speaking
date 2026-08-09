"""Contextual Mandarin tone realization.

A character's dictionary tone is not what a speaker actually produces in
connected speech. 好 is T3 in isolation, T3 with a shortened dip before a T4,
and T2 before another T3. Scoring a learner against the dictionary tone
therefore marks correct speech wrong.

This module turns dictionary ("underlying") tones into the set of surface
realizations that should be *accepted*, keeping full provenance so nothing is
silently overwritten:

    underlying_tone  →  context rules  →  accepted_surface_tones + rule

Design constraints this file exists to satisfy:

* The dictionary tone is never mutated. `ExpectedTone` carries both.
* More than one realization can be accepted (這個's 個 is fine as T4 or
  neutral), so the representation is a tuple, never a single int.
* Rules live here, not scattered through the scorer, so each one is testable
  in isolation and a linguist can read them without reading Praat code.
* Where the linguistics are genuinely ambiguous the code says so by accepting
  both readings, rather than picking one and pretending it is settled.

What this module deliberately does NOT do: it does not touch the legacy
scoring path. `chinese_tones.apply_tone_sandhi` still drives progression
exactly as before; this is the parallel diagnostic representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ── Realization labels ────────────────────────────────────────────────────
# What shape the syllable is expected to carry. The contour scorer may later
# use a different template per realization; today it only distinguishes tone
# classes, so `half_third` is carried as metadata and not yet scored
# differently (see KNOWN GAPS at the bottom of this file).
CANONICAL = "canonical"
FULL_THIRD = "full_third"
HALF_THIRD = "half_third"
THIRD_SANDHI = "third_tone_sandhi"
THIRD_CHAIN = "third_tone_chain"
NEUTRAL = "neutral"

# ── Rule identifiers (stable strings, safe to log and group by) ───────────
RULE_T3_T3 = "T3_T3"
RULE_T3_CHAIN = "T3_CHAIN_AMBIGUOUS_GROUPING"
RULE_YI = "YI_SANDHI"
RULE_BU = "BU_SANDHI"
RULE_NEUTRAL_LEXICAL = "NEUTRAL_LEXICAL"
RULE_NEUTRAL_OPTIONAL = "CONTEXTUAL_NEUTRAL_ALLOWED"


# ── Prosodic boundaries ───────────────────────────────────────────────────
# Third-tone sandhi is a phrase-internal process. It does not reach across a
# pause, so 友美，妳… must be read as [友美] then [妳], not as a run of three
# third tones. The pipeline loses this on its own: `caf_metrics.segment_words`
# splits the transcript on punctuation and then flattens the pieces into one
# token list, so by the time tokens arrive here the comma is gone. The raw
# transcript is therefore consulted separately — see `han_break_flags`.
STRONG_BOUNDARY_PUNCTUATION = frozenset(
    "，。？！；：、"      # full-width: comma, period, question, exclamation,
                        # semicolon, colon, enumeration comma
    ",.?!;:"            # ASCII equivalents, which learners' transcripts also use
    "…—\n\r"            # ellipsis, dash, line breaks
)


def _is_han(char: str) -> bool:
    return "一" <= char <= "鿿"


def han_break_flags(text: str) -> List[bool]:
    """For each Han character in ``text``, is it followed by a strong boundary?

    Returned in the same order as the characters the tone planner sees, since
    segmentation only ever drops non-Han characters and never reorders them.
    Whitespace alone is not treated as a boundary — a space between words does
    not block sandhi — but punctuation is.
    """
    positions = [i for i, char in enumerate(text or "") if _is_han(char)]
    flags: List[bool] = []
    for order, index in enumerate(positions):
        next_index = positions[order + 1] if order + 1 < len(positions) else len(text)
        between = text[index + 1 : next_index]
        flags.append(any(char in STRONG_BOUNDARY_PUNCTUATION for char in between))
    return flags


@dataclass(frozen=True)
class ExpectedTone:
    """What one syllable is allowed to sound like, and why.

    ``accepted_surface_tones`` is a tuple because several environments have
    more than one correct realization. A learner matching *any* of them has
    not made a tone error.
    """

    char: str
    underlying_tone: int
    accepted_surface_tones: Tuple[int, ...]
    realization: str = CANONICAL
    rule: Optional[str] = None
    #: Index of the jieba token this character came from. Kept so later work
    #: can reason about prosodic grouping, which is what longer third-tone
    #: chains actually depend on.
    token_index: int = 0
    #: True when this character opens a new token — the boundary information
    #: a future phrase-level grouping pass will need.
    boundary_before: bool = False
    #: True when a strong prosodic boundary (punctuation) follows. Sandhi does
    #: not cross one of these.
    boundary_after: bool = False

    @property
    def measurable_by_contour(self) -> bool:
        """Whether a pitch-contour scorer can say anything about this tone.

        Neutral tone has no fixed contour target, and the current scorer
        returns a constant for it rather than a measurement. Treating that
        constant as a score is exactly the confusion this refactor removes.
        """
        return 5 not in self.accepted_surface_tones or len(
            self.accepted_surface_tones
        ) > 1


# ── 一 / 不 ───────────────────────────────────────────────────────────────
# Both have a citation tone that almost never surfaces unchanged. pypinyin
# only gets these right when the whole word happens to be in its dictionary
# (不是 → bú shì is listed; 不去 → bú qù is not, and comes back as bù qù), so
# the rule is applied here from the citation tone rather than trusted from
# the lookup.
YI = "一"
BU = "不"
#: 一 keeps its citation T1 when it is an ordinal or a bare recited number.
_YI_ORDINAL_PREFIXES = {"第"}


def _yi_surface(next_tone: Optional[int], previous_char: Optional[str]) -> Tuple[int, ...]:
    """一: T2 before T4, T4 before T1/T2/T3, T1 as an ordinal or in isolation."""
    if previous_char in _YI_ORDINAL_PREFIXES:
        return (1,)
    if next_tone is None:
        # Sentence-final or recited as a bare number — citation tone.
        return (1,)
    if next_tone == 4:
        return (2,)
    if next_tone in (1, 2, 3):
        return (4,)
    # Before a neutral syllable (一個 yí ge) the rising realization is the
    # common one, but the neutral syllable's underlying tone is gone by this
    # point, so both readings are accepted rather than guessed at.
    return (2, 4)


def _bu_surface(next_tone: Optional[int]) -> Tuple[int, ...]:
    """不: T2 before T4, otherwise its citation T4."""
    if next_tone == 4:
        return (2,)
    return (4,)


# ── Optional neutral tone ─────────────────────────────────────────────────
# Syllables that are commonly, but not obligatorily, destressed. Both the
# full tone and neutral are accepted; marking either one wrong would be a
# false error. Extend this table rather than adding conditionals to a scorer.
_OPTIONAL_NEUTRAL_AFTER: Dict[str, Set[str]] = {
    # 這個 / 那個 / 哪個 / 一個 / 幾個 / 每個 — 個 is usually destressed.
    "個": {"這", "那", "哪", "一", "幾", "每", "兩", "三", "四", "五", "六"},
}
#: Suffixes that are neutral in essentially every environment.
_OPTIONAL_NEUTRAL_SUFFIX: Set[str] = {"們", "子", "頭", "麼", "們"}


def _optional_neutral(char: str, previous_char: Optional[str]) -> bool:
    if char in _OPTIONAL_NEUTRAL_SUFFIX:
        return True
    allowed = _OPTIONAL_NEUTRAL_AFTER.get(char)
    return bool(allowed and previous_char in allowed)


# ── The processor ─────────────────────────────────────────────────────────


def plan_expected_tones(
    chars: Sequence[str],
    underlying_tones: Sequence[int],
    token_indices: Optional[Sequence[int]] = None,
    breaks_after: Optional[Sequence[bool]] = None,
) -> List[ExpectedTone]:
    """Turn one utterance's dictionary tones into accepted surface targets.

    Operates over the **whole utterance**, not one word at a time. That is the
    fix for the bug where 很好 — which jieba splits into 很 / 好 — never got
    third-tone sandhi, because the old per-token call saw a single T3 with
    nothing after it and left 很 to be scored against a full dipping template.

    ``token_indices`` says which jieba token each character came from.

    ``breaks_after`` marks characters followed by a strong prosodic boundary
    (see ``han_break_flags``). Sandhi does not reach across a pause, so a T3
    run is cut at every such mark: 友美，妳 is [友美] + [妳], not a chain of
    three. Omitting it reproduces the old boundary-blind behaviour, which is
    why the analyzer always supplies it.
    """
    if not chars or len(chars) != len(underlying_tones):
        return []
    indices = list(token_indices or [0] * len(chars))
    if len(indices) != len(chars):
        indices = [0] * len(chars)
    breaks = list(breaks_after or [False] * len(chars))
    if len(breaks) != len(chars):
        breaks = [False] * len(chars)

    # Pass 1 — 一 / 不. These rewrite the tone the later rules see, so they run
    # first. Working tones start from the dictionary lookup.
    working: List[int] = [int(t) for t in underlying_tones]
    underlying: List[int] = list(working)
    accepted: List[Tuple[int, ...]] = [(t,) for t in working]
    realizations: List[str] = [CANONICAL] * len(chars)
    rules: List[Optional[str]] = [None] * len(chars)

    for i, char in enumerate(chars):
        following = working[i + 1] if i + 1 < len(chars) else None
        previous = chars[i - 1] if i > 0 else None
        if char == YI:
            underlying[i] = 1
            surface = _yi_surface(following, previous)
            accepted[i] = surface
            working[i] = surface[0]
            rules[i] = RULE_YI
        elif char == BU:
            underlying[i] = 4
            surface = _bu_surface(following)
            accepted[i] = surface
            working[i] = surface[0]
            rules[i] = RULE_BU

    # Pass 2 — third-tone sandhi. Crosses word boundaries (很/好) but never a
    # prosodic one (友美，| 妳).
    for start, end in _third_tone_runs(working, breaks):
        length = end - start
        if length < 2:
            continue
        if length == 2:
            # The uncontroversial case: T3 T3 → T2 T3.
            accepted[start] = (2,)
            realizations[start] = THIRD_SANDHI
            rules[start] = RULE_T3_T3
        else:
            # Three or more in a row. The actual output depends on how the
            # speaker groups the phrase — 我很好 is [2,2,3] read as one unit
            # but [3,2,3] with a break after 我 — and nothing available here
            # tells us which grouping the learner used. Both readings are
            # accepted for the non-final syllables instead of imposing one
            # global transformation. See test_tone_context for the documented
            # behaviour.
            for i in range(start, end - 1):
                accepted[i] = (2, 3)
                realizations[i] = THIRD_CHAIN
                rules[i] = RULE_T3_CHAIN

    # Pass 3 — half third. A T3 that keeps its T3 target but is not phrase
    # final and not before another T3 is realized as the low part only: it
    # does not need the full fall-rise. Categorically still T3; the label is
    # what a future contour template will key on. A T3 before a pause is
    # phrase-final and keeps the full dip whatever follows the pause.
    for i, tone in enumerate(working):
        if accepted[i] != (3,):
            continue
        following = None if breaks[i] else (
            working[i + 1] if i + 1 < len(chars) else None
        )
        if following is None or following == 3:
            realizations[i] = FULL_THIRD
        else:
            realizations[i] = HALF_THIRD

    # Pass 4 — neutral tone, lexical and optional.
    for i, char in enumerate(chars):
        previous = chars[i - 1] if i > 0 else None
        if underlying[i] == 5:
            accepted[i] = (5,)
            realizations[i] = NEUTRAL
            rules[i] = rules[i] or RULE_NEUTRAL_LEXICAL
        elif _optional_neutral(char, previous) and 5 not in accepted[i]:
            # Both the full tone and the destressed form are correct.
            accepted[i] = tuple(accepted[i]) + (5,)
            rules[i] = RULE_NEUTRAL_OPTIONAL

    plan: List[ExpectedTone] = []
    for i, char in enumerate(chars):
        plan.append(
            ExpectedTone(
                char=char,
                underlying_tone=underlying[i],
                accepted_surface_tones=tuple(accepted[i]),
                realization=realizations[i],
                rule=rules[i],
                token_index=indices[i],
                boundary_before=i == 0 or indices[i] != indices[i - 1],
                boundary_after=breaks[i],
            )
        )
    return plan


def _third_tone_runs(
    tones: Sequence[int], breaks_after: Optional[Sequence[bool]] = None
) -> List[Tuple[int, int]]:
    """Maximal [start, end) spans of consecutive T3 syllables.

    A span is cut by a strong prosodic boundary as well as by a non-T3
    syllable: sandhi is phrase-internal, so 友美，妳 yields the runs [0,2) and
    [2,3) rather than one run of three.
    """
    breaks = list(breaks_after or [False] * len(tones))
    runs: List[Tuple[int, int]] = []
    start: Optional[int] = None
    for i, tone in enumerate(tones):
        if tone == 3:
            if start is None:
                start = i
            if i < len(breaks) and breaks[i]:
                runs.append((start, i + 1))
                start = None
        elif start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(tones)))
    return runs


def plan_for_tokens(
    tokens: Sequence[str],
    hint_tones: Optional[Sequence[int]] = None,
    text: Optional[str] = None,
) -> List[ExpectedTone]:
    """Convenience wrapper: jieba tokens in, one ExpectedTone per Chinese char.

    Tones come from ``hint_tones`` when the caller has the pinyin actually
    displayed to the student (teacher-corrected readings beat a second
    independent lookup), otherwise from pypinyin per token so polyphones read
    the way they do inside their own word.
    """
    import re

    from chinese_tones import word_tones

    chars: List[str] = []
    tones: List[int] = []
    indices: List[int] = []
    for token_index, token in enumerate(tokens):
        if not re.search(r"[一-鿿]", token):
            continue
        token_tones = word_tones(token)
        for offset, char in enumerate(token):
            if offset >= len(token_tones):
                break
            chars.append(char)
            tones.append(token_tones[offset])
            indices.append(token_index)

    if hint_tones is not None and len(hint_tones) == len(chars):
        tones = [int(t) for t in hint_tones]

    # Punctuation never survives into `tokens`, so boundaries are read off the
    # raw transcript instead. Character order is preserved by segmentation, so
    # the flags line up positionally with `chars`.
    breaks = han_break_flags(text) if text else None
    if breaks is not None and len(breaks) != len(chars):
        breaks = None

    return plan_expected_tones(chars, tones, indices, breaks)


# ── KNOWN GAPS (deliberate, tracked) ──────────────────────────────────────
# * `half_third` is represented but not yet scored differently: the contour
#   scorer still uses one T3 template for both realizations. Adding a
#   dedicated half-third template changes scores, and therefore progression,
#   so it is out of scope for a patch that must leave progression frozen.
# * Longer T3 chains accept both readings rather than modelling prosodic
#   grouping. Doing it properly needs phrase boundaries the pipeline does not
#   currently produce; `token_index`/`boundary_before` are carried for that.
# * 一 before a neutral syllable accepts both T2 and T4 because the neutral
#   syllable's underlying tone is not recoverable here.
# * The optional-neutral table is a starting set, not a survey. It is data,
#   not logic, precisely so it can grow without touching any decision code.
