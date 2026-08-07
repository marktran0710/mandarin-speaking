"""Scale the frozen alignment pipeline and build the immutable token manifest.

The preprocessing investigation is closed. Nothing here decides anything: the
aligner, the boundary policy (original 0 ms, no padding) and the eligibility
rules are all as previously validated, and no acoustic descriptor is used to
filter. Descriptors travel with the manifest so a later analysis can condition
on them, having been told they were never validated as a filter.

The honest limitation, carried forward rather than optimised away: a fresh
blinded review put original-boundary human usability at 81/100, and no
automatic QC rule reached a usable precision/retention trade. Roughly one token
in five is expected to be imperfect, and the manifest cannot say which.

    python -m pronunciation.wav2vec_tone.build_benchmark_manifest
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import frozen_qc
from pronunciation.wav2vec_tone.align_ompal_pilot import (
    align_utterance,
    load_audio,
    load_pronunciations,
)
from pronunciation.wav2vec_tone.praat_features import extract_one

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
METADATA = DATA_DIR / "ompal_tone_benchmark_metadata.csv"
MOE_TABLE = DATA_DIR / "moe_pronunciations.csv"
SEGMENT_DIR = DATA_DIR / "benchmark_token_segments"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest.csv"
SUMMARY = DATA_DIR / "ompal_full_tone_benchmark_summary.json"

SAMPLE_RATE = 16000
MANIFEST_VERSION = "1.0"
BOUNDARY_POLICY = "original_0ms"
ALIGNER = "torchaudio MMS_FA CTC forced alignment (with_star=True)"

PRIOR_REVIEWS = (
    ("round1", "ompal_alignment_review_items.csv", "pair", None),
    ("round2", "ompal_alignment_review_items_round2.csv", "pair", None),
    ("padding", "padding_trial_key.csv", "token_id", None),
    ("binary", "binary_trial_key.csv", "token_id", "ompal_binary_human_review.csv"),
    ("binpad", "binpad_trial_key.csv", "token_id", "ompal_binpad_human_review.csv"),
    ("confirm", "confirm_trial_key.csv", "token_id", "ompal_confirm_human_review.csv"),
    ("audit", "audit_trial_key.csv", "token_id", "ompal_audit_human_review.csv"),
    ("qc", "qc_trial_key.csv", "token_id", "ompal_qc_human_review.csv"),
)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=15,
                              cwd=str(Path(__file__).resolve().parents[3])
                              ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def full_word_sequences() -> dict:
    """Every word of every utterance, in order, from the OMPAL annotations.

    token_index in the metadata indexes this full list, but the metadata only
    keeps single-character tokens. Building the alignment sequence from the
    filtered rows would therefore drop a syllable and shift every index after
    it -- silently, and only in the 12 utterances that contain a
    multi-character word. The pilot never touched those, so its results stand,
    but at corpus scale they would be mislabelled.
    """
    sequences = {}
    for filename in ("non-native_scores-detail.json", "native_scores.json"):
        payload = json.loads((OMPAL_DIR / filename).read_text(encoding="utf-8"))
        for utterance_id, record in payload.items():
            sequences[utterance_id] = ["".join(w["text"]) for w in record["words"]]
    return sequences


def token_key(utterance_id, index) -> str:
    return f"{utterance_id}_{int(index):02d}"


def human_qc_history() -> dict:
    """Which tokens a human has already heard, and the latest binary verdict.

    Provenance only. These are judgements about whether a clip is analysable,
    not about whether the learner said it correctly, and must never be used as
    a pronunciation label.
    """
    history = defaultdict(lambda: {"rounds": [], "latest": "", "binary_verdicts": []})
    for name, key_file, style, review_file in PRIOR_REVIEWS:
        key_path = DATA_DIR / key_file
        if not key_path.exists():
            continue
        rows = list(csv.DictReader(key_path.open(encoding="utf-8")))
        by_trial = {}
        for row in rows:
            if style == "pair":
                token = token_key(row["utterance_id"], row["token_index"])
            else:
                utterance, index = row["token_id"].rsplit("_", 1)
                token = token_key(utterance, index)
            history[token]["rounds"].append(name)
            by_trial[row.get("trial_id", "")] = token

        review_path = DATA_DIR / review_file if review_file else None
        if review_path and review_path.exists():
            for row in csv.DictReader(review_path.open(encoding="utf-8")):
                token = by_trial.get(row["trial_id"])
                verdict = row.get("human_usability_judgment", "").strip().upper()
                if token and verdict in ("ACCEPT", "REJECT"):
                    history[token]["binary_verdicts"].append(verdict)
                    history[token]["latest"] = verdict
    for entry in history.values():
        verdicts = set(entry["binary_verdicts"])
        entry["stability"] = ("stable_accept" if verdicts == {"ACCEPT"} and len(entry["binary_verdicts"]) > 1
                              else "stable_reject" if verdicts == {"REJECT"} and len(entry["binary_verdicts"]) > 1
                              else "ambiguous" if len(verdicts) > 1
                              else "single" if verdicts else "")
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="first N utterances (debug)")
    parser.add_argument("--speech-type", default="l2,native")
    args = parser.parse_args()

    import soundfile as sf
    from torchaudio.pipelines import MMS_FA

    wanted_types = set(args.speech_type.split(","))
    pronunciations = load_pronunciations(MOE_TABLE)
    sequences = full_word_sequences()
    history = human_qc_history()
    commit = git_commit()

    rows = list(csv.DictReader(METADATA.open(encoding="utf-8")))
    print(f"[1] {len(rows)} rated tokens in the audited metadata")

    # --- eligibility, counted without collapsing reasons -------------------
    by_utterance = defaultdict(list)
    for row in rows:
        by_utterance[row["utterance_id"]].append(row)
    for tokens in by_utterance.values():
        tokens.sort(key=lambda r: int(r["token_index"]))

    flow = Counter()
    exclusions = Counter()
    overlap_notes = []
    eligible, skipped_utterances = [], []

    for utterance_id, tokens in sorted(by_utterance.items()):
        if tokens[0]["speech_type"] not in wanted_types:
            continue
        has_audio = tokens[0]["audio_present"] == "1"
        flow["tokens_total"] += len(tokens)
        if not has_audio:
            # These are the unresolved 656 id mismatches, left untouched.
            exclusions["annotation_audio_id_mismatch"] += len(tokens)
            skipped_utterances.append((utterance_id, "no_matching_audio"))
            continue
        flow["tokens_audio_matched"] += len(tokens)

        verified = [t for t in tokens if t["usable"] == "1"]
        ambiguous = [t for t in tokens
                     if t["pronunciation_ambiguous"] == "1"]
        exclusions["ambiguous_polyphonic_pronunciation"] += len(ambiguous)
        flow["tokens_moe_verified"] += len(verified)
        if not verified:
            skipped_utterances.append((utterance_id, "no_verified_token"))
            continue

        # One entry per word of the FULL utterance, so token_index lines up.
        words = sequences.get(utterance_id)
        if not words:
            exclusions["missing_annotation_sequence"] += len(verified)
            skipped_utterances.append((utterance_id, "no_word_sequence"))
            continue
        forms = [
            pronunciations.get(word, {}).get("segmental_forms", [])
            if len(word) == 1 else []          # multi-char word -> star
            for word in words
        ]
        undetermined = [t for t in verified
                        if int(t["token_index"]) >= len(forms)
                        or len(forms[int(t["token_index"])]) != 1]
        if undetermined:
            exclusions["rated_token_segmentally_undetermined"] += len(undetermined)
            skipped_utterances.append((utterance_id, "rated_token_undetermined"))
            continue

        flow["tokens_eligible"] += len(verified)
        eligible.append({
            "utterance_id": utterance_id,
            "tokens": tokens,
            "rated": verified,
            "romanized": [f[0] if len(f) == 1 else "*" for f in forms],
            "n_words": len(words),
            "speech_type": tokens[0]["speech_type"],
        })

    if args.limit:
        eligible = eligible[:args.limit]

    print(f"[2] {len(eligible)} eligible utterances, "
          f"{sum(len(e['rated']) for e in eligible)} rated tokens to align")
    print("[3] loading frozen aligner…")
    model = MMS_FA.get_model(with_star=True)
    dictionary = MMS_FA.get_dict(star="*")

    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    manifest, failures = [], []
    started = time.time()

    for position, item in enumerate(eligible, start=1):
        utterance_id = item["utterance_id"]
        path = OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav"
        try:
            audio = load_audio(path)[0]
            spans = align_utterance(model, dictionary, audio, item["romanized"])
        except Exception as error:  # noqa: BLE001 - preserved, not dropped
            failures.append({"utterance_id": utterance_id,
                             "reason": f"{type(error).__name__}: {error}"})
            for token in item["rated"]:
                manifest.append(manifest_row(token, item, None, None, None,
                                             history, commit, "utterance_failed"))
            continue

        for token in item["rated"]:
            span = spans[int(token["token_index"])]
            if span is None:
                manifest.append(manifest_row(token, item, None, None, None,
                                             history, commit, "no_span"))
                continue
            start, end, score = span
            begin = max(0, int(round(start * SAMPLE_RATE)))
            finish = min(len(audio), int(round(end * SAMPLE_RATE)))
            segment = audio[begin:finish]
            if len(segment) < int(0.02 * SAMPLE_RATE):
                manifest.append(manifest_row(token, item, span, None, None,
                                             history, commit, "segment_too_short"))
                continue
            name = f"{token_key(utterance_id, token['token_index'])}.wav"
            sf.write(SEGMENT_DIR / name, segment, SAMPLE_RATE)
            descriptors = extract_one(segment)
            descriptors["rms_relative_db"] = frozen_qc.rms_relative_db(segment, audio)
            descriptors["local_snr_db"] = frozen_qc.local_snr_db(
                segment, audio, (begin, finish))
            manifest.append(manifest_row(token, item, span, name, descriptors,
                                         history, commit, "ok"))

        if position % 25 == 0:
            rate = position / max(time.time() - started, 1e-9)
            print(f"    {position}/{len(eligible)}  ({rate:.1f} utt/s)")

    print(f"    aligned {len(eligible) - len(failures)}/{len(eligible)} utterances "
          f"in {time.time() - started:.0f}s")

    fields = list(manifest[0].keys())
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)

    flow["alignment_attempted"] = sum(len(e["rated"]) for e in eligible)
    flow["alignment_successful"] = sum(1 for r in manifest if r["alignment_success"] == "1")
    flow["segment_extracted"] = sum(1 for r in manifest if r["extracted_token_path"])
    exclusions["alignment_failure"] = flow["alignment_attempted"] - flow["alignment_successful"]

    overlap_notes.append(
        "annotation_audio_id_mismatch and ambiguous_polyphonic_pronunciation are "
        "OVERLAPPING: a token can be both, and the mismatch count is taken first "
        "so ambiguity is only counted among tokens that do have audio.")
    overlap_notes.append(
        "rated_token_segmentally_undetermined and alignment_failure are mutually "
        "exclusive with each other and with the two above.")

    report(manifest, flow, exclusions, overlap_notes, failures, skipped_utterances,
           commit)


def manifest_row(token, item, span, segment_name, descriptors, history,
                 commit, status) -> dict:
    utterance_id = item["utterance_id"]
    key = token_key(utterance_id, token["token_index"])
    entry = history.get(key, {})
    start, end, score = span if span else (None, None, None)
    descriptors = descriptors or {}

    def value(name):
        raw = descriptors.get(name)
        return "" if raw is None or (isinstance(raw, float) and not np.isfinite(raw)) \
            else (f"{raw:.6g}" if isinstance(raw, float) else raw)

    return {
        "corpus": "OMPAL",
        "speaker_id": token["speaker_id"],
        "utterance_id": utterance_id,
        "token_index": token["token_index"],
        "token_id": key,
        "speech_type": token["speech_type"],
        "target_character": token["word"],
        "word_script": token["word_script"],
        "expected_pinyin": token["expected_pinyin"],
        "expected_tone": token["expected_tone"],
        "pinyin_variety": token["pinyin_variety"],
        "pinyin_source": token["pinyin_source"],
        "moe_verification_status": token["pinyin_source_status"],
        "pronunciation_ambiguous": token["pronunciation_ambiguous"],
        # Correct/incorrect only. OMPAL never records which wrong tone was
        # produced, so this must not be read as a produced-tone class.
        "tone_correctness": token["majority_tone_correct"],
        "n_ratings": token["n_ratings"],
        "raw_ratings": "|".join(
            v for v in (token["rater_1_tone"], token["rater_2_tone"],
                        token["rater_3_tone"]) if v),
        "agreement_count": token["agreement_count"],
        "alignment_success": "1" if status == "ok" else "0",
        "alignment_status_detail": status,
        "start_seconds": f"{start:.4f}" if start is not None else "",
        "end_seconds": f"{end:.4f}" if end is not None else "",
        "duration_seconds": value("duration_seconds"),
        "alignment_score": f"{score:.4f}" if score is not None else "",
        "praat_flags": descriptors.get("flags", ""),
        "source_utterance_path":
            f"private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        "extracted_token_path":
            f"benchmark_token_segments/{segment_name}" if segment_name else "",
        "sample_rate": SAMPLE_RATE,
        "voiced_proportion": value("voiced_proportion"),
        "mean_f0_hz": value("mean_f0_hz"),
        "median_f0_hz": value("median_f0_hz"),
        "f0_range_hz": value("f0_range_hz"),
        "slope_start_to_mid": value("slope_start_to_mid"),
        "slope_mid_to_end": value("slope_mid_to_end"),
        "rms_relative_db": value("rms_relative_db"),
        "local_snr_db": value("local_snr_db"),
        "human_qc_seen": "1" if entry.get("rounds") else "0",
        "human_qc_rounds": "|".join(entry.get("rounds", [])),
        "human_qc_latest_binary": entry.get("latest", ""),
        "human_qc_stability": entry.get("stability", ""),
        "aligner": ALIGNER,
        "boundary_policy": BOUNDARY_POLICY,
        "manifest_version": MANIFEST_VERSION,
        "code_commit": commit,
        "target_pronunciation_source": "moe_dict (moedict.tw), Taiwan Mandarin",
    }


def describe(values):
    values = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not len(values):
        return None
    return {p: float(np.percentile(values, q)) if q is not None else float(f(values))
            for p, q, f in (("min", None, np.min), ("p10", 10, None),
                            ("p25", 25, None), ("median", 50, None),
                            ("p75", 75, None), ("p90", 90, None),
                            ("max", None, np.max))}


def report(manifest, flow, exclusions, overlap_notes, failures,
           skipped_utterances, commit) -> None:
    ok = [r for r in manifest if r["alignment_success"] == "1"]
    learner = [r for r in ok if r["speech_type"] == "l2"]

    lines = [
        "=" * 84,
        "OMPAL FULL BENCHMARK MANIFEST",
        "=" * 84,
        f"manifest version {MANIFEST_VERSION}  |  commit {commit}  |  "
        f"boundary {BOUNDARY_POLICY}",
        "",
        "CORPUS FLOW (tokens)",
        f"  rated tokens (audited metadata)      : {flow['tokens_total']}",
        f"  -> audio/annotation matched          : {flow['tokens_audio_matched']}",
        f"  -> MoE pronunciation verified        : {flow['tokens_moe_verified']}",
        f"  -> eligible for alignment            : {flow['tokens_eligible']}",
        f"  -> alignment attempted               : {flow['alignment_attempted']}",
        f"  -> alignment successful              : {flow['alignment_successful']}",
        f"  -> token segment extracted           : {flow['segment_extracted']}",
        "",
        "EXCLUSIONS BY REASON (not combined)",
    ]
    for reason, count in exclusions.most_common():
        lines.append(f"  {reason:<42}{count:>7}")
    lines += ["", "  Overlap:"] + [f"    {note}" for note in overlap_notes]

    if failures:
        lines += ["", f"  utterance-level alignment failures: {len(failures)}"]
        for failure in failures[:5]:
            lines.append(f"    {failure['utterance_id']}: {failure['reason']}")

    lines += ["", "-" * 84, "FINAL LEARNER TOKEN DISTRIBUTION", "-" * 84,
              f"  tokens          : {len(learner)}",
              f"  speakers        : {len({r['speaker_id'] for r in learner})}",
              f"  utterances      : {len({r['utterance_id'] for r in learner})}",
              f"  lexical items   : {len({r['target_character'] for r in learner})}"]

    tones = Counter(r["expected_tone"] for r in learner)
    lines.append("")
    for tone in ("1", "2", "3", "4", "5"):
        if tones.get(tone):
            label = "neutral" if tone == "5" else f"T{tone}"
            lines.append(f"  expected {label:<8}{tones[tone]:>6}")

    correct = sum(1 for r in learner if r["tone_correctness"] == "1")
    lines += ["",
              f"  OMPAL correct   : {correct}",
              f"  OMPAL incorrect : {len(learner) - correct}",
              f"  correct %       : {correct / max(len(learner), 1) * 100:.1f}%",
              "",
              "  expected tone x correctness:",
              f"    {'tone':<8}{'correct':>10}{'incorrect':>11}{'% incorrect':>13}"]
    for tone in ("1", "2", "3", "4", "5"):
        subset = [r for r in learner if r["expected_tone"] == tone]
        if not subset:
            continue
        good = sum(1 for r in subset if r["tone_correctness"] == "1")
        bad = len(subset) - good
        label = "neutral" if tone == "5" else f"T{tone}"
        lines.append(f"    {label:<8}{good:>10}{bad:>11}"
                     f"{bad / len(subset) * 100:>12.1f}%")

    per_speaker = Counter(r["speaker_id"] for r in learner)
    if per_speaker:
        counts = sorted(per_speaker.values())
        lines += ["",
                  f"  tokens per speaker: min {counts[0]}, median "
                  f"{int(np.median(counts))}, max {counts[-1]}"]
    durations = describe([float(r["duration_seconds"]) for r in learner
                          if r["duration_seconds"]])
    if durations:
        lines.append("  duration (s): " + "  ".join(
            f"{k} {v:.3f}" for k, v in durations.items()))

    lines += ["", "  NOTE: acoustic descriptors in the manifest are metadata. No",
              "  automatic QC rule was validated, and a fresh blinded review put",
              "  original-boundary usability at 81/100. Around one token in five",
              "  is expected to be imperfect and the manifest cannot say which."]

    # --- lexical confound for THIS task -----------------------------------
    lines += ["", "-" * 84,
              "LEXICAL-IDENTITY CONFOUND — target task is correct/incorrect",
              "-" * 84]
    by_word = defaultdict(lambda: [0, 0])
    for row in learner:
        by_word[row["target_character"]][0 if row["tone_correctness"] == "1" else 1] += 1
    both = {w for w, (c, i) in by_word.items() if c and i}
    covered = sum(c + i for w, (c, i) in by_word.items() if w in both)
    dominance = [max(c, i) / (c + i) for c, i in by_word.values()]

    lines += [
        f"  lexical items                        : {len(by_word)}",
        f"  items with BOTH outcomes             : {len(both)} "
        f"({len(both) / max(len(by_word), 1) * 100:.1f}%)",
        f"  learner tokens in such items         : {covered} "
        f"({covered / max(len(learner), 1) * 100:.1f}%)",
        f"  dominant-label proportion            : mean {np.mean(dominance):.3f}, "
        f"median {np.median(dominance):.3f}",
    ]

    # Speaker-disjoint lexical-only baseline: predict each word's majority
    # training outcome. This is the check the AISHELL set failed.
    speakers = sorted({r["speaker_id"] for r in learner})
    rng = np.random.default_rng(0)
    order = list(speakers)
    rng.shuffle(order)
    folds = [set(order[i::5]) for i in range(5)]
    predictions, truths = [], []
    for fold in folds:
        train = [r for r in learner if r["speaker_id"] not in fold]
        test = [r for r in learner if r["speaker_id"] in fold]
        table = defaultdict(lambda: [0, 0])
        for row in train:
            table[row["target_character"]][0 if row["tone_correctness"] == "1" else 1] += 1
        majority = "1" if sum(1 for r in train if r["tone_correctness"] == "1") * 2 >= len(train) else "0"
        for row in test:
            counts = table.get(row["target_character"])
            guess = majority if not counts else ("1" if counts[0] >= counts[1] else "0")
            predictions.append(guess)
            truths.append(row["tone_correctness"])
    if truths:
        accuracy = np.mean([p == t for p, t in zip(predictions, truths)])
        base = max(Counter(truths).values()) / len(truths)
        recall_bad = (sum(1 for p, t in zip(predictions, truths) if t == "0" and p == "0")
                      / max(sum(1 for t in truths if t == "0"), 1))
        lines += [
            "",
            f"  lexical-only baseline (5-fold speaker-disjoint):",
            f"    accuracy                           : {accuracy * 100:.1f}%",
            f"    majority-class baseline            : {base * 100:.1f}%",
            f"    recall on INCORRECT tokens         : {recall_bad * 100:.1f}%",
            "",
            "  On AISHELL a lexical lookup scored 86.1% and beat every acoustic",
            "  model. Here the label is correctness, so the lookup can at best",
            "  reproduce the base rate and has near-zero recall on the errors --",
            "  the class the task exists to find.",
        ]
    print("\n".join(lines))

    summary = {
        "manifest_version": MANIFEST_VERSION, "code_commit": commit,
        "aligner": ALIGNER, "boundary_policy": BOUNDARY_POLICY,
        "flow": dict(flow), "exclusions": dict(exclusions),
        "overlap_notes": overlap_notes,
        "utterance_failures": failures,
        "learner": {
            "tokens": len(learner),
            "speakers": len({r["speaker_id"] for r in learner}),
            "utterances": len({r["utterance_id"] for r in learner}),
            "lexical_items": len(by_word),
            "by_tone": {t: tones.get(t, 0) for t in ("1", "2", "3", "4", "5")},
            "correct": correct, "incorrect": len(learner) - correct,
            "duration": durations,
        },
        "lexical_confound": {
            "items_both_outcomes": len(both),
            "tokens_covered": covered,
            "coverage_rate": covered / max(len(learner), 1),
            "lexical_only_accuracy": float(accuracy) if truths else None,
            "lexical_only_recall_incorrect": float(recall_bad) if truths else None,
        },
        "known_limitation": (
            "No automatic QC rule validated; fresh blinded human usability of "
            "original-boundary segments was 81/100. Descriptors are metadata "
            "only and must not be used as a cleanliness claim."),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float),
                       encoding="utf-8")
    print(f"\nmanifest : {MANIFEST}")
    print(f"summary  : {SUMMARY}")
    print(f"segments : {SEGMENT_DIR}")


if __name__ == "__main__":
    main()
