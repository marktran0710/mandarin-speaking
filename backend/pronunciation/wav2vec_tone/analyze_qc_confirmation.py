"""Pre-registered confirmation analysis for rms_relative_db.

Signal validation and rule validation are kept apart throughout and produce
separate verdicts. A signal can generalise while the threshold picked from 38
development tokens does not transfer, and collapsing the two would hide that.

The threshold is applied exactly as frozen. If retention or precision
disappoints, that is the result.

    python -m pronunciation.wav2vec_tone.analyze_qc_confirmation
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import frozen_qc

DATA_DIR = Path(__file__).resolve().parent / "data"
KEY_CSV = DATA_DIR / "qc_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_qc_human_review.csv"
CHOICES = ("ACCEPT", "REJECT")
DEVELOPMENT_DIRECTION = "higher->usable"
MIN_STRATUM = 10


def auc(values, labels) -> float:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    keep = np.isfinite(values)
    values, labels = values[keep], labels[keep]
    positives, negatives = int(labels.sum()), int((~labels).sum())
    if not positives or not negatives:
        return float("nan")
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    ordered = values[order]
    index = 0
    while index < len(ordered):
        stop = index
        while stop + 1 < len(ordered) and ordered[stop + 1] == ordered[index]:
            stop += 1
        ranks[order[index:stop + 1]] = (index + stop) / 2.0 + 1.0
        index = stop + 1
    return float((ranks[labels].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


def bootstrap_auc(values, labels, seed=0, samples=5000):
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    keep = np.isfinite(values)
    values, labels = values[keep], labels[keep]
    if labels.sum() < 3 or (~labels).sum() < 3:
        return None
    rng = np.random.default_rng(seed)
    positive, negative = np.flatnonzero(labels), np.flatnonzero(~labels)
    draws = []
    for _ in range(samples):
        picked = np.concatenate([rng.choice(positive, len(positive), replace=True),
                                 rng.choice(negative, len(negative), replace=True)])
        value = auc(values[picked], labels[picked])
        if np.isfinite(value):
            draws.append(value)
    return (float(np.percentile(draws, 2.5)),
            float(np.percentile(draws, 97.5))) if draws else None


def wilson(successes: int, total: int, z: float = 1.96):
    if not total:
        return (float("nan"), float("nan"))
    p = successes / total
    denominator = 1 + z ** 2 / total
    centre = (p + z ** 2 / (2 * total)) / denominator
    margin = z * sqrt(p * (1 - p) / total + z ** 2 / (4 * total ** 2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def stats(values):
    values = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not len(values):
        return None
    return {"n": int(len(values)), "median": float(np.median(values)),
            "q1": float(np.percentile(values, 25)),
            "q3": float(np.percentile(values, 75))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No key at {KEY_CSV} — run prepare_qc_confirmation first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(f"No judgments at {review_path}.\n"
                 "Run prepare_qc_confirmation, then serve_review --round qc, "
                 "do the listening, and save the CSV there.")

    key = {r["trial_id"]: r for r in csv.DictReader(KEY_CSV.open(encoding="utf-8"))}
    judged, unknown = [], []
    for row in csv.DictReader(review_path.open(encoding="utf-8")):
        entry = key.get(row["trial_id"])
        verdict = row["human_usability_judgment"].strip().upper()
        if entry is None or verdict not in CHOICES:
            unknown.append(row.get("trial_id", "?"))
            continue
        judged.append({**entry, "verdict": verdict})

    if not judged:
        sys.exit("No usable judgments found.")

    # Duplicates are for reliability only; the QC analysis uses the first
    # presentation of each token so no token is counted twice.
    by_token = defaultdict(list)
    for row in judged:
        by_token[row["token_id"]].append(row)
    unique = [sorted(group, key=lambda r: r["trial_id"])[0]
              for group in by_token.values()]
    pairs = [(g[0]["verdict"], g[1]["verdict"])
             for g in (sorted(v, key=lambda r: r["trial_id"])
                       for v in by_token.values()) if len(g) > 1]

    for row in unique:
        row["rms_relative_db"] = float(row["rms_relative_db"])
        row["local_snr_db"] = (float(row["local_snr_db"])
                               if row["local_snr_db"] else float("nan"))
        for name in ("alignment_score", "duration_seconds", "voiced_proportion"):
            row[name] = float(row[name])

    is_accept = [r["verdict"] == "ACCEPT" for r in unique]
    counts = Counter(r["verdict"] for r in unique)
    unjudged = sorted(set(key) - {r["trial_id"] for r in judged})

    lines = [
        "=" * 88,
        "PRE-REGISTERED QC CONFIRMATION",
        "=" * 88,
        f"Trials prepared      : {len(key)}",
        f"Trials judged        : {len(judged)}",
        f"Unique fresh tokens  : {len(unique)}",
        f"Hidden duplicate pairs completed : {len(pairs)}",
        f"Human ACCEPT         : {counts['ACCEPT']} "
        f"({counts['ACCEPT'] / len(unique) * 100:.1f}%)",
        f"Human REJECT         : {counts['REJECT']} "
        f"({counts['REJECT'] / len(unique) * 100:.1f}%)",
    ]
    if unjudged:
        lines.append(f"Not judged           : {len(unjudged)} "
                     f"({', '.join(unjudged[:8])}) — left missing")
    if unknown:
        lines.append(f"Unrecognised         : {len(unknown)}")

    # --- signals ------------------------------------------------------------
    def report(name, label):
        values = [r[name] for r in unique]
        available = sum(1 for v in values if np.isfinite(v))
        accept_stats = stats([r[name] for r in unique if r["verdict"] == "ACCEPT"])
        reject_stats = stats([r[name] for r in unique if r["verdict"] == "REJECT"])
        value = auc(values, is_accept)
        interval = bootstrap_auc(values, is_accept, args.seed)
        direction = ("higher->usable" if value > 0.5 else "lower->usable")
        block = [f"  {label}",
                 f"    coverage      : {available}/{len(unique)}"
                 + ("  (missing left missing, never imputed)"
                    if available < len(unique) else "")]
        if accept_stats and reject_stats:
            block += [
                f"    ACCEPT        : median {accept_stats['median']:.3f}  "
                f"IQR [{accept_stats['q1']:.3f}, {accept_stats['q3']:.3f}]  "
                f"n={accept_stats['n']}",
                f"    REJECT        : median {reject_stats['median']:.3f}  "
                f"IQR [{reject_stats['q1']:.3f}, {reject_stats['q3']:.3f}]  "
                f"n={reject_stats['n']}",
                f"    AUC           : {value:.3f}"
                + (f"  95% CI [{interval[0]:.3f}, {interval[1]:.3f}]"
                   if interval else ""),
                f"    direction     : {direction}",
            ]
        return block, {"auc": value, "ci": interval, "direction": direction,
                       "coverage": available, "accept": accept_stats,
                       "reject": reject_stats}

    lines += ["", "-" * 88, "PRIMARY SIGNAL", "-" * 88]
    primary_block, primary = report("rms_relative_db", "rms_relative_db")
    lines += primary_block

    lines += ["", "-" * 88, "SECONDARY SIGNAL", "-" * 88]
    secondary_block, secondary = report("local_snr_db", "local_snr_db")
    lines += secondary_block

    lines += ["", "-" * 88, "BASELINE COMPARATORS (no thresholds tuned)", "-" * 88]
    baselines = {}
    for name in ("alignment_score", "duration_seconds", "voiced_proportion"):
        block, result = report(name, name)
        lines += block
        baselines[name] = result

    # --- frozen rule --------------------------------------------------------
    keeps = [frozen_qc.qc_keep(r["rms_relative_db"]) for r in unique]
    retained = [r for r, k in zip(unique, keeps) if k]
    discarded = [r for r, k in zip(unique, keeps) if k is False]
    kept_accept = sum(1 for r in retained if r["verdict"] == "ACCEPT")
    kept_reject = len(retained) - kept_accept
    dropped_accept = sum(1 for r in discarded if r["verdict"] == "ACCEPT")
    dropped_reject = len(discarded) - dropped_accept
    precision = kept_accept / len(retained) if retained else float("nan")
    retention = len(retained) / len(unique)
    interval = wilson(kept_accept, len(retained)) if retained else (float("nan"),) * 2

    lines += ["", "-" * 88,
              f"FROZEN RULE: rms_relative_db >= {frozen_qc.RMS_THRESHOLD_DB} dB "
              f"(unchanged)", "-" * 88,
              f"  retained            : {len(retained)}/{len(unique)} "
              f"({retention * 100:.1f}%)",
              f"  human ACCEPT kept   : {kept_accept}",
              f"  human REJECT kept   : {kept_reject}",
              f"  precision retained  : {precision * 100:.1f}%  "
              f"Wilson 95% CI [{interval[0] * 100:.1f}%, {interval[1] * 100:.1f}%]",
              f"  human ACCEPT discarded : {dropped_accept}",
              f"  human REJECT discarded : {dropped_reject}",
              "",
              "  2x2:",
              f"    {'':<14}{'human ACCEPT':>14}{'human REJECT':>14}",
              f"    {'QC KEEP':<14}{kept_accept:>14}{kept_reject:>14}",
              f"    {'QC DISCARD':<14}{dropped_accept:>14}{dropped_reject:>14}",
              f"  baseline ACCEPT rate without any rule: "
              f"{counts['ACCEPT'] / len(unique) * 100:.1f}%"]

    # --- phonetic confound --------------------------------------------------
    lines += ["", "-" * 88, "PHONETIC CONFOUND CHECK (descriptive only)", "-" * 88,
              "  Onset classes group by manner and aspiration, since those "
              "plausibly drive",
              "  token loudness. They are never used as QC predictors.",
              "",
              f"  {'stratum':<26}{'n':>5}{'RMS median':>12}{'ACC%':>8}{'AUC':>8}"]
    strata_results = {}
    for field, label in (("initial_class", "onset"), ("expected_tone", "tone")):
        for level in sorted({r[field] for r in unique}):
            subset = [r for r in unique if r[field] == level]
            values = [r["rms_relative_db"] for r in subset]
            accepts = [r["verdict"] == "ACCEPT" for r in subset]
            name = f"{label}={level}"
            sub_auc = auc(values, accepts) if len(set(accepts)) > 1 else float("nan")
            if len(subset) >= MIN_STRATUM:
                strata_results[name] = sub_auc
            lines.append(f"  {name:<26}{len(subset):>5}{np.median(values):>12.2f}"
                         f"{np.mean(accepts) * 100:>7.0f}%"
                         + (f"{sub_auc:>8.3f}" if np.isfinite(sub_auc) else f"{'--':>8}")
                         + ("" if len(subset) >= MIN_STRATUM else "   (too small)"))

    def bucket(row):
        value = row["duration_seconds"]
        return "short" if value < 0.14 else "mid" if value < 0.22 else "long"

    for level in ("short", "mid", "long"):
        subset = [r for r in unique if bucket(r) == level]
        if not subset:
            continue
        values = [r["rms_relative_db"] for r in subset]
        accepts = [r["verdict"] == "ACCEPT" for r in subset]
        sub_auc = auc(values, accepts) if len(set(accepts)) > 1 else float("nan")
        name = f"duration={level}"
        if len(subset) >= MIN_STRATUM:
            strata_results[name] = sub_auc
        lines.append(f"  {name:<26}{len(subset):>5}{np.median(values):>12.2f}"
                     f"{np.mean(accepts) * 100:>7.0f}%"
                     + (f"{sub_auc:>8.3f}" if np.isfinite(sub_auc) else f"{'--':>8}")
                     + ("" if len(subset) >= MIN_STRATUM else "   (too small)"))

    onset_medians = {level: np.median([r["rms_relative_db"] for r in unique
                                       if r["initial_class"] == level])
                     for level in sorted({r["initial_class"] for r in unique})}
    spread = max(onset_medians.values()) - min(onset_medians.values())
    lines += ["",
              f"  RMS median spread across onset classes: {spread:.2f} dB",
              "  (a large spread would mean the measure partly encodes which "
              "sound was spoken)"]

    # --- reliability --------------------------------------------------------
    lines += ["", "-" * 88, "HIDDEN DUPLICATE RELIABILITY", "-" * 88]
    if pairs:
        agree = sum(1 for a, b in pairs if a == b)
        rate = agree / len(pairs)
        table = Counter(pairs)
        lines += [f"  pairs            : {len(pairs)}",
                  f"  exact agreement  : {agree}/{len(pairs)} ({rate * 100:.0f}%)",
                  "  transitions      : "
                  + ", ".join(f"{a}->{b}: {n}" for (a, b), n in sorted(table.items()))]
        observed = rate
        first = Counter(a for a, _ in pairs)
        second = Counter(b for _, b in pairs)
        expected = sum((first[c] / len(pairs)) * (second[c] / len(pairs))
                       for c in CHOICES)
        kappa = ((observed - expected) / (1 - expected)) if expected < 1 else float("nan")
        lines.append(f"  kappa (descriptive only): "
                     + ("undefined — one answer throughout"
                        if not np.isfinite(kappa) else f"{kappa:.3f}")
                     + "  (prevalence makes this unstable at n=10)")
    else:
        rate = float("nan")
        lines.append("  No completed duplicate pairs.")

    # --- verdicts -----------------------------------------------------------
    signal_checks = [
        (f"1. AUC >= {frozen_qc.SIGNAL_CRITERIA['min_auc']}",
         np.isfinite(primary["auc"]) and primary["auc"] >= frozen_qc.SIGNAL_CRITERIA["min_auc"],
         f"{primary['auc']:.3f}"),
        ("2. direction matches development",
         primary["direction"] == DEVELOPMENT_DIRECTION,
         f"{primary['direction']} vs {DEVELOPMENT_DIRECTION}"),
        (f"3. duplicate agreement >= "
         f"{frozen_qc.SIGNAL_CRITERIA['min_duplicate_agreement'] * 100:.0f}%",
         np.isfinite(rate) and rate >= frozen_qc.SIGNAL_CRITERIA["min_duplicate_agreement"],
         f"{rate * 100:.0f}%" if np.isfinite(rate) else "no pairs"),
        ("4. not explained by one stratum",
         bool(strata_results) and sum(
             1 for v in strata_results.values()
             if np.isfinite(v) and v > 0.5) >= max(1, len(strata_results) // 2),
         f"{sum(1 for v in strata_results.values() if np.isfinite(v) and v > 0.5)}"
         f"/{len(strata_results)} strata (n>={MIN_STRATUM}) point the same way"),
    ]
    rule_checks = [
        (f"5. retained ACCEPT >= "
         f"{frozen_qc.RULE_CRITERIA['min_retained_accept_rate'] * 100:.0f}%",
         np.isfinite(precision)
         and precision >= frozen_qc.RULE_CRITERIA["min_retained_accept_rate"],
         f"{precision * 100:.1f}%"),
        (f"6. retention >= {frozen_qc.RULE_CRITERIA['min_retention'] * 100:.0f}%",
         retention >= frozen_qc.RULE_CRITERIA["min_retention"],
         f"{retention * 100:.1f}%"),
    ]

    lines += ["", "=" * 88, "PRE-REGISTERED VERDICT", "=" * 88, "  SIGNAL:"]
    for label, passed, detail in signal_checks:
        lines.append(f"    [{'PASS' if passed else 'FAIL'}] {label:<40} {detail}")
    lines.append("  RULE:")
    for label, passed, detail in rule_checks:
        lines.append(f"    [{'PASS' if passed else 'FAIL'}] {label:<40} {detail}")

    signal_ok = all(p for _, p, _ in signal_checks)
    rule_ok = all(p for _, p, _ in rule_checks)
    if signal_ok and rule_ok:
        conclusion = ("A. SIGNAL + RULE SUPPORTED — the frozen rule may be "
                      "considered for benchmark QC. Do not scale yet.")
    elif signal_ok:
        conclusion = ("B. SIGNAL SUPPORTED, RULE NOT SUPPORTED — the measure "
                      "generalises but T does not transfer. Do NOT tune T on "
                      "this set.")
    else:
        conclusion = ("C. SIGNAL NOT CONFIRMED — stop acoustic-QC engineering.")
    lines += ["", f"  -> {conclusion}", "",
              "  No new acoustic feature should be searched after this without "
              "an explicit new research rationale."]
    print("\n".join(lines))

    payload = {
        "prepared": len(key), "judged": len(judged), "unique_tokens": len(unique),
        "accept": counts["ACCEPT"], "reject": counts["REJECT"],
        "primary": primary, "secondary": secondary, "baselines": baselines,
        "frozen_threshold": frozen_qc.RMS_THRESHOLD_DB,
        "rule": {"retained": len(retained), "retention": retention,
                 "kept_accept": kept_accept, "kept_reject": kept_reject,
                 "dropped_accept": dropped_accept, "dropped_reject": dropped_reject,
                 "precision": precision, "wilson_ci": interval},
        "strata_auc": strata_results,
        "onset_median_spread_db": float(spread),
        "duplicate_pairs": len(pairs), "duplicate_agreement": rate,
        "signal_checks": {label: passed for label, passed, _ in signal_checks},
        "rule_checks": {label: passed for label, passed, _ in rule_checks},
        "conclusion": conclusion,
    }
    path = DATA_DIR / "ompal_qc_confirmation.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                    encoding="utf-8")
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()
