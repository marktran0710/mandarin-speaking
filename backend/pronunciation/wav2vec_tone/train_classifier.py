"""Train a 4-way tone classifier on frozen wav2vec2 embeddings.

Logistic regression on purpose. With the encoder frozen, the interesting
question is how much tone information the representation already carries -- a
linear probe answers that directly, while a high-capacity model would blur it
by learning structure of its own.

The classifier is saved on its own, without the encoder. wav2vec2 weights are
unchanged by definition here, so storing them again would add hundreds of
megabytes that reproduce exactly from the checkpoint name.

    python -m pronunciation.wav2vec_tone.train_classifier \
        --embeddings models/embeddings.npz --out models/tone_classifier.joblib
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.dataset import VALID_TONES

TONE_LABELS = list(VALID_TONES)


def load_embeddings(path: str | Path):
    stored = np.load(Path(path), allow_pickle=True)
    return stored["embeddings"], stored["tones"], stored["speakers"]


def split_by_speaker(embeddings, tones, speakers, test_ratio=0.25, seed=0):
    """Hold out whole speakers, mirroring dataset.speaker_independent_split.

    Kept here so a saved .npz can be split without re-reading the CSV, using
    the same rule: no speaker may appear on both sides.
    """
    import random

    unique = sorted({str(s) for s in speakers})
    if len(unique) < 2:
        raise ValueError(
            f"speaker-independent split needs at least 2 speakers, found "
            f"{len(unique)}"
        )
    random.Random(seed).shuffle(unique)
    count = max(1, min(len(unique) - 1, round(len(unique) * test_ratio)))
    held_out = set(unique[:count])

    mask = np.asarray([str(s) in held_out for s in speakers])
    return (
        embeddings[~mask], tones[~mask],
        embeddings[mask], tones[mask],
        sorted(held_out),
    )


def build_classifier(seed: int = 0):
    """A standardised linear probe.

    Standardisation matters: wav2vec2 dimensions have very different scales,
    and without it the regulariser would penalise them unevenly, which is a
    property of the scaling rather than of the tones.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=2000,
            # Multinomial is the default for multi-class with the lbfgs solver;
            # the explicit multi_class argument was removed in scikit-learn 1.8.
            #
            # Balanced because tone frequencies are uneven in natural text; the
            # classifier should not gain accuracy by favouring the commonest.
            class_weight="balanced",
            random_state=seed,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", required=True, help="from extract_embeddings")
    parser.add_argument("--out", default="models/tone_classifier.joblib")
    parser.add_argument("--test-ratio", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import joblib

    embeddings, tones, speakers = load_embeddings(args.embeddings)
    x_train, y_train, x_test, y_test, held_out = split_by_speaker(
        embeddings, tones, speakers, args.test_ratio, args.seed
    )
    print(f"train {x_train.shape[0]} samples / test {x_test.shape[0]} samples")
    print(f"held-out speakers ({len(held_out)}): {', '.join(held_out[:10])}"
          + (" …" if len(held_out) > 10 else ""))

    classifier = build_classifier(args.seed)
    classifier.fit(x_train, y_train)

    train_accuracy = float(classifier.score(x_train, y_train))
    test_accuracy = float(classifier.score(x_test, y_test))
    print(f"train accuracy {train_accuracy * 100:.1f}%")
    print(f"test  accuracy {test_accuracy * 100:.1f}%   (unseen speakers)")
    # A wide gap means the probe is fitting the training voices rather than
    # tone, which is what the speaker-independent split exists to reveal.
    print(f"gap            {(train_accuracy - test_accuracy) * 100:+.1f} pts")

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "classifier": classifier,
            "tone_labels": TONE_LABELS,
            "embedding_dim": int(embeddings.shape[1]),
            "held_out_speakers": held_out,
        },
        output,
    )
    print(f"saved classifier to {output} (encoder weights not included)")


if __name__ == "__main__":
    main()
