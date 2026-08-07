"""What actually makes a segment unusable, and could a feature have seen it?

Reports the confirmed failure modes and maps each onto whether the pipeline's
existing signals could plausibly detect it. Nothing is implemented here -- the
point is to choose the next signal on evidence instead of guessing again after
the last three features reached 88% precision.

The controls carry the argument. A defect that shows up as often in accepted
segments is not what drives rejection, and a QC feature built on it would fire
on good data.

    python -m pronunciation.wav2vec_tone.analyze_failure_audit
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
KEY_CSV = DATA_DIR / "audit_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_audit_human_review.csv"

REASON_ORDER = ("WRONG_TOKEN", "TRUNCATED_ONSET", "TRUNCATED_RHYME",
                "ADJACENT_SPEECH", "TOO_SHORT_OR_INCOMPLETE",
                "LOW_AUDIO_QUALITY", "OTHER")

# Which family each failure belongs to, and what could see it. Fixed judgements
# about the signals, not about the counts -- the counts decide which row matters.
DETECTABILITY = {
    "WRONG_TOKEN": (
        "alignment-location",
        "No — score is high on confident mistakes",
        "Re-align constrained to the neighbouring syllable and compare "
        "likelihoods; a competing syllable scoring as well is the tell"),
    "TRUNCATED_ONSET": (
        "boundary/completeness",
        "Partly — duration helps, onsets are unvoiced so voicing does not",
        "Energy rise inside the first frames vs just before the boundary"),
    "TRUNCATED_RHYME": (
        "boundary/completeness",
        "Partly — duration correlates but does not localise the cut",
        "Voiced run still rising/ongoing at the segment edge"),
    "ADJACENT_SPEECH": (
        "boundary/completeness",
        "No — extra speech raises duration and voicing, both read as healthy",
        "Count voiced nuclei in the span; more than one means a neighbour "
        "came along"),
    "TOO_SHORT_OR_INCOMPLETE": (
        "boundary/completeness",
        "Yes — duration already separates these (AUC 0.760)",
        "None needed; a duration floor covers it"),
    "LOW_AUDIO_QUALITY": (
        "acoustic-quality",
        "No — nothing in the pipeline measures SNR or clipping",
        "Segmental SNR, clipping rate, spectral flatness"),
    "OTHER": ("mixed", "Unknown until the notes are read", "Depends on the notes"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No key at {KEY_CSV} — run prepare_failure_audit first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_failure_audit, then serve_review --round audit, "
            "do the listening, and save the CSV there."
        )

    key = {row["trial_id"]: row
           for row in csv.DictReader(KEY_CSV.open(encoding="utf-8"))}
    rows, unknown = [], []
    for judgment in csv.DictReader(review_path.open(encoding="utf-8")):
        entry = key.get(judgment["trial_id"])
        verdict = judgment["human_usability_judgment"].strip().upper()
        if entry is None or verdict not in ("ACCEPT", "REJECT"):
            unknown.append(judgment.get("trial_id", "?"))
            continue
        rows.append({**entry, **judgment,
                     "human_usability_judgment": verdict,
                     "failure_reason": judgment.get("failure_reason", "").strip().upper()})
    if not rows:
        sys.exit("No usable judgments found.")

    previously_reject = [r for r in rows if r["previous_verdict"] == "REJECT"]
    previously_accept = [r for r in rows if r["previous_verdict"] == "ACCEPT"]
    unjudged = sorted(set(key) - {r["trial_id"] for r in rows})

    lines = [
        "=" * 82,
        "FAILURE-MODE AUDIT",
        "=" * 82,
        f"Reviewed                    : {len(rows)} of {len(key)} prepared",
        f"Previously REJECT           : {len(previously_reject)}",
        f"Previously ACCEPT controls  : {len(previously_accept)}",
    ]
    if unjudged:
        lines.append(f"Not judged                  : {len(unjudged)} "
                     f"({', '.join(unjudged[:10])}) — left missing")

    # --- repeatability on this material ------------------------------------
    transitions = Counter((r["previous_verdict"], r["human_usability_judgment"])
                          for r in rows)
    lines += ["", "-" * 82, "BINARY REPEAT AGREEMENT (earlier verdict was hidden)",
              "-" * 82]
    for previous in ("REJECT", "ACCEPT"):
        for now in ("REJECT", "ACCEPT"):
            count = transitions[(previous, now)]
            base = len(previously_reject if previous == "REJECT" else previously_accept)
            lines.append(f"  previous {previous:<7} -> {now:<7}: {count:>3}"
                         + (f"  ({count / base * 100:.0f}% of {base})" if base else ""))
    stable = transitions[("REJECT", "REJECT")] + transitions[("ACCEPT", "ACCEPT")]
    lines.append(f"  overall self-agreement    : {stable}/{len(rows)} "
                 f"({stable / len(rows) * 100:.0f}%)")

    confirmed = [r for r in rows
                 if r["previous_verdict"] == "REJECT"
                 and r["human_usability_judgment"] == "REJECT"]
    all_rejects_now = [r for r in rows if r["human_usability_judgment"] == "REJECT"]

    # --- failure modes ------------------------------------------------------
    lines += ["", "-" * 82,
              f"FAILURE MODES — confirmed REJECT tokens (n={len(confirmed)})",
              "-" * 82]
    counts = Counter(r["failure_reason"] for r in confirmed)
    for reason in REASON_ORDER:
        count = counts.get(reason, 0)
        share = count / len(confirmed) * 100 if confirmed else 0.0
        lines.append(f"  {reason:<26}{count:>4}  ({share:5.1f}%)")
    missing_reason = sum(1 for r in confirmed if not r["failure_reason"])
    if missing_reason:
        lines.append(f"  (no reason recorded)      {missing_reason:>4}")

    newly = [r for r in rows if r["previous_verdict"] == "ACCEPT"
             and r["human_usability_judgment"] == "REJECT"]
    if newly:
        lines += ["", f"  Controls newly rejected ({len(newly)}) — reasons:"]
        for reason, count in Counter(r["failure_reason"] for r in newly).most_common():
            lines.append(f"    {reason or '(none)':<26}{count:>4}")

    # --- by feature ---------------------------------------------------------
    def by_bucket(label, bucket_of):
        block = ["", f"Failure modes by {label}:"]
        groups = defaultdict(Counter)
        for row in all_rejects_now:
            groups[bucket_of(row)][row["failure_reason"]] += 1
        if not groups:
            return block + ["  (none)"]
        present = [r for r in REASON_ORDER
                   if any(r in counter for counter in groups.values())]
        block.append(f"  {'group':<16}{'n':>4}" + "".join(f"{r[:11]:>13}" for r in present))
        for name in sorted(groups):
            counter = groups[name]
            block.append(f"  {str(name):<16}{sum(counter.values()):>4}"
                         + "".join(f"{counter.get(r, 0):>13}" for r in present))
        return block

    lines += by_bucket("duration", lambda r: (
        "<0.10s" if float(r["duration_seconds"]) < 0.10
        else "0.10-0.15s" if float(r["duration_seconds"]) < 0.15
        else "0.15-0.22s" if float(r["duration_seconds"]) < 0.22 else ">=0.22s"))
    lines += by_bucket("alignment score", lambda r: (
        "<0.70" if float(r["alignment_score"]) < 0.70
        else "0.70-0.90" if float(r["alignment_score"]) < 0.90 else ">=0.90"))
    lines += by_bucket("expected tone", lambda r: f"T{r['expected_tone']}")

    # --- control comparison -------------------------------------------------
    accepted_now = [r for r in rows if r["human_usability_judgment"] == "ACCEPT"]
    if accepted_now and all_rejects_now:
        lines += ["", "-" * 82,
                  "REJECT vs ACCEPT on existing features (matched design)",
                  "-" * 82,
                  f"  {'feature':<22}{'REJECT median':>16}{'ACCEPT median':>16}"]
        for feature in ("duration_seconds", "alignment_score", "voiced_proportion"):
            reject_values = [float(r[feature]) for r in all_rejects_now]
            accept_values = [float(r[feature]) for r in accepted_now]
            lines.append(f"  {feature:<22}{np.median(reject_values):>16.3f}"
                         f"{np.median(accept_values):>16.3f}")
        lines.append("  Matching pulled these together on purpose; a feature that "
                     "still separates")
        lines.append("  them here is doing real work, and one that does not was "
                     "riding on duration.")

    # --- detectability ------------------------------------------------------
    lines += ["", "-" * 82, "DETECTABILITY OF EACH OBSERVED FAILURE MODE", "-" * 82,
              f"  {'failure mode':<26}{'family':<22}{'existing features enough?'}"]
    families = Counter()
    for reason in REASON_ORDER:
        if not counts.get(reason):
            continue
        family, sufficient, _ = DETECTABILITY[reason]
        families[family] += counts[reason]
        lines.append(f"  {reason:<26}{family:<22}{sufficient}")
    lines.append("")
    lines.append("  Proposed new diagnostic per mode (NOT implemented):")
    for reason in REASON_ORDER:
        if not counts.get(reason):
            continue
        lines.append(f"    {reason}: {DETECTABILITY[reason][2]}")

    # --- summary ------------------------------------------------------------
    ranked = [r for r, _ in counts.most_common() if r]
    dominant = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    confirmed_rate = (len(confirmed) / len(previously_reject)
                      if previously_reject else float("nan"))

    if families:
        top_family, top_count = families.most_common(1)[0]
        family_verdict = (top_family if top_count / sum(families.values()) >= 0.5
                          else "mixed")
    else:
        top_family, family_verdict = None, "unknown"

    lines += ["", "=" * 82, "SUMMARY", "=" * 82,
              f"Confirmed rejection rate : {len(confirmed)}/{len(previously_reject)}"
              + (f" ({confirmed_rate * 100:.0f}%)" if previously_reject else ""),
              f"Dominant failure mode    : {dominant or '(none)'}"
              + (f"  ({counts[dominant]}/{len(confirmed)})" if dominant else ""),
              f"Second most common       : {second or '(none)'}"
              + (f"  ({counts[second]}/{len(confirmed)})" if second else ""),
              "",
              f"Most failures are        : {family_verdict}"]
    for family, count in families.most_common():
        lines.append(f"  {family:<24}{count:>4} "
                     f"({count / sum(families.values()) * 100:.0f}%)")

    if dominant:
        lines += ["",
                  f"Most promising NEW QC signal to test next: "
                  f"{DETECTABILITY[dominant][2]}",
                  f"Reason: it targets {dominant}, the dominant confirmed failure, "
                  f"which existing features cannot see."]
    lines += ["",
              f"Sample bound: {len(confirmed)} confirmed failures. Treat the "
              f"ranking as a direction, not a distribution."]
    print("\n".join(lines))

    summary = {
        "reviewed": len(rows), "prepared": len(key), "unjudged": unjudged,
        "previously_reject": len(previously_reject),
        "previously_accept_controls": len(previously_accept),
        "transitions": {f"{a}->{b}": c for (a, b), c in transitions.items()},
        "confirmed_rejects": len(confirmed),
        "confirmed_rate": confirmed_rate,
        "failure_counts": {r: counts.get(r, 0) for r in REASON_ORDER},
        "families": dict(families),
        "dominant": dominant, "second": second,
        "family_verdict": family_verdict,
        "controls_newly_rejected": len(newly),
    }
    path = DATA_DIR / "ompal_failure_audit_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
