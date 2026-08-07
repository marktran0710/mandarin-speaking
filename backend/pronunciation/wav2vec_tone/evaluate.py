"""Evaluate the tone classifier on held-out speakers.

Accuracy alone hides the failure that matters. Mandarin tone 3 is the rarest
and the most reduced in connected speech, so a classifier can score well
overall while barely recognising it -- per-tone recall and the confusion matrix
are what expose that.

    python -m pronunciation.wav2vec_tone.evaluate \
        --embeddings models/embeddings.npz --model models/tone_classifier.joblib
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.dataset import VALID_TONES
from pronunciation.wav2vec_tone.train_classifier import (
    load_embeddings,
    split_by_speaker,
)


def evaluate(classifier, x_test, y_test) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
    )

    predicted = classifier.predict(x_test)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_test, predicted, labels=list(VALID_TONES), zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "macro_f1": float(f1_score(y_test, predicted, average="macro", zero_division=0)),
        "per_tone": {
            tone: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, tone in enumerate(VALID_TONES)
        },
        "confusion_matrix": confusion_matrix(
            y_test, predicted, labels=list(VALID_TONES)
        ).tolist(),
        "n": int(len(y_test)),
    }


def print_report(report: dict) -> None:
    print("=== TONE CLASSIFIER (held-out speakers) ===")
    print(f"n              : {report['n']}")
    print(f"accuracy       : {report['accuracy'] * 100:.1f}%")
    print(f"macro F1       : {report['macro_f1']:.3f}")
    print(f"chance (4-way) : 25.0%")
    print()
    print(f"{'tone':<6}{'precision':>11}{'recall':>9}{'F1':>8}{'support':>9}")
    print("-" * 43)
    for tone in VALID_TONES:
        row = report["per_tone"][tone]
        print(
            f"T{tone:<5}{row['precision']:>11.3f}{row['recall']:>9.3f}"
            f"{row['f1']:>8.3f}{row['support']:>9}"
        )
    print()
    print("confusion, rows = true tone, cols = predicted:")
    print("        " + "".join(f"{f'T{t}':>7}" for t in VALID_TONES))
    for index, tone in enumerate(VALID_TONES):
        row = report["confusion_matrix"][index]
        print(f"  T{tone}   " + "".join(f"{value:>7}" for value in row))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", required=True)
    parser.add_argument("--model", default="models/tone_classifier.joblib")
    parser.add_argument("--test-ratio", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", help="also write the report as JSON")
    args = parser.parse_args()

    import joblib

    bundle = joblib.load(Path(args.model))
    classifier = bundle["classifier"]

    embeddings, tones, speakers = load_embeddings(args.embeddings)
    # Same seed and ratio reproduce the split used in training, so the test
    # speakers here are the ones the classifier never saw.
    _, _, x_test, y_test, held_out = split_by_speaker(
        embeddings, tones, speakers, args.test_ratio, args.seed
    )
    stored = bundle.get("held_out_speakers")
    if stored and sorted(stored) != sorted(held_out):
        print(
            "WARNING: held-out speakers differ from those used in training.\n"
            "         Pass the same --test-ratio and --seed, or this measures\n"
            "         speakers the classifier was trained on."
        )

    report = evaluate(classifier, x_test, y_test)
    print_report(report)

    if args.json:
        import json

        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
