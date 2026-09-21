"""Self-supervised speech embeddings as an alternative to hand-designed features.

Five rounds of DSP feature engineering moved agreement from kappa 0.020 to
0.087 against a 0.61-0.70 target, with a persistent gap between in-sample AUC
(0.877) and cross-validated AUC (0.592): the hand-designed features can fit the
labels but do not transfer across speakers. wav2vec2 is pretrained on large
amounts of speech to produce representations that are already speaker-invariant,
which is precisely the property the hand-designed features lacked.

Layer choice matters and is not arbitrary. In wav2vec2 the upper layers
specialise toward phonetic and lexical identity, while prosodic information --
pitch movement, which is what a tone *is* -- is carried more strongly in the
lower-to-middle layers. The default here is a middle layer, and the layer is
configurable so it can be treated as a hyperparameter chosen on training data
rather than assumed.

Embeddings are cached to disk because extraction is the expensive step and the
corpus is fixed; a re-run must not repeat it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

# Mandarin-pretrained first: tone is exactly what an English-only model is least
# likely to represent well. Falls back to the widely available English base
# model so a missing repo degrades to a working run rather than a crash.
MODEL_CANDIDATES = (
    "TencentGameMate/chinese-wav2vec2-base",
    "facebook/wav2vec2-base",
)
DEFAULT_LAYER = 6
TARGET_SAMPLE_RATE = 16000


class SyllableEmbedder:
    """Frame-level wav2vec2 embeddings, pooled over syllable spans."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        layer: int = DEFAULT_LAYER,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.layer = layer
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._processor = None
        self._model_name = model_name

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoFeatureExtractor, AutoModel

        names = (self._model_name,) if self._model_name else MODEL_CANDIDATES
        errors = []
        for name in names:
            try:
                self._processor = AutoFeatureExtractor.from_pretrained(name)
                self._model = AutoModel.from_pretrained(name)
                self._model.eval()
                torch.set_grad_enabled(False)
                self._model_name = name
                return
            except Exception as error:  # noqa: BLE001 - reported after all tries
                errors.append(f"{name}: {error}")
        raise RuntimeError("Could not load any speech model:\n" + "\n".join(errors))

    @property
    def model_name(self) -> str:
        self._load()
        return str(self._model_name)

    def _cache_path(self, audio_path: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        key = hashlib.sha1(
            f"{audio_path}|{self._model_name or MODEL_CANDIDATES[0]}|{self.layer}".encode()
        ).hexdigest()[:20]
        return self.cache_dir / f"{key}.npz"

    def frame_embeddings(self, audio_path: str) -> Tuple[np.ndarray, np.ndarray]:
        """Return (frame_times_seconds, embeddings[n_frames, dim])."""
        cache = self._cache_path(audio_path)
        if cache and cache.is_file():
            stored = np.load(cache)
            return stored["times"], stored["vectors"]

        self._load()
        import soundfile as sf
        import torch

        audio, sample_rate = sf.read(audio_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sample_rate != TARGET_SAMPLE_RATE:
            # Linear resample keeps the dependency surface small; wav2vec2 is
            # tolerant of it and the corpus is already close to 16 kHz.
            duration = len(audio) / sample_rate
            target_len = int(duration * TARGET_SAMPLE_RATE)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, target_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        inputs = self._processor(
            audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
        )
        with torch.no_grad():
            output = self._model(**inputs, output_hidden_states=True)
        index = min(self.layer, len(output.hidden_states) - 1)
        vectors = output.hidden_states[index][0].numpy().astype(np.float32)

        # wav2vec2 emits one frame per 20 ms with a 25 ms receptive field.
        stride = 0.020
        times = (np.arange(len(vectors)) * stride + stride / 2).astype(np.float32)
        if cache:
            np.savez_compressed(cache, times=times, vectors=vectors)
        return times, vectors


def pool_span(
    times: np.ndarray,
    vectors: np.ndarray,
    start: float,
    end: float,
    sections: int = 3,
) -> Optional[np.ndarray]:
    """Mean-pool a span, in ``sections`` equal parts concatenated.

    A single mean over the whole syllable would discard time order, which for a
    tone is the entire signal -- a rise and a fall have the same average. Three
    sections keep coarse trajectory while staying far below the dimensionality
    a mean-per-frame representation would impose on ~9,800 training samples.

    Returns None when the span contains no frames, so "no evidence" stays
    distinct from a zero vector.
    """
    mask = (times >= start) & (times <= end)
    if not bool(mask.any()):
        return None
    selected = vectors[mask]
    if len(selected) < sections:
        # Too short to split: repeat the overall mean so the width stays fixed.
        mean = selected.mean(axis=0)
        return np.concatenate([mean] * sections)
    bounds = np.linspace(0, len(selected), sections + 1).astype(int)
    parts = [
        selected[bounds[i] : max(bounds[i + 1], bounds[i] + 1)].mean(axis=0)
        for i in range(sections)
    ]
    return np.concatenate(parts)


def embedding_width(vectors: np.ndarray, sections: int = 3) -> int:
    return int(vectors.shape[1] * sections)
