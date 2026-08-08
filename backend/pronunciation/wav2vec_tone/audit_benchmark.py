"""Audit the eligibility gap, validate the manifest, and check for confounds.

The corpus flow had an unexplained 8,759 -> 2,176 step. It is fully explained
by one rule in the frozen pipeline: an utterance is aligned only when EVERY
one of its rated tokens has a determined pronunciation, and when one does not,
the whole utterance is dropped -- including its other, perfectly determined
tokens. The exclusion counter only ever recorded the undetermined tokens
themselves, so the collateral loss was invisible.

Nothing is changed here. The rule is frozen; this quantifies what it costs and
writes a token-level record so the reduction can be reconstructed exactly.

    python -m pronunciation.wav2vec_tone.audit_benchmark
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.align_ompal_pilot import load_pronunciations

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
METADATA = DATA_DIR / "ompal_tone_benchmark_metadata.csv"
MOE_TABLE = DATA_DIR / "moe_pronunciations.csv"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest.csv"
AUDIT_CSV = DATA_DIR / "ompal_alignment_eligibility_audit.csv"
SUMMARY = DATA_DIR / "ompal_full_tone_benchmark_summary.json"
REPORT_MD = REPORTS_DIR / "ompal_full_benchmark_audit.md"

DATASET_VERSION = "ompal-tone-benchmark-1.0"
PIPELINE_VERSION = "align-mmsfa-star-0ms-1.0"
HUMAN_QC_USABILITY = "81/100 (blinded, original boundaries)"

EXPECTED = {"rated_tokens": 20671, "audio_annotation_matched": 13261,
            "moe_verified": 8759, "alignment_eligible": 2176}


def syllable_base(pinyin: str) -> str:
    decomposed = unicodedata.normalize("NFD", pinyin)
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", plain.lower().replace("ü", "v"))


def full_word_sequences() -> dict:
    sequences = {}
    for filename in ("non-native_scores-detail.json", "native_scores.json"):
        payload = json.loads((OMPAL_DIR / filename).read_text(encoding="utf-8"))
        for utterance_id, record in payload.items():
            sequences[utterance_id] = ["".join(w["text"]) for w in record["words"]]
    return sequences


def build_audit():
    """Replay the frozen eligibility logic token by token."""
    pronunciations = load_pronunciations(MOE_TABLE)
    sequences = full_word_sequences()
    rows = list(csv.DictReader(METADATA.open(encoding="utf-8")))

    by_utterance = defaultdict(list)
    for row in rows:
        by_utterance[row["utterance_id"]].append(row)
    for tokens in by_utterance.values():
        tokens.sort(key=lambda r: int(r["token_index"]))

    audit = []
    flow = Counter({"rated_tokens": len(rows)})
    utterance_outcomes = Counter()

    for utterance_id, tokens in sorted(by_utterance.items()):
        has_audio = tokens[0]["audio_present"] == "1"
        if has_audio:
            flow["audio_annotation_matched"] += len(tokens)
        verified = [t for t in tokens if t["usable"] == "1"] if has_audio else []
        flow["moe_verified"] += len(verified)

        words = sequences.get(utterance_id) if has_audio else None
        forms = ([pronunciations.get(w, {}).get("segmental_forms", [])
                  if len(w) == 1 else [] for w in words] if words else [])
        undetermined_ids = {
            t["utterance_id"] + "_" + t["token_index"] for t in verified
            if int(t["token_index"]) >= len(forms)
            or len(forms[int(t["token_index"])]) != 1
        }
        if not has_audio:
            utterance_outcomes["no_matching_audio"] += 1
        elif not verified:
            utterance_outcomes["no_verified_token"] += 1
        elif not words:
            utterance_outcomes["no_word_sequence"] += 1
        elif undetermined_ids:
            utterance_outcomes["dropped_undetermined_sibling"] += 1
        else:
            utterance_outcomes["eligible"] += 1

        for token in verified:
            key = token["utterance_id"] + "_" + token["token_index"]
            reasons = []
            if not words:
                reasons.append("missing_annotation_word_sequence")
            elif key in undetermined_ids:
                reasons.append("token_pronunciation_segmentally_undetermined")
            elif undetermined_ids:
                # The rule that hid the gap: this token is perfectly usable and
                # was dropped only because a sibling in the same utterance was
                # not, and the aligner is run per utterance.
                reasons.append("utterance_dropped_sibling_token_undetermined")
            eligible = not reasons
            if eligible:
                flow["alignment_eligible"] += 1
            audit.append({
                "token_id": f"{utterance_id}_{int(token['token_index']):02d}",
                "speaker_id": token["speaker_id"],
                "utterance_id": utterance_id,
                "token_position": token["token_index"],
                "character": token["word"],
                "expected_pinyin": token["expected_pinyin"],
                "expected_tone": token["expected_tone"],
                "syllable_base": syllable_base(token["expected_pinyin"]),
                "moe_verified": "1",
                "moe_verification_status": token["pinyin_source_status"],
                "audio_annotation_matched": "1",
                "alignment_eligible": "1" if eligible else "0",
                "eligibility_exclusion_reason_primary": reasons[0] if reasons else "",
                "eligibility_exclusion_reasons_all": "|".join(reasons),
                "n_rated_tokens_in_utterance": len(verified),
                "n_undetermined_in_utterance": len(undetermined_ids),
                "speech_type": token["speech_type"],
                "ompal_label": token["majority_tone_correct"],
                "source_audio_path":
                    f"private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
                "annotation_source": ("native_scores.json"
                                      if token["speech_type"] == "native"
                                      else "non-native_scores-detail.json"),
                "dataset_version": DATASET_VERSION,
                "pipeline_version": PIPELINE_VERSION,
            })
    return audit, flow, utterance_outcomes


def confounds(manifest) -> dict:
    """Descriptive confound audit plus leakage-aware metadata-only baselines."""
    learner = [r for r in manifest if r["speech_type"] == "l2"]
    labels = [r["tone_correctness"] for r in learner]
    base_rate = max(Counter(labels).values()) / len(labels)

    def group_stats(field):
        table = defaultdict(lambda: [0, 0])
        for row in learner:
            table[row[field]][0 if row["tone_correctness"] == "1" else 1] += 1
        only_correct = sum(1 for c, i in table.values() if c and not i)
        only_incorrect = sum(1 for c, i in table.values() if i and not c)
        both = sum(1 for c, i in table.values() if c and i)
        counts = [c + i for c, i in table.values()]
        rates = [c / (c + i) for c, i in table.values()]
        return {
            "n_groups": len(table), "only_correct": only_correct,
            "only_incorrect": only_incorrect, "both": both,
            "tokens_per_group": {
                "min": int(min(counts)), "median": float(np.median(counts)),
                "max": int(max(counts))},
            "correctness_rate": {
                "min": float(min(rates)), "median": float(np.median(rates)),
                "max": float(max(rates))},
            "tokens_in_both_groups": sum(
                c + i for c, i in table.values() if c and i),
        }

    def speaker_disjoint_baseline(field):
        """Predict a group's majority training label; unseen groups fall back."""
        speakers = sorted({r["speaker_id"] for r in learner})
        rng = np.random.default_rng(0)
        shuffled = list(speakers)
        rng.shuffle(shuffled)
        folds = [set(shuffled[i::5]) for i in range(5)]
        predictions, truth = [], []
        for fold in folds:
            train = [r for r in learner if r["speaker_id"] not in fold]
            test = [r for r in learner if r["speaker_id"] in fold]
            table = defaultdict(lambda: [0, 0])
            for row in train:
                table[row[field]][0 if row["tone_correctness"] == "1" else 1] += 1
            majority = ("1" if sum(1 for r in train if r["tone_correctness"] == "1")
                        * 2 >= len(train) else "0")
            for row in test:
                counts = table.get(row[field])
                predictions.append(majority if not counts
                                   else ("1" if counts[0] >= counts[1] else "0"))
                truth.append(row["tone_correctness"])
        accuracy = float(np.mean([p == t for p, t in zip(predictions, truth)]))
        incorrect = [t == "0" for t in truth]
        recall = (float(np.mean([p == "0" for p, flag in zip(predictions, incorrect)
                                 if flag])) if any(incorrect) else float("nan"))
        return {"accuracy": accuracy, "recall_incorrect": recall}

    speaker_rates = {}
    for speaker in sorted({r["speaker_id"] for r in learner}):
        subset = [r for r in learner if r["speaker_id"] == speaker]
        speaker_rates[speaker] = {
            "n": len(subset),
            "correct_rate": sum(1 for r in subset
                                if r["tone_correctness"] == "1") / len(subset)}
    rates = [v["correct_rate"] for v in speaker_rates.values()]

    # A speaker-only predictor cannot be evaluated speaker-disjointly: the test
    # speaker is unseen by definition, so it collapses to the majority class.
    # The in-sample figure is reported as an upper bound on how much speaker
    # identity alone could explain, and labelled as leaky.
    speaker_in_sample = float(np.mean([
        (v["correct_rate"] >= 0.5) == (r["tone_correctness"] == "1")
        for r in learner for v in [speaker_rates[r["speaker_id"]]]]))

    return {
        "n_tokens": len(learner),
        "class_balance": {"correct": labels.count("1"), "incorrect": labels.count("0"),
                          "majority_baseline": base_rate},
        "character": group_stats("target_character"),
        "syllable_base": group_stats("_syllable_base"),
        "expected_tone": group_stats("expected_tone"),
        "speaker": group_stats("speaker_id"),
        "utterance": group_stats("utterance_id"),
        "baselines_speaker_disjoint": {
            "majority_class": {"accuracy": base_rate, "recall_incorrect": 0.0},
            "expected_tone_only": speaker_disjoint_baseline("expected_tone"),
            "character_only": speaker_disjoint_baseline("target_character"),
            "syllable_only": speaker_disjoint_baseline("_syllable_base"),
        },
        "speaker_baseline_note": (
            "A speaker-only predictor is undefined under speaker-disjoint "
            "evaluation because the test speaker is unseen; it collapses to the "
            "majority class. The in-sample figure below is leaky and is an "
            "upper bound only."),
        "speaker_only_in_sample_leaky": speaker_in_sample,
        "speaker_correct_rate": {
            "min": float(min(rates)), "median": float(np.median(rates)),
            "max": float(max(rates)),
            "iqr": [float(np.percentile(rates, 25)), float(np.percentile(rates, 75))]},
    }


def validate(audit, flow, manifest) -> list[str]:
    problems = []
    for name, expected in EXPECTED.items():
        actual = flow[name]
        if actual != expected:
            problems.append(f"flow {name}: expected {expected}, got {actual}")

    excluded = sum(1 for r in audit if r["alignment_eligible"] == "0")
    eligible = sum(1 for r in audit if r["alignment_eligible"] == "1")
    if excluded + eligible != flow["moe_verified"]:
        problems.append(f"invariant: {excluded} + {eligible} != {flow['moe_verified']}")
    if eligible != EXPECTED["alignment_eligible"]:
        problems.append(f"eligible {eligible} != {EXPECTED['alignment_eligible']}")

    if len(manifest) != EXPECTED["alignment_eligible"]:
        problems.append(f"manifest rows {len(manifest)} != "
                        f"{EXPECTED['alignment_eligible']}")
    successful = sum(1 for r in manifest if r["alignment_success"] == "1")
    if successful != len(manifest):
        problems.append(f"alignment_successful {successful} != manifest rows "
                        f"{len(manifest)}")

    ids = Counter(r["token_id"] for r in manifest)
    duplicates = [k for k, v in ids.items() if v > 1]
    if duplicates:
        problems.append(f"duplicate token_id in manifest: {len(duplicates)}")
    audit_ids = Counter(r["token_id"] for r in audit)
    if any(v > 1 for v in audit_ids.values()):
        problems.append("duplicate token_id in audit file")

    for row in manifest:
        if not row["extracted_token_path"]:
            problems.append(f"{row['token_id']}: missing token audio path")
        if not row["source_utterance_path"]:
            problems.append(f"{row['token_id']}: missing source audio path")
        if row["tone_correctness"] not in ("0", "1"):
            problems.append(f"{row['token_id']}: missing/invalid label")
        if row["expected_tone"] not in ("1", "2", "3", "4", "5"):
            problems.append(f"{row['token_id']}: missing expected tone")
        if not row["code_commit"] or not row["manifest_version"]:
            problems.append(f"{row['token_id']}: missing provenance")
        try:
            start, end = float(row["start_seconds"]), float(row["end_seconds"])
            if not (end > start >= 0):
                problems.append(f"{row['token_id']}: impossible timestamps "
                                f"{start}-{end}")
        except ValueError:
            problems.append(f"{row['token_id']}: unparseable timestamps")

    speakers = {r["speaker_id"] for r in manifest}
    unexpected = {s for s in speakers if not re.fullmatch(r"0[12]\d{3}", s)}
    if unexpected:
        problems.append(f"unexpected speaker ids: {sorted(unexpected)[:5]}")

    missing_segment = [r["token_id"] for r in manifest
                       if not (DATA_DIR / r["extracted_token_path"]).exists()]
    if missing_segment:
        problems.append(f"{len(missing_segment)} manifest rows point at a "
                        f"segment file that does not exist")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    audit, flow, utterance_outcomes = build_audit()
    manifest = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    for row in manifest:
        row["_syllable_base"] = syllable_base(row["expected_pinyin"])

    with AUDIT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit[0].keys()))
        writer.writeheader()
        writer.writerows(audit)

    primary = Counter(r["eligibility_exclusion_reason_primary"] for r in audit
                      if r["alignment_eligible"] == "0")
    raw_flags = Counter(reason for r in audit
                        for reason in r["eligibility_exclusion_reasons_all"].split("|")
                        if reason)
    problems = validate(audit, flow, manifest)
    diagnostics = confounds(manifest)
    learner = [r for r in manifest if r["speech_type"] == "l2"]

    summary = {
        "corpus_flow": {
            "rated_tokens": flow["rated_tokens"],
            "audio_annotation_matched": flow["audio_annotation_matched"],
            "moe_verified": flow["moe_verified"],
            "alignment_eligible": flow["alignment_eligible"],
            "alignment_attempted": flow["alignment_eligible"],
            "alignment_successful": len(manifest),
            "segment_extracted": sum(1 for r in manifest
                                     if r["extracted_token_path"]),
        },
        "hierarchical_exclusions": {
            "rated_to_matched": {
                "annotation_audio_id_mismatch":
                    flow["rated_tokens"] - flow["audio_annotation_matched"]},
            "matched_to_moe_verified": {
                "ambiguous_or_unverified_pronunciation":
                    flow["audio_annotation_matched"] - flow["moe_verified"]},
            "moe_verified_to_eligible": dict(primary),
            "moe_verified_to_eligible_total":
                flow["moe_verified"] - flow["alignment_eligible"],
        },
        "raw_exclusion_flags": dict(raw_flags),
        "flag_overlap_note": (
            "Within the moe_verified -> eligible stage each token carries at "
            "most one reason, so primary and raw counts coincide. Across "
            "stages the earlier reasons are hierarchical: a token without "
            "audio is never tested for pronunciation ambiguity."),
        "utterance_outcomes": dict(utterance_outcomes),
        "alignment_results": {
            "attempted": flow["alignment_eligible"],
            "successful": len(manifest), "failed": 0,
            "technical_success_rate": 1.0,
            "boundary_accuracy_note": (
                "Technical success only. Independent blinded human review put "
                f"usable original-boundary segments at {HUMAN_QC_USABILITY}."),
        },
        "segment_extraction_results": {
            "extracted": sum(1 for r in manifest if r["extracted_token_path"]),
            "failed": sum(1 for r in manifest if not r["extracted_token_path"]),
        },
        "speaker_statistics": {
            "learner_speakers": len({r["speaker_id"] for r in learner}),
            "native_speakers": len({r["speaker_id"] for r in manifest
                                    if r["speech_type"] == "native"}),
            "tokens_per_learner_speaker": diagnostics["speaker"]["tokens_per_group"],
            "correct_rate_by_speaker": diagnostics["speaker_correct_rate"],
        },
        "label_statistics": diagnostics["class_balance"],
        "tone_statistics": {
            f"T{t}": {
                "n": sum(1 for r in learner if r["expected_tone"] == t),
                "incorrect": sum(1 for r in learner if r["expected_tone"] == t
                                 and r["tone_correctness"] == "0"),
            } for t in ("1", "2", "3", "4", "5")
        },
        "lexical_statistics": {
            "characters": diagnostics["character"],
            "syllable_bases": diagnostics["syllable_base"],
        },
        "confound_diagnostics": diagnostics,
        "provenance": {
            "dataset_version": DATASET_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "aligner": manifest[0]["aligner"],
            "boundary_policy": manifest[0]["boundary_policy"],
            "code_commit": manifest[0]["code_commit"],
            "target_pronunciation_source": manifest[0]["target_pronunciation_source"],
        },
        "frozen_preprocessing_decisions": [
            "existing CTC forced aligner, unchanged",
            "original 0 ms boundaries, no padding",
            "no RMS, SNR, duration or alignment-score filtering",
            "no QC classifier",
            "unresolved audio/annotation id mismatches not remapped",
            "ambiguous polyphonic pronunciations not guessed",
        ],
        "known_limitations": [
            f"Blinded human usability of original boundaries: {HUMAN_QC_USABILITY}. "
            "Roughly one token in five is expected imperfect and the manifest "
            "cannot identify which.",
            "No neutral-tone tokens: every neutral-capable character is "
            "tone-ambiguous under MoE and was excluded.",
            "5,189 MoE-verified tokens were lost as collateral of the "
            "whole-utterance eligibility rule, not because of anything wrong "
            "with those tokens.",
            "Acoustic descriptors are metadata; no QC rule was validated.",
        ],
        "validation_failures": problems,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float),
                       encoding="utf-8")

    write_report(summary, primary, raw_flags, manifest, learner, diagnostics,
                 utterance_outcomes, problems)

    print(f"audit rows      : {len(audit)}")
    print(f"eligible        : {sum(1 for r in audit if r['alignment_eligible'] == '1')}")
    print(f"excluded        : {sum(1 for r in audit if r['alignment_eligible'] == '0')}")
    print("\nprimary exclusion reasons:")
    for reason, count in primary.most_common():
        print(f"  {reason:<48}{count:>6}")
    print(f"  {'TOTAL':<48}{sum(primary.values()):>6}")
    print(f"\nvalidation failures: {len(problems)}")
    for problem in problems[:10]:
        print(f"  FAIL {problem}")
    print(f"\naudit  : {AUDIT_CSV}")
    print(f"summary: {SUMMARY}")
    print(f"report : {REPORT_MD}")


def write_report(summary, primary, raw_flags, manifest, learner, diagnostics,
                 utterance_outcomes, problems) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    flow = summary["corpus_flow"]
    tones = summary["tone_statistics"]
    balance = summary["label_statistics"]

    lines = [
        "# OMPAL tone-correctness benchmark — full audit",
        "",
        f"Dataset `{DATASET_VERSION}` · pipeline `{PIPELINE_VERSION}` · commit "
        f"`{summary['provenance']['code_commit']}`",
        "",
        "## Corpus flow",
        "",
        "| stage | tokens |",
        "|---|---|",
        f"| rated tokens (audited metadata) | {flow['rated_tokens']} |",
        f"| audio/annotation matched | {flow['audio_annotation_matched']} |",
        f"| MoE pronunciation verified | {flow['moe_verified']} |",
        f"| eligible for alignment | {flow['alignment_eligible']} |",
        f"| alignment attempted | {flow['alignment_attempted']} |",
        f"| alignment successful | {flow['alignment_successful']} |",
        f"| token segment extracted | {flow['segment_extracted']} |",
        "",
        "Reconciles exactly at every step:",
        "",
        "```",
        f"{flow['rated_tokens']} - "
        f"{summary['hierarchical_exclusions']['rated_to_matched']['annotation_audio_id_mismatch']}"
        f" = {flow['audio_annotation_matched']}",
        f"{flow['audio_annotation_matched']} - "
        f"{summary['hierarchical_exclusions']['matched_to_moe_verified']['ambiguous_or_unverified_pronunciation']}"
        f" = {flow['moe_verified']}",
        f"{flow['moe_verified']} - "
        f"{summary['hierarchical_exclusions']['moe_verified_to_eligible_total']}"
        f" = {flow['alignment_eligible']}",
        "```",
        "",
        "## Eligibility gap audit — why 6,583 tokens were not eligible",
        "",
        "The gap is one rule, not many. The aligner runs on a whole utterance,",
        "and the frozen eligibility check requires **every rated token in that",
        "utterance** to have a determined pronunciation. When one does not, the",
        "entire utterance is skipped — and its other rated tokens go with it.",
        "",
        "The exclusion counter only ever recorded the undetermined tokens",
        "themselves (1,394), so the 5,189 tokens lost alongside them were",
        "invisible in the flow. Nothing was wrong with those 5,189 tokens.",
        "",
        "| Primary exclusion reason | N |",
        "|---|---|",
    ]
    for reason, count in primary.most_common():
        lines.append(f"| {reason} | {count} |")
    lines += [f"| **TOTAL** | **{sum(primary.values())}** |", ""]

    lines += [
        "Utterance-level view:",
        "",
        "| utterance outcome | utterances |",
        "|---|---|",
    ]
    for outcome, count in sorted(utterance_outcomes.items(), key=lambda x: -x[1]):
        lines.append(f"| {outcome} | {count} |")

    lines += [
        "",
        "### Hierarchical vs overlapping",
        "",
        "Within this stage every token carries exactly one reason, so the",
        "primary and raw-flag counts coincide:",
        "",
        "```",
    ]
    for reason, count in raw_flags.most_common():
        lines.append(f"raw_flag {reason}: {count}")
    lines += [
        "```",
        "",
        "Across stages the reasons are hierarchical rather than overlapping: a",
        "token with no matching audio is never tested for pronunciation",
        "ambiguity, so it appears once, at the stage where it exits.",
        "",
        "## Alignment result",
        "",
        f"**{flow['alignment_successful']} / {flow['alignment_attempted']} eligible "
        f"tokens aligned successfully. Technical alignment success rate = 100%.**",
        "",
        "This does **not** mean 100% boundary accuracy. It means the aligner",
        "returned a span for every token it was asked to place. An independent",
        f"blinded human review put usable original-boundary segments at",
        f"**{HUMAN_QC_USABILITY}** — roughly one token in five is expected to be",
        "imperfect for tone analysis, and the manifest cannot say which. No QC",
        "rule reached a usable precision/retention trade, so none is applied.",
        "",
        "## Benchmark composition",
        "",
        f"- learner tokens: **{len(learner)}** from "
        f"**{summary['speaker_statistics']['learner_speakers']}** speakers and "
        f"**{len({r['utterance_id'] for r in learner})}** utterances",
        f"- native reference tokens: {len(manifest) - len(learner)}",
        f"- correct **{balance['correct']}** / incorrect **{balance['incorrect']}** "
        f"({balance['incorrect'] / (balance['correct'] + balance['incorrect']) * 100:.1f}% "
        f"incorrect)",
        f"- distinct characters: {diagnostics['character']['n_groups']}, "
        f"distinct syllable bases: {diagnostics['syllable_base']['n_groups']}",
        "",
        "| expected tone | tokens | incorrect | % incorrect |",
        "|---|---|---|---|",
    ]
    for tone in ("1", "2", "3", "4", "5"):
        entry = tones[f"T{tone}"]
        if not entry["n"]:
            continue
        lines.append(f"| T{tone} | {entry['n']} | {entry['incorrect']} | "
                     f"{entry['incorrect'] / entry['n'] * 100:.1f}% |")

    speaker = summary["speaker_statistics"]
    lines += [
        "",
        f"Tokens per learner speaker: min {speaker['tokens_per_learner_speaker']['min']}, "
        f"median {speaker['tokens_per_learner_speaker']['median']:.0f}, "
        f"max {speaker['tokens_per_learner_speaker']['max']}.",
        f"Correct rate by speaker: min "
        f"{speaker['correct_rate_by_speaker']['min'] * 100:.0f}%, median "
        f"{speaker['correct_rate_by_speaker']['median'] * 100:.0f}%, max "
        f"{speaker['correct_rate_by_speaker']['max'] * 100:.0f}%.",
        "",
        "## Lexical / speaker confound audit",
        "",
        "The earlier AISHELL benchmark failed here: a no-audio lexical lookup",
        "beat every acoustic model. This benchmark is checked the same way.",
        "",
        "| metadata-only baseline (speaker-disjoint) | accuracy | recall on incorrect |",
        "|---|---|---|",
    ]
    for name, result in summary["confound_diagnostics"][
            "baselines_speaker_disjoint"].items():
        lines.append(f"| {name} | {result['accuracy'] * 100:.1f}% | "
                     f"{result['recall_incorrect'] * 100:.1f}% |")
    lines += [
        "",
        summary["confound_diagnostics"]["speaker_baseline_note"],
        "",
        f"Leaky in-sample speaker-only accuracy: "
        f"{summary['confound_diagnostics']['speaker_only_in_sample_leaky'] * 100:.1f}% "
        f"(upper bound, not a usable result).",
        "",
        f"- characters occurring only with Correct: "
        f"{diagnostics['character']['only_correct']} of "
        f"{diagnostics['character']['n_groups']}",
        f"- characters occurring only with Incorrect: "
        f"{diagnostics['character']['only_incorrect']}",
        f"- syllable bases with only one class: "
        f"{diagnostics['syllable_base']['only_correct'] + diagnostics['syllable_base']['only_incorrect']}"
        f" of {diagnostics['syllable_base']['n_groups']}",
        f"- tokens in characters carrying both classes: "
        f"{diagnostics['character']['tokens_in_both_groups']} "
        f"({diagnostics['character']['tokens_in_both_groups'] / len(learner) * 100:.1f}%)",
        "",
        "Every metadata-only baseline sits at or near the majority-class rate",
        "with near-zero recall on the incorrect class — it predicts 'correct'",
        "almost always and is blind to the errors the task exists to find. That",
        "is the opposite of the AISHELL pattern. Stated carefully: this shows",
        "the label is not trivially recoverable from metadata, not that no",
        "confound exists.",
        "",
        "## Validation",
        "",
    ]
    if problems:
        lines.append(f"**{len(problems)} assertion(s) FAILED:**")
        lines += [f"- {problem}" for problem in problems[:40]]
    else:
        lines.append("All assertions passed: flow counts, the "
                     "`8759 = 6583 + 2176` invariant, manifest row count, "
                     "duplicate ids, audio paths, labels, expected tones, "
                     "timestamps, provenance and speaker ids.")
    lines += [
        "",
        "## Frozen decisions and known limitations",
        "",
    ]
    lines += [f"- {item}" for item in summary["frozen_preprocessing_decisions"]]
    lines.append("")
    lines += [f"- {item}" for item in summary["known_limitations"]]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
