"""Extract frozen wav2vec2 embeddings for the whole filtered dataset, once.

Running the encoder is the expensive step in Phase 1 and its output is
deterministic -- the weights are frozen, so the same clip always yields the
same vector. Caching means every later classifier experiment reads an NPZ
instead of re-running 879 forward passes.

The pipeline is exactly the one verified by embedding_smoke_test: reload audio
from the source parquet by dataset_index, decode to 16 kHz mono, mean-pool the
final hidden state. Mean-pooling is deliberately unchanged here; this cache is
the baseline any alternative pooling has to beat.

    python -m pronunciation.wav2vec_tone.cache_embeddings
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.embedding_smoke_test import (
    DEFAULT_METADATA,
    decode_to_16k_mono,
)
from pronunciation.wav2vec_tone.extract_embeddings import (
    DEFAULT_MODEL,
    TARGET_SAMPLE_RATE,
    FrozenWav2Vec2,
)
from pronunciation.wav2vec_tone.prepare_dataset import DATASET_ID, KEEP_TONES

DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "embeddings_frozen_meanpool.npz"
EXPECTED_DIMENSION = 768
SHORT_THRESHOLDS = (0.15, 0.20, 0.25)


def extract_all(metadata_path: Path, model_name: str, limit: int | None = None) -> dict:
    from datasets import Audio, load_dataset

    rows = list(csv.DictReader(metadata_path.open(encoding="utf-8")))
    if limit:
        rows = rows[:limit]
    print(f"[1] {len(rows)} records from {metadata_path.name}")

    print("[2] opening source parquet…")
    dataset = load_dataset(DATASET_ID, split="train").cast_column(
        "audio", Audio(decode=False)
    )
    subset = dataset.select([int(row["dataset_index"]) for row in rows])

    # The cache is keyed by dataset_index; if an index no longer points at the
    # recording the metadata claims, every embedding after it is mislabelled
    # and nothing downstream could tell.
    mismatches = [
        (row["dataset_index"], row["utt_id"], actual)
        for row, actual in zip(rows, subset["utt_id"])
        if row["utt_id"] != actual
    ]
    if mismatches:
        raise RuntimeError(
            f"{len(mismatches)} dataset_index values point at the wrong "
            f"recording, e.g. {mismatches[0]}. The metadata is stale."
        )
    print(f"    utt_id verified for all {len(rows)} records")

    print("[3] loading encoder…")
    encoder = FrozenWav2Vec2(model_name)
    print(encoder.describe())

    print("[4] embedding…")
    kept: dict[str, list] = {
        key: [] for key in
        ("embedding", "speaker_id", "pinyin", "syllable_base", "tone",
         "duration_seconds", "dataset_index", "utt_id", "frames")
    }
    failures = []
    started = time.time()

    for position, (row, audio_field) in enumerate(zip(rows, subset["audio"]), start=1):
        try:
            audio, _ = decode_to_16k_mono(audio_field["bytes"])
            duration = len(audio) / TARGET_SAMPLE_RATE
            if duration <= 0:
                raise ValueError("decoded audio has zero duration")

            inputs = encoder.processor(
                audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
            )
            with encoder._torch.no_grad():
                hidden = encoder.model(**inputs).last_hidden_state[0].numpy()

            kept["embedding"].append(hidden.mean(axis=0).astype(np.float32))
            kept["frames"].append(int(hidden.shape[0]))
            kept["speaker_id"].append(row["speaker_id"])
            kept["pinyin"].append(row["pinyin"])
            kept["syllable_base"].append(row["syllable_base"])
            kept["tone"].append(int(row["tone"]))
            kept["duration_seconds"].append(duration)
            kept["dataset_index"].append(int(row["dataset_index"]))
            kept["utt_id"].append(row["utt_id"])
        except Exception as error:  # noqa: BLE001 - collected and reported
            # Skipped, never zero-filled: a zero vector is indistinguishable
            # from a real measurement once it reaches a classifier.
            failures.append(f"{row['utt_id']}: {error}")

        if position % 100 == 0:
            rate = position / max(time.time() - started, 1e-9)
            print(f"    {position}/{len(rows)}  ({rate:.1f}/s)", end="\r")

    elapsed = time.time() - started
    print(f"    embedded {len(kept['embedding'])}/{len(rows)} in {elapsed:.0f}s"
          f"  ({len(rows) / max(elapsed, 1e-9):.1f}/s)      ")
    for failure in failures[:10]:
        print(f"    FAILED {failure}")

    if not kept["embedding"]:
        raise RuntimeError("Nothing was embedded.")

    return {
        "embeddings": np.vstack(kept["embedding"]),
        "speakers": np.asarray(kept["speaker_id"], dtype=object),
        "pinyin": np.asarray(kept["pinyin"], dtype=object),
        "syllable_bases": np.asarray(kept["syllable_base"], dtype=object),
        "tones": np.asarray(kept["tone"], dtype=int),
        "durations": np.asarray(kept["duration_seconds"], dtype=np.float64),
        "dataset_indices": np.asarray(kept["dataset_index"], dtype=int),
        "utt_ids": np.asarray(kept["utt_id"], dtype=object),
        "frames": np.asarray(kept["frames"], dtype=int),
        "model_name": encoder.model_name,
        "failures": failures,
        "requested": len(rows),
    }


def verify(cache: dict, expected_total: int, expected_speakers: int) -> list[str]:
    """Return a list of problems; empty means the cache is sound."""
    embeddings = cache["embeddings"]
    problems = []

    if len(embeddings) != expected_total:
        problems.append(f"expected {expected_total} samples, cached {len(embeddings)}")
    if embeddings.shape[1] != EXPECTED_DIMENSION:
        problems.append(
            f"embedding dimension is {embeddings.shape[1]}, expected {EXPECTED_DIMENSION}"
        )
    if int(np.isnan(embeddings).any(axis=1).sum()):
        problems.append(f"{int(np.isnan(embeddings).any(axis=1).sum())} NaN embeddings")
    if int(np.isinf(embeddings).any(axis=1).sum()):
        problems.append(f"{int(np.isinf(embeddings).any(axis=1).sum())} Inf embeddings")

    indices = cache["dataset_indices"]
    duplicates = len(indices) - len(set(indices.tolist()))
    if duplicates:
        problems.append(f"{duplicates} duplicate dataset_index values")

    missing_tones = [t for t in KEEP_TONES if t not in set(cache["tones"].tolist())]
    if missing_tones:
        problems.append(f"tones missing from the cache: {missing_tones}")

    speakers = len(set(cache["speakers"].tolist()))
    if speakers != expected_speakers:
        problems.append(f"expected {expected_speakers} speakers, cached {speakers}")

    if float(embeddings.std(axis=0).mean()) < 1e-6:
        problems.append("embeddings are constant across samples")
    return problems


def duration_stats(durations: np.ndarray) -> dict:
    # numpy's default linear interpolation between order statistics.
    return {
        "min": float(durations.min()),
        "p10": float(np.percentile(durations, 10)),
        "p25": float(np.percentile(durations, 25)),
        "median": float(np.median(durations)),
        "mean": float(durations.mean()),
        "p75": float(np.percentile(durations, 75)),
        "p90": float(np.percentile(durations, 90)),
        "max": float(durations.max()),
    }


def format_report(cache: dict, path: Path, problems: list[str]) -> str:
    durations = cache["durations"]
    tones = cache["tones"]
    total = len(durations)
    overall = duration_stats(durations)
    tone_counts = Counter(tones.tolist())

    lines = [
        "=" * 68,
        f"Cached samples: {total}",
        f"Embedding dimension: {cache['embeddings'].shape[1]}",
        f"Unique speakers: {len(set(cache['speakers'].tolist()))}",
        "Tone distribution: "
        + ", ".join(f"T{t}={tone_counts.get(t, 0)}" for t in KEEP_TONES),
        f"NaN: {int(np.isnan(cache['embeddings']).any(axis=1).sum())}",
        f"Inf: {int(np.isinf(cache['embeddings']).any(axis=1).sum())}",
        f"Duplicate indices: "
        f"{len(cache['dataset_indices']) - len(set(cache['dataset_indices'].tolist()))}",
        "",
        "Overall duration (seconds):",
    ]
    lines += [f"  {key:<7}: {value:.3f}" for key, value in overall.items()]

    lines.append("")
    for threshold in SHORT_THRESHOLDS:
        count = int((durations < threshold).sum())
        lines.append(f"  <{threshold:.2f} s : {count:>4}  ({count / total * 100:5.1f}%)")
    count = int((durations >= SHORT_THRESHOLDS[-1]).sum())
    lines.append(f"  >={SHORT_THRESHOLDS[-1]:.2f} s: {count:>4}"
                 f"  ({count / total * 100:5.1f}%)")

    lines += ["", "Duration by tone (seconds):", "",
              f"  {'tone':<6}{'n':>5}{'min':>8}{'p10':>8}{'p25':>8}"
              f"{'median':>9}{'mean':>8}{'p75':>8}{'p90':>8}{'max':>8}{'<0.20s':>9}"]
    for tone in KEEP_TONES:
        subset = durations[tones == tone]
        if not len(subset):
            continue
        stats = duration_stats(subset)
        short = int((subset < 0.20).sum())
        lines.append(
            f"  T{tone:<5}{len(subset):>5}"
            + "".join(f"{stats[key]:>8.3f}" for key in
                      ("min", "p10", "p25"))
            + f"{stats['median']:>9.3f}"
            + "".join(f"{stats[key]:>8.3f}" for key in ("mean", "p75", "p90", "max"))
            + f"{short / len(subset) * 100:>8.1f}%"
        )

    frames = cache["frames"]
    lines += [
        "",
        "wav2vec2 frames pooled per sample (20 ms stride):",
        f"  min {int(frames.min())}   p10 {int(np.percentile(frames, 10))}   "
        f"median {int(np.median(frames))}   max {int(frames.max())}",
        "",
        f"Saved embedding path: {path}",
        "=" * 68,
    ]
    if problems:
        lines.append("VERIFICATION FAILED:")
        lines += [f"  - {problem}" for problem in problems]
    else:
        lines.append("Verification passed: count, dimension, NaN/Inf, duplicate")
        lines.append("indices, tone coverage and speaker coverage all as expected.")
    return "\n".join(lines)


def save(cache: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        embeddings=cache["embeddings"],
        speakers=cache["speakers"],
        pinyin=cache["pinyin"],
        syllable_bases=cache["syllable_bases"],
        tones=cache["tones"],
        durations=cache["durations"],
        dataset_indices=cache["dataset_indices"],
        utt_ids=cache["utt_ids"],
        frames=cache["frames"],
        # Provenance: which encoder produced these, and how they were pooled.
        # Without it a later cache with different settings is indistinguishable.
        model_name=np.asarray(cache["model_name"]),
        pooling=np.asarray("mean"),
        sample_rate=np.asarray(TARGET_SAMPLE_RATE),
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, help="first N records only (debugging)")
    parser.add_argument("--expect-total", type=int, default=879)
    parser.add_argument("--expect-speakers", type=int, default=24)
    args = parser.parse_args()

    cache = extract_all(Path(args.metadata), args.model, args.limit)
    path = save(cache, Path(args.out))
    problems = (
        [] if args.limit
        else verify(cache, args.expect_total, args.expect_speakers)
    )
    print()
    print(format_report(cache, path, problems))
    print(f"\nsize on disk: {path.stat().st_size / 1e6:.1f} MB")
    print("Embeddings cached. No classifier was trained.")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
