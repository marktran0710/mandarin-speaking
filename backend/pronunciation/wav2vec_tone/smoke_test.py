"""End-to-end Phase 1 smoke test on a very small dataset.

Proves the pipeline runs correctly. It does NOT prove the classifier is good --
with a handful of samples the accuracy is noise, and it is reported only so a
silently-broken pipeline (all-one-class predictions, constant embeddings) is
visible.

    # build a tiny CSV from any folder of WAVs, then run everything
    python -m pronunciation.wav2vec_tone.smoke_test --csv data/tiny.csv

    # or synthesise audio and run with no data at all
    python -m pronunciation.wav2vec_tone.smoke_test --synthetic
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.dataset import describe, load_dataset
from pronunciation.wav2vec_tone.evaluate import evaluate, print_report
from pronunciation.wav2vec_tone.extract_embeddings import extract, save_embeddings
from pronunciation.wav2vec_tone.train_classifier import (
    assert_no_speaker_overlap,
    build_classifier,
    speaker_split_mask,
)


def write_synthetic_dataset(root: Path, speakers: int = 8, per_tone: int = 3) -> Path:
    """Generate WAVs whose pitch contour imitates each Mandarin tone.

    Synthetic audio exists so the pipeline can be exercised with no corpus at
    all. The tones are crude sine sweeps, so a real model has little reason to
    classify them well -- treat any accuracy here as a plumbing check only.
    """
    import soundfile as sf

    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    rate = 16000
    duration = 0.4
    times = np.linspace(0.0, duration, int(rate * duration), endpoint=False)
    # Rough pitch trajectories: level, rising, dipping, falling.
    shapes = {
        1: lambda t: np.ones_like(t),
        2: lambda t: 1.0 + 0.35 * (t / duration),
        3: lambda t: 1.0 - 0.30 * np.sin(np.pi * t / duration),
        4: lambda t: 1.0 - 0.35 * (t / duration),
    }

    rows = []
    rng = np.random.default_rng(0)
    for speaker in range(speakers):
        base = 120.0 + speaker * 18.0        # a different voice per speaker
        for tone, shape in shapes.items():
            for index in range(per_tone):
                freq = base * shape(times)
                phase = 2 * np.pi * np.cumsum(freq) / rate
                wave = 0.4 * np.sin(phase) + 0.01 * rng.standard_normal(len(times))
                name = f"s{speaker:02d}_t{tone}_{index}.wav"
                sf.write(audio_dir / name, wave.astype(np.float32), rate)
                rows.append((f"audio/{name}", f"S{speaker:03d}", f"syn{tone}", tone))

    csv_path = root / "smoke.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["audio_path", "speaker_id", "pinyin", "tone"])
        writer.writerows(rows)
    return csv_path


def run(csv_path: Path, workdir: Path, test_ratio: float, seed: int) -> dict:
    print("=" * 62)
    print("PHASE 1 SMOKE TEST")
    print("=" * 62)

    samples = load_dataset(csv_path)
    print(f"\n[1] dataset: {describe(samples)}")

    print("\n[2] extracting frozen wav2vec2 embeddings…")
    embeddings, tones, speakers, paths, pinyin = extract(samples)
    print(f"    embedding matrix: {embeddings.shape}")

    cache = save_embeddings(
        workdir / "embeddings.npz", embeddings, tones, speakers, paths, pinyin
    )
    stored = np.load(cache, allow_pickle=True)
    print(f"\n[3] cached to {cache.name}: arrays = {sorted(stored.files)}")

    print("\n[4] speaker-independent split")
    mask, held_out = speaker_split_mask(speakers, test_ratio, seed)
    x_train, y_train = embeddings[~mask], tones[~mask]
    x_test, y_test = embeddings[mask], tones[mask]
    train_speakers = sorted({str(s) for s in speakers[~mask]})
    test_speakers = sorted({str(s) for s in speakers[mask]})
    overlap = assert_no_speaker_overlap(speakers[~mask], speakers[mask])
    print(f"    train: {len(y_train)} samples / {len(train_speakers)} speakers")
    print(f"    test : {len(y_test)} samples / {len(test_speakers)} speakers")
    print(f"    speaker overlap: {overlap}  (asserted)")

    print("\n[5] training logistic regression…")
    classifier = build_classifier(seed)
    classifier.fit(x_train, y_train)

    print("\n[6] evaluating on unseen speakers")
    report = evaluate(classifier, x_test, y_test)
    print()
    print_report(report)

    return {
        "embedding_dim": int(embeddings.shape[1]),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "train_speakers": len(train_speakers),
        "test_speakers": len(test_speakers),
        "speaker_overlap": overlap,
        "accuracy": report["accuracy"],
        "macro_f1": report["macro_f1"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="dataset CSV; omit with --synthetic")
    parser.add_argument("--synthetic", action="store_true",
                        help="generate throwaway audio instead of using a CSV")
    parser.add_argument("--keep", help="directory to keep artifacts in")
    parser.add_argument("--test-ratio", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    if not args.csv and not args.synthetic:
        parser.error("pass --csv PATH or --synthetic")

    workdir = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="w2vtone-"))
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        csv_path = (
            write_synthetic_dataset(workdir) if args.synthetic else Path(args.csv)
        )
        summary = run(csv_path, workdir, args.test_ratio, args.seed)
        print("\n" + "=" * 62)
        print("SUMMARY")
        for key, value in summary.items():
            shown = f"{value:.3f}" if isinstance(value, float) else value
            print(f"  {key:<16}: {shown}")
        print("=" * 62)
        print("Pipeline ran end to end. Accuracy on a dataset this small is")
        print("noise; this test proves the plumbing, not the model.")
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
