"""Paired padding comparison under the binary usability criterion.

Follows the plan fixed before the judgments existed: 40 ms vs 0 ms is primary,
paired on the same tokens, exact McNemar; 20 ms and 60 ms are descriptive. A
numerically better secondary condition does not displace the primary one --
that is what pre-registration is for.

The recommendation is gated on all four agreed conditions, and the damage check
is reported whether or not it passes, because a padding that rescues marginal
segments by spoiling clean ones is not an improvement.

    python -m pronunciation.wav2vec_tone.analyze_binary_padding
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
KEY_CSV = DATA_DIR / "binpad_trial_key.csv"
REVIEW_CSV = DATA_DIR / "ompal_binpad_human_review.csv"
CHOICES = ("ACCEPT", "REJECT")
PRIMARY_PAD, BASELINE_PAD = 40, 0


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar on the discordant pairs only."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(REVIEW_CSV))
    args = parser.parse_args()

    if not KEY_CSV.exists():
        sys.exit(f"No key at {KEY_CSV} — run prepare_binary_padding first.")
    review_path = Path(args.review)
    if not review_path.exists():
        sys.exit(
            f"No judgments at {review_path}.\n"
            "Run prepare_binary_padding, then serve_review --round binpad, "
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
    lines = [
        "=" * 80,
        "BINARY PADDING CONFIRMATION",
        "=" * 80,
        f"Trials prepared : {len(key)}",
        f"Trials judged   : {len(rows)}",
    ]
    if unjudged:
        lines.append(f"Not judged      : {len(unjudged)} "
                     f"({', '.join(unjudged[:10])}) — left missing")
    if unknown:
        lines.append(f"Unrecognised    : {len(unknown)}")

    # --- per condition ------------------------------------------------------
    by_pad = defaultdict(Counter)
    for row in rows:
        by_pad[int(row["padding_ms"])][row["human_usability_judgment"]] += 1
    lines += ["", "By padding condition:",
              f"  {'condition':<12}{'n':>5}{'ACCEPT':>9}{'REJECT':>9}"
              f"{'ACCEPT%':>10}{'REJECT%':>10}"]
    for pad in sorted(by_pad):
        counter = by_pad[pad]
        total = sum(counter.values())
        lines.append(
            f"  {str(pad) + ' ms':<12}{total:>5}{counter.get('ACCEPT', 0):>9}"
            f"{counter.get('REJECT', 0):>9}"
            f"{counter.get('ACCEPT', 0) / total * 100:>9.1f}%"
            f"{counter.get('REJECT', 0) / total * 100:>9.1f}%"
        )

    # --- primary paired comparison -----------------------------------------
    verdict_by = defaultdict(dict)
    for row in rows:
        verdict_by[row["token_id"]][int(row["padding_ms"])] = row
    paired = [(token, v[BASELINE_PAD], v[PRIMARY_PAD])
              for token, v in verdict_by.items()
              if BASELINE_PAD in v and PRIMARY_PAD in v]

    lines += ["", "-" * 80,
              f"PRIMARY (pre-registered): {PRIMARY_PAD} ms vs {BASELINE_PAD} ms, paired",
              "-" * 80]
    if not paired:
        lines.append("  No complete pairs — primary comparison cannot be run.")
        cells = {}
        p_value = None
    else:
        cells = Counter(
            (base["human_usability_judgment"], padded["human_usability_judgment"])
            for _, base, padded in paired
        )
        both_accept = cells[("ACCEPT", "ACCEPT")]
        lost = cells[("ACCEPT", "REJECT")]
        gained = cells[("REJECT", "ACCEPT")]
        both_reject = cells[("REJECT", "REJECT")]
        p_value = exact_mcnemar(gained, lost)

        lines += [
            f"  complete pairs                     : {len(paired)}",
            f"  both ACCEPT                        : {both_accept}",
            f"  {BASELINE_PAD} ms ACCEPT, {PRIMARY_PAD} ms REJECT"
            f"          : {lost}",
            f"  {BASELINE_PAD} ms REJECT, {PRIMARY_PAD} ms ACCEPT"
            f"          : {gained}",
            f"  both REJECT                        : {both_reject}",
            "",
            f"  net change from padding            : {gained - lost:+d} tokens",
            f"  exact McNemar (discordant {gained + lost}) : p = {p_value:.4f}",
        ]
        if gained + lost < 6:
            lines.append("  Note: fewer than 6 discordant pairs cannot reach "
                         "p<0.05 in this test, whatever the split.")

    # --- by original quality stratum ----------------------------------------
    def stratum_block(field, title, note=""):
        levels = sorted({r[field] for r in rows if r[field]})
        block = ["", title]
        if note:
            block.append(note)
        if len(levels) <= 1:
            block.append(f"  Only one level present ({levels or ['(none)']}), "
                         f"so this breakdown carries no information.")
            return block
        block.append(f"  {'group':<14}{'pad':>6}{'n':>5}{'ACCEPT':>9}{'ACCEPT%':>10}")
        for level in levels:
            for pad in sorted(by_pad):
                subset = [r for r in rows
                          if r[field] == level and int(r["padding_ms"]) == pad]
                if not subset:
                    continue
                accepted = sum(1 for r in subset
                               if r["human_usability_judgment"] == "ACCEPT")
                block.append(f"  {level:<14}{str(pad) + 'ms':>6}{len(subset):>5}"
                             f"{accepted:>9}{accepted / len(subset) * 100:>9.0f}%")
        return block

    lines += stratum_block(
        "alignment_status", "By original automatic alignment_status:")
    # These 44 tokens all came from round 2, which sampled auto-good only, so
    # alignment_status cannot separate marginal from clean here. The earlier
    # three-level human verdict can, and it is the split the question was
    # really about: does padding help the segments a listener found doubtful?
    lines += stratum_block(
        "prior_three_level",
        "By earlier three-level human judgment (marginal vs clean):",
        "  (that scale self-agreed only 36% of the time, so treat it as a rough"
        " stratifier, not as ground truth)")

    # --- damage check -------------------------------------------------------
    lines += ["", "-" * 80,
              "DAMAGE CHECK: does padding break tokens that were already usable?",
              "-" * 80]
    damaged_rows = []
    for token, base, padded in paired:
        if (base["human_usability_judgment"] == "ACCEPT"
                and padded["human_usability_judgment"] == "REJECT"):
            damaged_rows.append((token, base))
    if not damaged_rows:
        lines.append(f"  No token usable at {BASELINE_PAD} ms became unusable "
                     f"at {PRIMARY_PAD} ms.")
    else:
        lines.append(f"  {len(damaged_rows)} token(s) went ACCEPT -> REJECT:")
        for token, base in damaged_rows:
            lines.append(f"    {base['word']} ({base['expected_pinyin']}) "
                         f"spk {base['speaker_id']}  auto={base['alignment_status']}"
                         f"  {token}")
    clean = [r for r in rows if r["alignment_status"] == "good"]
    if clean:
        base_clean = [r for r in clean if int(r["padding_ms"]) == BASELINE_PAD]
        pad_clean = [r for r in clean if int(r["padding_ms"]) == PRIMARY_PAD]
        if base_clean and pad_clean:
            before = sum(1 for r in base_clean
                         if r["human_usability_judgment"] == "ACCEPT") / len(base_clean)
            after = sum(1 for r in pad_clean
                        if r["human_usability_judgment"] == "ACCEPT") / len(pad_clean)
            lines.append(f"  auto-good ACCEPT rate: {before * 100:.0f}% at "
                         f"{BASELINE_PAD} ms -> {after * 100:.0f}% at "
                         f"{PRIMARY_PAD} ms ({(after - before) * 100:+.0f} pts)")

    # --- gated recommendation ----------------------------------------------
    lines += ["", "=" * 80, "RECOMMENDATION (all four pre-agreed conditions)", "=" * 80]
    if paired:
        base_rate = (by_pad[BASELINE_PAD].get("ACCEPT", 0)
                     / max(sum(by_pad[BASELINE_PAD].values()), 1))
        pad_rate = (by_pad[PRIMARY_PAD].get("ACCEPT", 0)
                    / max(sum(by_pad[PRIMARY_PAD].values()), 1))
        checks = [
            (f"1. {PRIMARY_PAD} ms ACCEPT rate >= {BASELINE_PAD} ms",
             pad_rate >= base_rate, f"{pad_rate * 100:.1f}% vs {base_rate * 100:.1f}%"),
            ("2. more REJECT->ACCEPT than the reverse",
             cells[("REJECT", "ACCEPT")] > cells[("ACCEPT", "REJECT")],
             f"{cells[('REJECT', 'ACCEPT')]} vs {cells[('ACCEPT', 'REJECT')]}"),
            ("3. clean auto-good segments not damaged",
             not any(base["alignment_status"] == "good" for _, base in damaged_rows),
             f"{sum(1 for _, b in damaged_rows if b['alignment_status'] == 'good')}"
             f" auto-good token(s) broken"),
            ("4. direction consistent",
             cells[("REJECT", "ACCEPT")] >= cells[("ACCEPT", "REJECT")],
             "net " f"{cells[('REJECT', 'ACCEPT')] - cells[('ACCEPT', 'REJECT')]:+d}"),
        ]
        for label, passed, detail in checks:
            lines.append(f"  [{'PASS' if passed else 'FAIL'}] {label:<44} {detail}")
        if all(passed for _, passed, _ in checks):
            lines += ["", f"  -> Adopt {PRIMARY_PAD} ms symmetric padding.",
                      "     Significance is not claimed; the criteria are about "
                      "direction and absence of harm."]
        else:
            lines += ["", f"  -> Do NOT adopt {PRIMARY_PAD} ms. At least one "
                      "pre-agreed condition failed.",
                      "     Secondary conditions are descriptive and do not "
                      "substitute for the primary comparison."]

    print("\n".join(lines))

    summary = {
        "trials_prepared": len(key),
        "trials_judged": len(rows),
        "unjudged": unjudged,
        "by_padding": {str(p): dict(c) for p, c in sorted(by_pad.items())},
        "primary": {
            "comparison": f"{PRIMARY_PAD}ms_vs_{BASELINE_PAD}ms",
            "pairs": len(paired),
            "both_accept": cells.get(("ACCEPT", "ACCEPT"), 0) if cells else None,
            "baseline_accept_padded_reject": cells.get(("ACCEPT", "REJECT"), 0) if cells else None,
            "baseline_reject_padded_accept": cells.get(("REJECT", "ACCEPT"), 0) if cells else None,
            "both_reject": cells.get(("REJECT", "REJECT"), 0) if cells else None,
            "mcnemar_exact_p": p_value,
        },
        "by_status": {
            status: {
                str(pad): sum(1 for r in rows
                              if r["alignment_status"] == status
                              and int(r["padding_ms"]) == pad
                              and r["human_usability_judgment"] == "ACCEPT")
                for pad in sorted(by_pad)
            }
            for status in sorted({r["alignment_status"] for r in rows})
        },
        "by_prior_three_level": {
            level: {
                str(pad): sum(1 for r in rows
                              if r["prior_three_level"] == level
                              and int(r["padding_ms"]) == pad
                              and r["human_usability_judgment"] == "ACCEPT")
                for pad in sorted(by_pad)
            }
            for level in sorted({r["prior_three_level"] for r in rows if r["prior_three_level"]})
        },
        "damaged_tokens": [t for t, _ in damaged_rows],
    }
    path = DATA_DIR / "binpad_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary: {path}")


if __name__ == "__main__":
    main()
