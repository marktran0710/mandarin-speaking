"""Verify the frozen wav2vec2 embedding pipeline on a small stratified sample.

This checks plumbing, not quality: that audio reloads from the prepared
metadata, reaches the encoder as 16 kHz mono, and comes back as a finite
fixed-width vector. Nothing is trained and nothing is classified here.

Audio is reloaded from the Hugging Face parquet by `dataset_index` rather than
from a copied WAV, which is what makes the metadata-only preparation step
sufficient. Bytes are decoded in memory with soundfile, so the dataset's own
decoder (and its extra codec dependency) is never needed.

    python -m pronunciation.wav2vec_tone.embedding_smoke_test --per-tone 8
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.extract_embeddings import (
    DEFAULT_MODEL,
    TARGET_SAMPLE_RATE,
    FrozenWav2Vec2,
)
from pronunciation.wav2vec_tone.prepare_dataset import DATASET_ID, KEEP_TONES

DEFAULT_METADATA = Path(__file__).resolve().parent / "data" / "filtered_tone_metadata.csv"


def select_samples(metadata_path: Path, per_tone: int, seed: int) -> List[dict]:
    """Pick `per_tone` records of each tone, spreading them across speakers.

    Stratifying by tone is required by the task; spreading across speakers is
    the more useful part. A smoke test drawn from one voice could pass while
    the pipeline mishandles every other recording in the corpus.
    """
    rows = list(csv.DictReader(metadata_path.open(encoding="utf-8")))
    by_tone: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        by_tone[int(row["tone"])].append(row)

    rng = np.random.default_rng(seed)
    selected: List[dict] = []
    for tone in KEEP_TONES:
        candidates = by_tone.get(tone, [])
        # One recording per speaker first, so the sample spans as many voices
        # as it can before it starts repeating any of them.
        grouped: Dict[str, List[dict]] = defaultdict(list)
        for row in candidates:
            grouped[row["speaker_id"]].append(row)
        speakers = sorted(grouped)
        rng.shuffle(speakers)
        ordered = [
            row
            for depth in range(max((len(v) for v in grouped.values()), default=0))
            for speaker in speakers
            if depth < len(grouped[speaker])
            for row in [grouped[speaker][depth]]
        ]
        selected.extend(ordered[:per_tone])
    return selected


def decode_to_16k_mono(raw: bytes) -> Tuple[np.ndarray, int]:
    """Decode WAV bytes to mono float32 at 16 kHz; return (audio, source rate).

    Downsampling is done with a polyphase filter when scipy is available.
    Plain interpolation would alias -- energy above 8 kHz folds back into the
    speech band as a spurious low-frequency tone, which is exactly the kind of
    artefact a pitch-sensitive task should not introduce.
    """
    audio, sample_rate = __import__("soundfile").read(io.BytesIO(raw), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            from math import gcd

            from scipy.signal import resample_poly

            divisor = gcd(int(sample_rate), TARGET_SAMPLE_RATE)
            audio = resample_poly(
                audio, TARGET_SAMPLE_RATE // divisor, int(sample_rate) // divisor
            ).astype(np.float32)
        except ImportError:
            target_length = max(1, int(round(len(audio) / sample_rate * TARGET_SAMPLE_RATE)))
            audio = np.interp(
                np.linspace(0.0, len(audio) - 1, target_length),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32), int(sample_rate)


def run(metadata_path: Path, per_tone: int, seed: int, model_name: str) -> dict:
    from datasets import Audio, load_dataset

    selected = select_samples(metadata_path, per_tone, seed)
    if not selected:
        raise RuntimeError(f"No records selected from {metadata_path}")

    print("=" * 64)
    print("WAV2VEC2 EMBEDDING SMOKE TEST")
    print("=" * 64)
    print(f"\n[1] selected {len(selected)} records from {metadata_path.name}")

    print("[2] reloading audio from the source parquet by dataset_index…")
    dataset = load_dataset(DATASET_ID, split="train").cast_column(
        "audio", Audio(decode=False)
    )
    indices = [int(row["dataset_index"]) for row in selected]
    subset = dataset.select(indices)

    # The index only means anything if it still points at the same recording.
    # Silent row reordering would mislabel every embedding, so it is checked
    # rather than assumed.
    for row, actual in zip(selected, subset["utt_id"]):
        if row["utt_id"] != actual:
            raise RuntimeError(
                f"dataset_index {row['dataset_index']} points at {actual}, "
                f"expected {row['utt_id']}; the metadata is stale."
            )
    print(f"    utt_id matched for all {len(selected)} records")

    print(f"\n[3] loading encoder…")
    encoder = FrozenWav2Vec2(model_name)
    print(encoder.describe())

    print("\n[4] embedding…")
    records, failures = [], []
    source_rates = Counter()
    for row, audio_field in zip(selected, subset["audio"]):
        try:
            audio, source_rate = decode_to_16k_mono(audio_field["bytes"])
            source_rates[source_rate] += 1
            duration = len(audio) / TARGET_SAMPLE_RATE
            if duration <= 0:
                raise ValueError("decoded audio has zero duration")

            inputs = encoder.processor(
                audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
            )
            with encoder._torch.no_grad():
                hidden = encoder.model(**inputs).last_hidden_state[0].numpy()
            embedding = hidden.mean(axis=0).astype(np.float32)

            records.append({
                "speaker_id": row["speaker_id"],
                "pinyin": row["pinyin"],
                "tone": int(row["tone"]),
                "sampling_rate": TARGET_SAMPLE_RATE,
                "source_rate": source_rate,
                "duration_seconds": duration,
                "hidden_state_shape": tuple(hidden.shape),
                "embedding_shape": tuple(embedding.shape),
                "embedding": embedding,
            })
        except Exception as error:  # noqa: BLE001 - collected and reported
            failures.append(f"{row['utt_id']}: {error}")

    if not records:
        raise RuntimeError("Every sample failed:\n" + "\n".join(failures))

    print(f"    embedded {len(records)}/{len(selected)}")
    for failure in failures:
        print(f"    FAILED {failure}")

    print("\n[5] five representative records")
    step = max(1, len(records) // 5)
    for record in records[::step][:5]:
        print()
        for field in (
            "speaker_id", "pinyin", "tone", "sampling_rate",
            "duration_seconds", "hidden_state_shape", "embedding_shape",
        ):
            value = record[field]
            if field == "duration_seconds":
                value = f"{value:.3f}"
            print(f"  {field}: {value}")

    matrix = np.vstack([r["embedding"] for r in records])
    widths = {r["embedding_shape"][0] for r in records}
    if len(widths) != 1:
        raise RuntimeError(f"Embedding width is not constant: {sorted(widths)}")

    return {
        "records": records,
        "matrix": matrix,
        "failures": failures,
        "model_name": encoder.model_name,
        "trainable": encoder.trainable_parameters,
        "source_rates": source_rates,
        "selected": len(selected),
    }


def summarise(result: dict) -> str:
    records = result["records"]
    matrix = result["matrix"]
    tones = Counter(r["tone"] for r in records)
    nan_rows = int(np.isnan(matrix).any(axis=1).sum())
    inf_rows = int(np.isinf(matrix).any(axis=1).sum())
    durations = [r["duration_seconds"] for r in records]
    missing = [t for t in KEEP_TONES if not tones.get(t)]

    rate_note = ", ".join(
        f"{rate} Hz x{count}" for rate, count in sorted(result["source_rates"].items())
    )
    lines = [
        "",
        "=" * 64,
        f"Samples tested: {len(records)}",
        "Tone distribution: "
        + ", ".join(f"T{t}={tones.get(t, 0)}" for t in KEEP_TONES),
        f"Audio loading successful: {len(records)}/{result['selected']}",
        f"Sampling rate: {TARGET_SAMPLE_RATE} Hz mono  (source: {rate_note})",
        f"Wav2Vec2 model: {result['model_name']}",
        f"Wav2Vec2 trainable parameters: {result['trainable']}",
        f"Embedding dimension: {matrix.shape[1]}",
        f"NaN embeddings: {nan_rows}",
        f"Inf embeddings: {inf_rows}",
        f"Failures: {len(result['failures'])}",
        "=" * 64,
        f"all four tones present : {not missing}"
        + (f"  MISSING {missing}" if missing else ""),
        f"non-zero duration      : {min(durations):.3f}s - {max(durations):.3f}s",
        f"constant embedding dim : {len({r['embedding_shape'] for r in records}) == 1}",
    ]
    # A constant embedding would satisfy every check above while carrying no
    # information at all, so the spread across samples is reported too.
    spread = float(matrix.std(axis=0).mean())
    lines.append(f"mean per-dim std       : {spread:.4f}"
                 f"  ({'varies' if spread > 1e-6 else 'CONSTANT - suspect'})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--per-tone", type=int, default=8,
                        help="records per tone (8 -> 32 samples)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    result = run(Path(args.metadata), args.per_tone, args.seed, args.model)
    print(summarise(result))
    print("\nEmbedding pipeline verified. No classifier was trained.")


if __name__ == "__main__":
    main()
