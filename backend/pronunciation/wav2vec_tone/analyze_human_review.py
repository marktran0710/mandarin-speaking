"""Score human alignment judgments against the automatic verdicts.

Run after the listening review. It reports and stops: no threshold is changed,
no file is rewritten. The automatic `alignment_status` stays exactly as the
aligner produced it, so the two verdicts can be compared later rather than
one quietly absorbing the other.

The comparison that matters is the acoustic proxy against the ear -- it called
是/四/字 misaligned on low measured voicing, and this is what shows whether
that was a real defect or a blind spot in the check.

    python -m pronunciation.wav2vec_tone.analyze_human_review
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
ITEMS_CSV = DATA_DIR / "ompal_alignment_review_items.csv"
REVIEW_CSV = DATA_DIR / "ompal_alignment_human_review.csv"
JUDGMENTS = ("GOOD", "QUESTIONABLE", "WRONG")
DURATION_BINS = ((0.0, 0.10), (0.10, 0.15), (0.15, 0.20), (0.20, 0.30), (0.30, 9.9))


def breakdown(rows, key, title: str) -> list[str]:
    groups = defaultdict(Counter)
    for row in rows:
        groups[key(row)][row["human_boundary_judgment"]] += 1
    lines = ["", title,
             f"  {'group':<30}{'n':>5}{'GOOD':>8}{'QUEST':>8}{'WRONG':>8}{'% good':>9}"]
    for name in sorted(groups, key=lambda g: -sum(groups[g].values())):
        counts = groups[name]
        total = sum(counts.values())
        lines.append(
            f"  {str(name)[:29]:<30}{total:>5}"
            + "".join(f"{counts.get(j, 0):>8}" for j in JUDGMENTS)
            + f"{counts.get('GOOD', 0) / total * 100:>8.0f}%"
        )
    return lines


def paths_for(round_number: int):
    suffix = "" if round_number == 1 else f"_round{round_number}"
    return (
        ITEMS_CSV if not suffix
        else ITEMS_CSV.with_name(ITEMS_CSV.stem + suffix + ".csv"),
        REVIEW_CSV if not suffix
        else REVIEW_CSV.with_name(REVIEW_CSV.stem + suffix + ".csv"),
    )


def load_round(round_number: int, required: bool = True):
    """Join one round of judgments to its item metadata; [] if not done yet."""
    items_path, review_path = paths_for(round_number)
    if not review_path.exists():
        if required:
            sys.exit(
                f"No judgments at {review_path}.\n"
                f"Run prepare_human_review --round {round_number}, then "
                f"serve_review --round {round_number}, do the listening, and "
                f"save the downloaded CSV to that path."
            )
        return [], []
    items = {row["review_id"]: row
             for row in csv.DictReader(items_path.open(encoding="utf-8"))}
    rows = []
    unknown = []
    for judgment in csv.DictReader(review_path.open(encoding="utf-8")):
        item = items.get(judgment["review_id"])
        if item is None:
            unknown.append(judgment["review_id"])
            continue
        verdict = judgment["human_boundary_judgment"].strip().upper()
        if verdict not in JUDGMENTS:
            unknown.append(f"{judgment['review_id']}:{verdict}")
            continue
        rows.append({**item, **judgment, "human_boundary_judgment": verdict,
                     "review_round": str(round_number)})
    return rows, unknown


def auto_good_block(rows):
    """The decision this whole exercise exists to make."""
    good = [r for r in rows if r["alignment_status"] == "good"]
    if not good:
        return []
    counts = Counter(r["human_boundary_judgment"] for r in good)
    total = len(good)
    good_rate = counts.get("GOOD", 0) / total
    wrong_rate = counts.get("WRONG", 0) / total
    lines = [
        "",
        "=" * 74,
        "COMBINED: automatic `good` segments only, across all reviews",
        "=" * 74,
        f"  auto-good total reviewed : {total}",
        f"  human GOOD               : {counts.get('GOOD', 0)}",
        f"  human QUESTIONABLE       : {counts.get('QUESTIONABLE', 0)}",
        f"  human WRONG              : {counts.get('WRONG', 0)}",
        f"  human GOOD rate          : {good_rate * 100:.1f}%",
        f"  human WRONG rate         : {wrong_rate * 100:.1f}%",
        "  by review round:",
    ]
    by_round = defaultdict(Counter)
    for row in good:
        by_round[row.get("review_round", "?")][row["human_boundary_judgment"]] += 1
    for round_number in sorted(by_round):
        counter = by_round[round_number]
        subtotal = sum(counter.values())
        lines.append(
            f"    round {round_number}: n={subtotal}  "
            f"GOOD {counter.get('GOOD', 0)} "
            f"({counter.get('GOOD', 0) / subtotal * 100:.0f}%)  "
            f"QUEST {counter.get('QUESTIONABLE', 0)}  "
            f"WRONG {counter.get('WRONG', 0)}"
        )

    # Threshold fixed before any round-2 data was seen.
    if good_rate >= 0.95 and wrong_rate <= 0.02:
        verdict = ("ADOPT alignment_status == 'good' as the acceptance rule "
                   "for full-corpus benchmark extraction.")
    elif good_rate >= 0.90:
        verdict = ("BORDERLINE -- above 90% but short of the agreed 95%. "
                   "Adjust alignment before scaling.")
    else:
        verdict = "DO NOT SCALE on this rule -- adjust alignment first."
    lines += ["",
              "  Decision rule (fixed in advance: >=95% GOOD, very low WRONG):",
              f"  -> {verdict}"]
    return lines


def analyse(rows, unknown, label):
    counts = Counter(r["human_boundary_judgment"] for r in rows)
    total = len(rows)

    lines = [
        "=" * 74,
        f"HUMAN AUDITORY REVIEW OF FORCED ALIGNMENT -- {label}",
        "=" * 74,
        f"Total reviewed: {total}",
    ]
    for verdict in JUDGMENTS:
        count = counts.get(verdict, 0)
        lines.append(f"  {verdict:<14}{count:>5}  ({count / total * 100:5.1f}%)")
    if unknown:
        lines.append(f"  unrecognised rows skipped: {len(unknown)}")

    lines += breakdown(rows, lambda r: r["alignment_status"],
                       "By automatic alignment_status:")
    lines += breakdown(rows, lambda r: r["flag_reason"] or "(none)",
                       "By automatic flag_reason:")
    lines += breakdown(rows, lambda r: f"{r['word']} ({r['expected_pinyin']})",
                       "By target word:")
    lines += breakdown(rows, lambda r: f"T{r['expected_tone']}", "By expected tone:")

    def duration_bin(row):
        value = float(row["duration_seconds"])
        for low, high in DURATION_BINS:
            if low <= value < high:
                return f"{low:.2f}-{high:.2f}s" if high < 9 else f">={low:.2f}s"
        return "?"

    lines += breakdown(rows, duration_bin, "By segment duration:")

    # Agreement between the ear and the automatic status, mapped onto the
    # same three-way scale.
    same = sum(1 for r in rows
               if r["human_boundary_judgment"] == {"good": "GOOD",
                                                   "questionable": "QUESTIONABLE",
                                                   "failed": "WRONG"}[r["alignment_status"]])
    auto_bad = [r for r in rows if r["alignment_status"] != "good"]
    rescued = sum(1 for r in auto_bad if r["human_boundary_judgment"] == "GOOD")
    auto_good = [r for r in rows if r["alignment_status"] == "good"]
    missed = sum(1 for r in auto_good if r["human_boundary_judgment"] == "WRONG")

    lines += [
        "",
        "-" * 74,
        "EAR vs AUTOMATIC CHECK",
        "-" * 74,
        f"  exact three-way agreement : {same}/{total} ({same / total * 100:.0f}%)",
        f"  auto flagged, ear says GOOD : {rescued}/{len(auto_bad) or 1}"
        f"  -- false alarms by the proxy",
        f"  auto said good, ear says WRONG: {missed}/{len(auto_good) or 1}"
        f"  -- misses by the proxy",
        "",
        "  Nothing is adjusted on the strength of this. alignment_status is",
        "  left exactly as the aligner produced it.",
    ]
    summary = {
        "total_reviewed": total,
        "judgments": {j: counts.get(j, 0) for j in JUDGMENTS},
        "by_alignment_status": {
            status: dict(Counter(r["human_boundary_judgment"] for r in rows
                                 if r["alignment_status"] == status))
            for status in sorted({r["alignment_status"] for r in rows})
        },
        "by_word": {
            word: dict(Counter(r["human_boundary_judgment"] for r in rows
                               if r["word"] == word))
            for word in sorted({r["word"] for r in rows})
        },
        "by_tone": {
            tone: dict(Counter(r["human_boundary_judgment"] for r in rows
                               if r["expected_tone"] == tone))
            for tone in sorted({r["expected_tone"] for r in rows})
        },
        "proxy_false_alarms": rescued,
        "proxy_misses": missed,
        "exact_agreement": same,
    }
    return "\n".join(lines), summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--combine", action="store_true",
                        help="report each available round, then auto-good combined")
    args = parser.parse_args()

    all_rows, reports, summaries = [], [], {}
    rounds = (1, 2, 3) if args.combine else (args.round,)
    for number in rounds:
        rows, unknown = load_round(number, required=not args.combine)
        if not rows:
            continue
        text, summary = analyse(rows, unknown, f"round {number}")
        reports.append(text)
        summaries[f"round_{number}"] = summary
        all_rows.extend(rows)

    if not all_rows:
        sys.exit("No usable judgments found.")
    print("\n\n".join(reports))

    combined = auto_good_block(all_rows)
    if combined:
        print("\n".join(combined))
        good = [r for r in all_rows if r["alignment_status"] == "good"]
        counter = Counter(r["human_boundary_judgment"] for r in good)
        summaries["auto_good_combined"] = {
            "total": len(good),
            "judgments": {j: counter.get(j, 0) for j in JUDGMENTS},
            "good_rate": counter.get("GOOD", 0) / len(good),
            "wrong_rate": counter.get("WRONG", 0) / len(good),
        }

    path = DATA_DIR / "ompal_alignment_human_review_summary.json"
    path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
