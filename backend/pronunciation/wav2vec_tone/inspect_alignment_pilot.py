"""Independent boundary check on a stratified sample of aligned tokens.

IMPORTANT LIMITATION: this does not listen. I cannot hear the audio, so what
follows is not the auditory inspection the task asks for -- it is an
independent acoustic corroboration, and the extracted wav files are written so
a human can do the listening part.

Independence is the point. The boundaries came from a CTC model; re-asking that
same model whether it was right would prove nothing. So the check uses Praat
intensity and voicing, which know nothing about the aligner:

* a syllable has exactly one voiced intensity peak (its nucleus) -- zero means
  the span missed the syllable, two means it swallowed a neighbour;
* syllable boundaries fall near intensity minima, so a boundary sitting on an
  energy peak suggests the cut landed mid-vowel;
* consecutive spans should not overlap, and large gaps mean audio was dropped.

    python -m pronunciation.wav2vec_tone.inspect_alignment_pilot
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
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
SAMPLE_RATE = 16000

# A boundary is "clean" if intensity there is at least this far below the
# segment's own peak -- i.e. the cut is in a trough, not through a vowel.
BOUNDARY_DROP_DB = 3.0
NUCLEUS_PROMINENCE_DB = 4.0


def load_audio(path: Path) -> np.ndarray:
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
    return np.ascontiguousarray(audio, dtype=np.float32)


def utterance_profile(audio: np.ndarray):
    """Intensity contour and voicing over the whole utterance, via Praat."""
    import parselmouth

    sound = parselmouth.Sound(audio.astype(np.float64), SAMPLE_RATE)
    intensity = sound.to_intensity(minimum_pitch=60.0, time_step=0.005)
    pitch = sound.to_pitch(time_step=0.005, pitch_floor=60.0, pitch_ceiling=500.0)
    return {
        "intensity_times": np.asarray(intensity.xs(), dtype=float),
        "intensity_db": np.asarray(intensity.values[0], dtype=float),
        "pitch_times": np.asarray(pitch.xs(), dtype=float),
        "voiced": (pitch.selected_array["frequency"] > 0),
    }


def value_at(times: np.ndarray, values: np.ndarray, moment: float) -> float:
    if not len(times):
        return float("nan")
    return float(values[int(np.argmin(np.abs(times - moment)))])


def count_nuclei(profile, start: float, end: float) -> int:
    """Voiced intensity peaks inside a span -- one per syllable is expected."""
    times, db = profile["intensity_times"], profile["intensity_db"]
    inside = (times >= start) & (times <= end)
    if inside.sum() < 3:
        return 0
    window_times, window_db = times[inside], db[inside]

    voiced_at = np.interp(
        window_times, profile["pitch_times"], profile["voiced"].astype(float)
    ) > 0.5
    if not voiced_at.any():
        return 0

    peaks = 0
    for index in range(1, len(window_db) - 1):
        if not voiced_at[index]:
            continue
        if window_db[index] >= window_db[index - 1] and window_db[index] > window_db[index + 1]:
            left = window_db[:index].min() if index else window_db[index]
            right = window_db[index + 1:].min()
            if window_db[index] - max(left, right) >= NUCLEUS_PROMINENCE_DB:
                peaks += 1
    # A flat but clearly voiced span is still one nucleus.
    return peaks if peaks else (1 if voiced_at.mean() > 0.5 else 0)


def inspect(row, profile, neighbours) -> dict:
    start, end = float(row["start_seconds"]), float(row["end_seconds"])
    times, db = profile["intensity_times"], profile["intensity_db"]
    inside = (times >= start) & (times <= end)
    peak_db = float(db[inside].max()) if inside.any() else float("nan")

    start_db = value_at(times, db, start)
    end_db = value_at(times, db, end)
    nuclei = count_nuclei(profile, start, end)

    overlap = 0.0
    for other_start, other_end in neighbours:
        overlap += max(0.0, min(end, other_end) - max(start, other_start))

    clean_start = np.isfinite(start_db) and (peak_db - start_db) >= BOUNDARY_DROP_DB
    clean_end = np.isfinite(end_db) and (peak_db - end_db) >= BOUNDARY_DROP_DB

    if nuclei == 0:
        verdict, reason = "wrong", "no voiced nucleus in span"
    elif nuclei > 1:
        verdict, reason = "questionable", f"{nuclei} nuclei - may span two syllables"
    elif overlap > 0.02:
        verdict, reason = "questionable", f"overlaps neighbour by {overlap * 1000:.0f} ms"
    elif not (clean_start or clean_end):
        verdict, reason = "questionable", "both boundaries cut through high energy"
    elif not (clean_start and clean_end):
        verdict, reason = "correct", "one boundary mid-energy (normal in connected speech)"
    else:
        verdict, reason = "correct", "single nucleus, both boundaries in energy troughs"

    return {
        "verdict": verdict, "reason": reason, "nuclei": nuclei,
        "peak_db": peak_db, "start_db": start_db, "end_db": end_db,
        "overlap_seconds": overlap,
    }


def choose_sample(rows, wanted: int, seed: int):
    """Stratify over tone x human label, spread across speakers."""
    usable = [r for r in rows if r["alignment_status"] != "failed" and r["start_seconds"]]
    buckets: dict[tuple, list] = defaultdict(list)
    for row in usable:
        buckets[(row["expected_tone"], row["majority_tone_correct"])].append(row)

    rng = np.random.default_rng(seed)
    for items in buckets.values():
        rng.shuffle(items)
        items.sort(key=lambda r: r["speaker_id"])

    keys = sorted(buckets)
    chosen, depth = [], 0
    while len(chosen) < wanted and any(len(buckets[k]) > depth for k in keys):
        for key in keys:
            if len(chosen) >= wanted:
                break
            if len(buckets[key]) > depth:
                chosen.append(buckets[key][depth])
        depth += 1
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows = list(csv.DictReader(PILOT_CSV.open(encoding="utf-8")))
    sample = choose_sample(rows, args.sample, args.seed)

    by_utterance: dict[str, list] = defaultdict(list)
    for row in rows:
        if row["start_seconds"]:
            by_utterance[row["utterance_id"]].append(row)

    profiles: dict[str, dict] = {}
    results = []
    print("=" * 92)
    print("INDEPENDENT BOUNDARY CHECK  (Praat intensity + voicing; NOT auditory)")
    print("=" * 92)
    print(f"  {'utterance':<10}{'spk':>6}{'word':>5}{'pinyin':>8}{'tone':>5}"
          f"{'label':>7}{'start':>8}{'end':>8}{'dur':>7}{'nuc':>4}  verdict / reason")

    for row in sample:
        utterance_id = row["utterance_id"]
        if utterance_id not in profiles:
            path = OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav"
            profiles[utterance_id] = utterance_profile(load_audio(path))
        neighbours = [
            (float(o["start_seconds"]), float(o["end_seconds"]))
            for o in by_utterance[utterance_id]
            if o["token_index"] != row["token_index"]
        ]
        verdict = inspect(row, profiles[utterance_id], neighbours)
        results.append({**row, **verdict})
        label = "correct" if row["majority_tone_correct"] == "1" else "INCORRECT"
        print(f"  {utterance_id:<10}{row['speaker_id']:>6}{row['word']:>5}"
              f"{row['expected_pinyin']:>8}{row['expected_tone']:>5}{label:>7}"
              f"{float(row['start_seconds']):>8.3f}{float(row['end_seconds']):>8.3f}"
              f"{float(row['duration_seconds']):>7.3f}{verdict['nuclei']:>4}"
              f"  {verdict['verdict']}: {verdict['reason']}")

    counts = Counter(r["verdict"] for r in results)
    print()
    print(f"manual inspection tokens: {len(results)}")
    print(f"correct boundary        : {counts.get('correct', 0)}")
    print(f"questionable boundary   : {counts.get('questionable', 0)}")
    print(f"wrong boundary          : {counts.get('wrong', 0)}")
    print(f"  tones covered  : {sorted({r['expected_tone'] for r in results})}")
    print(f"  speakers       : {len({r['speaker_id'] for r in results})}")
    print(f"  human-correct  : {sum(1 for r in results if r['majority_tone_correct'] == '1')}"
          f" / human-incorrect: {sum(1 for r in results if r['majority_tone_correct'] == '0')}")

    out = DATA_DIR / "ompal_alignment_inspection.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        fields = ["utterance_id", "speaker_id", "word", "expected_pinyin",
                  "expected_tone", "majority_tone_correct", "start_seconds",
                  "end_seconds", "duration_seconds", "alignment_score",
                  "alignment_status", "verdict", "reason", "nuclei",
                  "overlap_seconds", "segment_path"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    (DATA_DIR / "ompal_alignment_inspection_summary.json").write_text(
        json.dumps({
            "method": "praat_intensity_voicing_independent_of_aligner",
            "auditory_verification": False,
            "n": len(results), "verdicts": dict(counts),
            "tones": sorted({r["expected_tone"] for r in results}),
            "speakers": len({r["speaker_id"] for r in results}),
        }, indent=2), encoding="utf-8")
    print(f"\ninspection csv: {out}")
    print("\nNOTE: this is an acoustic proxy. The extracted segment wavs are")
    print("provided so a human can confirm by ear.")


if __name__ == "__main__":
    main()
