"""Predict the tone of one WAV file, as JSON.

    python -m pronunciation.wav2vec_tone.predict \
        --audio sample.wav --model models/tone_classifier.joblib

Output:

    {
      "predicted_tone": 3,
      "probabilities": {
        "tone_1": 0.03, "tone_2": 0.12, "tone_3": 0.79, "tone_4": 0.06
      }
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.dataset import VALID_TONES
from pronunciation.wav2vec_tone.extract_embeddings import DEFAULT_MODEL, FrozenWav2Vec2

_ENCODER: FrozenWav2Vec2 | None = None


def _encoder(model_name: str) -> FrozenWav2Vec2:
    """Load the encoder once; it is the expensive part of a prediction."""
    global _ENCODER
    if _ENCODER is None or _ENCODER.model_name != model_name:
        _ENCODER = FrozenWav2Vec2(model_name)
    return _ENCODER


def predict(
    audio_path: str | Path,
    model_path: str | Path = "models/tone_classifier.joblib",
    encoder_name: str = DEFAULT_MODEL,
) -> dict:
    """Return the predicted tone and a probability per tone."""
    import joblib

    bundle = joblib.load(Path(model_path))
    classifier = bundle["classifier"]

    embedding = _encoder(encoder_name).embed(audio_path).reshape(1, -1)

    expected_dim = bundle.get("embedding_dim")
    if expected_dim is not None and embedding.shape[1] != expected_dim:
        raise ValueError(
            f"embedding is {embedding.shape[1]}-dimensional but the classifier "
            f"was trained on {expected_dim}. The encoder does not match the one "
            f"used for training."
        )

    probabilities = classifier.predict_proba(embedding)[0]
    # Read the class order off the fitted model rather than assuming 1,2,3,4 --
    # a mismatch here would silently relabel every prediction.
    classes = list(classifier.classes_)
    by_tone = {
        f"tone_{tone}": round(
            float(probabilities[classes.index(tone)]) if tone in classes else 0.0, 4
        )
        for tone in VALID_TONES
    }
    return {
        "predicted_tone": int(classes[int(probabilities.argmax())]),
        "probabilities": by_tone,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="one WAV file")
    parser.add_argument("--model", default="models/tone_classifier.joblib")
    parser.add_argument("--encoder", default=DEFAULT_MODEL)
    args = parser.parse_args()

    print(json.dumps(predict(args.audio, args.model, args.encoder), indent=2))


if __name__ == "__main__":
    main()
