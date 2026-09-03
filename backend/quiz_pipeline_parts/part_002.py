

# ── Orchestration ─────────────────────────────────────────────────────────


async def validate_candidates(
    chat: Chat,
    candidates: Sequence[Candidate],
    *,
    max_repairs: int = 2,
    seed: str = "solver",
) -> BankResult:
    """Runs every candidate through pre-gate -> solver -> judge, repairing and
    re-solving up to `max_repairs` times before dropping it."""
    result = BankResult()

    live: list[tuple[Candidate, int]] = []
    for candidate in candidates:
        broken = pre_gate(candidate)
        if broken:
            result.dropped.append(
                ItemOutcome(candidate, "dropped", "pre-gate", 0, broken)
            )
        else:
            live.append((candidate, 0))

    while live:
        batch_candidates = [c for c, _ in live]
        solved = await _batched(
            lambda b: run_solver(chat, b, seed), batch_candidates
        )

        judge_inputs: list[tuple[int, Candidate, SolverVerdict]] = []
        next_round: list[tuple[Candidate, int]] = []
        for index, ((candidate, rounds), solver) in enumerate(zip(live, solved)):
            if solver is None:
                # No usable solver answer — the item is unverified, and an
                # unverified item is exactly what this pipeline exists to
                # stop shipping.
                result.dropped.append(
                    ItemOutcome(candidate, "dropped", "solver", rounds, "solver-no-answer")
                )
                continue
            judge_inputs.append((index, candidate, solver))

        if not judge_inputs:
            break

        judged = await _batched(
            lambda b: run_judge(chat, b),
            [(c, s) for _, c, s in judge_inputs],
        )

        repair_queue: list[tuple[Candidate, JudgeVerdict, int]] = []
        for (index, candidate, solver), judge in zip(judge_inputs, judged):
            rounds = live[index][1]
            if judge is None:
                result.dropped.append(
                    ItemOutcome(candidate, "dropped", "judge", rounds, "judge-no-verdict", solver)
                )
                continue
            if judge.verdict == "pass":
                result.kept.append(
                    ItemOutcome(
                        candidate,
                        "pass",
                        "repaired" if rounds else "judge",
                        rounds,
                        judge.reason,
                        solver,
                        judge,
                    )
                )
                continue
            if judge.verdict == "reject" or rounds >= max_repairs or not judge.replace:
                reason = "rejected" if judge.verdict == "reject" else "repair-exhausted"
                result.dropped.append(
                    ItemOutcome(candidate, "dropped", "judge", rounds, reason, solver, judge)
                )
                continue
            repair_queue.append((candidate, judge, rounds))

        if not repair_queue:
            break

        repaired = await _batched(
            lambda b: run_repair(chat, b),
            [(c, j) for c, j, _ in repair_queue],
        )
        for (candidate, judge, rounds), fixed in zip(repair_queue, repaired):
            if fixed is None:
                result.dropped.append(
                    ItemOutcome(candidate, "dropped", "repair", rounds, "repair-failed", None, judge)
                )
                continue
            next_round.append((fixed, rounds + 1))

        live = next_round

    return result


async def _batched(run, items: Sequence):
    """Runs `run` over BATCH_SIZE-sized slices concurrently, flattening the
    results back into one list aligned with `items`. A batch that raises
    yields Nones for its slice rather than failing the whole bank."""
    slices = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    async def guarded(chunk):
        try:
            return await run(chunk)
        except Exception as exc:  # noqa: BLE001 - one bad batch must not sink the bank
            logger.warning("quiz pipeline batch failed: %s", exc)
            return [None] * len(chunk)

    results = await asyncio.gather(*(guarded(chunk) for chunk in slices))
    flat: list = []
    for chunk, produced in zip(slices, results):
        # A short/long response must not shift every later item's verdict.
        padded = list(produced)[: len(chunk)]
        padded += [None] * (len(chunk) - len(padded))
        flat.extend(padded)
    return flat


def _parse_rows(raw: str, expected: int) -> list[dict | None]:
    """Pulls `{"results": [...]}` out of a model response and lines the rows
    up with the batch by their `n` field, so a model that skips or reorders
    items can't silently shift every verdict onto the wrong question."""
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text).removesuffix("```").strip()
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        logger.warning("quiz pipeline: unparseable response: %s", raw[:200])
        return [None] * expected

    rows = parsed.get("results") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        return [None] * expected

    out: list[dict | None] = [None] * expected
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("n", position + 1)) - 1
        except (TypeError, ValueError):
            index = position
        if 0 <= index < expected:
            out[index] = row
    return out


def candidates_from_material(
    words: Iterable[dict],
    kinds: Sequence[QuestionKind],
) -> list[Candidate]:
    """Turns the per-word material already stored on a story into concrete
    candidates, the same assembly `scripts/dump-quiz-questions.py` performs —
    the entry point for validating material that already exists."""
    out: list[Candidate] = []
    for word in words:
        for question in word.get("questions", []):
            if question.get("kind") not in kinds:
                continue
            out.append(
                Candidate(
                    kind=question["kind"],
                    word=word["word"],
                    prompt=question.get("prompt", ""),
                    answer=question.get("answer", ""),
                    wrong_options=tuple(question.get("aiWrongOptions", [])),
                    key=f"{word['word']}:{question['kind']}:{question.get('poolIndex', 0)}",
                )
            )
    return out
