"""Builds a validated bank of quiz questions for one (story, level, mode).

Until now the quiz assembled itself in the browser at run time from per-word
material stored on the story, which had two consequences: nothing could be
reviewed before a student saw it, and the material had no per-level variants
so a Medium quiz served Easy's cloze sentences against Medium's word list.

Here a bank is built once, up front, and stored as finished questions:

    words for (story, level)
        -> material            (the existing single-shot generators)
        -> candidates          (deterministic assembly, kind mix per tier)
        -> quiz_pipeline       (blind solver + judge, repair up to twice)
        -> the questions that survived

Material is generated per level and never stored, which is what makes the
tier mix-up impossible rather than merely fixed.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence

from quiz_pipeline import (
    CLOZE_BLANK,
    OPTION_COUNT,
    BankResult,
    Candidate,
    Chat,
    validate_candidates,
)

logger = logging.getLogger("speaking_app.quiz_bank")

# Mirrors TIER_KIND_WEIGHTS in src/components/StoryVocabQuiz.tsx — the mix
# that gives each tier its character (tier 1 direct forms only, tiers 2-3
# add the harder shapes). Kept in step by hand; the frontend still needs its
# copy for stories that have no bank yet and fall back to run-time assembly.
TIER_KIND_WEIGHTS: dict[str, list[tuple[str, int]]] = {
    "tier1": [("translation", 50), ("pinyin", 20), ("reverse", 30)],
    "tier2": [
        ("translation", 25),
        ("pinyin", 15),
        ("reverse", 15),
        ("cloze", 15),
        ("synonym", 10),
        ("listening", 20),
    ],
    "tier3": [
        ("translation", 15),
        ("pinyin", 15),
        ("reverse", 15),
        ("cloze", 15),
        ("synonym", 10),
        ("pos", 10),
        ("listening", 20),
    ],
}

# Kinds whose options come from an LLM. The rest are assembled from the
# story's own word list and need no generation call at all.
AI_KINDS = {"translation", "cloze", "synonym"}

MAX_BANK_SIZE = 100


@dataclass
class BankWord:
    word: str
    translation: str
    pinyin: str = ""
    pos: str = ""
    context: str = ""  # the scene sentence the word appears in


@dataclass
class MaterialForWord:
    """What the AI generators produced for one word."""

    distractors: list[str]
    cloze: list[tuple[str, list[str]]]  # (sentence containing the word, wrong words)
    synonyms: list[tuple[str, list[str]]]  # (synonym, wrong words)


# A material generator: (words) -> {word: MaterialForWord}. Injected so the
# bank builder can be tested without network access and so main.py keeps
# ownership of the provider fallback chain.
MaterialSource = Callable[[Sequence[BankWord]], Awaitable[dict[str, MaterialForWord]]]


def _quota(mode: str, target: int) -> dict[str, int]:
    """How many questions of each kind a bank of `target` should aim for,
    proportional to the tier's weights."""
    weights = TIER_KIND_WEIGHTS.get(mode) or TIER_KIND_WEIGHTS["tier1"]
    total = sum(w for _, w in weights)
    quota = {kind: round(target * weight / total) for kind, weight in weights}
    # Rounding can drift a question or two either way; the shortfall is
    # harmless because assembly is capped at `target` anyway.
    return {k: v for k, v in quota.items() if v > 0}


def _pick_wrong_options(
    correct: str,
    preferred: Sequence[str],
    fallback_pool: Sequence[str],
    rng: random.Random,
) -> list[str] | None:
    """Three wrong options: the AI's own distractors first, then other words
    from the story. Returns None when neither source can fill the slots —
    a question with two options is not worth shipping."""
    need = OPTION_COUNT - 1
    seen = {correct.strip().lower()}
    chosen: list[str] = []
    for option in list(preferred) + list(fallback_pool):
        key = option.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        chosen.append(option)
        if len(chosen) == need:
            return chosen
    return None


def assemble_candidates(
    words: Sequence[BankWord],
    material: dict[str, MaterialForWord],
    mode: str,
    target: int,
    *,
    rng: random.Random | None = None,
) -> list[Candidate]:
    """Every question the word list can produce for this tier, shuffled and
    capped at `target`. Deliberately over-produces: the pipeline will drop
    some, and a bank built exactly to size would always come up short."""
    rng = rng or random.Random(f"{mode}:{target}:{len(words)}")
    quota = _quota(mode, target)
    all_words = [w.word for w in words]
    all_translations = [w.translation for w in words if w.translation]
    all_pinyin = [w.pinyin for w in words if w.pinyin]

    buckets: dict[str, list[Candidate]] = {kind: [] for kind in quota}

    for entry in words:
        others = [w for w in all_words if w != entry.word]
        mat = material.get(entry.word)
        gloss = " / ".join(p for p in (entry.translation, entry.pos) if p)

        def make(kind: str, prompt: str, answer: str, wrongs: list[str] | None, tag: str = "0"):
            if kind not in buckets or not wrongs:
                return
            buckets[kind].append(
                Candidate(
                    kind=kind,
                    word=entry.word,
                    prompt=prompt,
                    answer=answer,
                    wrong_options=tuple(wrongs),
                    key=f"{entry.word}:{kind}:{tag}",
                    gloss=gloss,
                    context=entry.context,
                )
            )

        if entry.translation:
            make(
                "translation",
                entry.word,
                entry.translation,
                _pick_wrong_options(
                    entry.translation,
                    mat.distractors if mat else [],
                    [t for t in all_translations if t != entry.translation],
                    rng,
                ),
            )
            make(
                "reverse",
                entry.translation,
                entry.word,
                _pick_wrong_options(entry.word, [], others, rng),
            )
            make(
                "listening",
                entry.word,
                entry.word,
                _pick_wrong_options(entry.word, [], others, rng),
            )

        if entry.pinyin:
            make(
                "pinyin",
                entry.word,
                entry.pinyin,
                _pick_wrong_options(
                    entry.pinyin, [], [p for p in all_pinyin if p != entry.pinyin], rng
                ),
            )

        if entry.pos:
            make(
                "pos",
                entry.word,
                entry.pos,
                _pick_wrong_options(
                    entry.pos, [], [p for p in ("N", "V", "ADJ", "ADV") if p != entry.pos], rng
                ),
            )

        if mat:
            for index, (sentence, wrongs) in enumerate(mat.cloze):
                if entry.word not in sentence:
                    continue
                make(
                    "cloze",
                    sentence.replace(entry.word, CLOZE_BLANK, 1),
                    entry.word,
                    _pick_wrong_options(entry.word, wrongs, others, rng),
                    tag=str(index),
                )
            for index, (synonym, wrongs) in enumerate(mat.synonyms):
                make(
                    "synonym",
                    entry.word,
                    synonym,
                    _pick_wrong_options(synonym, wrongs, others, rng),
                    tag=str(index),
                )

    # Take each kind's share, then top up from whatever is left over so a
    # kind the word list can't supply doesn't shrink the whole bank.
    picked: list[Candidate] = []
    leftovers: list[Candidate] = []
    for kind, want in quota.items():
        pool = buckets.get(kind, [])
        rng.shuffle(pool)
        picked.extend(pool[:want])
        leftovers.extend(pool[want:])
    rng.shuffle(leftovers)
    picked.extend(leftovers[: max(0, target - len(picked))])
    rng.shuffle(picked)
    return picked[:target]


def _is_excluded(
    exclusions: Sequence[dict], word: str, kind: str, index: int | None = None
) -> bool:
    return any(
        e.get("word") == word
        and e.get("kind") == kind
        and (e.get("index") is None or e.get("index") == index)
        for e in exclusions
    )


def candidates_for_review(
    words: Sequence[dict], exclusions: Sequence[dict]
) -> list[Candidate]:
    """Every currently-live AI question candidate for a story tier, as the
    Quiz Review page's 'Validate' action checks them — one Candidate per
    distractor pool (kind 'translation'), cloze candidate, and synonym
    candidate, skipping whatever the teacher already excluded. Mirrors
    scripts/dump-quiz-questions.py's word_questions() validity rules
    (collectQuizEntries parity) so a validated item matches what the quiz
    could actually serve. Look-alike pools aren't validated: they're plain
    word lists with no "is this also correct" question shape to judge."""
    out: list[Candidate] = []
    for entry in words:
        word = entry["word"]
        translation = (entry.get("translation") or "").strip()

        if not _is_excluded(exclusions, word, "distractors"):
            wrongs = [d for d in entry.get("distractors", []) if d and d != translation]
            if translation and wrongs:
                out.append(
                    Candidate(
                        kind="translation",
                        word=word,
                        prompt=word,
                        answer=translation,
                        wrong_options=tuple(wrongs[: OPTION_COUNT - 1]),
                        key=f"{word}:distractors",
                    )
                )

        for i, candidate in enumerate(entry.get("cloze", [])):
            if _is_excluded(exclusions, word, "cloze", i):
                continue
            sentence = candidate.get("sentence", "")
            wrongs = [d for d in candidate.get("distractors", []) if d and d != word]
            if not wrongs or sentence.count(word) != 1:
                continue
            out.append(
                Candidate(
                    kind="cloze",
                    word=word,
                    prompt=sentence.replace(word, CLOZE_BLANK, 1),
                    answer=word,
                    wrong_options=tuple(wrongs[: OPTION_COUNT - 1]),
                    key=f"{word}:cloze:{i}",
                )
            )

        for i, candidate in enumerate(entry.get("synonym", [])):
            if _is_excluded(exclusions, word, "synonym", i):
                continue
            synonym = candidate.get("synonym", "")
            wrongs = [d for d in candidate.get("distractors", []) if d and d != synonym]
            if not synonym or synonym == word or not wrongs:
                continue
            out.append(
                Candidate(
                    kind="synonym",
                    word=word,
                    prompt=word,
                    answer=synonym,
                    wrong_options=tuple(wrongs[: OPTION_COUNT - 1]),
                    key=f"{word}:synonym:{i}",
                )
            )
    return out


async def build_bank(
    chat: Chat,
    material_source: MaterialSource,
    words: Sequence[BankWord],
    mode: str,
    target: int,
    *,
    max_repairs: int = 2,
) -> BankResult:
    """Material -> candidates -> validation, for one (story, level, mode)."""
    target = max(1, min(target, MAX_BANK_SIZE))

    needs_ai = bool(AI_KINDS & set(_quota(mode, target)))
    material: dict[str, MaterialForWord] = {}
    if needs_ai:
        try:
            material = await material_source(words)
        except Exception as exc:  # noqa: BLE001 - a bank of the non-AI kinds still beats nothing
            logger.warning("quiz material generation failed, building without it: %s", exc)

    # Over-produce by half so the pipeline's drops don't leave the bank
    # short of what the teacher asked for.
    candidates = assemble_candidates(words, material, mode, int(target * 1.5))
    result = await validate_candidates(chat, candidates, max_repairs=max_repairs)
    if len(result.kept) > target:
        result.kept = result.kept[:target]
    return result
