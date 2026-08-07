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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_human_review, then serve_review, do the listening, "
            "and save the downloaded CSV to that path."
        )

    items = {row["review_id"]: row
             for row in csv.DictReader(ITEMS_CSV.open(encoding="utf-8"))}
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
        rows.append({**item, **judgment, "human_boundary_judgment": verdict})

    if not rows:
        sys.exit("No usable judgments found.")

    counts = Counter(r["human_boundary_judgment"] for r in rows)
    total = len(rows)

    lines = [
        "=" * 74,
        "HUMAN AUDITORY REVIEW OF FORCED ALIGNMENT",
        "=" * 74,
        f"Total reviewed: {total} of {len(items)} prepared",
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
    print("\n".join(lines))

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
    path = DATA_DIR / "ompal_alignment_human_review_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
