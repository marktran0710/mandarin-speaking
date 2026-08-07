"""Turn WAV files into frozen Mandarin wav2vec2 embeddings.

Frozen means the model's weights are never updated: it is used purely as a
fixed feature extractor, so the only thing learned downstream is the small
classifier. That keeps Phase 1 cheap and makes any result attributable to the
representation rather than to training tricks.

The default checkpoint is Mandarin-pretrained. Tone is exactly what an
English-only model has least reason to encode, and this one is already present
in the local Hugging Face cache, so no download is needed.

    python -m pronunciation.wav2vec_tone.extract_embeddings \
        --csv data/tones.csv --out models/embeddings.npz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.dataset import ToneSample, describe, load_dataset

# Mandarin-pretrained, and already in the local HF cache. The English base model
# is the fallback so a missing repo degrades to a working run rather than a
# crash -- but expect worse tone results from it.
DEFAULT_MODEL = "TencentGameMate/chinese-wav2vec2-base"
FALLBACK_MODEL = "facebook/wav2vec2-base"
TARGET_SAMPLE_RATE = 16000


class FrozenWav2Vec2:
    """A wav2vec2 encoder used strictly as a fixed feature extractor."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        import torch
        from transformers import AutoFeatureExtractor, AutoModel

        errors = []
        for name in (model_name, FALLBACK_MODEL):
            try:
                self.processor = AutoFeatureExtractor.from_pretrained(name)
                self.model = AutoModel.from_pretrained(name)
                self.model_name = name
                break
            except Exception as error:  # noqa: BLE001 - all attempts reported
                errors.append(f"{name}: {error}")
        else:
            raise RuntimeError("Could not load any model:\n" + "\n".join(errors))

        # Freeze: no gradients, eval mode. Phase 1 does not fine-tune.
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad = False
        self._torch = torch

        self.total_parameters = sum(p.numel() for p in self.model.parameters())
        self.trainable_parameters = sum(
            p.numel() for p in self.model.parameters() if p.requires_grad
        )
        # Asserted, not just reported: a single unfrozen parameter would mean
        # the encoder drifts during any later experiment, and every embedding
        # extracted before that point would silently stop matching.
        if self.trainable_parameters != 0:
            raise RuntimeError(
                f"{self.trainable_parameters} wav2vec2 parameters are still "
                f"trainable; Phase 1 requires the encoder fully frozen."
            )

    def describe(self) -> str:
        lines = [
            f"model: {self.model_name}",
            f"  total parameters    : {self.total_parameters:,}",
            f"  trainable parameters: {self.trainable_parameters:,}"
            f"   (frozen: {self.trainable_parameters == 0})",
            f"  input normalized by feature extractor: "
            f"{getattr(self.processor, 'do_normalize', 'unknown')}",
            f"  target sample rate   : {TARGET_SAMPLE_RATE} Hz mono",
        ]
        return "\n".join(lines)

    def embed(self, audio_path: str | Path) -> np.ndarray:
        """One mean-pooled embedding for the whole file.

        Mean-pooling over time collapses the utterance to a single vector. For
        a one-syllable clip that is the syllable's embedding, which is what
        Phase 1 assumes the dataset provides.
        """
        waveform = load_audio_16k_mono(audio_path)
        inputs = self.processor(
            waveform, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
        )
        with self._torch.no_grad():
            output = self.model(**inputs)
        hidden = output.last_hidden_state[0].numpy()
        return hidden.mean(axis=0).astype(np.float32)


def load_audio_16k_mono(audio_path: str | Path) -> np.ndarray:
    """Read a WAV as mono float32 at 16 kHz.

    wav2vec2 was trained on 16 kHz mono; feeding it another rate silently
    changes the effective speed of the audio and every frame it produces.
    """
    import soundfile as sf

    audio, sample_rate = sf.read(str(audio_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != TARGET_SAMPLE_RATE:
        duration = len(audio) / sample_rate
        target_length = max(1, int(round(duration * TARGET_SAMPLE_RATE)))
        audio = np.interp(
            np.linspace(0.0, len(audio) - 1, target_length),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)
    return audio


def extract(
    samples, model_name: str = DEFAULT_MODEL, verbose: bool = True
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (embeddings, tones, speaker_ids) for every readable sample.

    A file that cannot be read is reported and skipped rather than filled with
    zeros: a zero vector is indistinguishable from a real measurement once it
    reaches the classifier.
    """
    encoder = FrozenWav2Vec2(model_name)
    if verbose:
        print(encoder.describe())

    vectors, tones, speakers, paths, pinyins, failures = [], [], [], [], [], []
    for index, sample in enumerate(samples, start=1):
        try:
            vector = encoder.embed(sample.audio_path)
            if verbose and not vectors:
                print(f"  embedding shape for one file: {vector.shape}"
                      f"  ({sample.audio_path.name})")
            vectors.append(vector)
            tones.append(sample.tone)
            speakers.append(sample.speaker_id)
            paths.append(str(sample.audio_path))
            pinyins.append(sample.pinyin)
        except Exception as error:  # noqa: BLE001 - collected and reported
            failures.append(f"{sample.audio_path}: {error}")
        if verbose and index % 50 == 0:
            print(f"  {index}/{len(samples)}", end="\r")

    if verbose:
        print(f"  extracted {len(vectors)}/{len(samples)}        ")
        for failure in failures[:10]:
            print(f"  SKIPPED {failure}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")
    if not vectors:
        raise RuntimeError("No audio could be read; nothing to extract.")
    return (
        np.vstack(vectors),
        np.asarray(tones, dtype=int),
        np.asarray(speakers, dtype=object),
        np.asarray(paths, dtype=object),
        np.asarray(pinyins, dtype=object),
    )


def save_embeddings(path, embeddings, tones, speakers, paths, pinyin) -> Path:
    """Cache everything needed to rerun classifier experiments without audio.

    Paths and pinyin travel with the vectors so a surprising prediction can be
    traced back to the exact clip that produced it. Re-running wav2vec2 is the
    expensive step; nothing here should require it twice.
    """
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        embeddings=embeddings,
        tones=tones,
        speakers=speakers,
        audio_paths=paths,
        pinyin=pinyin,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="dataset CSV")
    parser.add_argument("--out", required=True, help="output .npz")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--split-output", action="store_true",
        help="also write <out>_train.npz and <out>_test.npz, split by speaker",
    )
    parser.add_argument("--test-ratio", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    samples = load_dataset(args.csv)
    print(describe(samples))

    embeddings, tones, speakers, paths, pinyin = extract(samples, args.model)
    output = save_embeddings(args.out, embeddings, tones, speakers, paths, pinyin)
    print(f"saved {embeddings.shape} to {output}")
    print(f"  arrays: embeddings, tones, speakers, audio_paths, pinyin")

    if args.split_output:
        from pronunciation.wav2vec_tone.train_classifier import speaker_split_mask

        stem = output.with_suffix("")
        test_mask, held_out = speaker_split_mask(
            speakers, args.test_ratio, args.seed
        )
        for name, mask in (("train", ~test_mask), ("test", test_mask)):
            written = save_embeddings(
                f"{stem}_{name}.npz",
                embeddings[mask], tones[mask], speakers[mask],
                paths[mask], pinyin[mask],
            )
            print(f"  {name}: {int(mask.sum())} samples -> {written}")
        print(f"  held-out speakers: {', '.join(held_out)}")


if __name__ == "__main__":
    main()
