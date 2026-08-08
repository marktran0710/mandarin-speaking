"""Complete the split audit and decide whether ompal_speaker_split_v1 freezes.

Reads the split files produced earlier and re-derives everything from them.
Nothing is regenerated: if the assignment on disk disagreed with the recorded
hash, that is a finding, not something to quietly recompute.

    python -m pronunciation.wav2vec_tone.verify_split
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
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
SPLIT_CSV = DATA_DIR / "ompal_speaker_disjoint_split.csv"
SUMMARY = DATA_DIR / "ompal_split_summary.json"
LOCK = DATA_DIR / "ompal_split_FROZEN.json"
REPORT = REPORTS_DIR / "ompal_speaker_disjoint_split_audit.md"

SPLIT_ID = "ompal_speaker_split_v1"
SPLITS = ("train", "dev", "test")
EXPECTED = {"tokens": 2068, "correct": 1717, "incorrect": 351,
            "speakers": 45, "native": 108}
MIN_MINORITY = 40
GLOBAL_INCORRECT_RATE = 351 / 2068


def syllable_base(pinyin: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", pinyin)
                    if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", plain.lower().replace("ü", "v"))


class Checks:
    """Every assertion is recorded, passed or failed, and reported."""

    def __init__(self):
        self.results = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append({"name": name, "pass": bool(ok), "detail": detail})
        return bool(ok)

    @property
    def failures(self):
        return [r for r in self.results if not r["pass"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    rows = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    for row in rows:
        row["_syllable"] = syllable_base(row["expected_pinyin"])
        row["_incorrect"] = row["tone_correctness"] == "0"
    learner = [r for r in rows if r["speech_type"] == "l2"]
    native = [r for r in rows if r["speech_type"] == "native"]
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    checks = Checks()

    by_split = {s: [r for r in learner if r["split"] == s] for s in SPLITS}
    speakers = {s: sorted({r["speaker_id"] for r in by_split[s]}) for s in SPLITS}

    # --- 1. class distribution --------------------------------------------
    klass = {}
    for split in SPLITS:
        subset = by_split[split]
        incorrect = sum(1 for r in subset if r["_incorrect"])
        klass[split] = {
            "n_tokens": len(subset), "correct": len(subset) - incorrect,
            "incorrect": incorrect,
            "incorrect_rate": incorrect / len(subset) if subset else 0.0,
            "delta_vs_global": (incorrect / len(subset) - GLOBAL_INCORRECT_RATE)
            if subset else 0.0,
        }
    total_correct = sum(klass[s]["correct"] for s in SPLITS)
    total_incorrect = sum(klass[s]["incorrect"] for s in SPLITS)
    checks.check("total Correct == 1717", total_correct == EXPECTED["correct"],
                 f"{total_correct}")
    checks.check("total Incorrect == 351", total_incorrect == EXPECTED["incorrect"],
                 f"{total_incorrect}")
    for split in ("dev", "test"):
        count = klass[split]["incorrect"]
        checks.check(f"{split} Incorrect >= {MIN_MINORITY}", count >= MIN_MINORITY,
                     f"{count}")

    # --- 2. tone x correctness --------------------------------------------
    tone_tables = {}
    sparse = []
    for split in SPLITS:
        table = {}
        for tone in ("1", "2", "3", "4"):
            subset = [r for r in by_split[split] if r["expected_tone"] == tone]
            bad = sum(1 for r in subset if r["_incorrect"])
            table[tone] = {"correct": len(subset) - bad, "incorrect": bad,
                           "total": len(subset)}
            if split in ("dev", "test") and 0 < bad < 10:
                sparse.append(f"{split} T{tone} Incorrect = {bad}")
            if split in ("dev", "test") and bad == 0 and subset:
                sparse.append(f"{split} T{tone} Incorrect = 0 (EMPTY CELL)")
        tone_tables[split] = table

    # --- 3. speaker difficulty --------------------------------------------
    profiles = {}
    for speaker in sorted({r["speaker_id"] for r in learner}):
        subset = [r for r in learner if r["speaker_id"] == speaker]
        incorrect = sum(1 for r in subset if r["_incorrect"])
        profiles[speaker] = {
            "split": subset[0]["split"], "n_tokens": len(subset),
            "n_correct": len(subset) - incorrect, "n_incorrect": incorrect,
            "incorrect_rate": incorrect / len(subset),
        }
    difficulty = {}
    for split in SPLITS:
        rates = np.asarray([profiles[s]["incorrect_rate"] for s in speakers[split]])
        difficulty[split] = {
            "min": float(rates.min()), "q1": float(np.percentile(rates, 25)),
            "median": float(np.median(rates)), "q3": float(np.percentile(rates, 75)),
            "max": float(rates.max()), "mean": float(rates.mean()),
        }
    all_rates = np.asarray([p["incorrect_rate"] for p in profiles.values()])
    corpus_q1, corpus_q3 = np.percentile(all_rates, [25, 75])
    concentration = {}
    for split in ("dev", "test"):
        rates = [profiles[s]["incorrect_rate"] for s in speakers[split]]
        concentration[split] = {
            "below_corpus_q1": sum(1 for r in rates if r < corpus_q1),
            "above_corpus_q3": sum(1 for r in rates if r > corpus_q3),
            "n_speakers": len(rates),
        }

    # --- 4. lexical coverage ----------------------------------------------
    train_characters = {r["target_character"] for r in by_split["train"]}
    train_syllables = {r["_syllable"] for r in by_split["train"]}
    lexical = {}
    for split in SPLITS:
        subset = by_split[split]
        characters = {r["target_character"] for r in subset}
        syllables = {r["_syllable"] for r in subset}
        entry = {"n_characters": len(characters), "n_syllables": len(syllables)}
        if split != "train":
            unseen_characters = characters - train_characters
            unseen_syllables = syllables - train_syllables
            token_unseen_character = sum(
                1 for r in subset if r["target_character"] in unseen_characters)
            token_unseen_syllable = sum(
                1 for r in subset if r["_syllable"] in unseen_syllables)
            single_class_characters = [
                c for c in characters
                if len({r["_incorrect"] for r in subset
                        if r["target_character"] == c}) == 1]
            single_class_syllables = [
                s for s in syllables
                if len({r["_incorrect"] for r in subset if r["_syllable"] == s}) == 1]
            entry.update({
                "characters_unseen_in_train": sorted(unseen_characters),
                "syllables_unseen_in_train": sorted(unseen_syllables),
                "tokens_unseen_character": token_unseen_character,
                "pct_tokens_unseen_character": token_unseen_character / len(subset) * 100,
                "tokens_unseen_syllable": token_unseen_syllable,
                "pct_tokens_unseen_syllable": token_unseen_syllable / len(subset) * 100,
                "single_class_characters": len(single_class_characters),
                "single_class_syllables": len(single_class_syllables),
            })
        lexical[split] = entry

    # --- 5. leakage --------------------------------------------------------
    train, dev, test = (set(speakers[s]) for s in SPLITS)
    checks.check("train ∩ dev == empty", not (train & dev), str(sorted(train & dev)))
    checks.check("train ∩ test == empty", not (train & test), str(sorted(train & test)))
    checks.check("dev ∩ test == empty", not (dev & test), str(sorted(dev & test)))
    checks.check("45 unique learner speakers assigned once",
                 len(train | dev | test) == EXPECTED["speakers"]
                 and len(train) + len(dev) + len(test) == EXPECTED["speakers"],
                 f"{len(train | dev | test)} unique / "
                 f"{len(train) + len(dev) + len(test)} total")
    checks.check("2068 learner tokens assigned once",
                 sum(klass[s]["n_tokens"] for s in SPLITS) == EXPECTED["tokens"],
                 str(sum(klass[s]["n_tokens"] for s in SPLITS)))

    token_ids = Counter(r["token_id"] for r in rows)
    checks.check("no duplicate token IDs", all(v == 1 for v in token_ids.values()),
                 f"{sum(1 for v in token_ids.values() if v > 1)} duplicated")
    full_rows = Counter(tuple(sorted((k, v) for k, v in r.items()
                                     if not k.startswith("_"))) for r in rows)
    checks.check("no duplicate rows", all(v == 1 for v in full_rows.values()),
                 f"{sum(1 for v in full_rows.values() if v > 1)} duplicated")

    token_splits = defaultdict(set)
    for row in learner:
        token_splits[row["token_id"]].add(row["split"])
    checks.check("no token ID in two splits",
                 all(len(v) == 1 for v in token_splits.values()))
    utterance_splits = defaultdict(set)
    for row in learner:
        utterance_splits[row["utterance_id"]].add(row["split"])
    straddling = [u for u, v in utterance_splits.items() if len(v) > 1]
    checks.check("no utterance straddles splits", not straddling,
                 f"{len(straddling)} straddling")
    utterance_speakers = defaultdict(set)
    for row in learner:
        utterance_speakers[row["utterance_id"]].add(row["speaker_id"])
    checks.check("no utterance maps to two speakers",
                 all(len(v) == 1 for v in utterance_speakers.values()))

    checks.check("every learner row has a split label",
                 all(r["split"] in SPLITS for r in learner),
                 f"{sum(1 for r in learner if r['split'] not in SPLITS)} missing")

    # Derived paths must encode the same speaker as the row claims, otherwise a
    # split boundary could be crossed by a filename rather than by an id.
    path_mismatch = [
        r["token_id"] for r in rows
        if f"SPEAKER{r['utterance_id'][1:6]}" not in r["source_utterance_path"]
        or r["utterance_id"][1:6] != r["speaker_id"]
        or not r["extracted_token_path"].endswith(f"{r['token_id']}.wav")
    ]
    checks.check("derived paths match row speaker/token", not path_mismatch,
                 f"{len(path_mismatch)} mismatched")

    missing_audio = [r["token_id"] for r in rows
                     if not (DATA_DIR / r["extracted_token_path"]).exists()]
    checks.check("all token segment files exist", not missing_audio,
                 f"{len(missing_audio)} missing")

    # --- 6. native containment --------------------------------------------
    checks.check("native tokens == 108", len(native) == EXPECTED["native"],
                 str(len(native)))
    checks.check("all native rows marked native_reference",
                 all(r["split"] == "native_reference" for r in native))
    checks.check("no native row in a learner split",
                 not any(r["split"] in SPLITS for r in native))
    checks.check("no learner row marked native_reference",
                 not any(r["split"] == "native_reference" for r in learner))
    native_speakers = {r["speaker_id"] for r in native}
    checks.check("native speakers disjoint from learner speakers",
                 not (native_speakers & (train | dev | test)),
                 str(sorted(native_speakers)))
    checks.check("learner class counts exclude natives",
                 total_correct + total_incorrect == EXPECTED["tokens"],
                 f"{total_correct + total_incorrect}")

    # --- 7. reproducibility ------------------------------------------------
    assignment = {s: profiles[s]["split"] for s in sorted(profiles)}
    digest = hashlib.sha256(
        json.dumps(assignment, sort_keys=True).encode("utf-8")).hexdigest()
    recorded = summary["frozen_split_definition"]["sha256"]
    checks.check("assignment on disk matches recorded SHA-256", digest == recorded,
                 f"{digest[:16]} vs {recorded[:16]}")
    split_csv = {r["speaker_id"]: r["split"]
                 for r in csv.DictReader(SPLIT_CSV.open(encoding="utf-8"))}
    checks.check("speaker CSV agrees with manifest assignment",
                 split_csv == assignment,
                 f"{sum(1 for k in assignment if split_csv.get(k) != assignment[k])}"
                 f" disagreements")

    decision = "A. SPLIT READY TO FREEZE" if not checks.failures else "B. SPLIT NOT READY"

    payload = {
        "split_id": SPLIT_ID,
        "decision": decision,
        "class_distribution": klass,
        "global_incorrect_rate": GLOBAL_INCORRECT_RATE,
        "tone_tables": tone_tables,
        "sparse_cells": sparse,
        "speaker_difficulty": difficulty,
        "difficulty_concentration": concentration,
        "corpus_speaker_rate_quartiles": {"q1": float(corpus_q1), "q3": float(corpus_q3)},
        "speaker_profiles": profiles,
        "lexical_coverage": lexical,
        "assertions": checks.results,
        "assertion_failures": len(checks.failures),
        "sha256": digest,
        "seed": summary["seed"],
        "algorithm": summary["split_algorithm"],
        "objective_score": summary["objective_function"]["score"],
        "speakers": speakers,
        "native_reference_tokens": len(native),
    }
    (DATA_DIR / "ompal_split_verification.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")

    if not checks.failures:
        LOCK.write_text(json.dumps({
            "split_id": SPLIT_ID, "frozen": True,
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": digest, "seed": summary["seed"],
            "algorithm": summary["algorithm"] if "algorithm" in summary
            else summary["split_algorithm"],
            "objective_score": summary["objective_function"]["score"],
            "speaker_to_split": assignment,
            "token_counts": {s: klass[s]["n_tokens"] for s in SPLITS},
            "native_reference_tokens": len(native),
            "note": ("Frozen. Do not regenerate because model results "
                     "disappoint. Test must not inform any modelling decision."),
        }, indent=2), encoding="utf-8")

    print_report(payload, checks, klass, tone_tables, difficulty, lexical,
                 profiles, speakers, sparse, concentration, digest, decision)
    append_report(payload, klass, tone_tables, difficulty, profiles, speakers,
                  lexical, checks, digest, decision)


def print_report(payload, checks, klass, tone_tables, difficulty, lexical,
                 profiles, speakers, sparse, concentration, digest, decision):
    print("=" * 78)
    print(f"SPLIT VERIFICATION — {SPLIT_ID}")
    print("=" * 78)
    print(f"\n{'':<14}{'Train':>10}{'Dev':>10}{'Test':>10}")
    for label, key in (("Correct", "correct"), ("Incorrect", "incorrect")):
        print(f"{label:<14}" + "".join(f"{klass[s][key]:>10}" for s in SPLITS))
    print(f"{'Incorrect %':<14}" + "".join(f"{klass[s]['incorrect_rate'] * 100:>9.1f}%"
                                           for s in SPLITS))
    print(f"{'vs 17.0%':<14}" + "".join(f"{klass[s]['delta_vs_global'] * 100:>+9.1f}"
                                        for s in SPLITS))

    print("\nTone x correctness:")
    for split in SPLITS:
        print(f"  {split}:  " + "  ".join(
            f"T{t} {tone_tables[split][t]['correct']}/{tone_tables[split][t]['incorrect']}"
            for t in ("1", "2", "3", "4")) + "   (correct/incorrect)")
    print("  sparse cells: " + ("; ".join(sparse) if sparse else "none"))

    print("\nSpeaker incorrect-rate by split:")
    print(f"  {'split':<8}{'min':>8}{'Q1':>8}{'median':>8}{'Q3':>8}{'max':>8}{'mean':>8}")
    for split in SPLITS:
        entry = difficulty[split]
        print(f"  {split:<8}" + "".join(f"{entry[k] * 100:>7.1f}%"
                                        for k in ("min", "q1", "median", "q3", "max", "mean")))
    for split in ("dev", "test"):
        print(f"\n  {split} speakers:")
        for speaker in speakers[split]:
            profile = profiles[speaker]
            print(f"    {speaker}  n={profile['n_tokens']:>3}  "
                  f"incorrect={profile['n_incorrect']:>3}  "
                  f"rate={profile['incorrect_rate'] * 100:5.1f}%")
        entry = concentration[split]
        print(f"    -> {entry['below_corpus_q1']}/{entry['n_speakers']} below corpus Q1, "
              f"{entry['above_corpus_q3']}/{entry['n_speakers']} above corpus Q3")

    print("\nLexical coverage:")
    for split in SPLITS:
        entry = lexical[split]
        extra = ""
        if split != "train":
            extra = (f"  unseen chars {len(entry['characters_unseen_in_train'])}"
                     f" ({entry['pct_tokens_unseen_character']:.1f}% tokens),"
                     f" unseen syll {len(entry['syllables_unseen_in_train'])}"
                     f" ({entry['pct_tokens_unseen_syllable']:.1f}% tokens),"
                     f" single-class chars {entry['single_class_characters']},"
                     f" single-class syll {entry['single_class_syllables']}")
        print(f"  {split:<6} chars {entry['n_characters']:>3}  "
              f"syll {entry['n_syllables']:>3}{extra}")

    print(f"\nAssertions ({len(checks.results)}):")
    for result in checks.results:
        status = "PASS" if result["pass"] else "FAIL"
        detail = f"  [{result['detail']}]" if result["detail"] else ""
        print(f"  {status}  {result['name']}{detail}")
    print(f"\nfailures: {len(checks.failures)}")
    print(f"sha256  : {digest}")
    print(f"\nDECISION: {decision}")


def append_report(payload, klass, tone_tables, difficulty, profiles, speakers,
                  lexical, checks, digest, decision):
    lines = [
        "",
        "---",
        "",
        "# Final split verification",
        "",
        f"Decision: **{decision}** · {len(checks.failures)} assertion failure(s) "
        f"of {len(checks.results)}",
        "",
        "## Class distribution",
        "",
        "| | Train | Dev | Test |",
        "|---|---|---|---|",
        "| Correct | " + " | ".join(str(klass[s]["correct"]) for s in SPLITS) + " |",
        "| Incorrect | " + " | ".join(str(klass[s]["incorrect"]) for s in SPLITS) + " |",
        "| Incorrect % | " + " | ".join(f"{klass[s]['incorrect_rate'] * 100:.1f}%"
                                        for s in SPLITS) + " |",
        "| deviation from 17.0% | " + " | ".join(
            f"{klass[s]['delta_vs_global'] * 100:+.1f} pts" for s in SPLITS) + " |",
        "",
        "## Tone x correctness",
        "",
    ]
    for split in SPLITS:
        lines += [f"### {split.capitalize()}", "", "| tone | Correct | Incorrect |",
                  "|---|---|---|"]
        for tone in ("1", "2", "3", "4"):
            cell = tone_tables[split][tone]
            lines.append(f"| T{tone} | {cell['correct']} | {cell['incorrect']} |")
        lines.append("")
    if payload["sparse_cells"]:
        lines += ["Sparse cells (reported, not engineered away):", ""]
        lines += [f"- {cell}" for cell in payload["sparse_cells"]]
        lines.append("")

    lines += ["## Speaker difficulty", "",
              "| split | min | Q1 | median | Q3 | max | mean |",
              "|---|---|---|---|---|---|---|"]
    for split in SPLITS:
        entry = difficulty[split]
        lines.append(f"| {split} | " + " | ".join(
            f"{entry[k] * 100:.1f}%"
            for k in ("min", "q1", "median", "q3", "max", "mean")) + " |")
    lines.append("")
    for split in ("dev", "test"):
        lines += [f"**{split.capitalize()} speakers**: " + ", ".join(
            f"{s} ({profiles[s]['incorrect_rate'] * 100:.1f}%)"
            for s in speakers[split]), ""]

    lines += ["## Assertions", ""]
    for result in checks.results:
        mark = "PASS" if result["pass"] else "**FAIL**"
        detail = f" — {result['detail']}" if result["detail"] else ""
        lines.append(f"- {mark} · {result['name']}{detail}")
    lines += ["", f"SHA-256 of sorted speaker→split mapping: `{digest}`", ""]
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
