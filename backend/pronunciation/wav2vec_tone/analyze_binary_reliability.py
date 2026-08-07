"""Reliability of the binary usability criterion, from hidden duplicates.

Only one question matters here: does the reviewer agree with themselves? If
not, nothing measured with this criterion can be trusted, and no padding or
aligner comparison is worth running.

Cohen's kappa is reported alongside raw agreement because raw agreement is
inflated when one answer dominates -- at a 90% ACCEPT rate, a reviewer
answering ACCEPT at random still agrees with themselves ~82% of the time. With
ten pairs the kappa is very noisy, so a bootstrap interval is given rather than
a bare number.

    python -m pronunciation.wav2vec_tone.analyze_binary_reliability
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
KEY_CSV = DATA_DIR / "binary_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_binary_human_review.csv"
CHOICES = ("ACCEPT", "REJECT")
STABILITY_TARGET = 0.90


def cohen_kappa(pairs) -> float:
    """Kappa for the same rater twice: chance-corrected self-agreement."""
    if not pairs:
        return float("nan")
    total = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / total
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    expected = sum((first[c] / total) * (second[c] / total) for c in CHOICES)
    if expected >= 1.0:
        return float("nan")     # one answer used throughout; kappa undefined
    return (observed - expected) / (1 - expected)


def bootstrap_kappa(pairs, samples: int = 5000, seed: int = 0):
    if len(pairs) < 3:
        return None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(samples):
        picked = [pairs[i] for i in rng.integers(0, len(pairs), len(pairs))]
        value = cohen_kappa(picked)
        if np.isfinite(value):
            values.append(value)
    if not values:
        return None
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No key at {KEY_CSV} — run prepare_binary_reliability first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_binary_reliability, then serve_review --round binary, "
            "do the listening, and save the CSV there."
        )

    key = {row["trial_id"]: row
           for row in csv.DictReader(KEY_CSV.open(encoding="utf-8"))}
    rows, unknown = [], []
    for judgment in csv.DictReader(review_path.open(encoding="utf-8")):
        entry = key.get(judgment["trial_id"])
        verdict = judgment["human_usability_judgment"].strip().upper()
        if entry is None or verdict not in CHOICES:
            unknown.append(judgment.get("trial_id", "?"))
            continue
        rows.append({**entry, **judgment, "human_usability_judgment": verdict})

    if not rows:
        sys.exit("No usable judgments found.")

    unjudged = sorted(set(key) - {r["trial_id"] for r in rows})
    counts = Counter(r["human_usability_judgment"] for r in rows)
    total = len(rows)

    lines = [
        "=" * 78,
        "BINARY USABILITY CRITERION -- RELIABILITY",
        "=" * 78,
        f"Trials prepared : {len(key)}",
        f"Trials judged   : {total}",
    ]
    if unjudged:
        lines.append(f"Not judged      : {len(unjudged)} "
                     f"({', '.join(unjudged[:12])}) — left missing")
    if unknown:
        lines.append(f"Unrecognised    : {len(unknown)}")
    lines += [
        "",
        f"ACCEPT rate : {counts.get('ACCEPT', 0)}/{total} "
        f"({counts.get('ACCEPT', 0) / total * 100:.1f}%)",
        f"REJECT rate : {counts.get('REJECT', 0)}/{total} "
        f"({counts.get('REJECT', 0) / total * 100:.1f}%)",
    ]

    # --- hidden duplicate pairs --------------------------------------------
    by_token = defaultdict(list)
    for row in rows:
        by_token[row["token_id"]].append(row)
    pairs, pair_rows = [], []
    for token_id, group in by_token.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: r["trial_id"])
        first, second = group[0], group[1]
        pairs.append((first["human_usability_judgment"],
                      second["human_usability_judgment"]))
        pair_rows.append((token_id, first, second))

    lines += ["", "-" * 78, "HIDDEN DUPLICATE PAIRS", "-" * 78]
    if not pairs:
        lines.append("  No completed duplicate pairs — reliability cannot be estimated.")
    else:
        agree = sum(1 for a, b in pairs if a == b)
        rate = agree / len(pairs)
        kappa = cohen_kappa(pairs)
        interval = bootstrap_kappa(pairs)
        lines += [
            f"  pairs completed        : {len(pairs)}",
            f"  exact agreement        : {agree}/{len(pairs)} ({rate * 100:.1f}%)",
            f"  Cohen's kappa (self)   : "
            + ("undefined — one answer used throughout"
               if not np.isfinite(kappa) else f"{kappa:.3f}"),
        ]
        if interval and np.isfinite(kappa):
            lines.append(f"  bootstrap 95% CI       : "
                         f"{interval[0]:.3f} to {interval[1]:.3f}")
        lines.append(f"  (n={len(pairs)} pairs is small; read the interval, "
                     f"not the point estimate)")

        disagreements = [(t, f, s) for (t, f, s), (a, b) in zip(pair_rows, pairs)
                         if a != b]
        if disagreements:
            lines += ["", "  Disagreements (reported, not altered):"]
            for token_id, first, second in disagreements:
                lines.append(
                    f"    {first['word']} ({first['expected_pinyin']}) "
                    f"spk {first['speaker_id']}  {token_id}"
                    f"  auto={first['alignment_status']}"
                    f"  dur={first['duration_seconds']}s"
                )
                lines.append(
                    f"      {first['trial_id']} -> {first['human_usability_judgment']}"
                    f"   |   {second['trial_id']} -> "
                    f"{second['human_usability_judgment']}"
                )

        lines += ["", "-" * 78, "DECISION", "-" * 78]
        if rate >= STABILITY_TARGET:
            lines += [
                f"  Duplicate agreement {rate * 100:.0f}% >= "
                f"{STABILITY_TARGET * 100:.0f}%.",
                "  The binary criterion is stable enough to resume evaluating",
                "  alignment and padding.",
            ]
        else:
            lines += [
                f"  Duplicate agreement {rate * 100:.0f}% < "
                f"{STABILITY_TARGET * 100:.0f}%.",
                "  Do NOT scale alignment. The criterion or the interface needs",
                "  further refinement before any padding or aligner comparison",
                "  can mean anything.",
            ]
        if np.isfinite(kappa) and kappa < 0.6 and rate >= STABILITY_TARGET:
            lines += [
                "",
                "  Caution: raw agreement passes but kappa is low, which happens",
                "  when nearly every trial gets the same answer. High agreement",
                "  on an unbalanced set does not show the criterion discriminates.",
            ]

    # --- context: how the binary verdict lines up with earlier labels -------
    for field, title in (("alignment_status", "By automatic alignment_status:"),
                         ("prior_judgment", "By round-2 three-level judgment:")):
        groups = defaultdict(Counter)
        for row in rows:
            groups[row.get(field) or "(none)"][row["human_usability_judgment"]] += 1
        if len(groups) <= 1:
            continue
        lines += ["", title,
                  f"  {'group':<22}{'n':>5}{'ACCEPT':>9}{'REJECT':>9}{'ACC%':>8}"]
        for name in sorted(groups, key=lambda g: -sum(groups[g].values())):
            counter = groups[name]
            subtotal = sum(counter.values())
            lines.append(f"  {str(name)[:21]:<22}{subtotal:>5}"
                         f"{counter.get('ACCEPT', 0):>9}{counter.get('REJECT', 0):>9}"
                         f"{counter.get('ACCEPT', 0) / subtotal * 100:>7.0f}%")

    print("\n".join(lines))

    summary = {
        "trials_prepared": len(key),
        "trials_judged": total,
        "unjudged": unjudged,
        "accept": counts.get("ACCEPT", 0),
        "reject": counts.get("REJECT", 0),
        "accept_rate": counts.get("ACCEPT", 0) / total,
        "duplicate_pairs": len(pairs),
        "duplicate_agreement": (sum(1 for a, b in pairs if a == b) / len(pairs)
                                if pairs else None),
        "cohen_kappa_self": (float(cohen_kappa(pairs)) if pairs else None),
        "kappa_ci": bootstrap_kappa(pairs) if pairs else None,
        "stability_target": STABILITY_TARGET,
        "by_alignment_status": {
            status: dict(Counter(r["human_usability_judgment"] for r in rows
                                 if r["alignment_status"] == status))
            for status in sorted({r["alignment_status"] for r in rows})
        },
    }
    path = DATA_DIR / "binary_reliability_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
