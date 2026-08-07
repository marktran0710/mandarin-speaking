"""Score the blind padding diagnostic.

Reports every padding condition and every transition, and stops. It does not
pick a winner: a condition can raise the aggregate while quietly spoiling
segments that were already fine, and that trade is the whole question. The
controls exist to expose it, so GOOD -> QUESTIONABLE and GOOD -> WRONG are
reported as prominently as the rescues.

    python -m pronunciation.wav2vec_tone.analyze_padding_review
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
KEY_CSV = DATA_DIR / "padding_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_padding_human_review.csv"
JUDGMENTS = ("GOOD", "QUESTIONABLE", "WRONG")


def rate_line(label, counts, width=26) -> str:
    total = sum(counts.values())
    if not total:
        return f"  {label:<{width}}{'--':>6}"
    return (f"  {label:<{width}}{total:>5}"
            + "".join(f"{counts.get(j, 0):>7}" for j in JUDGMENTS)
            + "".join(f"{counts.get(j, 0) / total * 100:>7.0f}%" for j in JUDGMENTS))


def header(width=26) -> str:
    return (f"  {'condition':<{width}}{'n':>5}{'GOOD':>7}{'QUEST':>7}{'WRONG':>7}"
            f"{'GOOD%':>8}{'QUES%':>7}{'WRNG%':>7}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No trial key at {KEY_CSV} — run prepare_padding_review first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_padding_review, then serve_review --round padding, "
            "do the listening, and save the CSV there."
        )

    key = {row["trial_id"]: row
           for row in csv.DictReader(KEY_CSV.open(encoding="utf-8"))}
    rows, unknown = [], []
    for judgment in csv.DictReader(review_path.open(encoding="utf-8")):
        entry = key.get(judgment["trial_id"])
        verdict = judgment["human_boundary_judgment"].strip().upper()
        if entry is None or verdict not in JUDGMENTS:
            unknown.append(judgment.get("trial_id", "?"))
            continue
        rows.append({**entry, **judgment, "human_boundary_judgment": verdict})

    if not rows:
        sys.exit("No usable judgments found.")

    unjudged = sorted(set(key) - {r["trial_id"] for r in rows})
    lines = [
        "=" * 82,
        "BLIND PADDING DIAGNOSTIC",
        "=" * 82,
        f"Trials prepared : {len(key)}",
        f"Trials judged   : {len(rows)}",
    ]
    if unjudged:
        lines.append(f"Not judged      : {len(unjudged)} "
                     f"({', '.join(unjudged[:12])}"
                     f"{' …' if len(unjudged) > 12 else ''}) — left missing")
    if unknown:
        lines.append(f"Unrecognised    : {len(unknown)}")

    # --- by padding condition, overall -------------------------------------
    by_padding = defaultdict(Counter)
    for row in rows:
        by_padding[int(row["padding_ms"])][row["human_boundary_judgment"]] += 1
    lines += ["", "By padding condition (all tokens):", header()]
    for padding in sorted(by_padding):
        lines.append(rate_line(f"{padding} ms", by_padding[padding]))

    # --- split by what the token was originally -----------------------------
    for original in ("GOOD", "QUESTIONABLE", "WRONG"):
        subset = [r for r in rows if r["original_judgment"] == original]
        if not subset:
            continue
        grouped = defaultdict(Counter)
        for row in subset:
            grouped[int(row["padding_ms"])][row["human_boundary_judgment"]] += 1
        tokens = len({r["review_id"] for r in subset})
        lines += ["", f"Originally {original} ({tokens} tokens):", header()]
        for padding in sorted(grouped):
            lines.append(rate_line(f"{padding} ms", grouped[padding]))

    # --- transitions --------------------------------------------------------
    lines += ["", "-" * 82,
              "TRANSITIONS from the original round-2 judgment",
              "-" * 82,
              f"  {'padding':<10}" + "".join(f"{t:>16}" for t in
                                             ("QUEST->GOOD", "QUEST->WRONG",
                                              "WRONG->GOOD", "GOOD->QUEST",
                                              "GOOD->WRONG"))]
    transitions = defaultdict(Counter)
    for row in rows:
        transitions[int(row["padding_ms"])][
            (row["original_judgment"], row["human_boundary_judgment"])] += 1
    watched = (("QUESTIONABLE", "GOOD"), ("QUESTIONABLE", "WRONG"),
               ("WRONG", "GOOD"), ("GOOD", "QUESTIONABLE"), ("GOOD", "WRONG"))
    for padding in sorted(transitions):
        counts = transitions[padding]
        lines.append(f"  {str(padding) + ' ms':<10}"
                     + "".join(f"{counts.get(pair, 0):>16}" for pair in watched))

    # 0 ms is the same audio the reviewer already judged in round 2, so the
    # gap between the two is a direct measure of how repeatable the judgement
    # is. Any padding effect smaller than this is not interpretable.
    baseline = [r for r in rows if int(r["padding_ms"]) == 0]
    if baseline:
        agree = sum(1 for r in baseline
                    if r["human_boundary_judgment"] == r["original_judgment"])
        lines += [
            "", "-" * 82,
            "SELF-CONSISTENCY CHECK (0 ms = identical audio to round 2)",
            "-" * 82,
            f"  same verdict as round 2 : {agree}/{len(baseline)} "
            f"({agree / len(baseline) * 100:.0f}%)",
            "  Treat this as the noise floor. A padding difference smaller than",
            "  the gap here is not distinguishable from re-listening variance.",
        ]

    lines += [
        "", "=" * 82,
        "No condition is selected here. Whether a small symmetric context helps",
        "depends on both halves: rescued QUESTIONABLE/WRONG tokens *and* the",
        "controls staying intact. Read the two together.",
    ]
    print("\n".join(lines))

    summary = {
        "trials_prepared": len(key),
        "trials_judged": len(rows),
        "unjudged": unjudged,
        "by_padding": {str(p): dict(c) for p, c in sorted(by_padding.items())},
        "by_original": {
            original: {
                str(p): dict(Counter(
                    r["human_boundary_judgment"] for r in rows
                    if r["original_judgment"] == original
                    and int(r["padding_ms"]) == p))
                for p in sorted(by_padding)
            }
            for original in ("GOOD", "QUESTIONABLE", "WRONG")
        },
        "transitions": {
            str(p): {f"{a}->{b}": counts.get((a, b), 0) for a, b in watched}
            for p, counts in sorted(transitions.items())
        },
        "self_consistency_0ms": (
            {"agree": sum(1 for r in baseline
                          if r["human_boundary_judgment"] == r["original_judgment"]),
             "n": len(baseline)} if baseline else None
        ),
    }
    path = DATA_DIR / "padding_review_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
