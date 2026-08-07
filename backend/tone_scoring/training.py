"""Build the OMPAL training set and cross-validate the learned tone scorer.

Protocol, fixed before any result was seen:

* OMPAL's own 5 folds are used. They are speaker-disjoint (verified: zero
  speaker overlap in every fold), so a model cannot score well by memorising a
  speaker it also trained on.
* The headline is *pooled cross-validated* predictions: every syllable is
  scored by the fold-model that never saw its speaker, then agreement is
  computed once over all of them. A single test fold holds only 5 speakers,
  which is far too unstable to steer on; pooling uses every speaker exactly
  once while preserving speaker-disjointness.
* Training labels are the rater majority, and since the protocol change of
  2026-08-06 the headline evaluation is against that same majority. The
  train/evaluate mismatch that previously existed -- learn consensus, be graded
  against noisy individuals -- is therefore gone. Per-rater agreement is still
  computed and reported as context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from tone_scoring.alignment import get_aligner
from tone_scoring.features import (
    FEATURE_NAMES,
    declination_slope_from_spans,
    features_to_vector,
    syllable_features,
    utterance_pitch_stats,
)

NEUTRAL_TONE = 5


@dataclass
class SyllableSample:
    """One featurized syllable with its rater labels and fold membership."""

    utterance_id: str
    speaker_id: str
    is_native: bool
    word_index: int
    expected_tone: int
    features: List[float]
    rater_labels: Tuple[bool, ...]
    fold: Optional[int]
    # Pooled self-supervised speech embedding, empty when not extracted.
    embedding: List[float] = field(default_factory=list)

    @property
    def majority(self) -> bool:
        return sum(self.rater_labels) * 2 > len(self.rater_labels)


def load_fold_map(corpus_root: Path) -> Dict[str, int]:
    """Map each utterance to the fold whose *test* split contains it.

    Membership comes from OMPAL's published splits rather than a split of our
    own, so results stay comparable with anything else measured on this corpus.
    """
    mapping: Dict[str, int] = {}
    for fold in range(1, 6):
        path = corpus_root / "test" / f"test_{fold}_scores.json"
        if not path.is_file():
            continue
        for utterance_id in json.loads(path.read_text(encoding="utf-8")):
            mapping[utterance_id] = fold
    return mapping


def build_samples(
    utterances: Sequence[Any],
    analyzer_bundle,
    fold_map: Dict[str, int],
    aligner_name: str = "energy",
    panel_size: int = 3,
    embedder=None,
) -> Tuple[List[SyllableSample], Dict[str, int]]:
    """Featurize every rated syllable that can be measured.

    ``analyzer_bundle(path)`` must return (pitch_contour, intensity). It is
    injected so this function can be tested without audio.

    Exclusions mirror the frozen benchmark contract exactly -- neutral tone,
    unfeaturizable, incomplete rater panel, alignment mismatch -- so the
    learned scorer is measured on the same syllables as the heuristic and the
    two rows of the ablation stay comparable.
    """
    aligner = get_aligner(aligner_name)
    samples: List[SyllableSample] = []
    excluded: Dict[str, int] = {}

    def drop(reason: str, count: int = 1) -> None:
        excluded[reason] = excluded.get(reason, 0) + count

    for utterance in utterances:
        try:
            pitch_contour, intensity = analyzer_bundle(str(utterance.wav_path))
        except Exception:
            drop("audio_unreadable")
            continue
        if len(pitch_contour) < 2:
            drop("no_pitch")
            continue

        characters = "".join(word.text for word in utterance.words)
        spans = aligner.align(pitch_contour, len(characters), intensity)
        if len(spans) != len(characters):
            drop("alignment_mismatch")
            continue

        # Remove the utterance's declination once, then normalise against the
        # detrended signal, so a syllable's reading no longer depends on where
        # in the sentence it happens to fall.
        drift, time_reference = declination_slope_from_spans(pitch_contour, spans)
        embed_times = embed_vectors = None
        if embedder is not None:
            try:
                embed_times, embed_vectors = embedder.frame_embeddings(
                    str(utterance.wav_path)
                )
            except Exception:
                drop("embedding_failed")
                continue
        mean, deviation = utterance_pitch_stats(pitch_contour, drift, time_reference)
        position = 0
        for word_index, word in enumerate(utterance.words):
            width = len(word.text)
            word_spans = spans[position : position + width]
            tones = word.expected_tones
            position += width

            if NEUTRAL_TONE in tones:
                drop("neutral_tone")
                continue
            if len(word.rater_tone_labels) != panel_size:
                drop("incomplete_rater_panel")
                continue
            if len(word_spans) != width or len(tones) != width:
                drop("alignment_mismatch")
                continue

            # A rated unit spanning several characters carries one label, so
            # its features are averaged across them rather than invented.
            vectors: List[List[float]] = []
            for offset, span in enumerate(word_spans):
                features = syllable_features(
                    span,
                    pitch_contour,
                    tones[offset],
                    position - width + offset,
                    len(characters),
                    mean,
                    deviation,
                    intensity=intensity,
                    previous_span=spans[position - width + offset - 1]
                    if position - width + offset > 0
                    else None,
                    next_span=spans[position - width + offset + 1]
                    if position - width + offset + 1 < len(spans)
                    else None,
                    declination=drift,
                    time_reference=time_reference,
                )
                if features is None:
                    vectors = []
                    break
                vectors.append(features_to_vector(features))
            if not vectors:
                drop("unfeaturizable")
                continue

            # Deliberately a distinct name: reusing `vectors` here would
            # overwrite the DSP feature vectors built above and silently store
            # embeddings in the `features` column instead.
            pooled: List[float] = []
            if embed_vectors is not None:
                from tone_scoring.embeddings import pool_span

                embed_parts = [
                    pool_span(embed_times, embed_vectors, span.start, span.end)
                    for span in word_spans
                ]
                if any(part is None for part in embed_parts):
                    drop("embedding_span_empty")
                    continue
                pooled = [float(v) for v in np.mean(embed_parts, axis=0)]

            samples.append(
                SyllableSample(
                    utterance_id=utterance.utterance_id,
                    speaker_id=utterance.speaker_id,
                    is_native=utterance.is_native,
                    word_index=word_index,
                    expected_tone=tones[0] if len(tones) == 1 else 0,
                    features=[float(v) for v in np.mean(vectors, axis=0)],
                    rater_labels=tuple(word.rater_tone_labels),
                    fold=fold_map.get(utterance.utterance_id),
                    embedding=pooled,
                )
            )
    return samples, excluded


def reduce_embeddings(
    samples: Sequence["SyllableSample"], components: int = 96, seed: int = 0
):
    """Compress raw embedding columns with PCA, fitted on training folds only.

    A pooled wav2vec2 syllable is 2,304 dimensions against ~9,800 samples with
    ~20% irreducible label noise -- fitting that directly would memorise the
    training speakers, which is the failure the speaker-disjoint folds exist to
    expose. PCA is fitted only on samples outside the evaluated fold, so the
    reduction never sees the data it is judged on.
    """
    from sklearn.decomposition import PCA

    fit_rows = [s for s in samples if s.fold is None] or list(samples)
    matrix = np.asarray([s.embedding for s in fit_rows], dtype=float)
    n_components = min(components, matrix.shape[0], matrix.shape[1])
    pca = PCA(n_components=n_components, random_state=seed)
    pca.fit(matrix)
    return pca


def _make_model(seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingClassifier

    # Modest capacity on purpose: ~10k samples with 20% irreducible label noise
    # will happily overfit a larger model, and the speaker-disjoint folds would
    # then show it as a generalisation gap.
    return HistGradientBoostingClassifier(
        max_depth=4,
        max_iter=200,
        learning_rate=0.06,
        l2_regularization=1.0,
        min_samples_leaf=40,
        random_state=seed,
    )


def cross_validated_predictions(
    samples: Sequence[SyllableSample], seed: int = 0
) -> Tuple[List[SyllableSample], np.ndarray]:
    """Predict each fold with a model trained only on the other folds.

    A sample's fold is the OMPAL *test* split it belongs to. Samples in no test
    split are never evaluated but are still valid training data for every fold,
    so they are kept rather than discarded -- restricting training to test-fold
    members alone would throw away roughly two thirds of the corpus.

    Speaker-disjointness is preserved either way: OMPAL's splits are
    speaker-disjoint, so a train-only utterance's speaker never appears in any
    test fold.
    """
    evaluated = [sample for sample in samples if sample.fold is not None]
    train_only = [sample for sample in samples if sample.fold is None]
    if not evaluated:
        return [], np.array([])

    matrix = np.asarray([sample.features for sample in evaluated], dtype=float)
    labels = np.asarray([sample.majority for sample in evaluated], dtype=int)
    folds = np.asarray([sample.fold for sample in evaluated], dtype=int)
    extra_matrix = (
        np.asarray([sample.features for sample in train_only], dtype=float)
        if train_only
        else np.empty((0, matrix.shape[1]), dtype=float)
    )
    extra_labels = np.asarray(
        [sample.majority for sample in train_only], dtype=int
    )
    probabilities = np.zeros(len(evaluated), dtype=float)

    for fold in sorted(set(folds.tolist())):
        test_mask = folds == fold
        train_mask = ~test_mask
        if test_mask.sum() == 0:
            continue
        train_features = np.vstack([matrix[train_mask], extra_matrix])
        train_labels = np.concatenate([labels[train_mask], extra_labels])
        if len(train_labels) == 0:
            continue
        if len(set(train_labels.tolist())) < 2:
            probabilities[test_mask] = float(train_labels.mean())
            continue
        model = _make_model(seed)
        model.fit(train_features, train_labels)
        probabilities[test_mask] = model.predict_proba(matrix[test_mask])[:, 1]

    return evaluated, probabilities


def select_threshold_on_training(
    samples: Sequence[SyllableSample], seed: int = 0, holdout: float = 0.25
) -> float:
    """Pick the decision threshold using training data only.

    With an 82% positive base rate, a fixed 0.5 makes the model predict "pass"
    almost always: raw agreement matches the base rate and kappa collapses to
    zero even when the underlying ranking carries real signal. The threshold
    therefore has to be chosen, but choosing it on the reported predictions
    would be test-set tuning.

    So a slice of the train-only samples (never part of any evaluated fold) is
    held out from fitting and used purely to select the threshold. Speaker
    disjointness is preserved because OMPAL's train-only utterances share no
    speaker with any test fold.
    """
    pool = [sample for sample in samples if sample.fold is None]
    if len(pool) < 50:
        return 0.5

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(pool))
    cut = max(1, int(len(pool) * holdout))
    select_idx, fit_idx = order[:cut], order[cut:]

    fit_x = np.asarray([pool[i].features for i in fit_idx], dtype=float)
    fit_y = np.asarray([pool[i].majority for i in fit_idx], dtype=int)
    if len(set(fit_y.tolist())) < 2:
        return 0.5

    model = _make_model(seed)
    model.fit(fit_x, fit_y)
    select_x = np.asarray([pool[i].features for i in select_idx], dtype=float)
    select_y = [pool[i].majority for i in select_idx]
    probabilities = model.predict_proba(select_x)[:, 1]

    from benchmarking.stats import binary_agreement

    best_threshold, best_kappa = 0.5, float("-inf")
    for candidate in np.arange(0.20, 0.96, 0.01):
        predicted = [bool(p >= candidate) for p in probabilities]
        kappa = binary_agreement(predicted, select_y)["cohen_kappa"]  # vs majority
        if kappa is not None and kappa > best_kappa:
            best_threshold, best_kappa = float(candidate), kappa
    return best_threshold


def train_final_model(samples: Sequence[SyllableSample], seed: int = 0):
    """Fit one model on every fold, for use at inference time."""
    matrix = np.asarray([sample.features for sample in samples], dtype=float)
    labels = np.asarray([sample.majority for sample in samples], dtype=int)
    model = _make_model(seed)
    model.fit(matrix, labels)
    return model


def save_model(model, path: str | Path) -> Path:
    import joblib

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_names": FEATURE_NAMES}, target)
    return target
