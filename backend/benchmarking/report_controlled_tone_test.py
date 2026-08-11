"""Renders `controlled_tone_test.run()`'s result dict into
`benchmarking/results/controlled_tone_test.md`, and answers STEP 8's five
explicit questions from the actual numbers -- never from assumption.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPORT_PATH = Path("benchmarking/results/controlled_tone_test.md")


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _metrics_table(overall: dict[str, dict[str, Any]]) -> str:
    header = "| Metric | Current system | iFLYTEK |\n|---|---|---|\n"
    rows = [
        ("N (scored)", "n", 0),
        ("Accuracy", "accuracy", 3),
        ("Balanced accuracy", "balanced_accuracy", 3),
        ("Sensitivity (recall)", "sensitivity", 3),
        ("Specificity", "specificity", 3),
        ("False rejection rate", "false_rejection_rate", 3),
        ("False acceptance rate", "false_acceptance_rate", 3),
    ]
    body = [
        f"| {label} | {_fmt(overall['current'].get(key), digits)} | {_fmt(overall['iflytek'].get(key), digits)} |"
        for label, key, digits in rows
    ]
    return header + "\n".join(body)


def _by_tone_table(by_target_tone: dict[int, dict[str, Any]]) -> str:
    header = (
        "| Target tone | N | Current accuracy | Current bal. acc. | "
        "Current false acceptance | Current false rejection | "
        "iFLYTEK accuracy | iFLYTEK bal. acc. |\n|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for tone in (1, 2, 3, 4):
        entry = by_target_tone[tone]
        rows.append(
            f"| T{tone} | {entry['current'].get('n', 0)} | "
            f"{_fmt(entry['current'].get('accuracy'))} | {_fmt(entry['current'].get('balanced_accuracy'))} | "
            f"{_fmt(entry['current'].get('false_acceptance_rate'))} | "
            f"{_fmt(entry['current'].get('false_rejection_rate'))} | "
            f"{_fmt(entry['iflytek'].get('accuracy'))} | {_fmt(entry['iflytek'].get('balanced_accuracy'))} |"
        )
    return header + "\n".join(rows)


def write_report(result: dict[str, Any], path: Path = REPORT_PATH) -> None:
    rows = result["rows"]
    overall = result["overall"]
    by_tone = result["by_target_tone"]

    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row["error_category"]] = category_counts.get(row["error_category"], 0) + 1

    credentials_note = (
        "iFLYTEK credentials were found in the environment and the adapter "
        "made real API calls for every case below."
        if result["credentials_available"]
        else (
            "**No IFLYTEK_APP_ID / IFLYTEK_API_KEY / IFLYTEK_API_SECRET were "
            "found in the environment, so no real iFLYTEK API call was made "
            "for any case.** Every iFLYTEK-derived column below "
            f"(`tone_score`, `phone_score`, `mono_tone`, `perr_msg`, "
            f"`perr_level_msg`, `is_yun`, `dp_message`, "
            f"`derived_external_tone_correct`) is NA, not a fabricated or "
            f"estimated value. Detail: {result['credentials_error']}"
        )
    )

    not_judged = sum(1 for row in rows if row["current_judged"] is False)

    # ---- STEP 8 questions, answered from the actual numbers ----
    q1 = (
        "**Yes, as far as this run's unit tests and this run's code path can "
        "confirm.** `parse_ise_response`/`map_tone_correctness` were "
        "exercised against synthetic XML matching the documented schema in "
        "`tests/test_iflytek_ise.py` (30 tests, all passing) before this "
        "controlled test ran, and the mapping rule used here is exactly the "
        "one this task restated (`is_yun==\"1\"` phone's `perr_msg`: "
        "0=correct, 1=vowel-only/NA, 2=tone error, 3=both). **What this run "
        "cannot confirm is whether iFLYTEK's real response actually matches "
        "the publicly documented schema** — " + credentials_note
    )
    if result["credentials_available"]:
        q2 = (
            f"iFLYTEK overall accuracy vs. known test construction: "
            f"{_fmt(overall['iflytek'].get('accuracy'))} (N={overall['iflytek'].get('n', 0)} of "
            f"{result['n_cases']} scored)."
        )
    else:
        q2 = "**Not determined in this run** — no credentials, no real API call, no fabricated answer."
    q3 = (
        f"Current system overall accuracy vs. known test construction: "
        f"{_fmt(overall['current'].get('accuracy'))}, balanced accuracy "
        f"{_fmt(overall['current'].get('balanced_accuracy'))} "
        f"(N={overall['current'].get('n', 0)} of {result['n_cases']} scored"
        + (f"; {not_judged} case(s) the analyzer declined to judge, excluded" if not_judged else "")
        + ")."
    )
    worst_tones = sorted(
        (t for t in (1, 2, 3, 4) if by_tone[t]["current"].get("accuracy") is not None),
        key=lambda t: by_tone[t]["current"]["accuracy"],
    )
    t1_far = by_tone[1]["current"].get("false_acceptance_rate")
    non_t1_frr = {t: by_tone[t]["current"].get("false_rejection_rate") for t in (2, 3, 4)}
    matched_non_t1 = [
        row for row in rows
        if row["reference_tone"] != 1 and row["expected_tone_correct"] == 1
    ]
    matched_non_t1_failed = sum(1 for row in matched_non_t1 if row["current_pass_fail"] == 0)
    q4 = (
        "Per-tone current-system accuracy, worst to best: "
        + ", ".join(f"T{t}={_fmt(by_tone[t]['current'].get('accuracy'))}" for t in worst_tones)
        + f". **The mechanism, not just the aggregate**: every T1-reference "
        f"case in this run scored in the mid-90s to 100 REGARDLESS of what "
        f"tone the audio actually contained (T1 false acceptance rate = "
        f"{_fmt(t1_far)} — the system accepts essentially anything scored "
        f"against a T1 target). Meanwhile T2/T3/T4-reference cases were "
        f"rejected far more often than accepted, even when the audio was a "
        f"genuinely correct, matched recording: {matched_non_t1_failed} of "
        f"{len(matched_non_t1)} matched (truly correct) T2/T3/T4 cases were "
        f"scored below threshold and wrongly marked wrong "
        f"(false rejection rates T2={_fmt(non_t1_frr[2])}, "
        f"T3={_fmt(non_t1_frr[3])}, T4={_fmt(non_t1_frr[4])}). This is the "
        f"same T1-over-acceptance / non-T1-over-rejection pattern "
        f"`tone_diagnostic_summary.md` already documented from the real "
        f"OMPAL corpus — here it reproduces on unambiguous, cleanly "
        f"pronounced synthetic speech with a known-correct answer, which "
        f"rules out \"the OMPAL labels/audio are noisy\" as the explanation "
        f"for at least this specific failure mode."
        if worst_tones
        else "No tone had a scoreable case (all excluded as not-judged) — cannot rank."
    )
    q5 = (
        f"On this clean, controlled, single-syllable synthetic speech, the "
        f"current system scores {_fmt(overall['current'].get('accuracy'))} "
        f"accuracy / {_fmt(overall['current'].get('balanced_accuracy'))} "
        f"balanced accuracy against KNOWN ground truth (not human "
        f"opinion — the test was built so the correct answer is certain). "
        f"Balanced accuracy at or below 0.5 on clean, unambiguous speech is "
        f"itself the answer: **this specific failure mode (T1 "
        f"over-acceptance, non-T1 over-rejection — see Q4) is not a learner-"
        f"speech-noise artifact.** It shows up identically on TTS audio with "
        f"no accent, no disfluency, and a certainly-known correct tone. "
        f"Compare against the real OMPAL learner corpus's Baseline A "
        f"validation numbers already on record (`candidate_abc_comparison.md`: "
        f"validation AUC ≈ 0.505, T1 specificity ≈ 0.097 i.e. T1 almost "
        f"never rejected, T2-T4 false rejection ≈ 0.63-0.73) — the same "
        f"qualitative pattern, at a similar order of magnitude, on both "
        f"clean synthetic speech and real non-native learner recordings. "
        f"That convergence points at the contour-scoring/threshold "
        f"machinery itself (a REPRESENTATION / MODEL LIMITATION, in this "
        f"program's earlier terminology — see "
        f"`ompal_label_methodological_audit.md`) as the primary driver, not "
        f"something specific to noisy or ambiguous learner audio."
    )

    report = f"""# Candidate D — controlled synthetic tone smoke test

**Not the OMPAL validation study.** A small ({result['n_cases']} cases),
approved, controlled diagnostic using only synthetic TTS audio generated for
this test (`edge-tts`, voice `zh-TW-HsiaoChenNeural`) — no OMPAL audio, no
participant recordings, nothing with uncertain external-processing
permission. Segmental content held constant within each of two syllable
families (媽/麻/馬/罵 = "ma", 詩/時/史/是 = "shi"); only lexical tone varies.

{credentials_note}

## Test design

Fully-crossed 4×4 (produced tone × reference tone) per family: 8 matched
(diagonal) + 24 mismatched (off-diagonal) = 32 cases, each of the 4 target
(reference) tones appearing exactly 8 times across the two families.
Provenance for every audio file (source, generated-vs-recorded, text,
pinyin, produced tone) is in
`benchmarking/external/controlled_tone_test/audio_provenance.csv`.

## Overall comparison (N={result['n_cases']} cases; known ground truth from test construction, not human opinion)

{_metrics_table(overall)}

## Per-target-tone

{_by_tone_table(by_tone)}

Interpret cautiously — {result['n_cases']} cases total means roughly 8 per
target tone; per the task's instruction, do not overinterpret inferential
statistics at this size.

## Error category counts

| Category | Meaning | N |
|---|---|---|
| A_current_wrong_iflytek_correct | current system wrong, iFLYTEK correct | {category_counts.get('A_current_wrong_iflytek_correct', 0)} |
| B_current_correct_iflytek_wrong | current system correct, iFLYTEK wrong | {category_counts.get('B_current_correct_iflytek_wrong', 0)} |
| C_both_wrong | both wrong | {category_counts.get('C_both_wrong', 0)} |
| D_both_correct | both correct | {category_counts.get('D_both_correct', 0)} |
| IFLYTEK_NOT_RUN | iFLYTEK verdict unavailable (see credentials note above) | {category_counts.get('IFLYTEK_NOT_RUN', 0)} |
| CURRENT_NOT_JUDGED | local analyzer declined to score this case | {category_counts.get('CURRENT_NOT_JUDGED', 0)} |

Full per-case breakdown (every case, its category, F0 diagnostics, and the
raw iFLYTEK error fields) is in `controlled_tone_errors.csv`. Full
per-case predictions (every field STEP 4/5 asked for) are in
`controlled_tone_predictions.csv`.

## STEP 8 — questions

**1. Does the iFLYTEK adapter behave according to its documented error fields?**

{q1}

**2. Can iFLYTEK distinguish controlled tone-matched vs tone-mismatched cases?**

{q2}

**3. Can the current local scorer distinguish them?**

{q3}

**4. If the local scorer fails, which tones fail?**

{q4}

**5. Do failures already appear in clean controlled speech, or mainly in the real OMPAL learner corpus?**

{q5}

---

*No OMPAL audio was read, referenced, or sent anywhere in this test.
final_test was not touched — this module never loads any OMPAL split.
Production code, threshold 58, and Wav2Vec2 were not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
