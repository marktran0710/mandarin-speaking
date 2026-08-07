"""Can automatic indicators predict which segments a human finds usable?

Padding is closed and the original boundaries stay. The remaining lever is
selection: if the pipeline can tell in advance which segments are usable, the
benchmark can keep those and drop the rest.

Only original-boundary (0 ms) judgments count here. The binary reliability
review was presented at 40 ms, so it is excluded despite being binary --
mixing it in would attribute padded audio to unpadded features.

Predictors are restricted to what the aligner and signal already produce.
Tone correctness, expected tone, lexical identity, speaker and any wav2vec2
output are excluded: several would leak the answer, and a QC rule that needs
to know the target tone cannot run before the tone is measured.

The objective is precision among retained segments, not retention. A benchmark
contaminated by unusable audio is worse than a smaller clean one.

    python -m pronunciation.wav2vec_tone.segment_qc_diagnostic
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
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"

# (key file, judgments file, padding column, value that means original boundary)
SOURCES = (
    ("binpad_trial_key.csv", "ompal_binpad_human_review.csv", "padding_ms", "0"),
    ("confirm_trial_key.csv", "ompal_confirm_human_review.csv", "padding_ms", "0"),
)
# Excluded on purpose, with the reason recorded in the output.
EXCLUDED = (("binary_trial_key.csv", "presented at 40 ms, not original boundary"),)

TARGET_PRECISION = 0.95


def token_key(utterance_id: str, index) -> str:
    return f"{utterance_id}_{int(index):02d}"


def collect() -> tuple[list[dict], dict]:
    """All 0 ms binary judgments, joined to the pipeline's own QC features."""
    features = {}
    for row in csv.DictReader(PILOT_CSV.open(encoding="utf-8")):
        if not row["start_seconds"]:
            continue
        features[token_key(row["utterance_id"], row["token_index"])] = row

    judgments = defaultdict(list)
    per_source = {}
    for key_file, review_file, pad_column, original in SOURCES:
        key_path, review_path = DATA_DIR / key_file, DATA_DIR / review_file
        if not (key_path.exists() and review_path.exists()):
            per_source[key_file] = None
            continue
        key = {r["trial_id"]: r
               for r in csv.DictReader(key_path.open(encoding="utf-8"))}
        count = 0
        for row in csv.DictReader(review_path.open(encoding="utf-8")):
            entry = key.get(row["trial_id"])
            if entry is None or str(entry[pad_column]) != original:
                continue
            verdict = row["human_usability_judgment"].strip().upper()
            if verdict not in ("ACCEPT", "REJECT"):
                continue
            judgments[entry["token_id"]].append({
                "verdict": verdict,
                "source": key_file.replace("_trial_key.csv", ""),
                "trial_id": row["trial_id"],
            })
            count += 1
        per_source[key_file] = count

    rows, repeats, conflicts = [], [], []
    for token_id, entries in sorted(judgments.items()):
        verdicts = {e["verdict"] for e in entries}
        if len(entries) > 1:
            repeats.append((token_id, entries))
            if len(verdicts) > 1:
                conflicts.append((token_id, entries))
                continue        # kept out of the primary set, reported below
        feature = features.get(token_id)
        if feature is None:
            continue
        rows.append({
            "token_id": token_id,
            "verdict": entries[0]["verdict"],
            "n_judgments": len(entries),
            "source": entries[0]["source"],
            "alignment_score": float(feature["alignment_score"] or "nan"),
            "voiced_proportion": float(feature["voiced_proportion"] or "nan"),
            "duration_seconds": float(feature["duration_seconds"] or "nan"),
            "alignment_status": feature["alignment_status"],
            "flags": feature["alignment_note"],
        })
    return rows, {"per_source": per_source, "repeats": repeats,
                  "conflicts": conflicts}


def auc(values, labels) -> float:
    """ROC AUC via rank sum; ties get average ranks."""
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    finite = np.isfinite(values)
    values, labels = values[finite], labels[finite]
    positives, negatives = int(labels.sum()), int((~labels).sum())
    if not positives or not negatives:
        return float("nan")
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    sorted_values = values[order]
    index = 0
    while index < len(sorted_values):
        stop = index
        while stop + 1 < len(sorted_values) and sorted_values[stop + 1] == sorted_values[index]:
            stop += 1
        ranks[order[index:stop + 1]] = (index + stop) / 2.0 + 1.0
        index = stop + 1
    return float((ranks[labels].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


def describe(values) -> str:
    values = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not len(values):
        return f"{'--':>8}"
    return (f"{len(values):>5}{values.min():>9.3f}{np.percentile(values, 25):>9.3f}"
            f"{np.median(values):>9.3f}{values.mean():>9.3f}"
            f"{np.percentile(values, 75):>9.3f}{values.max():>9.3f}")


def evaluate_rule(rows, name: str, predicate) -> dict:
    retained = [r for r in rows if predicate(r)]
    discarded = [r for r in rows if not predicate(r)]
    accepted = sum(1 for r in retained if r["verdict"] == "ACCEPT")
    rejected = len(retained) - accepted
    return {
        "rule": name,
        "retained": len(retained),
        "retention_rate": len(retained) / len(rows) if rows else 0.0,
        "accept_retained": accepted,
        "reject_retained": rejected,
        "precision": accepted / len(retained) if retained else float("nan"),
        "accept_discarded": sum(1 for r in discarded if r["verdict"] == "ACCEPT"),
        "reject_discarded": sum(1 for r in discarded if r["verdict"] == "REJECT"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    rows, meta = collect()
    if not rows:
        sys.exit("No 0 ms binary judgments found.")

    counts = Counter(r["verdict"] for r in rows)
    total = len(rows)
    base_rate = counts["ACCEPT"] / total

    lines = [
        "=" * 84,
        "SEGMENT QC DIAGNOSTIC — original-boundary (0 ms) segments only",
        "=" * 84,
        "Sources:",
    ]
    for key_file, _, _, _ in SOURCES:
        count = meta["per_source"].get(key_file)
        lines.append(f"  {key_file:<26}"
                     + ("absent" if count is None else f"{count:>4} judgments at 0 ms"))
    for key_file, reason in EXCLUDED:
        lines.append(f"  {key_file:<26}EXCLUDED — {reason}")

    lines += [
        "",
        f"Unique reviewed 0-ms tokens   : {total}",
        f"ACCEPT                        : {counts['ACCEPT']} ({base_rate * 100:.1f}%)",
        f"REJECT                        : {counts['REJECT']} "
        f"({counts['REJECT'] / total * 100:.1f}%)",
        f"Repeated-token judgments      : {len(meta['repeats'])}",
        f"Conflicting repeated judgments: {len(meta['conflicts'])}",
    ]
    for token_id, entries in meta["conflicts"]:
        lines.append("  conflict " + token_id + ": "
                     + ", ".join(f"{e['source']}/{e['trial_id']}={e['verdict']}"
                                 for e in entries)
                     + "  (excluded from the primary set, not resolved)")
    if not meta["repeats"]:
        lines.append("  (the two sources are token-disjoint by construction, so no "
                     "token was judged twice at 0 ms)")

    lines += ["",
              "Features unavailable for OMPAL segments and therefore not analysed:",
              "  voiced_frames, total_frames — recorded for the AISHELL set only.",
              "  No other alignment-confidence value exists in the pipeline."]

    # --- univariate --------------------------------------------------------
    accept_mask = [r["verdict"] == "ACCEPT" for r in rows]
    numeric = ("alignment_score", "voiced_proportion", "duration_seconds")
    lines += ["", "-" * 84, "NUMERIC FEATURES", "-" * 84,
              f"  {'feature / group':<28}{'n':>5}{'min':>9}{'p25':>9}{'median':>9}"
              f"{'mean':>9}{'p75':>9}{'max':>9}"]
    aucs = {}
    for feature in numeric:
        for label, wanted in (("ACCEPT", True), ("REJECT", False)):
            subset = [r[feature] for r, keep in zip(rows, accept_mask) if keep == wanted]
            lines.append(f"  {feature + ' / ' + label:<28}" + describe(subset))
        value = auc([r[feature] for r in rows], accept_mask)
        aucs[feature] = value
        direction = ("higher -> more usable" if value > 0.5
                     else "lower -> more usable" if value < 0.5 else "none")
        lines.append(f"  {'  AUC':<28}{value:>9.3f}   ({direction})")
        lines.append("")

    # --- flags -------------------------------------------------------------
    flag_names = sorted({f for r in rows for f in r["flags"].split("|") if f})
    lines += ["-" * 84, "FLAGS AND STATUS", "-" * 84,
              f"  {'indicator':<26}{'absent n':>10}{'ACC%':>8}"
              f"{'present n':>11}{'ACC%':>8}"]
    flag_stats = {}
    for flag in flag_names:
        present = [r for r in rows if flag in r["flags"].split("|")]
        absent = [r for r in rows if flag not in r["flags"].split("|")]
        pa = (sum(1 for r in present if r["verdict"] == "ACCEPT") / len(present)
              if present else float("nan"))
        aa = (sum(1 for r in absent if r["verdict"] == "ACCEPT") / len(absent)
              if absent else float("nan"))
        flag_stats[flag] = {"present": len(present), "accept_present": pa,
                            "absent": len(absent), "accept_absent": aa}
        lines.append(f"  {flag:<26}{len(absent):>10}{aa * 100:>7.0f}%"
                     f"{len(present):>11}"
                     + (f"{pa * 100:>7.0f}%" if present else f"{'--':>8}"))
    for status in sorted({r["alignment_status"] for r in rows}):
        subset = [r for r in rows if r["alignment_status"] == status]
        rate = sum(1 for r in subset if r["verdict"] == "ACCEPT") / len(subset)
        lines.append(f"  status={status:<19}{'':>10}{'':>8}{len(subset):>11}"
                     f"{rate * 100:>7.0f}%")

    # --- a small, pre-specified rule set -----------------------------------
    # Round numbers fixed in advance, not swept. With 116 tokens a threshold
    # search would fit the review set rather than describe it.
    rules = [
        ("no flags at all", lambda r: not r["flags"]),
        ("alignment_status == good", lambda r: r["alignment_status"] == "good"),
        ("score >= 0.70", lambda r: r["alignment_score"] >= 0.70),
        ("score >= 0.85", lambda r: r["alignment_score"] >= 0.85),
        ("voiced_proportion >= 0.50", lambda r: r["voiced_proportion"] >= 0.50),
        ("duration >= 0.10 s", lambda r: r["duration_seconds"] >= 0.10),
        ("good AND score >= 0.85",
         lambda r: r["alignment_status"] == "good" and r["alignment_score"] >= 0.85),
        ("good AND voiced >= 0.50",
         lambda r: r["alignment_status"] == "good" and r["voiced_proportion"] >= 0.50),
        ("good AND score >= 0.85 AND voiced >= 0.50 AND dur >= 0.10",
         lambda r: (r["alignment_status"] == "good" and r["alignment_score"] >= 0.85
                    and r["voiced_proportion"] >= 0.50
                    and r["duration_seconds"] >= 0.10)),
    ]
    results = [evaluate_rule(rows, name, predicate) for name, predicate in rules]

    lines += ["", "-" * 84,
              f"CANDIDATE RULES ({len(rules)} pre-specified; no threshold search)",
              "-" * 84,
              f"  {'rule':<50}{'kept':>6}{'keep%':>7}{'ACC':>5}{'REJ':>5}"
              f"{'prec':>7}{'ACC lost':>10}"]
    for result in results:
        lines.append(
            f"  {result['rule']:<50}{result['retained']:>6}"
            f"{result['retention_rate'] * 100:>6.0f}%{result['accept_retained']:>5}"
            f"{result['reject_retained']:>5}{result['precision'] * 100:>6.1f}%"
            f"{result['accept_discarded']:>10}"
        )
    lines += [f"  {'(no rule — keep everything)':<50}{total:>6}{100:>6.0f}%"
              f"{counts['ACCEPT']:>5}{counts['REJECT']:>5}{base_rate * 100:>6.1f}%"
              f"{0:>10}"]

    # --- verdict -----------------------------------------------------------
    viable = [r for r in results
              if np.isfinite(r["precision"]) and r["precision"] >= TARGET_PRECISION
              and r["retention_rate"] >= 0.5]
    best_feature = max(aucs, key=lambda k: abs(aucs[k] - 0.5))
    ranked = sorted(
        (r for r in results if np.isfinite(r["precision"])),
        key=lambda r: (r["precision"], r["retention_rate"]), reverse=True)
    best_rule = ranked[0] if ranked else None

    lines += ["", "=" * 84, "SUMMARY", "=" * 84,
              f"Reviewed 0-ms tokens : {total}",
              f"Human ACCEPT rate    : {base_rate * 100:.1f}%",
              "",
              f"Best single QC indicator : {best_feature}",
              f"AUC / association        : {aucs[best_feature]:.3f} "
              f"({'higher' if aucs[best_feature] > 0.5 else 'lower'} = more usable)"]
    if best_rule:
        lines += [
            "",
            f"Most promising simple QC rule : {best_rule['rule']}",
            f"Retention                     : {best_rule['retained']}/{total} "
            f"({best_rule['retention_rate'] * 100:.0f}%)",
            f"Human ACCEPT among retained   : {best_rule['accept_retained']} "
            f"({best_rule['precision'] * 100:.1f}%)",
            f"Human REJECT among retained   : {best_rule['reject_retained']}",
        ]

    if viable:
        answer = "YES"
        detail = (f"{len(viable)} rule(s) reach >={TARGET_PRECISION * 100:.0f}% "
                  f"precision while keeping at least half the data.")
    elif best_rule and best_rule["precision"] >= TARGET_PRECISION:
        answer = "UNCERTAIN"
        detail = ("A rule reaches the precision target but discards most of the "
                  "data, so it is not yet a usable filter.")
    else:
        answer = "NO" if base_rate < TARGET_PRECISION - 0.05 else "UNCERTAIN"
        best_precision = max((r["precision"] for r in results
                              if np.isfinite(r["precision"])), default=float("nan"))
        detail = (f"No pre-specified rule reaches "
                  f"{TARGET_PRECISION * 100:.0f}% precision "
                  f"(best {best_precision * 100:.1f}%, base rate "
                  f"{base_rate * 100:.1f}%).")
    lines += ["",
              f"Can automated QC plausibly reach >={TARGET_PRECISION * 100:.0f}% "
              f"clean segments? {answer}",
              f"  {detail}"]

    # Honest bound on what this set can establish.
    lines += ["",
              f"Sample bound: {counts['REJECT']} REJECT tokens in total. A rule's "
              f"precision here rests on",
              f"a handful of negatives, so differences of a few percent between "
              f"rules are noise."]
    print("\n".join(lines))

    payload = {
        "sources": {k: v for k, v in meta["per_source"].items()},
        "excluded_sources": {k: r for k, r in EXCLUDED},
        "unique_tokens": total,
        "accept": counts["ACCEPT"], "reject": counts["REJECT"],
        "accept_rate": base_rate,
        "repeated_tokens": len(meta["repeats"]),
        "conflicting_tokens": [t for t, _ in meta["conflicts"]],
        "auc": aucs,
        "flags": flag_stats,
        "by_status": {
            status: {
                "n": sum(1 for r in rows if r["alignment_status"] == status),
                "accept_rate": (
                    sum(1 for r in rows if r["alignment_status"] == status
                        and r["verdict"] == "ACCEPT")
                    / sum(1 for r in rows if r["alignment_status"] == status))
            }
            for status in sorted({r["alignment_status"] for r in rows})
        },
        "rules": results,
        "target_precision": TARGET_PRECISION,
        "answer": answer,
        "adopted": None,
    }
    path = DATA_DIR / "ompal_segment_qc_diagnostic.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()
