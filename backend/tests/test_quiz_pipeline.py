"""Tests for the multi-agent quiz validation pipeline.

Every LLM call goes through the injected `chat` callable, so these drive the
orchestration with scripted agent responses — no network, no keys.
"""

import json

import pytest

from quiz_pipeline import (
    Candidate,
    JudgeVerdict,
    SolverVerdict,
    pre_gate,
    run_judge,
    run_repair,
    run_solver,
    validate_candidates,
)


def cloze(word="友美", answer="友美", wrongs=("小美", "美麗", "美好")):
    return Candidate(
        kind="cloze",
        word=word,
        prompt="＿＿＿是我的好朋友，她很友善。",
        answer=answer,
        wrong_options=tuple(wrongs),
        key="c1",
    )


def scripted(*responses):
    """A chat callable that returns each canned response in turn, and records
    what it was asked."""
    calls = []
    queue = list(responses)

    async def chat(system, user):
        calls.append({"system": system, "user": user})
        return queue.pop(0) if queue else "{}"

    chat.calls = calls
    return chat


def results(*rows):
    return json.dumps({"results": list(rows)})


# ── pre-gate ──────────────────────────────────────────────────────────────


def test_pre_gate_passes_a_well_formed_item():
    assert pre_gate(cloze()) is None


@pytest.mark.parametrize(
    "candidate,rule",
    [
        (cloze(answer=""), "empty-answer"),
        (cloze(wrongs=("小美", "小美", "美好")), "duplicate-options"),
        (cloze(wrongs=("友美", "美麗", "美好")), "answer-duplicated-in-options"),
        (cloze(wrongs=("小美", "美麗")), "too-few-options"),
    ],
)
def test_pre_gate_catches_malformed_items(candidate, rule):
    assert pre_gate(candidate) == rule


def test_pre_gate_rejects_a_cloze_that_leaks_its_answer():
    leaky = Candidate(
        kind="cloze",
        word="週末",
        prompt="這個週末＿＿＿要做什麼？",
        answer="週末",
        wrong_options=("早上", "晚上", "中午"),
    )
    assert pre_gate(leaky) == "cloze-answer-leaked"


# ── solver ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_solver_is_never_shown_the_intended_answer():
    chat = scripted(results({"n": 1, "choice": "友美", "alsoCorrect": [], "confidence": "high"}))
    await run_solver(chat, [cloze()])

    prompt = chat.calls[0]["user"]
    assert "Intended answer" not in prompt
    # All four options appear, with nothing marking which one is correct.
    for option in ("友美", "小美", "美麗", "美好"):
        assert option in prompt


@pytest.mark.asyncio
async def test_solver_reports_a_second_acceptable_option():
    chat = scripted(
        results(
            {
                "n": 1,
                "choice": "友美",
                "alsoCorrect": ["小美"],
                "confidence": "high",
                "why": "小美 is also a name",
            }
        )
    )
    [verdict] = await run_solver(chat, [cloze()])
    assert verdict.also_correct == ("小美",)


@pytest.mark.asyncio
async def test_solver_prompt_states_the_per_kind_bar():
    """A cloze and a translation must not be judged by the same 'also
    correct' standard — that mixture is what produced 40% false positives."""
    translation = Candidate(
        kind="translation", word="週末", prompt="週末", answer="weekend",
        wrong_options=("weekdays", "holiday", "vacation"),
    )
    chat = scripted(results({"n": 1, "choice": "x", "alsoCorrect": [], "confidence": "high"}))
    await run_solver(chat, [cloze(), translation])

    prompt = chat.calls[0]["user"]
    assert "natural AND true" in prompt  # the cloze bar
    assert "merely related" in prompt  # the translation bar


# ── judge ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_sees_story_context_the_solver_did_not():
    candidate = Candidate(
        kind="translation",
        word="友美",
        prompt="友美",
        answer="friend's name",
        wrong_options=("friendship", "good friend", "beautiful friend"),
        gloss="friend's name / N",
        context="友美是我的好朋友。",
    )
    solver = SolverVerdict("friend's name", (), "high", "")
    chat = scripted(results({"n": 1, "verdict": "pass", "replace": [], "reason": "ok"}))
    await run_judge(chat, [(candidate, solver)])

    prompt = chat.calls[0]["user"]
    assert "friend's name / N" in prompt
    assert "友美是我的好朋友。" in prompt


@pytest.mark.asyncio
async def test_judge_defaults_an_unknown_verdict_to_reject():
    chat = scripted(results({"n": 1, "verdict": "maybe?", "replace": [], "reason": ""}))
    [verdict] = await run_judge(chat, [(cloze(), SolverVerdict("友美", (), "high", ""))])
    assert verdict.verdict == "reject"


# ── repair ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repair_swaps_only_the_rejected_option():
    judge = JudgeVerdict("repair", ("小美",), "小美 is also a name")
    chat = scripted(results({"n": 1, "replacements": ["蛋糕"]}))
    [fixed] = await run_repair(chat, [(cloze(), judge)])
    assert fixed.wrong_options == ("蛋糕", "美麗", "美好")
    assert fixed.answer == "友美"


@pytest.mark.asyncio
async def test_repair_gives_up_when_the_replacement_count_is_wrong():
    judge = JudgeVerdict("repair", ("小美", "美麗"), "")
    chat = scripted(results({"n": 1, "replacements": ["蛋糕"]}))
    [fixed] = await run_repair(chat, [(cloze(), judge)])
    assert fixed is None


# ── orchestration ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_clean_item_passes_without_repair():
    chat = scripted(
        results({"n": 1, "choice": "友美", "alsoCorrect": [], "confidence": "high"}),
        results({"n": 1, "verdict": "pass", "replace": [], "reason": "sound"}),
    )
    result = await validate_candidates(chat, [cloze()])
    assert [o.candidate.answer for o in result.kept] == ["友美"]
    assert result.dropped == []


@pytest.mark.asyncio
async def test_a_multi_fit_item_is_repaired_then_kept():
    chat = scripted(
        results({"n": 1, "choice": "友美", "alsoCorrect": ["小美"], "confidence": "high"}),
        results({"n": 1, "verdict": "repair", "replace": ["小美"], "reason": "also a name"}),
        results({"n": 1, "replacements": ["蛋糕"]}),
        results({"n": 1, "choice": "友美", "alsoCorrect": [], "confidence": "high"}),
        results({"n": 1, "verdict": "pass", "replace": [], "reason": "sound"}),
    )
    result = await validate_candidates(chat, [cloze()])
    assert len(result.kept) == 1
    kept = result.kept[0]
    assert kept.candidate.wrong_options == ("蛋糕", "美麗", "美好")
    assert kept.rounds == 1


@pytest.mark.asyncio
async def test_an_item_that_stays_broken_is_dropped_after_two_repairs():
    stubborn = [
        results({"n": 1, "choice": "友美", "alsoCorrect": ["小美"], "confidence": "high"}),
        results({"n": 1, "verdict": "repair", "replace": ["小美"], "reason": "also a name"}),
        results({"n": 1, "replacements": ["小明"]}),
    ] * 3
    result = await validate_candidates(chat := scripted(*stubborn), [cloze()], max_repairs=2)
    assert result.kept == []
    assert result.dropped[0].reason == "repair-exhausted"
    assert result.dropped[0].rounds == 2
    assert chat  # silence the walrus lint


@pytest.mark.asyncio
async def test_a_rejected_item_is_dropped_without_a_repair_attempt():
    chat = scripted(
        results({"n": 1, "choice": "小美", "alsoCorrect": [], "confidence": "high"}),
        results({"n": 1, "verdict": "reject", "replace": [], "reason": "answer is wrong"}),
    )
    result = await validate_candidates(chat, [cloze()])
    assert result.kept == []
    assert result.dropped[0].reason == "rejected"
    # solver + judge only — no repair call was spent on a hopeless item.
    assert len(chat.calls) == 2


@pytest.mark.asyncio
async def test_an_unverifiable_item_is_dropped_rather_than_shipped():
    """An unparseable solver response leaves the item unchecked, and shipping
    unchecked questions is the thing this pipeline exists to stop."""
    chat = scripted("not json at all")
    result = await validate_candidates(chat, [cloze()])
    assert result.kept == []
    assert result.dropped[0].reason == "solver-no-answer"


@pytest.mark.asyncio
async def test_rows_are_matched_by_n_not_by_position():
    """A model that answers out of order must not shift verdicts onto the
    wrong questions."""
    a = cloze(word="友美")
    b = Candidate(
        kind="cloze", word="週末", prompt="這個＿＿＿要做什麼？", answer="週末",
        wrong_options=("早上", "晚上", "中午"), key="c2",
    )
    chat = scripted(
        results(
            {"n": 2, "choice": "週末", "alsoCorrect": [], "confidence": "high"},
            {"n": 1, "choice": "小美", "alsoCorrect": [], "confidence": "high"},
        ),
        results(
            {"n": 2, "verdict": "pass", "replace": [], "reason": "sound"},
            {"n": 1, "verdict": "reject", "replace": [], "reason": "wrong answer"},
        ),
    )
    result = await validate_candidates(chat, [a, b])
    assert [o.candidate.word for o in result.kept] == ["週末"]
    assert [o.candidate.word for o in result.dropped] == ["友美"]
