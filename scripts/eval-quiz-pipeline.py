"""Measure the quiz validation pipeline against the hand-labelled audit.

`quiz-questions.json` holds all 321 questions the quiz can currently serve;
`quiz-questions-review.json` flags 136 of them as broken, with a rule and a
note per finding. The remaining 185 are, by omission, labelled good. That is
a real evaluation set, so the pipeline gets scored on it instead of being
assumed to work:

    recall          how many of the 136 known-bad items it catches
    false positives how many of the 185 known-good items it throws away

Detection only — the repair loop is skipped, since the question here is
whether the blind solver plus judge can *see* the defect.

Run: python scripts/eval-quiz-pipeline.py [--limit N] [--kinds cloze,synonym]
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from quiz_pipeline import (  # noqa: E402
    BATCH_SIZE,
    Candidate,
    pre_gate,
    run_judge,
    run_solver,
)

try:
    from dotenv import load_dotenv

    load_dotenv(REPO / "backend" / ".env")
except ImportError:  # pragma: no cover - dotenv is in backend requirements
    pass

import httpx  # noqa: E402

GROQ_KEY = os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY")
GROQ_MODEL = os.getenv("GROQ_FEEDBACK_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-2.0-flash")

# Groq's free tier throttles on tokens-per-minute, and a full 321-question
# run is ~64 calls of dense prompts. Two in flight plus Retry-After backoff
# finishes without tripping it; four does not.
CONCURRENCY = 2
_semaphore = asyncio.Semaphore(CONCURRENCY)


async def chat(system: str, user: str) -> str:
    """Groq first, Gemini as fallback — the same order the quiz generators in
    main.py already use."""
    async with _semaphore:
        last: Exception | None = None
        for attempt in range(6):
            try:
                if GROQ_KEY:
                    return await _groq(system, user)
                if GEMINI_KEY:
                    return await _gemini(system, user)
                raise RuntimeError("Set GROQ_API_KEY or GEMINI_API_KEY in backend/.env")
            except httpx.HTTPStatusError as exc:
                last = exc
                if exc.response.status_code not in (429, 503):
                    raise
                # Groq tells us exactly how long to wait; guessing wastes
                # either time or another 429.
                wait = exc.response.headers.get("retry-after")
                try:
                    delay = float(wait) if wait else 0.0
                except ValueError:
                    delay = 0.0
                await asyncio.sleep(max(delay, 3 * (attempt + 1)))
            except Exception as exc:  # noqa: BLE001
                last = exc
                await asyncio.sleep(2 + attempt)
        raise RuntimeError(f"chat failed after retries: {last}")


async def _groq(system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": GROQ_MODEL,
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def _gemini(system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}",
            json={"contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}]},
        )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def load_labelled() -> list[tuple[int, Candidate, dict | None]]:
    """The 321 questions in the dump's flat order, each paired with its audit
    finding if it has one. The numbering mirrors review-quiz-questions.py's
    traversal exactly, which is what makes the labels line up."""
    dump = json.loads((REPO / "quiz-questions.json").read_text(encoding="utf-8"))
    review = json.loads((REPO / "quiz-questions-review.json").read_text(encoding="utf-8"))
    findings = {f["questionNumber"]: f for f in review["findings"]}

    out: list[tuple[int, Candidate, dict | None]] = []
    n = 0
    for story in dump["stories"]:
        for scene in story["scenes"]:
            for word in scene["words"]:
                for question in word["questions"]:
                    n += 1
                    out.append(
                        (
                            n,
                            Candidate(
                                kind=question["kind"],
                                word=word["word"],
                                prompt=question["prompt"],
                                answer=question["answer"],
                                wrong_options=tuple(question.get("aiWrongOptions", [])),
                                key=f"q{n}",
                                gloss=" / ".join(
                                    part
                                    for part in (word.get("translation"), word.get("pos"))
                                    if part
                                ),
                                context=question.get("sourceSentence")
                                or scene.get("suggestedAnswer")
                                or "",
                            ),
                            findings.get(n),
                        )
                    )
    return out


async def evaluate(rows: list[tuple[int, Candidate, dict | None]]) -> dict:
    verdicts: dict[int, tuple[str, str]] = {}  # n -> (caught?, why)

    pending: list[tuple[int, Candidate]] = []
    for n, candidate, _ in rows:
        broken = pre_gate(candidate)
        if broken:
            verdicts[n] = ("caught", f"pre-gate:{broken}")
        else:
            pending.append((n, candidate))

    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    print(f"pre-gate caught {len(verdicts)}; {len(pending)} items -> {len(batches)} batches")

    async def run_batch(batch, index):
        candidates = [c for _, c in batch]
        try:
            return await _run_batch(batch, candidates, index)
        except Exception as exc:  # noqa: BLE001 - one dead batch must not sink the run
            print(f"  batch {index + 1}/{len(batches)} FAILED: {exc}")
            return {n: ("error", f"batch-failed:{exc}") for n, _ in batch}

    async def _run_batch(batch, candidates, index):
        solved = await run_solver(chat, candidates, seed="eval")
        pairs = [(c, s) for (_, c), s in zip(batch, solved) if s is not None]
        judged = await run_judge(chat, pairs) if pairs else []

        out = {}
        judge_iter = iter(judged)
        for (n, _candidate), solver in zip(batch, solved):
            if solver is None:
                out[n] = ("caught", "solver-no-answer")
                continue
            judge = next(judge_iter, None)
            if judge is None:
                out[n] = ("caught", "judge-no-verdict")
            elif judge.verdict == "pass":
                out[n] = ("clean", judge.reason)
            else:
                out[n] = ("caught", f"{judge.verdict}:{judge.reason}")
        print(f"  batch {index + 1}/{len(batches)} done")
        return out

    for chunk in await asyncio.gather(
        *(run_batch(batch, i) for i, batch in enumerate(batches))
    ):
        verdicts.update(chunk)

    return verdicts


def report(rows, verdicts) -> None:
    # Items whose batch never came back aren't evidence either way — scoring
    # them as "not caught" would silently understate recall.
    errored = [n for n, _, _ in rows if verdicts.get(n, ("clean",))[0] == "error"]
    if errored:
        print(f"\n{len(errored)} items had no verdict (API errors) — excluded from scoring")
    rows = [r for r in rows if r[0] not in set(errored)]

    bad = [(n, c, f) for n, c, f in rows if f is not None]
    good = [(n, c, f) for n, c, f in rows if f is None]

    caught_bad = [n for n, _, _ in bad if verdicts.get(n, ("clean",))[0] == "caught"]
    caught_good = [n for n, _, _ in good if verdicts.get(n, ("clean",))[0] == "caught"]

    print()
    print("=" * 62)
    print(f"  known-bad   {len(bad):>4}   caught {len(caught_bad):>4}"
          f"   recall {len(caught_bad) / max(1, len(bad)):.1%}")
    print(f"  known-good  {len(good):>4}   caught {len(caught_good):>4}"
          f"   false-positive {len(caught_good) / max(1, len(good)):.1%}")
    print("=" * 62)

    by_rule_total = collections.Counter(f["rule"] for _, _, f in bad)
    by_rule_caught = collections.Counter(
        f["rule"] for n, _, f in bad if verdicts.get(n, ("clean",))[0] == "caught"
    )
    print("\nrecall by audit rule:")
    for rule, total in by_rule_total.most_common():
        got = by_rule_caught[rule]
        print(f"  {rule:<28} {got:>3}/{total:<3}  {got / total:.0%}")

    missed = [(n, c, f) for n, c, f in bad if verdicts.get(n, ("clean",))[0] != "caught"]
    if missed:
        print(f"\nmissed {len(missed)} known-bad items (first 10):")
        for n, candidate, finding in missed[:10]:
            print(f"  #{n} [{finding['rule']}] {candidate.prompt}")
            print(f"      answer={candidate.answer} options={list(candidate.wrong_options)}")
            print(f"      audit: {finding['note']}")

    if caught_good:
        print(f"\nfalse positives on known-good items (first 10):")
        for n in caught_good[:10]:
            candidate = next(c for m, c, _ in rows if m == n)
            print(f"  #{n} [{candidate.kind}] {candidate.prompt}")
            print(f"      answer={candidate.answer} options={list(candidate.wrong_options)}")
            print(f"      pipeline: {verdicts[n][1]}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions")
    parser.add_argument("--kinds", default="", help="comma-separated kinds to evaluate")
    parser.add_argument("--out", default="", help="write per-question verdicts to this JSON file")
    args = parser.parse_args()

    rows = load_labelled()
    if args.kinds:
        wanted = {k.strip() for k in args.kinds.split(",") if k.strip()}
        rows = [r for r in rows if r[1].kind in wanted]
    if args.limit:
        rows = rows[: args.limit]

    print(f"evaluating {len(rows)} questions "
          f"({sum(1 for _, _, f in rows if f)} known-bad)")
    verdicts = await evaluate(rows)
    report(rows, verdicts)

    if args.out:
        payload = [
            {
                "n": n,
                "kind": c.kind,
                "prompt": c.prompt,
                "answer": c.answer,
                "options": list(c.wrong_options),
                "label": "bad" if f else "good",
                "auditRule": f["rule"] if f else None,
                "pipeline": verdicts.get(n, ("clean", ""))[0],
                "pipelineReason": verdicts.get(n, ("clean", ""))[1],
            }
            for n, c, f in rows
        ]
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nper-question verdicts -> {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
