"""Forced-alignment pilot: cut OMPAL utterances into human-rated syllables.

Uses torchaudio's CTC forced alignment with the MMS_FA multilingual model
rather than a hand-rolled aligner. MMS_FA consumes romanized text, which is
exactly what lets the verified Taiwan MoE pinyin drive the alignment -- the
pronunciation input is the MoE table, never a Mainland lexicon and never the
AISHELL labels.

Two kinds of ambiguity are kept apart, because they block different things:

* **Segmental** ambiguity blocks alignment. 不 reads bù/fōu/fǒu/fū, and those
  romanize differently, so the aligner cannot be told what to look for.
* **Tonal** ambiguity blocks the label but not the alignment. 上 reads
  shǎng/shàng -- different tones, identical romanization "shang", so the
  syllable can still be located precisely.

An utterance is eligible when every *rated* syllable -- the ones we will cut
and measure -- is segmentally determined. Other syllables may carry the star
token, which tells the aligner a syllable is present without claiming to know
which. That is not a guess, and without it 87% of utterances would be
unusable because one function word somewhere reads several ways.

Tone-correctness labels are never given to the aligner. They are carried
through untouched as evaluation ground truth.

    python -m pronunciation.wav2vec_tone.align_ompal_pilot --utterances 80
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_DIR = DATA_DIR / "alignment_pilot_segments"
METADATA = DATA_DIR / "ompal_tone_benchmark_metadata.csv"
MOE_TABLE = DATA_DIR / "moe_pronunciations.csv"
SAMPLE_RATE = 16000

# Plausible span for a single Mandarin syllable in connected speech. Used to
# flag, never to adjust a boundary.
MIN_PLAUSIBLE_SECONDS = 0.040
MAX_PLAUSIBLE_SECONDS = 0.800
# A syllable needs a voiced nucleus; a span with none is very likely misplaced.
MIN_VOICED_PROPORTION = 0.15
LOW_SCORE = 0.40


def romanize(pinyin: str) -> str:
    """MoE pinyin -> bare latin letters for the aligner's dictionary."""
    decomposed = unicodedata.normalize("NFD", pinyin)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.replace("ü", "u").replace("v", "u").lower().strip()


def load_pronunciations(path: Path) -> dict[str, dict]:
    table = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        forms = {
            romanize(entry.split("(")[0])
            for entry in row["all_readings"].split("|") if entry
        }
        table[row["word"]] = {
            "segmental_forms": sorted(f for f in forms if f),
            "expected_pinyin": row["expected_pinyin"],
            "expected_tone": row["expected_tone"],
            "status": row["source_status"],
        }
    return table


def select_utterances(metadata: Path, pronunciations: dict, wanted: int, seed: int):
    """Pick eligible learner utterances spanning tones, outcomes and speakers.

    Stratified deliberately: a pilot drawn from one speaker or one tone could
    pass while alignment fails systematically elsewhere.
    """
    rows = list(csv.DictReader(metadata.open(encoding="utf-8")))
    by_utterance: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["speech_type"] == "l2" and row["audio_present"] == "1":
            by_utterance[row["utterance_id"]].append(row)

    eligible = []
    for utterance_id, tokens in by_utterance.items():
        tokens = sorted(tokens, key=lambda r: int(r["token_index"]))
        forms = [pronunciations.get(t["word"], {}).get("segmental_forms", []) for t in tokens]
        rated = [t for t in tokens if t["usable"] == "1"]
        if not tokens or not rated:
            continue
        # A rated token must have a determined pronunciation -- that is the
        # segment we will cut and measure. Everything else in the utterance may
        # be a star: "a syllable is here, its identity is undetermined". That
        # keeps the aligner honest about what we know instead of guessing a
        # reading, and without it 90% of utterances would be unusable because
        # one function word somewhere is segmentally ambiguous.
        if any(len(forms[int(t["token_index"])]) != 1 for t in rated):
            continue
        eligible.append({
            "utterance_id": utterance_id,
            "speaker_id": tokens[0]["speaker_id"],
            "tokens": tokens,
            "romanized": [f[0] if len(f) == 1 else "*" for f in forms],
            "starred": sum(1 for f in forms if len(f) != 1),
            "n_rated": len(rated),
            "tones": {t["expected_tone"] for t in rated},
            "has_incorrect": any(t["majority_tone_correct"] == "0" for t in rated),
            "length": len(tokens),
        })

    rng = np.random.default_rng(seed)
    rng.shuffle(eligible)
    # Round-robin over speakers so no voice dominates, and take utterances
    # containing an error first so both outcomes are present.
    by_speaker: dict[str, list] = defaultdict(list)
    for item in eligible:
        by_speaker[item["speaker_id"]].append(item)
    for items in by_speaker.values():
        items.sort(key=lambda i: (not i["has_incorrect"], -len(i["tones"])))

    chosen, speakers = [], sorted(by_speaker)
    depth = 0
    while len(chosen) < wanted and any(len(by_speaker[s]) > depth for s in speakers):
        for speaker in speakers:
            if len(chosen) >= wanted:
                break
            if len(by_speaker[speaker]) > depth:
                chosen.append(by_speaker[speaker][depth])
        depth += 1
    return chosen, len(eligible)


def load_audio(path: Path):
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != SAMPLE_RATE:
        from math import gcd

        from scipy.signal import resample_poly

        divisor = gcd(int(rate), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor,
                              int(rate) // divisor).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32), int(rate)


def align_utterance(model, dictionary, audio, romanized):
    """Return one (start, end, score) per syllable, in seconds."""
    import torch
    import torchaudio.functional as F

    waveform = torch.from_numpy(audio).unsqueeze(0)
    with torch.inference_mode():
        emission, _ = model(waveform)

    tokenized = [[dictionary[c] for c in word if c in dictionary] for word in romanized]
    if any(not word for word in tokenized):
        raise ValueError("a syllable romanized to nothing the dictionary knows")
    targets = torch.tensor([[t for word in tokenized for t in word]], dtype=torch.int32)

    aligned, scores = F.forced_align(emission, targets, blank=0)
    spans = F.merge_tokens(aligned[0], scores[0].exp())

    ratio = waveform.size(1) / emission.size(1) / SAMPLE_RATE
    result, cursor = [], 0
    for word in tokenized:
        chunk = spans[cursor:cursor + len(word)]
        cursor += len(word)
        if not chunk:
            result.append(None)
            continue
        result.append((
            chunk[0].start * ratio,
            chunk[-1].end * ratio,
            float(np.mean([s.score for s in chunk])),
        ))
    return result


def voiced_proportion(segment: np.ndarray) -> float:
    """Share of frames Praat finds voiced -- a syllable should have a nucleus."""
    import parselmouth

    if len(segment) < int(0.03 * SAMPLE_RATE):
        return 0.0
    try:
        pitch = parselmouth.Sound(segment.astype(np.float64), SAMPLE_RATE).to_pitch(
            time_step=0.005, pitch_floor=60.0, pitch_ceiling=500.0
        )
    except Exception:  # noqa: BLE001 - a failure here is itself a bad sign
        return 0.0
    values = pitch.selected_array["frequency"]
    return float(np.mean((values > 0) & np.isfinite(values))) if len(values) else 0.0


def classify(duration: float, score: float, voiced: float) -> tuple[str, str]:
    """good / questionable / failed, with the reason. Flags, never repairs."""
    if duration <= 0:
        return "failed", "zero_or_negative_duration"
    if duration < MIN_PLAUSIBLE_SECONDS:
        return "failed", "shorter_than_any_syllable"
    if voiced < MIN_VOICED_PROPORTION:
        return "failed", "no_voiced_nucleus"
    reasons = []
    if duration > MAX_PLAUSIBLE_SECONDS:
        reasons.append("longer_than_plausible")
    if score < LOW_SCORE:
        reasons.append("low_alignment_score")
    if voiced < 0.35:
        reasons.append("weak_voicing")
    return ("questionable", "|".join(reasons)) if reasons else ("good", "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utterances", type=int, default=80)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=str(DATA_DIR / "ompal_alignment_pilot.csv"))
    parser.add_argument("--segments", default=str(PILOT_DIR))
    args = parser.parse_args()

    import soundfile as sf
    from torchaudio.pipelines import MMS_FA

    pronunciations = load_pronunciations(MOE_TABLE)
    chosen, eligible_total = select_utterances(
        METADATA, pronunciations, args.utterances, args.seed
    )
    print(f"[1] {eligible_total} eligible learner utterances "
          f"(every rated syllable segmentally determined); piloting {len(chosen)}")
    print(f"    speakers in pilot: {len({c['speaker_id'] for c in chosen})}, "
          f"utterance lengths {min(c['length'] for c in chosen)}-"
          f"{max(c['length'] for c in chosen)} syllables")
    starred = sum(c["starred"] for c in chosen)
    total_syll = sum(c["length"] for c in chosen)
    print(f"    star-marked syllables (identity undetermined, not guessed): "
          f"{starred}/{total_syll} ({starred / max(total_syll, 1) * 100:.1f}%)")

    print("[2] loading MMS_FA aligner…")
    model = MMS_FA.get_model(with_star=True)
    dictionary = MMS_FA.get_dict(star="*")

    segment_dir = Path(args.segments)
    segment_dir.mkdir(parents=True, exist_ok=True)

    records, failures = [], []
    aligned_utterances = 0
    attempted_tokens = 0

    print("[3] aligning…")
    for position, item in enumerate(chosen, start=1):
        path = OMPAL_DIR / f"wav/SPEAKER{item['utterance_id'][1:6]}/{item['utterance_id']}.wav"
        rated = [t for t in item["tokens"] if t["usable"] == "1"]
        attempted_tokens += len(rated)
        try:
            audio, _ = load_audio(path)
            spans = align_utterance(model, dictionary, audio, item["romanized"])
            aligned_utterances += 1
        except Exception as error:  # noqa: BLE001 - recorded per utterance
            failures.append(f"{item['utterance_id']}: {type(error).__name__}: {error}")
            for token in rated:
                records.append({
                    "utterance_id": item["utterance_id"],
                    "speaker_id": item["speaker_id"],
                    "token_index": token["token_index"],
                    "word": token["word"],
                    "expected_pinyin": token["expected_pinyin"],
                    "expected_tone": token["expected_tone"],
                    "majority_tone_correct": token["majority_tone_correct"],
                    "agreement_count": token["agreement_count"],
                    "start_seconds": "", "end_seconds": "", "duration_seconds": "",
                    "alignment_score": "", "voiced_proportion": "",
                    "alignment_status": "failed",
                    "alignment_note": f"utterance_failed:{type(error).__name__}",
                    "segment_path": "",
                })
            continue

        for token in rated:
            span = spans[int(token["token_index"])]
            if span is None:
                records.append({
                    "utterance_id": item["utterance_id"],
                    "speaker_id": item["speaker_id"],
                    "token_index": token["token_index"], "word": token["word"],
                    "expected_pinyin": token["expected_pinyin"],
                    "expected_tone": token["expected_tone"],
                    "majority_tone_correct": token["majority_tone_correct"],
                    "agreement_count": token["agreement_count"],
                    "start_seconds": "", "end_seconds": "", "duration_seconds": "",
                    "alignment_score": "", "voiced_proportion": "",
                    "alignment_status": "failed", "alignment_note": "no_span_returned",
                    "segment_path": "",
                })
                continue

            start, end, score = span
            duration = end - start
            begin_sample = max(0, int(start * SAMPLE_RATE))
            end_sample = min(len(audio), int(end * SAMPLE_RATE))
            segment = audio[begin_sample:end_sample]
            voiced = voiced_proportion(segment) if len(segment) else 0.0
            status, note = classify(duration, score, voiced)

            name = f"{item['utterance_id']}_{int(token['token_index']):02d}.wav"
            if len(segment):
                # Written to a separate pilot directory; the corpus audio is
                # only ever read.
                sf.write(segment_dir / name, segment, SAMPLE_RATE)

            records.append({
                "utterance_id": item["utterance_id"],
                "speaker_id": item["speaker_id"],
                "token_index": token["token_index"], "word": token["word"],
                "expected_pinyin": token["expected_pinyin"],
                "expected_tone": token["expected_tone"],
                "majority_tone_correct": token["majority_tone_correct"],
                "agreement_count": token["agreement_count"],
                "start_seconds": f"{start:.4f}", "end_seconds": f"{end:.4f}",
                "duration_seconds": f"{duration:.4f}",
                "alignment_score": f"{score:.4f}",
                "voiced_proportion": f"{voiced:.3f}",
                "alignment_status": status, "alignment_note": note,
                "segment_path": f"alignment_pilot_segments/{name}" if len(segment) else "",
            })
        if position % 20 == 0:
            print(f"    {position}/{len(chosen)}")

    path = Path(args.out)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    summary = report(records, chosen, aligned_utterances, attempted_tokens, failures)
    print(summary)
    (DATA_DIR / "ompal_alignment_pilot_summary.json").write_text(
        json.dumps(collect(records, chosen, aligned_utterances, attempted_tokens,
                           failures), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\npilot metadata : {path}")
    print(f"segments       : {segment_dir}")


def collect(records, chosen, aligned_utterances, attempted, failures) -> dict:
    from collections import Counter

    ok = [r for r in records if r["alignment_status"] != "failed"]
    durations = np.asarray([float(r["duration_seconds"]) for r in ok]) if ok else np.zeros(0)
    return {
        "pilot_utterances": len(chosen),
        "utterances_aligned": aligned_utterances,
        "speakers": len({c["speaker_id"] for c in chosen}),
        "rated_tokens_attempted": attempted,
        "tokens_aligned": len(ok),
        "success_rate": len(ok) / max(attempted, 1),
        "status_counts": dict(Counter(r["alignment_status"] for r in records)),
        "note_counts": dict(Counter(r["alignment_note"] for r in records if r["alignment_note"])),
        "duration": {
            "min": float(durations.min()) if len(durations) else None,
            "median": float(np.median(durations)) if len(durations) else None,
            "mean": float(durations.mean()) if len(durations) else None,
            "max": float(durations.max()) if len(durations) else None,
        },
        "utterance_failures": failures,
        "aligner": "torchaudio MMS_FA CTC forced alignment",
        "pronunciation_source": "Taiwan MoE dictionary (moedict.tw), romanized",
    }


def report(records, chosen, aligned_utterances, attempted, failures) -> str:
    from collections import Counter

    data = collect(records, chosen, aligned_utterances, attempted, failures)
    ok = [r for r in records if r["alignment_status"] != "failed"]
    durations = np.asarray([float(r["duration_seconds"]) for r in ok]) if ok else np.zeros(0)
    zero_negative = sum(1 for r in records
                        if r["alignment_note"] == "zero_or_negative_duration")

    lines = [
        "",
        "=" * 74,
        "FORCED-ALIGNMENT PILOT",
        "=" * 74,
        f"Utterances attempted        : {len(chosen)}",
        f"Utterances aligned          : {aligned_utterances}",
        f"Speakers                    : {len({c['speaker_id'] for c in chosen})}",
        f"Rated tokens attempted      : {attempted}",
        f"Tokens aligned              : {len(ok)}",
        f"Alignment success rate      : {len(ok) / max(attempted, 1) * 100:.1f}%",
        f"Missing / failed tokens     : {attempted - len(ok)}",
        f"Zero or negative durations  : {zero_negative}",
        "",
        "alignment_status:",
    ]
    for status, count in Counter(r["alignment_status"] for r in records).most_common():
        lines.append(f"  {status:<14}{count:>6}  ({count / len(records) * 100:5.1f}%)")
    notes = Counter(r["alignment_note"] for r in records if r["alignment_note"])
    if notes:
        lines.append("flag reasons:")
        for note, count in notes.most_common():
            lines.append(f"  {note:<28}{count:>6}")

    if len(durations):
        lines += [
            "",
            "Segment duration (seconds):",
            f"  min {durations.min():.3f}   p25 {np.percentile(durations, 25):.3f}   "
            f"median {np.median(durations):.3f}   mean {durations.mean():.3f}   "
            f"p75 {np.percentile(durations, 75):.3f}   max {durations.max():.3f}",
        ]
        by_tone = defaultdict(list)
        for record in ok:
            by_tone[record["expected_tone"]].append(float(record["duration_seconds"]))
        lines.append("  by expected tone: " + "   ".join(
            f"T{t} n={len(v)} med={np.median(v):.3f}" for t, v in sorted(by_tone.items())))
        outcomes = Counter(r["majority_tone_correct"] for r in ok)
        lines.append(f"  aligned tokens by human label: correct={outcomes.get('1', 0)}, "
                     f"incorrect={outcomes.get('0', 0)}")

    if failures:
        lines += ["", f"utterance-level failures ({len(failures)}):"]
        lines += [f"  {f}" for f in failures[:5]]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
