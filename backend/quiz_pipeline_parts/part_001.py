"""Multi-agent validation for generated vocabulary-quiz questions.

The single-shot generators in main.py (``generate_vocab_cloze_with_groq`` and
friends) produce one candidate per word with no verification, and an audit of
321 shipped questions found 136 broken — 96 of them the same defect: a
*distractor that is also a correct answer*. "＿＿＿是我的好朋友" with options
友美 / 小美 / 美麗 / 美好 has two right answers, because both 友美 and 小美 are
names.

A critic that is shown the intended answer reads the question forwards and
nods along; that is exactly the loop that let those 96 through. So the check
here is adversarial instead:

    generator -> pre-gate (code) -> solver (blind) -> judge -> repair -> ...

The solver never sees which option was meant to be correct. It answers the
question the way a strong student would and reports every option it thinks
would also be accepted. The judge then compares that blind attempt against
the intended answer and rules on the item.

Every LLM call goes through an injected ``chat`` callable, so the orchestration
can be tested — and the eval harness replayed — without network access.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field, replace
from typing import Awaitable, Callable, Iterable, Sequence

logger = logging.getLogger("speaking_app.quiz_pipeline")

CLOZE_BLANK = "＿＿＿"
OPTION_COUNT = 4

# How many items ride in one solver/judge call. Small enough that a single
# bad item can't derail the whole batch's JSON, large enough that a 100-item
# bank costs ~10 calls per stage rather than 100.
BATCH_SIZE = 10

# An LLM call: (system_prompt, user_prompt) -> raw response text.
Chat = Callable[[str, str], Awaitable[str]]

QuestionKind = str  # translation | cloze | reverse | synonym | pinyin | pos | listening


@dataclass(frozen=True)
class Candidate:
    """One quiz question as the generator proposed it."""

    kind: QuestionKind
    word: str
    prompt: str
    answer: str
    wrong_options: tuple[str, ...]
    # Stable id so shuffling is reproducible across runs and stages.
    key: str = ""
    # Story context for the judge ONLY — never shown to the solver. A
    # translation item's prompt is the bare word, so handing the solver the
    # gloss would hand it the answer. The judge already knows the intended
    # answer, so it loses nothing and gains what it needs: without this the
    # judge rejects a story's character names (友美) as "not real Mandarin".
    gloss: str = ""
    context: str = ""

    @property
    def options(self) -> tuple[str, ...]:
        return (self.answer, *self.wrong_options)


@dataclass(frozen=True)
class SolverVerdict:
    """The blind attempt. `choice` is what the solver picked without ever
    being told the intended answer; `also_correct` is what it would ALSO
    accept — the field that catches multi-fit items."""

    choice: str
    also_correct: tuple[str, ...]
    confidence: str  # "high" | "low"
    why: str


@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str  # "pass" | "repair" | "reject"
    replace: tuple[str, ...]  # options the judge wants swapped out
    reason: str


@dataclass
class ItemOutcome:
    candidate: Candidate
    status: str  # "pass" | "dropped"
    stage: str  # where it settled: "pre-gate" | "solver" | "judge" | "repair"
    rounds: int
    reason: str
    solver: SolverVerdict | None = None
    judge: JudgeVerdict | None = None


@dataclass
class BankResult:
    kept: list[ItemOutcome] = field(default_factory=list)
    dropped: list[ItemOutcome] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        by_reason: dict[str, int] = {}
        for item in self.dropped:
            by_reason[item.reason] = by_reason.get(item.reason, 0) + 1
        return by_reason


# ── Stage 2: pre-gate (deterministic, no LLM) ─────────────────────────────
# Rules that need no judgement at all. Running them first keeps obviously
# broken items from spending a solver call. Mirrors the frontend's
# quizAudit.ts rules that apply to a single question in isolation.


def _normalize(text: str) -> str:
    return re.sub(r"[.。!！?？\s]+$", "", text.strip().lower())


def pre_gate(candidate: Candidate) -> str | None:
    """Returns the name of the rule the candidate breaks, or None if it
    survives to the solver."""
    answer = _normalize(candidate.answer)
    if not answer:
        return "empty-answer"
    if not candidate.word.strip():
        return "empty-word"

    wrongs = [_normalize(w) for w in candidate.wrong_options]
    if any(not w for w in wrongs):
        return "empty-option"
    if answer in wrongs:
        return "answer-duplicated-in-options"
    if len(set(wrongs)) != len(wrongs):
        return "duplicate-options"
    if len(candidate.wrong_options) < OPTION_COUNT - 1:
        return "too-few-options"

    if candidate.kind == "cloze":
        if CLOZE_BLANK not in candidate.prompt:
            return "cloze-no-blank"
        # The answer appearing outside the blank hands the student the
        # answer in the prompt itself.
        if candidate.answer in candidate.prompt.replace(CLOZE_BLANK, ""):
            return "cloze-answer-leaked"
        if candidate.prompt.count(CLOZE_BLANK) != 1:
            return "cloze-multi-blank"

    return None


# ── Stage 3: solver (blind) ───────────────────────────────────────────────

_KIND_QUESTION = {
    "translation": 'What does the Traditional Chinese word "{word}" mean?',
    "reverse": 'Which Traditional Chinese word means "{prompt}"?',
    "cloze": "Which word fills the blank?\n{prompt}",
    "synonym": 'Which word means the same as "{prompt}"?',
    "pinyin": 'How is "{prompt}" read in pinyin?',
    "pos": 'What part of speech is "{prompt}"?',
    "listening": 'Which word is being read aloud? (spoken word: "{prompt}")',
}

# What "also correct" means depends entirely on the question shape, and a
# single bar gets it wrong in both directions. For a fill-in-the-blank, any
# option that yields a natural true sentence is a second answer and breaks
# the item. For a translation, a *related* word is not a second answer — it
# is the distractor doing its job, and treating it as a defect throws away
# the good items. One shared rule scored 90% recall but 40% false positives
# on the labelled audit set; these per-kind bars are the fix.
_ALSO_CORRECT_BAR = {
    "cloze": (
        "another option that also makes this sentence natural AND true. "
        "Judge the sentence as written — if swapping the option in produces "
        "Mandarin a native speaker would accept, it is also correct."
    ),
    "translation": (
        "another option that is an ACCURATE translation of this exact word. "
        "An option that is merely related, near in meaning, or in the same "
        "topic is NOT also-correct — that is a normal distractor."
    ),
    "reverse": (
        "another Chinese word that genuinely means this English phrase. "
        "A word in the same topic area is NOT also-correct."
    ),
    "synonym": (
        "another option that a dictionary would list as meaning the same "
        "thing. Loose association is NOT also-correct."
    ),
    "pinyin": "another spelling that is a valid standard reading of this word.",
    "pos": "another part-of-speech label that is equally defensible for this word.",
    "listening": "another word pronounced identically to the one spoken.",
}
_DEFAULT_BAR = "another option that is equally and genuinely correct."

SOLVER_SYSTEM = (
    "You are an experienced Traditional Chinese teacher taking a vocabulary "
    "quiz written by someone else. You do NOT know which option the author "
    "intended. Answer each question on its merits.\n\n"
    "Your second job matters more than the first: quiz items are often broken "
    "because more than one option is genuinely acceptable. Each question below "
    "states what counts as 'also correct' for its type — apply that bar "
    "exactly, neither wider nor narrower. A good quiz has close, tempting "
    "distractors; being close is not the same as being correct.\n\n"
    "Set confidence to 'low' only when you cannot tell which option the "
    "question is asking for at all.\n\n"
    'Respond with JSON only: {"results": [{"n": 1, "choice": "<exact option '
    'text>", "alsoCorrect": ["<exact option text>", ...], "confidence": '
    '"high"|"low", "why": "<one short sentence>"}]}'
)


def _shuffled_options(candidate: Candidate, seed: str) -> list[str]:
    """Options in a stable but answer-position-neutral order. Seeded on the
    candidate so a rerun asks the identical question — otherwise a flaky
    solver result can't be told apart from a reshuffle."""
    options = list(candidate.options)
    random.Random(f"{seed}:{candidate.key or candidate.prompt}").shuffle(options)
    return options


def _solver_prompt(batch: Sequence[Candidate], seed: str) -> str:
    lines = []
    for i, candidate in enumerate(batch, start=1):
        template = _KIND_QUESTION.get(candidate.kind, "{prompt}")
        question = template.format(word=candidate.word, prompt=candidate.prompt)
        options = _shuffled_options(candidate, seed)
        rendered = "\n".join(f"   - {option}" for option in options)
        bar = _ALSO_CORRECT_BAR.get(candidate.kind, _DEFAULT_BAR)
        lines.append(
            f"{i}. {question}\n   Options:\n{rendered}\n"
            f"   'Also correct' here means: {bar}"
        )
    return (
        "Answer each question, then list every other option that would also be "
        "acceptable.\n\n" + "\n\n".join(lines)
    )


async def run_solver(
    chat: Chat, batch: Sequence[Candidate], seed: str = "solver"
) -> list[SolverVerdict | None]:
    raw = await chat(SOLVER_SYSTEM, _solver_prompt(batch, seed))
    rows = _parse_rows(raw, len(batch))
    verdicts: list[SolverVerdict | None] = []
    for row in rows:
        if row is None:
            verdicts.append(None)
            continue
        verdicts.append(
            SolverVerdict(
                choice=str(row.get("choice", "")).strip(),
                also_correct=tuple(
                    str(x).strip() for x in row.get("alsoCorrect", []) or [] if str(x).strip()
                ),
                confidence=str(row.get("confidence", "low")).strip().lower(),
                why=str(row.get("why", "")).strip(),
            )
        )
    return verdicts


# ── Stage 4: judge ────────────────────────────────────────────────────────

JUDGE_SYSTEM = (
    "You are the editor of a Traditional Chinese vocabulary quiz for A1-A2 "
    "learners. For each item you are given the question, the answer its author "
    "intended, and a blind solve by a teacher who was NOT told the intended "
    "answer.\n\n"
    "Rule on each item:\n"
    '- "pass": the blind solve landed on the intended answer and found no '
    "other acceptable option. The item is sound.\n"
    '- "repair": the item is fixable by swapping specific wrong options — the '
    "blind solve accepted an option it should not have, or hesitated because a "
    "distractor was too close. Put those options in \"replace\".\n"
    '- "reject": the item is broken at its root — the intended answer is wrong '
    "or unnatural, the prompt gives no way to decide, the word is not real "
    "Mandarin, or the answer is vulgar or otherwise unfit for a course aimed "
    "at beginners and children. Swapping options would not save it.\n\n"
    "Some items test proper names invented for the story (characters, places). "
    "Those are legitimate vocabulary for this course — never reject a word "
    "just for being a name rather than a dictionary entry.\n\n"
    "Two standing rules:\n"
    "1. Close distractors are the POINT of a good quiz. An option that is "
    "merely near in meaning, in the same topic, or easy to confuse is working "
    "as intended — that alone is never grounds for repair. Only rule repair "
    "when an option is genuinely, equally correct.\n"
    "2. Where the blind solve did claim an option is equally correct, trust it "
    "over the author and repair the item — that is the defect this review "
    "exists to catch.\n"
    "Default to \"pass\" when the blind solve found the intended answer and "
    "raised nothing specific.\n\n"
    'Respond with JSON only: {"results": [{"n": 1, "verdict": '
    '"pass"|"repair"|"reject", "replace": ["<exact option text>", ...], '
    '"reason": "<one short sentence>"}]}'
)


def _judge_prompt(pairs: Sequence[tuple[Candidate, SolverVerdict]]) -> str:
    lines = []
    for i, (candidate, solver) in enumerate(pairs, start=1):
        template = _KIND_QUESTION.get(candidate.kind, "{prompt}")
        question = template.format(word=candidate.word, prompt=candidate.prompt)
        also = ", ".join(solver.also_correct) if solver.also_correct else "(none)"
        context = ""
        if candidate.gloss:
            context += f"\n   The word being tested: {candidate.word} — {candidate.gloss}"
        if candidate.context:
            context += f"\n   Where it appears in the story: {candidate.context}"
        lines.append(
            f"{i}. {question}{context}\n"
            f"   All options: {', '.join(candidate.options)}\n"
            f"   Intended answer: {candidate.answer}\n"
            f"   Blind solve picked: {solver.choice}\n"
            f"   Blind solve also accepts: {also}\n"
            f"   Blind solve confidence: {solver.confidence}\n"
            f"   Blind solve reasoning: {solver.why}"
        )
    return "Rule on each item.\n\n" + "\n\n".join(lines)


async def run_judge(
    chat: Chat, pairs: Sequence[tuple[Candidate, SolverVerdict]]
) -> list[JudgeVerdict | None]:
    raw = await chat(JUDGE_SYSTEM, _judge_prompt(pairs))
    rows = _parse_rows(raw, len(pairs))
    verdicts: list[JudgeVerdict | None] = []
    for row in rows:
        if row is None:
            verdicts.append(None)
            continue
        verdict = str(row.get("verdict", "")).strip().lower()
        if verdict not in {"pass", "repair", "reject"}:
            verdict = "reject"
        verdicts.append(
            JudgeVerdict(
                verdict=verdict,
                replace=tuple(
                    str(x).strip() for x in row.get("replace", []) or [] if str(x).strip()
                ),
                reason=str(row.get("reason", "")).strip(),
            )
        )
    return verdicts


# ── Stage 5: repair ───────────────────────────────────────────────────────

REPAIR_SYSTEM = (
    "You write distractors for a Traditional Chinese vocabulary quiz aimed at "
    "A1-A2 learners. An editor has rejected specific wrong options because a "
    "blind solver accepted them as correct too. Replace exactly those options.\n\n"
    "A good replacement is clearly wrong to anyone who knows the word, but "
    "plausible to someone who does not: same part of speech, same register, "
    "similar length. For a fill-in-the-blank item the replacement must make "
    "the sentence FALSE or UNNATURAL — never merely a different true "
    "sentence. Never reuse the intended answer or any option being kept.\n\n"
    'Respond with JSON only: {"results": [{"n": 1, "replacements": '
    '["<new option>", ...]}]} with one replacement per rejected option, in order.'
)


def _repair_prompt(items: Sequence[tuple[Candidate, JudgeVerdict]]) -> str:
    lines = []
    for i, (candidate, judge) in enumerate(items, start=1):
        template = _KIND_QUESTION.get(candidate.kind, "{prompt}")
        question = template.format(word=candidate.word, prompt=candidate.prompt)
        keeping = [o for o in candidate.wrong_options if o not in judge.replace]
        lines.append(
            f"{i}. {question}\n"
            f"   Correct answer (keep): {candidate.answer}\n"
            f"   Wrong options to KEEP: {', '.join(keeping) or '(none)'}\n"
            f"   Wrong options to REPLACE: {', '.join(judge.replace)}\n"
            f"   Editor's reason: {judge.reason}"
        )
    return "Replace the rejected options.\n\n" + "\n\n".join(lines)


async def run_repair(
    chat: Chat, items: Sequence[tuple[Candidate, JudgeVerdict]]
) -> list[Candidate | None]:
    raw = await chat(REPAIR_SYSTEM, _repair_prompt(items))
    rows = _parse_rows(raw, len(items))
    out: list[Candidate | None] = []
    for (candidate, judge), row in zip(items, rows):
        if row is None:
            out.append(None)
            continue
        replacements = [str(x).strip() for x in row.get("replacements", []) or [] if str(x).strip()]
        if len(replacements) != len(judge.replace):
            out.append(None)
            continue
        swap = dict(zip(judge.replace, replacements))
        out.append(
            replace(
                candidate,
                wrong_options=tuple(swap.get(o, o) for o in candidate.wrong_options),
            )
        )
    return out
