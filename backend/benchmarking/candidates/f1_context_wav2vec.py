"""CANDIDATE F1 — frozen Wav2Vec2 embedding + linguistic context (+ Praat).

    python -m benchmarking.candidates.f1_context_wav2vec

Research question, per Candidate E2's PARTIAL TRANSFER finding: E2 showed
that giving an interpretable hand-crafted scorer the linguistic context
`tone_context.plan_expected_tones` already computes helps in exactly the T3
categories it targets, but overall discrimination on real OMPAL speech stays
far below a usable bar. Candidate F1 asks whether the SAME context
information, combined with a richer (frozen, clean) speech representation
instead of a hand-crafted contour formula, transfers better.

**F1a** = frozen Wav2Vec2 embedding (Candidate C1's own encoder and
PCA(30)-then-standardize representation) + linguistic context features.
**F1b** = F1a + the existing Praat diagnostic features Candidate B1 already
uses (`benchmarking.candidates.praat_logistic.FEATURE_NAMES`).

**Candidate E2 and Candidate E V1 are frozen and NOT modified or reused as
components here** — Candidate F1 is a new representation, not a fusion of
E1/E2's scores. (E1/E2 ARE re-run, unmodified, on validation in this module
only to populate the six-way comparison table the task's "Report" section
explicitly lists them in — never to construct a Candidate F1 feature.)
`tone_context.py` is imported read-only. `chinese_tones.py` is not imported
by this module at all.

**Encoder provenance**: `FrozenEncoder`/`build_embeddings`
(`benchmarking.candidates.wav2vec_frozen_logistic`) are reused verbatim —
the SAME frozen, clean checkpoint Candidate C1's provenance audit already
cleared (`candidate_c_wav2vec_provenance_audit.md`: "ENCODER CLEAN,
CLASSIFIER CONTAMINATED"). This module never imports anything from
`pronunciation/wav2vec_tone/data/` (the contaminated downstream classifier)
— see `tests/test_f1_context_wav2vec.py`'s AST-based guard.

**Classifier**: `benchmarking.mlp` — one hidden layer, ONE fixed
architecture (16 hidden units, L2=1.0, learning rate 0.05, 3000 iterations),
chosen once before any Candidate F1 number existed and never searched.

**Development**: 5-fold speaker-grouped CV (same `grouped_kfold`, same seed
20260810, as Candidate B1/C1), with the embedding PCA, the Praat-feature
imputer, and the final feature standardizer ALL fit inside each training
fold only — never on the held-out fold. Class imbalance is handled by
`benchmarking.mlp.class_weights`, computed from each training fold's own
label counts only.

**`final_test` is never referenced.** Row loading is delegated to
`benchmarking.candidates.praat_logistic.load_split_rows`, which refuses that
partition without both of its independent gates; this module never passes
`unlock_final_test=True`.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarking import mlp
from benchmarking.baseline_a import evaluate as evaluate_baseline_a
from benchmarking.candidates.e2_ompal_development import run_e1_e2_on_development
from benchmarking.candidates.praat_logistic import (
    FEATURE_NAMES as PRAAT_FEATURE_NAMES,
    Preprocessor as PraatPreprocessor,
    TONES,
    _feature_matrix,
    _labels,
    _select_threshold,
    _usable,
    load_split_rows,
)
from benchmarking.candidates.wav2vec_frozen_logistic import (
    CHECKPOINT_NAME,
    EmbeddingPreprocessor,
    FrozenEncoder,
    _load_cache,
    build_embeddings,
)
from benchmarking.label_audit import _utterance_plan
from benchmarking.ompal_corpus import load_utterances
from benchmarking.splits import grouped_kfold
from benchmarking.stats import binary_agreement, roc_auc
from tone_context import HALF_THIRD, THIRD_CHAIN, THIRD_SANDHI

CORPUS_ROOT = Path("private-data/ompal")

#: "Use Candidate C1's frozen/PCA approach as the starting representation
#: (PCA=30 unless a technical incompatibility exists)." Fixed; only
#: overridden per-fold by the existing `min(PCA_DIM, n_train-1, n_features)`
#: guard Candidate C1's own `fit_frozen_models` already applies (a fold with
#: fewer than 30 usable training rows would make a 30-component PCA
#: ill-posed — the one "technical incompatibility" this module allows for).
PCA_DIM = 30
CV_FOLDS = 5
CV_SEED = 20260810  # same seed as Candidate B1/C1's own dev CV
#: STEP "if nearly tied, choose F1a" — fixed here, before either variant's
#: dev-CV AUC was computed.
NEARLY_TIED_AUC_GAP = 0.02

REPORT_DEV_MD = Path("benchmarking/results/candidate_f1_development.md")
REPORT_VAL_MD = Path("benchmarking/results/candidate_f1_validation.md")
PREDICTIONS_CSV = Path("benchmarking/results/candidate_f1_validation_predictions.csv")
COMPARISON_MD = Path("benchmarking/results/candidate_abcef1_comparison.md")
PROTOCOL_JSON = Path("benchmarking/results/candidate_f1_protocol.json")

B_VAL_PREDICTIONS = Path("benchmarking/results/candidate_b_validation_predictions.csv")
C_VAL_PREDICTIONS = Path("benchmarking/results/candidate_c_validation_predictions.csv")


# ---------------------------------------------------------------------------
# Linguistic-context feature vector (never character/word/speaker/audio ID)
# ---------------------------------------------------------------------------

TONE_VALUES = (1, 2, 3, 4)
ADJACENT_TONE_VALUES = ("none", 1, 2, 3, 4, 5)
#: "realization category: canonical / full_third / half_third /
#: T3_to_T2_sandhi / multiple" -- exactly the task's own bucket list.
#: `multiple` covers both `third_tone_chain` (ambiguous T3-chain grouping)
#: and any other case where more than one surface tone is accepted, since
#: both mean "the model must consider more than one correct answer", the
#: same thing Candidate E2's max-over-alternatives rule already treated as
#: one case.
REALIZATION_BUCKETS = ("canonical", "full_third", "half_third", "T3_to_T2_sandhi", "multiple")

CONTEXT_FEATURE_NAMES = (
    [f"underlying_tone_{t}" for t in TONE_VALUES]
    + [f"accepted_tone_{t}" for t in TONE_VALUES]
    + [f"realization_{b}" for b in REALIZATION_BUCKETS]
    + [f"prev_tone_{t}" for t in ADJACENT_TONE_VALUES]
    + [f"next_tone_{t}" for t in ADJACENT_TONE_VALUES]
    + ["boundary_before", "boundary_after", "utterance_position_normalized"]
)


def realization_bucket(expected: Any) -> str:
    if len(expected.accepted_surface_tones) > 1 or expected.realization == THIRD_CHAIN:
        return "multiple"
    if expected.realization == THIRD_SANDHI:
        return "T3_to_T2_sandhi"
    if expected.realization == "full_third":
        return "full_third"
    if expected.realization == HALF_THIRD:
        return "half_third"
    return "canonical"


def _onehot(value: Any, values: tuple) -> list[float]:
    return [1.0 if value == v else 0.0 for v in values]


def build_context_vector(plan: list[Any], i: int, position_normalized: float | None) -> list[float]:
    expected = plan[i]
    prev_tone = plan[i - 1].underlying_tone if i > 0 else "none"
    next_tone = plan[i + 1].underlying_tone if i < len(plan) - 1 else "none"
    vec: list[float] = []
    vec += _onehot(expected.underlying_tone, TONE_VALUES)
    vec += [1.0 if t in expected.accepted_surface_tones else 0.0 for t in TONE_VALUES]
    vec += _onehot(realization_bucket(expected), REALIZATION_BUCKETS)
    vec += _onehot(prev_tone, ADJACENT_TONE_VALUES)
    vec += _onehot(next_tone, ADJACENT_TONE_VALUES)
    vec += [1.0 if expected.boundary_before else 0.0, 1.0 if expected.boundary_after else 0.0]
    vec += [float(position_normalized) if position_normalized is not None else 0.0]
    return vec


def build_context_features(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Returns (matrix, valid_mask, t3_context_category per row -- 'NA' for
    non-T3 rows or invalid ones)."""
    utterances = {u.utterance_id: u for u in load_utterances(CORPUS_ROOT)}
    plan_cache: dict[str, list | None] = {}
    matrix = np.zeros((len(rows), len(CONTEXT_FEATURE_NAMES)))
    valid = np.zeros(len(rows), dtype=bool)
    t3_category: list[str] = ["NA"] * len(rows)

    for idx, row in enumerate(rows):
        audio_id = row["audio_id"]
        if audio_id not in plan_cache:
            utterance = utterances.get(audio_id)
            if utterance is None:
                plan_cache[audio_id] = None
            else:
                han_chars, _lexical, plan = _utterance_plan(utterance.text)
                plan_cache[audio_id] = plan if plan is not None and len(plan) == len(han_chars) else None
        plan = plan_cache[audio_id]
        if plan is None:
            continue
        i = int(row["syllable_index"])
        if i >= len(plan):
            continue
        expected = plan[i]
        if expected.underlying_tone != int(row["expected_tone"]):
            continue

        position = row.get("utterance_position_normalized")
        position_val = float(position) if position not in (None, "", "NA") else None
        matrix[idx] = build_context_vector(plan, i, position_val)
        valid[idx] = True
        if expected.underlying_tone == 3:
            t3_category[idx] = realization_bucket(expected)

    return matrix, valid, t3_category


# ---------------------------------------------------------------------------
# Simple standardizer (mean/std, fit on train only) for the final combined
# feature vector -- mirrors `praat_logistic.Preprocessor`'s discipline but
# with no imputation step (nothing upstream of this ever produces NaN: the
# embedding/context blocks are always fully populated by construction, and
# the Praat block is already imputed by `PraatPreprocessor` before it gets
# here).
# ---------------------------------------------------------------------------


class Standardizer:
    def __init__(self, means: np.ndarray, scales: np.ndarray) -> None:
        self.means = means
        self.scales = scales

    @classmethod
    def fit(cls, raw: np.ndarray) -> "Standardizer":
        means = raw.mean(axis=0)
        scales = raw.std(axis=0)
        scales = np.where(scales < 1e-9, 1.0, scales)
        return cls(means=means, scales=scales)

    def transform(self, raw: np.ndarray) -> np.ndarray:
        return (raw - self.means) / self.scales


# ---------------------------------------------------------------------------
# One fold's feature construction, shared by CV and by the final freeze fit
# ---------------------------------------------------------------------------


def _build_variant_matrix(
    emb_raw: np.ndarray, ctx_raw: np.ndarray, praat_raw: np.ndarray | None,
    train_mask: np.ndarray,
) -> tuple[EmbeddingPreprocessor, PraatPreprocessor | None, Standardizer, np.ndarray]:
    """Fit every preprocessing stage on `train_mask` rows only; return the
    fitted stages plus the TRAIN rows' final standardized feature matrix."""
    n_components = int(min(PCA_DIM, max(train_mask.sum() - 1, 1), emb_raw.shape[1]))
    emb_pre = EmbeddingPreprocessor.fit(emb_raw[train_mask], n_components)
    parts = [emb_pre.transform(emb_raw[train_mask]), ctx_raw[train_mask]]

    praat_pre = None
    if praat_raw is not None:
        praat_pre = PraatPreprocessor.fit(praat_raw[train_mask])
        parts.append(praat_pre.transform(praat_raw[train_mask]))

    combined_train_raw = np.hstack(parts)
    scaler = Standardizer.fit(combined_train_raw)
    return emb_pre, praat_pre, scaler, scaler.transform(combined_train_raw)


def _apply_variant_matrix(
    emb_pre: EmbeddingPreprocessor, praat_pre: PraatPreprocessor | None, scaler: Standardizer,
    emb_raw: np.ndarray, ctx_raw: np.ndarray, praat_raw: np.ndarray | None, mask: np.ndarray,
) -> np.ndarray:
    parts = [emb_pre.transform(emb_raw[mask]), ctx_raw[mask]]
    if praat_pre is not None:
        parts.append(praat_pre.transform(praat_raw[mask]))
    return scaler.transform(np.hstack(parts))


# ---------------------------------------------------------------------------
# Development: speaker-grouped CV, F1a and F1b
# ---------------------------------------------------------------------------


def prepare_rows(split_name: str, encoder: FrozenEncoder | None = None) -> dict[str, Any]:
    rows_raw = load_split_rows(split_name)
    rows, _excluded = _usable(rows_raw)
    rows = [row for row in rows if row["expected_tone"] in TONES]

    emb_matrix, emb_valid, missing_emb, encoder = build_embeddings(rows, split_name, encoder=encoder)
    ctx_matrix, ctx_valid, t3_category = build_context_features(rows)
    valid = emb_valid & ctx_valid

    rows = [r for r, ok in zip(rows, valid) if ok]
    emb_matrix = emb_matrix[valid]
    ctx_matrix = ctx_matrix[valid]
    t3_category = [c for c, ok in zip(t3_category, valid) if ok]
    praat_matrix = _feature_matrix(rows)
    labels = _labels(rows)
    speaker_ids = np.array([row["speaker_id"] for row in rows])

    return {
        "rows": rows, "emb": emb_matrix, "ctx": ctx_matrix, "praat": praat_matrix,
        "labels": labels, "speaker_ids": speaker_ids, "t3_category": t3_category,
        "missing_embeddings": missing_emb, "encoder": encoder,
    }


def run_grouped_cv(data: dict[str, Any], *, use_praat: bool, k: int = CV_FOLDS, seed: int = CV_SEED) -> dict[str, Any]:
    emb, ctx, labels, speaker_ids = data["emb"], data["ctx"], data["labels"], data["speaker_ids"]
    praat = data["praat"] if use_praat else None

    folds = grouped_kfold(sorted(set(speaker_ids)), k=k, seed=seed)
    oof_prob = np.full(len(labels), np.nan)
    fold_metrics: list[dict[str, Any]] = []

    for fold_index, (train_speakers, held_out_speakers) in enumerate(folds):
        train_mask = np.isin(speaker_ids, train_speakers)
        test_mask = np.isin(speaker_ids, held_out_speakers)
        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue
        if len(set(labels[train_mask])) < 2:
            continue

        emb_pre, praat_pre, scaler, x_train = _build_variant_matrix(emb, ctx, praat, train_mask)
        x_test = _apply_variant_matrix(emb_pre, praat_pre, scaler, emb, ctx, praat, test_mask)

        weight = mlp.class_weights(labels[train_mask])
        model = mlp.fit(x_train, labels[train_mask], sample_weight=weight)
        test_prob = model.predict_proba(x_test)
        oof_prob[test_mask] = test_prob

        fold_auc = roc_auc(list(test_prob), list(labels[test_mask].astype(bool)))
        fold_metrics.append({
            "fold": fold_index, "n_train": int(train_mask.sum()), "n_test": int(test_mask.sum()),
            "n_pca_components": int(min(PCA_DIM, max(train_mask.sum() - 1, 1), emb.shape[1])),
            "auc": fold_auc, "converged": model.converged,
        })

    valid = ~np.isnan(oof_prob)
    pooled_auc = roc_auc(list(oof_prob[valid]), list(labels[valid].astype(bool))) if valid.any() else None
    return {"oof_prob": oof_prob, "labels": labels, "fold_metrics": fold_metrics, "pooled_auc": pooled_auc, "folds": folds}


# ---------------------------------------------------------------------------
# Freeze the selected variant on ALL of development, evaluate once on
# validation
# ---------------------------------------------------------------------------


def fit_frozen(data: dict[str, Any], *, use_praat: bool) -> dict[str, Any]:
    emb, ctx, labels = data["emb"], data["ctx"], data["labels"]
    praat = data["praat"] if use_praat else None
    all_mask = np.ones(len(labels), dtype=bool)
    emb_pre, praat_pre, scaler, x_all = _build_variant_matrix(emb, ctx, praat, all_mask)
    weight = mlp.class_weights(labels)
    model = mlp.fit(x_all, labels, sample_weight=weight)
    return {"emb_pre": emb_pre, "praat_pre": praat_pre, "scaler": scaler, "model": model, "n_train": len(labels)}


def apply_frozen(frozen: dict[str, Any], data: dict[str, Any], *, use_praat: bool) -> np.ndarray:
    emb, ctx = data["emb"], data["ctx"]
    praat = data["praat"] if use_praat else None
    mask = np.ones(len(data["labels"]), dtype=bool)
    x = _apply_variant_matrix(frozen["emb_pre"], frozen["praat_pre"], frozen["scaler"], emb, ctx, praat, mask)
    return frozen["model"].predict_proba(x)


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _auc(scores, labels) -> float | None:
    pairs = [(s, bool(l)) for s, l in zip(scores, labels) if s is not None and not (isinstance(s, float) and np.isnan(s))]
    if not pairs:
        return None
    return roc_auc([p[0] for p in pairs], [p[1] for p in pairs])


def pooled_metrics(probabilities: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, Any]:
    valid = ~np.isnan(probabilities)
    probabilities, labels = probabilities[valid], labels[valid]
    predicted = probabilities >= threshold
    metrics = binary_agreement(list(predicted), list(labels.astype(bool)))
    metrics["auc"] = roc_auc(list(probabilities), list(labels.astype(bool))) if len(probabilities) else None
    metrics["n_scored"] = int(valid.sum())
    return metrics


def by_tone_metrics(rows: list[dict[str, Any]], probabilities: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, dict[str, Any]]:
    result = {}
    for tone in TONES:
        mask = np.array([row["expected_tone"] == tone for row in rows])
        if not mask.any():
            result[tone] = {"n": 0}
            continue
        result[tone] = pooled_metrics(probabilities[mask], labels[mask], threshold)
    return result


def by_t3_context_metrics(
    rows: list[dict[str, Any]], t3_category: list[str], probabilities: np.ndarray, labels: np.ndarray, threshold: float
) -> dict[str, dict[str, Any]]:
    result = {}
    for category in ("full_third", "half_third", "T3_to_T2_sandhi", "multiple"):
        mask = np.array([c == category for c in t3_category])
        if not mask.any():
            result[category] = {"n": 0}
            continue
        result[category] = pooled_metrics(probabilities[mask], labels[mask], threshold)
    return result


# ---------------------------------------------------------------------------
# Candidate E1 / E2 on validation (unmodified, re-run once for the
# six-way comparison table only -- see module docstring)
# ---------------------------------------------------------------------------


def evaluate_e1_e2_on_rows(e_rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [r for r in e_rows if r["human_majority_tone_correct"] is not None]
    e1_scores = [r["e1_score"] for r in labeled]
    e1_preds = [r["e1_pass"] for r in labeled]
    e2_scores = [r["e2_score"] for r in labeled]
    human = [r["human_majority_tone_correct"] for r in labeled]

    e1_pairs = [(s, p, h) for s, p, h in zip(e1_scores, e1_preds, human) if s is not None]
    e2_pairs = [(s, h) for s, h in zip(e2_scores, human) if s is not None]

    e1_metrics: dict[str, Any] = {"n": len(e1_pairs)}
    if e1_pairs:
        e1_metrics.update(binary_agreement([bool(p) for _, p, _ in e1_pairs], [bool(h) for _, _, h in e1_pairs]))
        e1_metrics["auc"] = roc_auc([s for s, _, _ in e1_pairs], [bool(h) for _, _, h in e1_pairs])
    e2_metrics: dict[str, Any] = {
        "n": len(e2_pairs),
        "auc": roc_auc([s for s, _ in e2_pairs], [bool(h) for _, h in e2_pairs]) if e2_pairs else None,
    }
    return {"e1": e1_metrics, "e2": e2_metrics, "n_labeled": len(labeled)}


# ---------------------------------------------------------------------------
# Predictions CSV
# ---------------------------------------------------------------------------

PREDICTIONS_FIELDS = [
    "audio_id", "speaker_id", "word", "expected_tone", "t3_context_category",
    "human_majority_tone_correct", "candidate_f1_probability", "candidate_f1_threshold",
    "candidate_f1_predicted_correct", "baseline_a_system_tone_correct", "baseline_a_system_character_score",
]


def write_predictions_csv(
    rows: list[dict[str, Any]], t3_category: list[str], probabilities: np.ndarray, threshold: float, path: Path = PREDICTIONS_CSV
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTIONS_FIELDS)
        writer.writeheader()
        for row, category, prob in zip(rows, t3_category, probabilities):
            writer.writerow({
                "audio_id": row["audio_id"],
                "speaker_id": row["speaker_id"],
                "word": row["word"],
                "expected_tone": row["expected_tone"],
                "t3_context_category": category,
                "human_majority_tone_correct": row["human_majority_tone_correct"],
                "candidate_f1_probability": round(float(prob), 4) if not np.isnan(prob) else "NA",
                "candidate_f1_threshold": threshold,
                "candidate_f1_predicted_correct": int(prob >= threshold) if not np.isnan(prob) else "NA",
                "baseline_a_system_tone_correct": row["system_tone_correct"],
                "baseline_a_system_character_score": row["system_character_score"],
            })
    return len(rows)


# ---------------------------------------------------------------------------
# Protocol freeze
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encoder_identity(encoder: FrozenEncoder | None) -> tuple[str, str | None]:
    """`build_embeddings` only constructs an encoder object on a cache miss
    (see its own docstring) -- with the development/validation caches
    already fully warm, `encoder` is routinely `None` here. Falls back to
    the checkpoint identity recorded in the cache metadata the last time it
    WAS constructed, the same fallback `wav2vec_frozen_logistic.run()`
    itself already uses for exactly this reason."""
    if encoder is not None:
        return encoder.checkpoint, encoder.checkpoint_hash
    _, dev_meta = _load_cache("development")
    return dev_meta.get("checkpoint", CHECKPOINT_NAME), dev_meta.get("checkpoint_sha256")


def write_protocol(
    variant: str, dev_cv_auc_f1a: float | None, dev_cv_auc_f1b: float | None,
    threshold: float, encoder: FrozenEncoder | None, path: Path = PROTOCOL_JSON,
) -> None:
    checkpoint, checkpoint_hash = _encoder_identity(encoder)
    protocol = {
        "candidate": "F1",
        "selected_variant": variant,
        "selection_rule": (
            f"F1a vs F1b compared on development pooled out-of-fold AUC; "
            f"if |auc_a - auc_b| <= {NEARLY_TIED_AUC_GAP}, F1a is chosen. "
            f"F1a dev CV AUC={dev_cv_auc_f1a}, F1b dev CV AUC={dev_cv_auc_f1b}."
        ),
        "encoder": {
            "checkpoint": checkpoint,
            "checkpoint_sha256": checkpoint_hash,
            "pooling": "mean",
            "note": "reused verbatim from Candidate C1's cleared, frozen encoder wrapper",
        },
        "pca_dim": PCA_DIM,
        "context_feature_names": CONTEXT_FEATURE_NAMES,
        "praat_feature_names": list(PRAAT_FEATURE_NAMES) if variant == "F1b" else None,
        "classifier": {
            "module": "benchmarking/mlp.py",
            "sha256": _file_hash(Path("benchmarking/mlp.py")),
            "hidden_units": mlp.DEFAULT_HIDDEN_UNITS,
            "l2": mlp.DEFAULT_L2,
            "learning_rate": mlp.DEFAULT_LEARNING_RATE,
            "max_iter": mlp.DEFAULT_MAX_ITER,
            "seed": mlp.DEFAULT_SEED,
            "note": "one fixed architecture, not searched",
        },
        "cv": {"folds": CV_FOLDS, "seed": CV_SEED},
        "threshold": threshold,
        "threshold_selection": "grid point maximizing balanced accuracy on development out-of-fold predictions (praat_logistic._select_threshold, reused unmodified)",
        "module": "benchmarking/candidates/f1_context_wav2vec.py",
        "module_sha256": _file_hash(Path("benchmarking/candidates/f1_context_wav2vec.py")),
        "excluded_from_features": [
            "character/word identity", "speaker identity (grouping only)", "audio ID",
            "human ratings other than the target label",
        ],
        "ompal_status": "development and validation only -- final_test not referenced anywhere in this module",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    print("Preparing development rows (embeddings + context features)...")
    dev_data = prepare_rows("development")
    print(f"  {len(dev_data['rows'])} usable development rows")

    print("STEP: F1a development CV (embedding + context)...")
    cv_a = run_grouped_cv(dev_data, use_praat=False)
    print(f"  F1a pooled dev CV AUC = {cv_a['pooled_auc']}")
    print("STEP: F1b development CV (embedding + context + Praat)...")
    cv_b = run_grouped_cv(dev_data, use_praat=True)
    print(f"  F1b pooled dev CV AUC = {cv_b['pooled_auc']}")

    auc_a, auc_b = cv_a["pooled_auc"] or 0.0, cv_b["pooled_auc"] or 0.0
    if abs(auc_a - auc_b) <= NEARLY_TIED_AUC_GAP:
        variant, selected_cv, use_praat = "F1a", cv_a, False
    elif auc_b > auc_a:
        variant, selected_cv, use_praat = "F1b", cv_b, True
    else:
        variant, selected_cv, use_praat = "F1a", cv_a, False
    print(f"Selected variant: {variant}")

    threshold = _select_threshold(selected_cv["oof_prob"], selected_cv["labels"])
    dev_pooled = pooled_metrics(selected_cv["oof_prob"], selected_cv["labels"], threshold)

    print("Freezing selected variant on all of development...")
    frozen = fit_frozen(dev_data, use_praat=use_praat)

    write_protocol(variant, cv_a["pooled_auc"], cv_b["pooled_auc"], threshold, dev_data["encoder"])

    print("Preparing validation rows...")
    val_data = prepare_rows("validation", encoder=dev_data["encoder"])
    print(f"  {len(val_data['rows'])} usable validation rows")
    val_prob = apply_frozen(frozen, val_data, use_praat=use_praat)

    val_pooled = pooled_metrics(val_prob, val_data["labels"], threshold)
    val_by_tone = by_tone_metrics(val_data["rows"], val_prob, val_data["labels"], threshold)
    val_by_t3 = by_t3_context_metrics(val_data["rows"], val_data["t3_category"], val_prob, val_data["labels"], threshold)

    n_predictions = write_predictions_csv(val_data["rows"], val_data["t3_category"], val_prob, threshold)

    print("Evaluating Candidate E V1 / Candidate E2 on validation (unmodified, for the comparison table only)...")
    val_rows_all, _ = _usable(load_split_rows("validation"))
    e_rows, e_diag = run_e1_e2_on_development(val_rows_all)
    e1e2 = evaluate_e1_e2_on_rows(e_rows)

    baseline_val_rows = val_rows_all
    baseline_a = evaluate_baseline_a(baseline_val_rows)

    return {
        "dev_n": len(dev_data["rows"]),
        "val_n": len(val_data["rows"]),
        "variant": variant,
        "cv_a": cv_a, "cv_b": cv_b,
        "threshold": threshold,
        "dev_pooled": dev_pooled,
        "val_pooled": val_pooled,
        "val_by_tone": val_by_tone,
        "val_by_t3": val_by_t3,
        "n_predictions_written": n_predictions,
        "baseline_a": baseline_a,
        "e1e2": e1e2,
        "e_diag": e_diag,
        "b_val_predictions_path": B_VAL_PREDICTIONS,
        "c_val_predictions_path": C_VAL_PREDICTIONS,
    }


if __name__ == "__main__":
    from benchmarking.candidates import report_f1_context_wav2vec as report

    result = run()
    verdict = report.write_reports(result)
    print(f"Predictions written to {PREDICTIONS_CSV} ({result['n_predictions_written']} rows)")
    print(f"Protocol written to {PROTOCOL_JSON}")
    print(f"Reports written to {REPORT_DEV_MD}, {REPORT_VAL_MD}, {COMPARISON_MD}")
    print(f"Verdict: {verdict}")
