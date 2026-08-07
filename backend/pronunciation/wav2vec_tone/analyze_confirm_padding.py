"""Confirmatory analysis of +/-20 ms padding, on fresh tokens.

The five acceptance conditions were fixed before any judgment existed and are
evaluated here mechanically, each printed PASS or FAIL. Significance is
supportive only; the rule was written that way because a paired test with few
discordant cases cannot reach it, and discovering that afterwards would be a
reason to move the goalposts.

Whichever way it goes, padding experimentation ends here: adopt 20 ms, or keep
the original boundaries and tighten segment QC instead.

    python -m pronunciation.wav2vec_tone.analyze_confirm_padding
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
KEY_CSV = DATA_DIR / "confirm_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_confirm_human_review.csv"
CHOICES = ("ACCEPT", "REJECT")
PADDED, BASELINE = 20, 0

# Fixed in advance. Do not edit after seeing results.
MAX_DAMAGE_RATE = 0.02
MIN_PADDED_ACCEPT = 0.90
MIN_STRATUM_N = 8          # below this a stratum is reported but not counted


def exact_mcnemar(gained: int, lost: int) -> float:
    n = gained + lost
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(gained, lost) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No key at {KEY_CSV} — run prepare_confirm_padding first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_confirm_padding, then serve_review --round confirm, "
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
    by_pad = defaultdict(Counter)
    for row in rows:
        by_pad[int(row["padding_ms"])][row["human_usability_judgment"]] += 1

    lines = [
        "=" * 80,
        "CONFIRMATORY TEST: +/-20 ms vs 0 ms, fresh tokens",
        "=" * 80,
        f"Trials prepared : {len(key)}",
        f"Trials judged   : {len(rows)}",
    ]
    if unjudged:
        lines.append(f"Not judged      : {len(unjudged)} "
                     f"({', '.join(unjudged[:10])}) — left missing")
    if unknown:
        lines.append(f"Unrecognised    : {len(unknown)}")

    for pad in sorted(by_pad):
        counter = by_pad[pad]
        total = sum(counter.values())
        lines += [
            "",
            f"{pad} ms:",
            f"  ACCEPT   : {counter.get('ACCEPT', 0)}",
            f"  REJECT   : {counter.get('REJECT', 0)}",
            f"  ACCEPT % : {counter.get('ACCEPT', 0) / total * 100:.1f}%",
        ]

    # --- paired ------------------------------------------------------------
    verdicts = defaultdict(dict)
    for row in rows:
        verdicts[row["token_id"]][int(row["padding_ms"])] = row
    paired = [(t, v[BASELINE], v[PADDED]) for t, v in verdicts.items()
              if BASELINE in v and PADDED in v]

    lines += ["", "-" * 80, "PAIRED TABLE (pre-registered primary)", "-" * 80]
    if not paired:
        lines.append("  No complete pairs — primary comparison cannot be run.")
        print("\n".join(lines))
        return

    cells = Counter((b["human_usability_judgment"], p["human_usability_judgment"])
                    for _, b, p in paired)
    both_accept = cells[("ACCEPT", "ACCEPT")]
    damaged = cells[("ACCEPT", "REJECT")]
    rescued = cells[("REJECT", "ACCEPT")]
    both_reject = cells[("REJECT", "REJECT")]
    p_value = exact_mcnemar(rescued, damaged)

    base_rate = by_pad[BASELINE].get("ACCEPT", 0) / max(sum(by_pad[BASELINE].values()), 1)
    pad_rate = by_pad[PADDED].get("ACCEPT", 0) / max(sum(by_pad[PADDED].values()), 1)
    base_reject = 1 - base_rate
    pad_reject = 1 - pad_rate
    relative = ((base_reject - pad_reject) / base_reject) if base_reject else 0.0

    lines += [
        f"  unique tokens paired          : {len(paired)}",
        f"  both ACCEPT                   : {both_accept}",
        f"  0 ms ACCEPT -> 20 ms REJECT   : {damaged}",
        f"  0 ms REJECT -> 20 ms ACCEPT   : {rescued}",
        f"  both REJECT                   : {both_reject}",
        "",
        f"  net direction                 : {rescued - damaged:+d} tokens",
        f"  exact McNemar (discordant {rescued + damaged}) : p = {p_value:.4f}",
        f"  absolute ACCEPT-rate difference: "
        f"{(pad_rate - base_rate) * 100:+.1f} pts "
        f"({base_rate * 100:.1f}% -> {pad_rate * 100:.1f}%)",
        f"  relative reduction in REJECT   : {relative * 100:+.1f}% "
        f"({base_reject * 100:.1f}% -> {pad_reject * 100:.1f}%)",
    ]
    if rescued + damaged < 6:
        lines.append("  Note: with fewer than 6 discordant pairs this test cannot "
                     "reach p<0.05 whatever the split; read the direction.")

    # --- strata -------------------------------------------------------------
    def stratum(field, label):
        block = ["", f"Direction by {label}:",
                 f"  {'group':<14}{'n':>5}{'0ms ACC%':>11}{'20ms ACC%':>12}"
                 f"{'delta':>9}{'counts':>10}"]
        results = []
        for level in sorted({r[field] for r in rows}):
            subset = [(b, p) for _, b, p in paired if b[field] == level]
            if not subset:
                continue
            base = sum(1 for b, _ in subset if b["human_usability_judgment"] == "ACCEPT")
            pad = sum(1 for _, p in subset if p["human_usability_judgment"] == "ACCEPT")
            delta = (pad - base) / len(subset) * 100
            counts = "counted" if len(subset) >= MIN_STRATUM_N else "too small"
            block.append(f"  {str(level):<14}{len(subset):>5}"
                         f"{base / len(subset) * 100:>10.0f}%"
                         f"{pad / len(subset) * 100:>11.0f}%{delta:>+8.0f}%{counts:>10}")
            if len(subset) >= MIN_STRATUM_N:
                results.append(delta >= 0)
        return block, results

    tone_block, tone_ok = stratum("expected_tone", "expected tone")
    lines += tone_block

    def bucket(row):
        value = float(row["duration_seconds"])
        return ("short" if value < 0.16 else "mid" if value < 0.24 else "long")

    for row in rows:
        row["duration_bucket"] = bucket(row)
    dur_block, dur_ok = stratum("duration_bucket", "duration bin")
    lines += dur_block

    speakers = Counter(b["speaker_id"] for _, b, _ in paired)
    interpretable = [s for s, n in speakers.items() if n >= MIN_STRATUM_N]
    lines += ["", f"Speaker strata: {len(speakers)} speakers, "
              f"{len(interpretable)} with n>={MIN_STRATUM_N}."]
    if not interpretable:
        lines.append("  Too thin to interpret per speaker (median "
                     f"{sorted(speakers.values())[len(speakers) // 2]} tokens each); "
                     "tone and duration strata are used for condition 5 instead.")

    strata_ok = tone_ok + dur_ok
    consistent = sum(strata_ok)

    # --- gated decision -----------------------------------------------------
    damage_rate = damaged / len(paired)
    checks = [
        ("1. 20 ms ACCEPT rate > 0 ms", pad_rate > base_rate,
         f"{pad_rate * 100:.1f}% vs {base_rate * 100:.1f}%"),
        ("2. REJECT->ACCEPT > ACCEPT->REJECT", rescued > damaged,
         f"{rescued} vs {damaged}"),
        (f"3. damage <= {MAX_DAMAGE_RATE * 100:.0f}% of tokens",
         damage_rate <= MAX_DAMAGE_RATE,
         f"{damaged}/{len(paired)} = {damage_rate * 100:.1f}%"),
        (f"4. 20 ms ACCEPT >= {MIN_PADDED_ACCEPT * 100:.0f}%",
         pad_rate >= MIN_PADDED_ACCEPT, f"{pad_rate * 100:.1f}%"),
        ("5. direction consistent across strata",
         bool(strata_ok) and consistent >= (len(strata_ok) + 1) // 2,
         f"{consistent}/{len(strata_ok)} interpretable strata non-negative"),
    ]
    lines += ["", "=" * 80, "PRE-REGISTERED DECISION", "=" * 80]
    for label, passed, detail in checks:
        lines.append(f"  [{'PASS' if passed else 'FAIL'}] {label:<40} {detail}")

    if all(passed for _, passed, _ in checks):
        lines += ["", "  -> ADOPT +/-20 ms as the fixed extraction padding.",
                  "     Padding experimentation ends here."]
    else:
        failed = [label for label, passed, _ in checks if not passed]
        lines += ["", "  -> DO NOT adopt 20 ms. Failed: "
                  + "; ".join(f.split('.')[0] for f in failed) + ".",
                  "     Stop padding optimisation. Keep the original boundaries",
                  "     and use stricter segment QC instead."]
    lines += ["",
              "  The 40 ms hypothesis failed its own pre-registered test and",
              "  remains rejected regardless of this outcome."]
    print("\n".join(lines))

    summary = {
        "trials_prepared": len(key), "trials_judged": len(rows),
        "unjudged": unjudged,
        "by_padding": {str(p): dict(c) for p, c in sorted(by_pad.items())},
        "paired": {
            "tokens": len(paired), "both_accept": both_accept,
            "accept_to_reject": damaged, "reject_to_accept": rescued,
            "both_reject": both_reject, "mcnemar_exact_p": p_value,
            "absolute_accept_difference": pad_rate - base_rate,
            "relative_reject_reduction": relative,
        },
        "decision": {label: passed for label, passed, _ in checks},
        "adopt_20ms": all(passed for _, passed, _ in checks),
        "note_40ms": "failed its pre-registered test; remains rejected",
    }
    path = DATA_DIR / "confirm_padding_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
