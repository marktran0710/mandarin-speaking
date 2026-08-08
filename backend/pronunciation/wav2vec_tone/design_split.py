"""Design, audit and freeze a speaker-disjoint train/dev/test split.

Speakers are assigned whole; no token ever moves on its own, so the split is
speaker-disjoint by construction rather than by a check afterwards.

The search sees only metadata and labels: token counts, correctness, expected
tone, character, syllable. No acoustic feature and no model result enters the
objective, so the split cannot be tuned toward a result that has not been
measured yet.

The binding constraint is the minority class. 351 Incorrect tokens is the whole
statistical budget, and a Dev or Test set with too few of them cannot support
PR-AUC or Incorrect-class recall at all. Class representation is therefore
weighted far above exact 70/15/15 token proportions.

    python -m pronunciation.wav2vec_tone.design_split
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest.csv"
SPLIT_CSV = DATA_DIR / "ompal_speaker_disjoint_split.csv"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
SUMMARY = DATA_DIR / "ompal_split_summary.json"
REPORT = REPORTS_DIR / "ompal_speaker_disjoint_split_audit.md"

SPLIT_ID = "ompal_speaker_split_v1"
ALGORITHM = "random restarts + pairwise/relocation hill-climbing, whole speakers"
SEED = 20260808
TARGET = {"train": 0.70, "dev": 0.15, "test": 0.15}
SPEAKER_TARGET = {"train": (30, 34), "dev": (5, 8), "test": (5, 8)}
MIN_MINORITY_WARN = 40

EXPECTED = {"tokens": 2068, "correct": 1717, "incorrect": 351, "speakers": 45,
            "native": 108}

# Class representation dominates; tone and lexical coverage are tie-breakers.
WEIGHTS = {"incorrect_rate": 400.0, "minority_floor": 250.0,
           "token_proportion": 100.0, "tone_proportion": 40.0,
           "speaker_count": 25.0, "difficulty_spread": 15.0}


def syllable_base(pinyin: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", pinyin)
                    if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", plain.lower().replace("ü", "v"))


def load_learner():
    rows = [r for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))
            if r["speech_type"] == "l2"]
    for row in rows:
        row["_syllable"] = syllable_base(row["expected_pinyin"])
        row["_incorrect"] = row["tone_correctness"] == "0"
    return rows


def speaker_profiles(rows):
    profiles = {}
    for speaker in sorted({r["speaker_id"] for r in rows}):
        subset = [r for r in rows if r["speaker_id"] == speaker]
        incorrect = sum(1 for r in subset if r["_incorrect"])
        profiles[speaker] = {
            "speaker_id": speaker, "n_tokens": len(subset),
            "n_correct": len(subset) - incorrect, "n_incorrect": incorrect,
            "incorrect_rate": incorrect / len(subset),
            "tones": Counter(r["expected_tone"] for r in subset),
            "incorrect_tones": Counter(r["expected_tone"] for r in subset
                                       if r["_incorrect"]),
        }
    return profiles


def score(assignment, profiles, totals) -> float:
    """Lower is better. Every term is a squared relative deviation."""
    penalty = 0.0
    by_split = defaultdict(lambda: {"tokens": 0, "incorrect": 0, "speakers": 0,
                                    "tones": Counter()})
    for speaker, split in assignment.items():
        profile = profiles[speaker]
        bucket = by_split[split]
        bucket["tokens"] += profile["n_tokens"]
        bucket["incorrect"] += profile["n_incorrect"]
        bucket["speakers"] += 1
        bucket["tones"].update(profile["tones"])

    global_rate = totals["incorrect"] / totals["tokens"]
    for split, target in TARGET.items():
        bucket = by_split[split]
        if not bucket["tokens"]:
            return float("inf")

        share = bucket["tokens"] / totals["tokens"]
        penalty += WEIGHTS["token_proportion"] * ((share - target) / target) ** 2

        rate = bucket["incorrect"] / bucket["tokens"]
        penalty += WEIGHTS["incorrect_rate"] * ((rate - global_rate) / global_rate) ** 2

        # A held-out set with too few Incorrect tokens cannot support the
        # minority-class metrics this benchmark exists to report, so shortfall
        # is penalised steeply rather than traded away.
        if split in ("dev", "test") and bucket["incorrect"] < MIN_MINORITY_WARN:
            shortfall = (MIN_MINORITY_WARN - bucket["incorrect"]) / MIN_MINORITY_WARN
            penalty += WEIGHTS["minority_floor"] * shortfall ** 2 * 10

        low, high = SPEAKER_TARGET[split]
        if not low <= bucket["speakers"] <= high:
            distance = min(abs(bucket["speakers"] - low), abs(bucket["speakers"] - high))
            penalty += WEIGHTS["speaker_count"] * distance ** 2

        for tone in ("1", "2", "3", "4"):
            expected = totals["tones"][tone] * target
            if expected:
                penalty += WEIGHTS["tone_proportion"] * (
                    (bucket["tones"][tone] - expected) / expected) ** 2

    # Keep Dev and Test from becoming unusually easy or unusually hard by
    # comparing their median speaker difficulty with the corpus median.
    global_median = float(np.median([p["incorrect_rate"] for p in profiles.values()]))
    for split in ("dev", "test"):
        rates = [profiles[s]["incorrect_rate"]
                 for s, assigned in assignment.items() if assigned == split]
        if rates:
            penalty += WEIGHTS["difficulty_spread"] * (
                (float(np.median(rates)) - global_median) / max(global_median, 1e-6)) ** 2
    return penalty


def search(profiles, totals, seed: int, restarts: int, sweeps: int):
    speakers = sorted(profiles)
    rng = np.random.default_rng(seed)
    sizes = {"train": 32, "dev": 6, "test": 7}
    best, best_score = None, float("inf")

    for _ in range(restarts):
        order = list(speakers)
        rng.shuffle(order)
        assignment = {}
        cursor = 0
        for split, count in sizes.items():
            for speaker in order[cursor:cursor + count]:
                assignment[speaker] = split
            cursor += count
        for speaker in order[cursor:]:
            assignment[speaker] = "train"

        current = score(assignment, profiles, totals)
        for _ in range(sweeps):
            improved = False
            # Swaps keep split sizes fixed; relocations let them breathe within
            # the allowed speaker-count bands.
            for i, first in enumerate(speakers):
                for second in speakers[i + 1:]:
                    if assignment[first] == assignment[second]:
                        continue
                    assignment[first], assignment[second] = (
                        assignment[second], assignment[first])
                    candidate = score(assignment, profiles, totals)
                    if candidate < current - 1e-12:
                        current, improved = candidate, True
                    else:
                        assignment[first], assignment[second] = (
                            assignment[second], assignment[first])
            for speaker in speakers:
                original = assignment[speaker]
                for split in ("train", "dev", "test"):
                    if split == original:
                        continue
                    assignment[speaker] = split
                    candidate = score(assignment, profiles, totals)
                    if candidate < current - 1e-12:
                        current, improved = candidate, True
                        original = split
                    else:
                        assignment[speaker] = original
            if not improved:
                break
        if current < best_score:
            best, best_score = dict(assignment), current
    return best, best_score


def describe(rows, assignment):
    stats = {}
    for split in ("train", "dev", "test"):
        subset = [r for r in rows if assignment[r["speaker_id"]] == split]
        incorrect = [r for r in subset if r["_incorrect"]]
        stats[split] = {
            "speakers": sorted({r["speaker_id"] for r in subset}),
            "n_speakers": len({r["speaker_id"] for r in subset}),
            "n_tokens": len(subset),
            "token_share": len(subset) / len(rows),
            "n_correct": len(subset) - len(incorrect),
            "n_incorrect": len(incorrect),
            "incorrect_rate": len(incorrect) / len(subset) if subset else 0.0,
            "tones": {t: sum(1 for r in subset if r["expected_tone"] == t)
                      for t in ("1", "2", "3", "4")},
            "incorrect_by_tone": {
                t: sum(1 for r in incorrect if r["expected_tone"] == t)
                for t in ("1", "2", "3", "4")},
            "characters": sorted({r["target_character"] for r in subset}),
            "syllables": sorted({r["_syllable"] for r in subset}),
            "utterances": len({r["utterance_id"] for r in subset}),
        }
    return stats


def leakage_checks(rows, assignment, stats) -> list[str]:
    problems = []
    train, dev, test = (set(stats[s]["speakers"]) for s in ("train", "dev", "test"))
    for name, overlap in (("train&dev", train & dev), ("train&test", train & test),
                          ("dev&test", dev & test)):
        if overlap:
            problems.append(f"speaker leakage {name}: {sorted(overlap)}")
    if len(train | dev | test) != EXPECTED["speakers"]:
        problems.append(f"assigned speakers {len(train | dev | test)} != "
                        f"{EXPECTED['speakers']}")

    totals = {k: sum(stats[s][k] for s in ("train", "dev", "test"))
              for k in ("n_tokens", "n_correct", "n_incorrect")}
    if totals["n_tokens"] != EXPECTED["tokens"]:
        problems.append(f"tokens {totals['n_tokens']} != {EXPECTED['tokens']}")
    if totals["n_correct"] != EXPECTED["correct"]:
        problems.append(f"correct {totals['n_correct']} != {EXPECTED['correct']}")
    if totals["n_incorrect"] != EXPECTED["incorrect"]:
        problems.append(f"incorrect {totals['n_incorrect']} != {EXPECTED['incorrect']}")

    seen = defaultdict(set)
    for row in rows:
        seen[row["token_id"]].add(assignment[row["speaker_id"]])
    multi = [k for k, v in seen.items() if len(v) > 1]
    if multi:
        problems.append(f"{len(multi)} token id(s) in more than one split")
    if len(seen) != len(rows):
        problems.append(f"duplicate token ids: {len(rows) - len(seen)}")

    utterance_splits = defaultdict(set)
    for row in rows:
        utterance_splits[row["utterance_id"]].add(assignment[row["speaker_id"]])
    straddling = [u for u, v in utterance_splits.items() if len(v) > 1]
    if straddling:
        problems.append(f"{len(straddling)} utterance(s) straddle splits")

    missing = [r["token_id"] for r in rows
               if not (DATA_DIR / r["extracted_token_path"]).exists()]
    if missing:
        problems.append(f"{len(missing)} segment file(s) missing on disk")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--restarts", type=int, default=40)
    parser.add_argument("--sweeps", type=int, default=12)
    args = parser.parse_args()

    rows = load_learner()
    counts = {"tokens": len(rows),
              "correct": sum(1 for r in rows if not r["_incorrect"]),
              "incorrect": sum(1 for r in rows if r["_incorrect"]),
              "speakers": len({r["speaker_id"] for r in rows})}
    for name, expected in (("tokens", EXPECTED["tokens"]),
                           ("correct", EXPECTED["correct"]),
                           ("incorrect", EXPECTED["incorrect"]),
                           ("speakers", EXPECTED["speakers"])):
        if counts[name] != expected:
            sys.exit(f"STOP: learner {name} = {counts[name]}, expected {expected}. "
                     f"Not adapting expectations; investigate the manifest.")
    print(f"learner population verified: {counts}")

    profiles = speaker_profiles(rows)
    totals = {**counts, "tones": Counter(r["expected_tone"] for r in rows)}
    assignment, objective = search(profiles, totals, args.seed,
                                   args.restarts, args.sweeps)
    stats = describe(rows, assignment)
    problems = leakage_checks(rows, assignment, stats)

    digest = hashlib.sha256(
        json.dumps({k: assignment[k] for k in sorted(assignment)},
                   sort_keys=True).encode("utf-8")).hexdigest()

    # --- outputs ----------------------------------------------------------
    with SPLIT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["speaker_id", "split", "n_tokens", "n_correct",
                         "n_incorrect", "incorrect_rate", "n_T1", "n_T2",
                         "n_T3", "n_T4"])
        for speaker in sorted(profiles):
            profile = profiles[speaker]
            writer.writerow([speaker, assignment[speaker], profile["n_tokens"],
                             profile["n_correct"], profile["n_incorrect"],
                             f"{profile['incorrect_rate']:.4f}",
                             *[profile["tones"].get(t, 0) for t in ("1", "2", "3", "4")]])

    all_rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    fields = [f for f in all_rows[0].keys()] + ["split", "split_id", "split_hash"]
    with MANIFEST_SPLIT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in all_rows:
            # Native tokens are carried with an explicit marker rather than
            # dropped, so nothing can silently assign them to a learner split.
            row["split"] = (assignment[row["speaker_id"]]
                            if row["speech_type"] == "l2" else "native_reference")
            row["split_id"] = SPLIT_ID
            row["split_hash"] = digest[:16]
            writer.writerow(row)

    lexical = {}
    train_characters = set(stats["train"]["characters"])
    train_syllables = set(stats["train"]["syllables"])
    for split in ("dev", "test"):
        subset = [r for r in rows if assignment[r["speaker_id"]] == split]
        unseen_characters = sorted(set(stats[split]["characters"]) - train_characters)
        unseen_syllables = sorted(set(stats[split]["syllables"]) - train_syllables)
        lexical[split] = {
            "n_characters": len(stats[split]["characters"]),
            "n_syllables": len(stats[split]["syllables"]),
            "characters_unseen_in_train": unseen_characters,
            "syllables_unseen_in_train": unseen_syllables,
            "pct_tokens_unseen_character": (
                sum(1 for r in subset if r["target_character"] in unseen_characters)
                / len(subset) * 100 if subset else 0.0),
            "pct_tokens_unseen_syllable": (
                sum(1 for r in subset if r["_syllable"] in unseen_syllables)
                / len(subset) * 100 if subset else 0.0),
        }
    lexical["train"] = {"n_characters": len(train_characters),
                        "n_syllables": len(train_syllables)}

    difficulty = {}
    for split in ("train", "dev", "test"):
        rates = [profiles[s]["incorrect_rate"] for s in stats[split]["speakers"]]
        difficulty[split] = {
            "min": float(np.min(rates)), "q1": float(np.percentile(rates, 25)),
            "median": float(np.median(rates)), "q3": float(np.percentile(rates, 75)),
            "max": float(np.max(rates))}

    summary = {
        "split_id": SPLIT_ID, "seed": args.seed, "split_algorithm": ALGORITHM,
        "objective_function": {
            "weights": WEIGHTS,
            "targets": TARGET,
            "speaker_count_bands": {k: list(v) for k, v in SPEAKER_TARGET.items()},
            "minority_floor": MIN_MINORITY_WARN,
            "score": objective,
            "inputs": "metadata and labels only; no acoustic feature, no model output",
        },
        "speaker_counts": {s: stats[s]["n_speakers"] for s in stats},
        "token_counts": {s: stats[s]["n_tokens"] for s in stats},
        "token_shares": {s: stats[s]["token_share"] for s in stats},
        "class_counts": {s: {"correct": stats[s]["n_correct"],
                             "incorrect": stats[s]["n_incorrect"]} for s in stats},
        "class_rates": {s: stats[s]["incorrect_rate"] for s in stats},
        "tone_counts": {s: stats[s]["tones"] for s in stats},
        "incorrect_by_tone": {s: stats[s]["incorrect_by_tone"] for s in stats},
        "lexical_coverage": lexical,
        "speaker_difficulty_statistics": difficulty,
        "leakage_checks": {"failures": problems, "passed": not problems},
        "frozen_split_definition": {
            "speaker_to_split": {k: assignment[k] for k in sorted(assignment)},
            "sha256": digest,
            "native_reference_tokens": EXPECTED["native"],
            "note": "Frozen. Do not regenerate because model results disappoint.",
        },
        "metrics_planning_note": (
            "Majority-class accuracy is 83.0%, so Accuracy alone is not "
            "informative. Later comparison must report Balanced Accuracy, "
            "Macro-F1, Incorrect-class precision/recall/F1, ROC-AUC and "
            "PR-AUC; Accuracy is secondary and descriptive only."),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float),
                       encoding="utf-8")
    write_report(summary, stats, profiles, assignment, problems, digest)

    print(f"\nobjective score: {objective:.4f}")
    header = f"{'':<14}{'Train':>10}{'Dev':>10}{'Test':>10}"
    print("\n" + header)
    for label, key in (("Speakers", "n_speakers"), ("Tokens", "n_tokens"),
                       ("Correct", "n_correct"), ("Incorrect", "n_incorrect")):
        print(f"{label:<14}" + "".join(f"{stats[s][key]:>10}"
                                       for s in ("train", "dev", "test")))
    print(f"{'Token %':<14}" + "".join(f"{stats[s]['token_share'] * 100:>9.1f}%"
                                       for s in ("train", "dev", "test")))
    print(f"{'Incorrect %':<14}" + "".join(f"{stats[s]['incorrect_rate'] * 100:>9.1f}%"
                                           for s in ("train", "dev", "test")))
    for tone in ("1", "2", "3", "4"):
        print(f"{'T' + tone:<14}" + "".join(f"{stats[s]['tones'][tone]:>10}"
                                            for s in ("train", "dev", "test")))
    print(f"\nleakage failures: {len(problems)}")
    for problem in problems:
        print(f"  FAIL {problem}")
    print(f"\nsplit hash: {digest[:16]}")
    print(f"files: {SPLIT_CSV.name}, {MANIFEST_SPLIT.name}, {SUMMARY.name}, "
          f"{REPORT.name}")


def write_report(summary, stats, profiles, assignment, problems, digest) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    columns = ("train", "dev", "test")
    lines = [
        f"# OMPAL speaker-disjoint split audit — `{SPLIT_ID}`",
        "",
        f"seed `{summary['seed']}` · algorithm: {ALGORITHM} · objective "
        f"{summary['objective_function']['score']:.4f} · hash `{digest[:16]}`",
        "",
        "## Split summary",
        "",
        "| | Train | Dev | Test |",
        "|---|---|---|---|",
        "| Speakers | " + " | ".join(str(stats[s]["n_speakers"]) for s in columns) + " |",
        "| Tokens | " + " | ".join(str(stats[s]["n_tokens"]) for s in columns) + " |",
        "| % of tokens | " + " | ".join(f"{stats[s]['token_share'] * 100:.1f}%"
                                        for s in columns) + " |",
        "| Correct | " + " | ".join(str(stats[s]["n_correct"]) for s in columns) + " |",
        "| Incorrect | " + " | ".join(str(stats[s]["n_incorrect"]) for s in columns) + " |",
        "| Incorrect % | " + " | ".join(f"{stats[s]['incorrect_rate'] * 100:.1f}%"
                                        for s in columns) + " |",
    ]
    for tone in ("1", "2", "3", "4"):
        lines.append(f"| T{tone} | " + " | ".join(str(stats[s]["tones"][tone])
                                                  for s in columns) + " |")
    lines += [
        "",
        "## Minority-class adequacy",
        "",
        "351 Incorrect tokens are the entire statistical budget for this",
        "benchmark, so held-out minority counts matter more than exact token",
        "proportions.",
        "",
    ]
    for split in columns:
        count = stats[split]["n_incorrect"]
        flag = ("  **WARNING: below the ~40 guidance**"
                if split in ("dev", "test") and count < MIN_MINORITY_WARN else "")
        lines.append(f"- {split.capitalize()} Incorrect = **{count}**{flag}")
    lines += [
        "",
        "## Tone x correctness by split",
        "",
    ]
    for split in columns:
        lines += [f"### {split.capitalize()}", "",
                  "| tone | Correct | Incorrect |", "|---|---|---|"]
        for tone in ("1", "2", "3", "4"):
            total = stats[split]["tones"][tone]
            bad = stats[split]["incorrect_by_tone"][tone]
            lines.append(f"| T{tone} | {total - bad} | {bad} |")
        lines.append("")

    lexical = summary["lexical_coverage"]
    lines += [
        "## Lexical coverage",
        "",
        f"Train covers {lexical['train']['n_characters']} characters and "
        f"{lexical['train']['n_syllables']} syllable bases.",
        "",
        "| | Dev | Test |",
        "|---|---|---|",
        f"| characters | {lexical['dev']['n_characters']} | "
        f"{lexical['test']['n_characters']} |",
        f"| syllables | {lexical['dev']['n_syllables']} | "
        f"{lexical['test']['n_syllables']} |",
        f"| characters unseen in Train | "
        f"{len(lexical['dev']['characters_unseen_in_train'])} | "
        f"{len(lexical['test']['characters_unseen_in_train'])} |",
        f"| syllables unseen in Train | "
        f"{len(lexical['dev']['syllables_unseen_in_train'])} | "
        f"{len(lexical['test']['syllables_unseen_in_train'])} |",
        f"| % tokens w/ unseen character | "
        f"{lexical['dev']['pct_tokens_unseen_character']:.1f}% | "
        f"{lexical['test']['pct_tokens_unseen_character']:.1f}% |",
        f"| % tokens w/ unseen syllable | "
        f"{lexical['dev']['pct_tokens_unseen_syllable']:.1f}% | "
        f"{lexical['test']['pct_tokens_unseen_syllable']:.1f}% |",
        "",
        "Lexical novelty is quantified, not eliminated — some is useful for",
        "measuring generalisation.",
        "",
        "## Speaker difficulty",
        "",
        "Speaker Incorrect rate, per split:",
        "",
        "| | min | Q1 | median | Q3 | max |",
        "|---|---|---|---|---|---|",
    ]
    for split in columns:
        entry = summary["speaker_difficulty_statistics"][split]
        lines.append(f"| {split} | " + " | ".join(
            f"{entry[k] * 100:.1f}%" for k in ("min", "q1", "median", "q3", "max")) + " |")

    lines += [
        "",
        "## Speaker assignment",
        "",
    ]
    for split in columns:
        lines.append(f"- **{split}** ({stats[split]['n_speakers']}): "
                     + ", ".join(stats[split]["speakers"]))

    lines += [
        "",
        "## Leakage checks",
        "",
    ]
    if problems:
        lines.append(f"**{len(problems)} FAILED:**")
        lines += [f"- {problem}" for problem in problems]
    else:
        lines += [
            "All passed:",
            "- train ∩ dev = ∅, train ∩ test = ∅, dev ∩ test = ∅",
            "- 45 unique learner speakers assigned, each to exactly one split",
            "- tokens 2068 = train + dev + test; correct 1717; incorrect 351",
            "- no token id in more than one split, no duplicate token ids",
            "- no utterance straddles two splits",
            "- every segment file referenced by the manifest exists on disk",
        ]

    lines += [
        "",
        "## Native reference data",
        "",
        f"The {EXPECTED['native']} native tokens (speakers 01001-01003) are "
        "outside the primary split. They appear in the split manifest only as "
        "`split = native_reference`, and are not to be used as training "
        "examples for the learner classifier without an explicit later "
        "research decision.",
        "",
        "## Metrics planning",
        "",
        summary["metrics_planning_note"],
        "",
        "## Freeze",
        "",
        f"Split `{SPLIT_ID}` is frozen. SHA-256 of the sorted speaker→split "
        f"mapping:",
        "",
        f"`{digest}`",
        "",
        "Do not regenerate this split because model results are disappointing.",
        "The Test set must not influence any modelling decision.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
