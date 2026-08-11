"""CANDIDATE F2 — supervised PARTIAL fine-tuning of Wav2Vec2.

    python -m benchmarking.candidates.wav2vec_partial_finetune

Research question: does adapting the speech encoder to expert-rated L2
Mandarin tone correctness improve discrimination beyond the frozen
representation Candidate F1 used? Candidate F1's context-conditioned
classifier on a FROZEN encoder reached validation AUC 0.595, short of the
pre-specified 0.65/T2/T3/T4>=0.60 bar. Candidate F2 keeps everything else
about F1 the same -- the same clean checkpoint, the same linguistic-context
feature definitions (`f1_context_wav2vec.build_context_features`, imported
read-only), the same small classifier head width -- and changes exactly one
thing: the TOP `NUM_UNFROZEN_LAYERS` of the encoder's 12 Transformer layers
are supervised-fine-tuned instead of frozen. This isolates the ablation the
task asks for (STEP 8): any AUC gain over Candidate F1 must come from
representation adaptation, not from a different context definition or a
different classifier architecture.

**Base checkpoint**: `TencentGameMate/chinese-wav2vec2-base` -- the SAME
checkpoint Candidate C1's provenance audit cleared
(`candidate_c_wav2vec_provenance_audit.md`: "ENCODER CLEAN, CLASSIFIER
CONTAMINATED" -- the encoder itself has never been fine-tuned on anything;
only a downstream classifier built on its frozen embeddings was
OMPAL-contaminated). This module loads the checkpoint itself via
`transformers.AutoModel.from_pretrained`, the same call
`pronunciation.wav2vec_tone.extract_embeddings.FrozenWav2Vec2` makes -- it
does NOT import `FrozenWav2Vec2` (which asserts zero trainable parameters
and would refuse to run) and does NOT import anything from
`pronunciation/wav2vec_tone/data/` (the contaminated downstream classifier
or its weights/calibration/thresholds) -- see
`tests/test_wav2vec_partial_finetune.py`'s AST-based guard.

**No existing Wav2Vec2 FINE-TUNING convention exists anywhere in this
repository** (checked per STEP 6, before choosing any optimization value --
`pronunciation/wav2vec_tone/` contains classifier-on-frozen-embeddings
training code, e.g. `train_classifier.py`/`develop_models.py`, but no
gradient-based encoder adaptation; the provenance audit's own §2 already
established the encoder "has never been fine-tuned on anything"). The
training recipe below is therefore standard, well-established
speech-fine-tuning practice (small encoder LR, larger head LR, weight
decay, gradient clipping), fixed once as ONE configuration before any
Candidate F2 result existed, never searched.

**Efficiency note (not a scoring shortcut)**: layers 0-`NUM_FROZEN_LAYERS-1`
(the convolutional feature extractor, the feature projection, the
positional-embedding convolution, and the lower Transformer layers) never
change during training, so their output for a given audio span is the same
every epoch and every fold. This module computes that frozen intermediate
representation ONCE per row (`compute_frozen_hidden_states`, a single
`output_hidden_states=True` forward pass through the untouched pretrained
model) and caches it to disk; every subsequent training step re-uses the
cached tensor and only runs the top, trainable layers. This changes nothing
about WHAT is fine-tuned or evaluated -- it is mathematically identical to
recomputing the frozen layers from scratch every step, just far cheaper on
CPU-only hardware (confirmed via `torch.cuda.is_available() == False` in
this environment).

**`final_test` is never referenced.** Row loading is delegated to
`benchmarking.candidates.praat_logistic.load_split_rows`. Validation is
loaded exactly once, after `write_protocol` has already written the frozen
protocol to disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from benchmarking.candidates.f1_context_wav2vec import (
    CONTEXT_FEATURE_NAMES,
    build_context_features,
)
from benchmarking.candidates.praat_logistic import (
    TONES,
    _labels,
    _select_threshold,
    _usable,
    load_split_rows,
)
from benchmarking.mlp import class_weights as np_class_weights
from benchmarking.splits import grouped_kfold
from benchmarking.stats import binary_agreement, roc_auc
from pronunciation.wav2vec_tone.extract_embeddings import DEFAULT_MODEL, load_audio_16k_mono

CORPUS_ROOT = Path("private-data/ompal")
CACHE_DIR = Path("private-data/wav2vec_partial_finetune_cache")

CHECKPOINT_NAME = DEFAULT_MODEL  # "TencentGameMate/chinese-wav2vec2-base" -- same as Candidate C1/F1
SAMPLE_RATE = 16000

#: STEP 2's primary design: 12 Transformer layers -> unfreeze the top 4.
NUM_UNFROZEN_LAYERS = 4

#: STEP 6 training recipe -- one fixed configuration, chosen before any
#: Candidate F2 result existed (see module docstring for why there was no
#: existing convention to follow instead). Small encoder LR (standard for
#: fine-tuning a pretrained speech encoder -- large enough to adapt, small
#: enough not to destroy pretrained structure in a few thousand steps),
#: larger head LR (randomly initialized, needs to move further, faster).
ENCODER_LEARNING_RATE = 2e-5
HEAD_LEARNING_RATE = 1e-3
WEIGHT_DECAY = 0.01
GRAD_CLIP_NORM = 1.0
GRAD_ACCUM_STEPS = 16  # mini-batch-like gradient averaging without padding/masking
MAX_EPOCHS = 4
EARLY_STOP_PATIENCE = 1
SEED = 20260810  # same seed used project-wide (top-level speaker split, CV, mlp.py)
#: Fraction of each training-speaker pool held out (speaker-disjoint) purely
#: for early stopping -- implemented by reusing `grouped_kfold` with k=5 and
#: taking fold 0's held-out group, rather than inventing a new random split.
EARLY_STOP_HOLDOUT_K = 5

CV_FOLDS = 5
CV_SEED = 20260810  # same seed as Candidate B1/C1/F1's own dev CV

HEAD_HIDDEN_UNITS = 16  # reuses Candidate F1's classifier width (benchmarking.mlp.DEFAULT_HIDDEN_UNITS)

DEV_DEV_MD = Path("benchmarking/results/candidate_f2_development.md")
VAL_MD = Path("benchmarking/results/candidate_f2_validation.md")
PREDICTIONS_CSV = Path("benchmarking/results/candidate_f2_validation_predictions.csv")
PROTOCOL_JSON = Path("benchmarking/results/candidate_f2_protocol.json")
COMPARISON_MD = Path("benchmarking/results/candidate_abcef1f2_comparison.md")
CHECKPOINT_PATH = Path("private-data/candidate_f2_finetuned_top_layers.pt")


# ---------------------------------------------------------------------------
# STEP 1 -- load the clean base checkpoint, record architecture
# ---------------------------------------------------------------------------


def _hash_state_dict(state_dict: dict[str, torch.Tensor]) -> str:
    hasher = hashlib.sha256()
    for name, param in sorted(state_dict.items()):
        hasher.update(name.encode("utf-8"))
        hasher.update(param.detach().cpu().numpy().tobytes())
    return hasher.hexdigest()


def load_base_model() -> dict[str, Any]:
    """STEP 1: the SAME clean checkpoint Candidate C1/F1 used, loaded fresh
    via `transformers.AutoModel.from_pretrained` -- no old classifier, no old
    calibration, no old weights are loaded."""
    from transformers import AutoFeatureExtractor, AutoModel

    model = AutoModel.from_pretrained(CHECKPOINT_NAME)
    processor = AutoFeatureExtractor.from_pretrained(CHECKPOINT_NAME)
    model.eval()

    base_checkpoint_hash = _hash_state_dict(model.state_dict())
    num_layers = model.config.num_hidden_layers
    hidden_size = model.config.hidden_size

    if num_layers == 12:
        n_unfrozen = NUM_UNFROZEN_LAYERS
    else:
        n_unfrozen = max(1, round(num_layers / 3))
    n_frozen = num_layers - n_unfrozen

    return {
        "model": model, "processor": processor,
        "checkpoint": CHECKPOINT_NAME, "checkpoint_sha256": base_checkpoint_hash,
        "num_hidden_layers": num_layers, "hidden_size": hidden_size,
        "n_unfrozen_layers": n_unfrozen, "n_frozen_layers": n_frozen,
    }


def apply_partial_freeze(base: dict[str, Any]) -> dict[str, Any]:
    """STEP 2: freeze the conv feature extractor, the feature projection,
    the positional-embedding convolution, its layer norm, and the LOWER
    Transformer layers; leave only the TOP `n_unfrozen_layers` trainable."""
    model = base["model"]
    n_frozen = base["n_frozen_layers"]

    for parameter in model.parameters():
        parameter.requires_grad = False

    top_layers = model.encoder.layers[n_frozen:]
    for layer in top_layers:
        for parameter in layer.parameters():
            parameter.requires_grad = True

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())

    # The exact set of trainable module paths, for the frozen protocol.
    trainable_modules = [
        f"encoder.layers.{n_frozen + i}" for i in range(len(top_layers))
    ]

    # Snapshot of the pretrained top-layer weights, before any training --
    # reloaded at the start of every CV fold (and before the final freeze
    # fit) so folds never leak fine-tuning from one another.
    pretrained_top_state = {
        name: tensor.clone() for name, tensor in
        zip((n for n, _ in top_layers.named_parameters()), (p for _, p in top_layers.named_parameters()))
    }

    return {
        **base, "top_layers": top_layers, "trainable_modules": trainable_modules,
        "trainable_parameters": trainable, "total_parameters": total,
        "pretrained_top_state": pretrained_top_state,
    }


def reset_top_layers(top_layers: nn.ModuleList, pretrained_top_state: dict[str, torch.Tensor]) -> None:
    """Reload the ORIGINAL pretrained weights into the trainable top layers
    -- called before every fold and before the final freeze fit, so one
    fold's fine-tuning never contaminates the next."""
    with torch.no_grad():
        for name, param in top_layers.named_parameters():
            param.copy_(pretrained_top_state[name])


# ---------------------------------------------------------------------------
# Efficiency layer: cache the frozen (never-changing) intermediate
# representation once per row, per split.
# ---------------------------------------------------------------------------


def _row_key(row: dict[str, Any]) -> str:
    return f"{row['audio_id']}::{row.get('syllable_index', '0')}"


def _resolve_audio_path(raw_path: str) -> Path:
    return Path(*raw_path.replace("\\", "/").split("/"))


def compute_frozen_hidden_state(
    model, processor, audio_path: str, start_time: float, end_time: float, n_frozen_layers: int
) -> np.ndarray | None:
    waveform = load_audio_16k_mono(_resolve_audio_path(audio_path))
    start_sample = max(0, int(round(start_time * SAMPLE_RATE)))
    end_sample = min(len(waveform), int(round(end_time * SAMPLE_RATE)))
    segment = waveform[start_sample:end_sample]
    if len(segment) < 400:  # same floor Candidate C1's FrozenEncoder uses
        return None
    inputs = processor(segment, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs, output_hidden_states=True)
    # hidden_states[n_frozen_layers] is the INPUT to the first trainable
    # layer -- i.e. exactly the output of every frozen stage (conv feature
    # extractor, feature projection, positional-embedding conv + layer
    # norm, and the lower Transformer layers), computed with the untouched
    # pretrained weights.
    return output.hidden_states[n_frozen_layers][0].numpy().astype(np.float32)


def build_frozen_activation_cache(
    rows: list[dict[str, Any]], split_name: str, model, processor, n_frozen_layers: int,
) -> tuple[dict[str, np.ndarray], int]:
    """Returns ({row_key: (T, hidden) array}, n_missing). Cached to disk,
    keyed by (audio_id, syllable_index) exactly like Candidate C1's own
    embedding cache."""
    cache_path = CACHE_DIR / f"{split_name}_frozen_hidden_l{n_frozen_layers}.npz"
    cached: dict[str, np.ndarray] = {}
    if cache_path.exists():
        stored = np.load(cache_path, allow_pickle=True)
        for key, arr in zip(stored["keys"], stored["activations"]):
            cached[str(key)] = arr

    missing = 0
    dirty = False
    for i, row in enumerate(rows):
        key = _row_key(row)
        if key in cached:
            continue
        hidden = compute_frozen_hidden_state(
            model, processor, row["audio_path"],
            float(row["syllable_start_time"]), float(row["syllable_end_time"]),
            n_frozen_layers,
        )
        if hidden is None:
            missing += 1
            continue
        cached[key] = hidden
        dirty = True
        if (i + 1) % 500 == 0:
            print(f"  [{split_name}] frozen-activation cache {i + 1}/{len(rows)} ({missing} unusable so far)")

    if dirty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        keys = sorted(cached)
        activations = np.empty(len(keys), dtype=object)
        for idx, k in enumerate(keys):
            activations[idx] = cached[k]
        np.savez_compressed(cache_path, keys=np.array(keys, dtype=object), activations=activations)

    return cached, missing


# ---------------------------------------------------------------------------
# STEP 4 -- small context-conditioned head, reusing Candidate F1's head width
# ---------------------------------------------------------------------------


#: A pre-registration-stage fix, not a tuning choice: an early diagnostic
#: run (before any Candidate F2 result was accepted -- see
#: `candidate_f2_development.md`'s note) found the plain-ReLU version of
#: this head collapsing to 100% dead units (every hidden activation exactly
#: zero for every input) within the first few class-weighted gradient
#: steps, producing a constant output and AUC exactly 0.5 no matter how
#: long training ran. LeakyReLU never fully zeroes its gradient, which is
#: the standard, well-documented remedy for this exact failure mode -- not
#: a value searched for better numbers. `pooled_norm` (LayerNorm on the raw
#: mean-pooled Wav2Vec2 hidden state) is the same kind of fix: the pooled
#: representation was going into the head with no normalization at all
#: (unlike Candidate F1's `Standardizer`, fit on its combined feature
#: vector), which is standard cause of exactly this kind of optimization
#: pathology when mixed with unnormalized one-hot context features.
_LEAKY_SLOPE = 0.01


class CorrectnessHead(nn.Module):
    def __init__(self, context_dim: int = len(CONTEXT_FEATURE_NAMES), hidden_size: int = 768, hidden_units: int = HEAD_HIDDEN_UNITS) -> None:
        super().__init__()
        self.pooled_norm = nn.LayerNorm(hidden_size)
        self.context_proj = nn.Linear(context_dim, context_dim)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size + context_dim, hidden_units),
            nn.LeakyReLU(_LEAKY_SLOPE),
            nn.Linear(hidden_units, 1),
        )

    def forward(self, pooled: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        pooled = self.pooled_norm(pooled)
        ctx = F.leaky_relu(self.context_proj(context), _LEAKY_SLOPE)
        combined = torch.cat([pooled, ctx], dim=-1)
        return self.classifier(combined).squeeze(-1)


def forward_logit(top_layers: nn.ModuleList, head: CorrectnessHead, hidden: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
    h = hidden.unsqueeze(0)  # [1, T, H]
    for layer in top_layers:
        h = layer(h)[0]
    pooled = h.mean(dim=1).squeeze(0)  # [H] -- same mean-pool-over-time convention as Candidate C1/F1
    return head(pooled, context)


# ---------------------------------------------------------------------------
# STEP 7 -- speaker-disjoint early-stopping split (reuses `grouped_kfold`,
# never a new random-split implementation)
# ---------------------------------------------------------------------------


def speaker_holdout_split(speakers: list[str]) -> tuple[list[str], list[str]]:
    unique = sorted(set(speakers))
    k = min(EARLY_STOP_HOLDOUT_K, len(unique))
    if k < 2:
        return list(unique), []
    inner_train, early_stop = grouped_kfold(unique, k=k, seed=SEED)[0]
    return list(inner_train), list(early_stop)


def _prepare_examples(
    idx_list: list[int], rows: list[dict[str, Any]], hidden_cache: dict[str, np.ndarray], ctx_matrix: np.ndarray, labels: np.ndarray,
) -> list[tuple[torch.Tensor, torch.Tensor, float]]:
    examples = []
    for i in idx_list:
        key = _row_key(rows[i])
        hidden = hidden_cache.get(key)
        if hidden is None:
            continue
        examples.append((torch.from_numpy(hidden), torch.from_numpy(ctx_matrix[i].astype(np.float32)), float(labels[i])))
    return examples


def evaluate_examples(
    top_layers: nn.ModuleList, head: CorrectnessHead, examples: list[tuple[torch.Tensor, torch.Tensor, float]]
) -> tuple[list[float], list[float]]:
    probs, labels = [], []
    with torch.no_grad():
        for hidden, ctx, label in examples:
            logit = forward_logit(top_layers, head, hidden, ctx)
            probs.append(float(torch.sigmoid(logit).item()))
            labels.append(label)
    return probs, labels


def _bce_loss(probs: list[float], labels: list[float]) -> float | None:
    if not probs:
        return None
    eps = 1e-9
    p = np.clip(np.array(probs), eps, 1 - eps)
    y = np.array(labels)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ---------------------------------------------------------------------------
# STEP 5/6 -- one training run: class-weighted BCE (training-fold-only
# weights), AdamW with differential LR, gradient clipping, gradient
# accumulation, early stopping on a speaker-disjoint development subset only.
# ---------------------------------------------------------------------------


def train_run(
    top_layers: nn.ModuleList, head: CorrectnessHead,
    train_examples: list[tuple[torch.Tensor, torch.Tensor, float]],
    early_stop_examples: list[tuple[torch.Tensor, torch.Tensor, float]],
) -> dict[str, Any]:
    labels_train = np.array([e[2] for e in train_examples])
    #: STEP 5: class weights from TRAINING data (this run's own train
    #: examples) only -- never global, never including the early-stop or
    #: held-out-fold rows.
    weights = np_class_weights(labels_train)
    n_pos, n_neg = int((labels_train == 1).sum()), int((labels_train == 0).sum())
    pos_weight = float(weights[labels_train == 1][0]) if n_pos else None
    neg_weight = float(weights[labels_train == 0][0]) if n_neg else None

    trainable_params = [p for layer in top_layers for p in layer.parameters()] + list(head.parameters())
    optimizer = torch.optim.AdamW(
        [
            {"params": [p for layer in top_layers for p in layer.parameters()], "lr": ENCODER_LEARNING_RATE},
            {"params": list(head.parameters()), "lr": HEAD_LEARNING_RATE},
        ],
        weight_decay=WEIGHT_DECAY,
    )

    rng = np.random.default_rng(SEED)
    best_early_stop_auc = -1.0
    best_state: dict[str, Any] | None = None
    epochs_since_improvement = 0
    history: list[dict[str, Any]] = []

    for epoch in range(1, MAX_EPOCHS + 1):
        order = rng.permutation(len(train_examples))
        total_loss = 0.0
        optimizer.zero_grad()
        for step, idx in enumerate(order, start=1):
            hidden, ctx, label = train_examples[int(idx)]
            logit = forward_logit(top_layers, head, hidden, ctx)
            weight = torch.tensor(float(weights[int(idx)]))
            loss = F.binary_cross_entropy_with_logits(logit, torch.tensor(float(label)), weight=weight)
            (loss / GRAD_ACCUM_STEPS).backward()
            total_loss += float(loss.item())
            if step % GRAD_ACCUM_STEPS == 0 or step == len(order):
                torch.nn.utils.clip_grad_norm_(trainable_params, GRAD_CLIP_NORM)
                optimizer.step()
                optimizer.zero_grad()
        mean_train_loss = total_loss / max(len(order), 1)

        es_probs, es_labels = evaluate_examples(top_layers, head, early_stop_examples)
        es_auc = roc_auc(es_probs, [bool(l) for l in es_labels]) if es_probs else None
        es_loss = _bce_loss(es_probs, es_labels)

        history.append({"epoch": epoch, "train_loss": round(mean_train_loss, 5), "early_stop_loss": es_loss, "early_stop_auc": es_auc})
        print(f"    epoch {epoch}: train_loss={mean_train_loss:.4f} early_stop_auc={es_auc} early_stop_loss={es_loss}")

        improved = es_auc is not None and es_auc > best_early_stop_auc
        if improved:
            best_early_stop_auc = es_auc
            best_state = {
                "top_layers": [{n: p.detach().clone() for n, p in layer.named_parameters()} for layer in top_layers],
                "head": {n: p.detach().clone() for n, p in head.named_parameters()},
            }
            epochs_since_improvement = 0
        else:
            epochs_since_improvement += 1
            if epochs_since_improvement > EARLY_STOP_PATIENCE:
                print(f"    early stopping at epoch {epoch} (no early-stop AUC improvement for {EARLY_STOP_PATIENCE + 1} epochs)")
                break

    if best_state is not None:
        with torch.no_grad():
            for layer, state in zip(top_layers, best_state["top_layers"]):
                for n, p in layer.named_parameters():
                    p.copy_(state[n])
            for n, p in head.named_parameters():
                p.copy_(best_state["head"][n])

    return {
        "history": history, "best_early_stop_auc": best_early_stop_auc if best_early_stop_auc >= 0 else None,
        "n_train": len(train_examples), "n_early_stop": len(early_stop_examples),
        "n_pos": n_pos, "n_neg": n_neg, "pos_weight": pos_weight, "neg_weight": neg_weight,
    }


# ---------------------------------------------------------------------------
# STEP 7 -- speaker-grouped development CV
# ---------------------------------------------------------------------------


def run_grouped_cv(
    rows: list[dict[str, Any]], hidden_cache: dict[str, np.ndarray], ctx_matrix: np.ndarray, labels: np.ndarray,
    top_layers: nn.ModuleList, pretrained_top_state: dict[str, torch.Tensor],
    *, k: int = CV_FOLDS, seed: int = CV_SEED,
) -> dict[str, Any]:
    speaker_ids = np.array([row["speaker_id"] for row in rows])
    folds = grouped_kfold(sorted(set(speaker_ids)), k=k, seed=seed)
    oof_prob = np.full(len(rows), np.nan)
    fold_reports: list[dict[str, Any]] = []

    for fold_index, (train_speakers, test_speakers) in enumerate(folds):
        print(f"  Fold {fold_index}: {len(train_speakers)} train speakers, {len(test_speakers)} held-out speakers")
        inner_train_speakers, early_stop_speakers = speaker_holdout_split(train_speakers)

        train_idx = [i for i, r in enumerate(rows) if r["speaker_id"] in inner_train_speakers]
        early_stop_idx = [i for i, r in enumerate(rows) if r["speaker_id"] in early_stop_speakers]
        test_idx = [i for i, r in enumerate(rows) if r["speaker_id"] in test_speakers]

        reset_top_layers(top_layers, pretrained_top_state)
        torch.manual_seed(SEED)
        head = CorrectnessHead()

        train_examples = _prepare_examples(train_idx, rows, hidden_cache, ctx_matrix, labels)
        early_stop_examples = _prepare_examples(early_stop_idx, rows, hidden_cache, ctx_matrix, labels)
        train_result = train_run(top_layers, head, train_examples, early_stop_examples)

        valid_test_idx = [i for i in test_idx if _row_key(rows[i]) in hidden_cache]
        test_examples = _prepare_examples(test_idx, rows, hidden_cache, ctx_matrix, labels)
        test_probs, test_labels = evaluate_examples(top_layers, head, test_examples)
        for i, p in zip(valid_test_idx, test_probs):
            oof_prob[i] = p
        fold_auc = roc_auc(test_probs, [bool(l) for l in test_labels]) if test_probs else None

        fold_reports.append({
            "fold": fold_index, "n_train": train_result["n_train"], "n_early_stop": train_result["n_early_stop"],
            "n_test": len(test_examples), "n_pos_train": train_result["n_pos"], "n_neg_train": train_result["n_neg"],
            "pos_weight": train_result["pos_weight"], "neg_weight": train_result["neg_weight"],
            "history": train_result["history"], "best_early_stop_auc": train_result["best_early_stop_auc"],
            "test_auc": fold_auc,
        })
        print(f"    fold {fold_index} held-out speaker AUC = {fold_auc}")

    valid = ~np.isnan(oof_prob)
    pooled_auc = roc_auc(list(oof_prob[valid]), list(labels[valid].astype(bool))) if valid.any() else None
    return {"oof_prob": oof_prob, "labels": labels, "fold_reports": fold_reports, "pooled_auc": pooled_auc, "folds": folds}


# ---------------------------------------------------------------------------
# Row preparation (shared by development CV and the final freeze fit)
# ---------------------------------------------------------------------------


def prepare_rows(split_name: str) -> dict[str, Any]:
    rows_raw = load_split_rows(split_name)
    rows, _excluded = _usable(rows_raw)
    rows = [row for row in rows if row["expected_tone"] in TONES]
    ctx_matrix, ctx_valid, t3_category = build_context_features(rows)
    rows = [r for r, ok in zip(rows, ctx_valid) if ok]
    ctx_matrix = ctx_matrix[ctx_valid]
    t3_category = [c for c, ok in zip(t3_category, ctx_valid) if ok]
    labels = _labels(rows)
    return {"rows": rows, "ctx": ctx_matrix, "labels": labels, "t3_category": t3_category}


# ---------------------------------------------------------------------------
# STEP 10 -- final freeze fit (all of development, before validation opens)
# ---------------------------------------------------------------------------


def fit_frozen_final(
    rows: list[dict[str, Any]], hidden_cache: dict[str, np.ndarray], ctx_matrix: np.ndarray, labels: np.ndarray,
    top_layers: nn.ModuleList, pretrained_top_state: dict[str, torch.Tensor],
) -> dict[str, Any]:
    speaker_ids = [row["speaker_id"] for row in rows]
    inner_train_speakers, early_stop_speakers = speaker_holdout_split(speaker_ids)
    train_idx = [i for i, r in enumerate(rows) if r["speaker_id"] in inner_train_speakers]
    early_stop_idx = [i for i, r in enumerate(rows) if r["speaker_id"] in early_stop_speakers]

    reset_top_layers(top_layers, pretrained_top_state)
    torch.manual_seed(SEED)
    head = CorrectnessHead()

    train_examples = _prepare_examples(train_idx, rows, hidden_cache, ctx_matrix, labels)
    early_stop_examples = _prepare_examples(early_stop_idx, rows, hidden_cache, ctx_matrix, labels)
    result = train_run(top_layers, head, train_examples, early_stop_examples)
    return {"top_layers": top_layers, "head": head, "train_result": result}


def predict_all(
    top_layers: nn.ModuleList, head: CorrectnessHead, rows: list[dict[str, Any]],
    hidden_cache: dict[str, np.ndarray], ctx_matrix: np.ndarray,
) -> np.ndarray:
    probs = np.full(len(rows), np.nan)
    with torch.no_grad():
        for i, row in enumerate(rows):
            hidden = hidden_cache.get(_row_key(row))
            if hidden is None:
                continue
            ctx = torch.from_numpy(ctx_matrix[i].astype(np.float32))
            logit = forward_logit(top_layers, head, torch.from_numpy(hidden), ctx)
            probs[i] = float(torch.sigmoid(logit).item())
    return probs


# ---------------------------------------------------------------------------
# Checkpoint + protocol
# ---------------------------------------------------------------------------


def save_checkpoint(top_layers: nn.ModuleList, head: CorrectnessHead, path: Path = CHECKPOINT_PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "top_layers_state": [layer.state_dict() for layer in top_layers],
        "head_state": head.state_dict(),
    }
    torch.save(payload, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_protocol(
    base: dict[str, Any], cv_result: dict[str, Any], freeze_result: dict[str, Any],
    checkpoint_sha256: str, threshold: float, path: Path = PROTOCOL_JSON,
) -> None:
    protocol = {
        "candidate": "F2",
        "base_checkpoint": {
            "identifier": base["checkpoint"], "sha256": base["checkpoint_sha256"],
            "architecture": "Wav2Vec2Model", "num_hidden_layers": base["num_hidden_layers"],
            "hidden_size": base["hidden_size"],
        },
        "partial_finetune": {
            "n_frozen_layers": base["n_frozen_layers"], "n_unfrozen_layers": base["n_unfrozen_layers"],
            "trainable_modules": base["trainable_modules"],
            "trainable_parameters": base["trainable_parameters"], "total_parameters": base["total_parameters"],
            "trainable_fraction": base["trainable_parameters"] / base["total_parameters"],
            "also_trained": ["linguistic-context projection (CorrectnessHead.context_proj)", "binary correctness head (CorrectnessHead.classifier)"],
            "frozen": ["convolutional feature extractor", "feature projection", "positional-embedding convolution + its layer norm", f"encoder.layers[0:{base['n_frozen_layers']}]"],
        },
        "context_feature_names": CONTEXT_FEATURE_NAMES,
        "excluded_from_input": [
            "character identity", "word identity", "speaker identity", "sentence ID", "audio ID",
            "rater identity", "Praat features", "Candidate E2 score",
        ],
        "target": "OMPAL majority human tone correctness (0=incorrect, 1=correct)",
        "training_recipe": {
            "optimizer": "AdamW", "encoder_learning_rate": ENCODER_LEARNING_RATE, "head_learning_rate": HEAD_LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY, "grad_clip_norm": GRAD_CLIP_NORM, "grad_accum_steps": GRAD_ACCUM_STEPS,
            "max_epochs": MAX_EPOCHS, "early_stop_patience": EARLY_STOP_PATIENCE, "seed": SEED,
            "class_weighting": "benchmarking.mlp.class_weights (balanced, computed from each training run's own training examples only)",
            "no_existing_finetuning_convention_found": True,
            "note": "one fixed configuration, chosen before any Candidate F2 result existed; not searched",
        },
        "cv": {"folds": CV_FOLDS, "seed": CV_SEED, "early_stop_holdout_k": EARLY_STOP_HOLDOUT_K},
        "development_cv_pooled_auc": cv_result["pooled_auc"],
        "final_freeze": {
            "n_train": freeze_result["train_result"]["n_train"], "n_early_stop": freeze_result["train_result"]["n_early_stop"],
            "best_early_stop_auc": freeze_result["train_result"]["best_early_stop_auc"],
            "history": freeze_result["train_result"]["history"],
        },
        "checkpoint_path": str(CHECKPOINT_PATH), "checkpoint_sha256": checkpoint_sha256,
        "threshold": threshold,
        "threshold_selection": "grid point maximizing balanced accuracy on development CV out-of-fold predictions (praat_logistic._select_threshold, reused unmodified) -- same rule as Candidate B1/C1/F1",
        "module": "benchmarking/candidates/wav2vec_partial_finetune.py", "module_sha256": _file_hash(Path("benchmarking/candidates/wav2vec_partial_finetune.py")),
        "ompal_status": "development used for every training/model-selection decision; validation opened exactly once, after this protocol was frozen; final_test never referenced",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Predictions CSV (validation, one-shot)
# ---------------------------------------------------------------------------

PREDICTIONS_FIELDS = [
    "audio_id", "speaker_id", "word", "expected_tone", "t3_context_category",
    "human_majority_tone_correct", "candidate_f2_probability", "candidate_f2_threshold",
    "candidate_f2_predicted_correct", "baseline_a_system_tone_correct", "baseline_a_system_character_score",
]


def write_predictions_csv(
    rows: list[dict[str, Any]], t3_category: list[str], probabilities: np.ndarray, threshold: float, path: Path = PREDICTIONS_CSV,
) -> int:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTIONS_FIELDS)
        writer.writeheader()
        for row, category, prob in zip(rows, t3_category, probabilities):
            writer.writerow({
                "audio_id": row["audio_id"], "speaker_id": row["speaker_id"], "word": row["word"],
                "expected_tone": row["expected_tone"], "t3_context_category": category,
                "human_majority_tone_correct": row["human_majority_tone_correct"],
                "candidate_f2_probability": round(float(prob), 4) if not np.isnan(prob) else "NA",
                "candidate_f2_threshold": threshold,
                "candidate_f2_predicted_correct": int(prob >= threshold) if not np.isnan(prob) else "NA",
                "baseline_a_system_tone_correct": row["system_tone_correct"],
                "baseline_a_system_character_score": row["system_character_score"],
            })
    return len(rows)


# ---------------------------------------------------------------------------
# STEP 8 -- direct F1 vs F2 ablation on IDENTICAL development rows
# ---------------------------------------------------------------------------


def run_f1_ablation() -> dict[str, Any]:
    """Re-runs Candidate F1's own frozen procedure (F1a: embedding + context,
    the variant F1 selected -- `f1_context_wav2vec.prepare_rows` +
    `run_grouped_cv(..., use_praat=False)`, both imported unmodified) to get
    row-keyed out-of-fold probabilities directly comparable to Candidate
    F2's own out-of-fold probabilities."""
    from benchmarking.candidates import f1_context_wav2vec as f1

    print("  Re-running Candidate F1 (F1a) development CV for the ablation (unmodified)...")
    f1_data = f1.prepare_rows("development")
    f1_cv = f1.run_grouped_cv(f1_data, use_praat=False)
    prob_by_key = {}
    for row, prob in zip(f1_data["rows"], f1_cv["oof_prob"]):
        if not np.isnan(prob):
            prob_by_key[(row["audio_id"], row["syllable_index"])] = float(prob)
    return {"prob_by_key": prob_by_key, "rows": f1_data["rows"], "labels": f1_data["labels"], "pooled_auc": f1_cv["pooled_auc"]}


def compare_f1_f2(f2_rows, f2_oof_prob, f2_labels, f1_ablation: dict[str, Any]) -> dict[str, Any]:
    f1_prob_by_key = f1_ablation["prob_by_key"]

    def _pairs(tone: int | None):
        f1_scores, f2_scores, common_labels = [], [], []
        for row, f2_prob, label in zip(f2_rows, f2_oof_prob, f2_labels):
            if np.isnan(f2_prob):
                continue
            if tone is not None and row["expected_tone"] != str(tone):
                continue
            key = (row["audio_id"], row["syllable_index"])
            f1_prob = f1_prob_by_key.get(key)
            if f1_prob is None:
                continue
            f1_scores.append(f1_prob)
            f2_scores.append(f2_prob)
            common_labels.append(bool(label))
        return f1_scores, f2_scores, common_labels

    result = {}
    for label, tone in (("overall", None), ("T1", 1), ("T2", 2), ("T3", 3), ("T4", 4)):
        f1_scores, f2_scores, common_labels = _pairs(tone)
        f1_auc = roc_auc(f1_scores, common_labels) if f1_scores else None
        f2_auc = roc_auc(f2_scores, common_labels) if f2_scores else None
        result[label] = {
            "n": len(common_labels), "auc_f1": f1_auc, "auc_f2": f2_auc,
            "delta": (f2_auc - f1_auc) if (f1_auc is not None and f2_auc is not None) else None,
        }
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    print("STEP 1: loading base checkpoint...")
    base = load_base_model()
    print(f"  {base['checkpoint']} sha256={base['checkpoint_sha256'][:16]}... "
          f"{base['num_hidden_layers']} layers, hidden={base['hidden_size']}")
    print("STEP 2: applying partial freeze...")
    base = apply_partial_freeze(base)
    print(f"  trainable {base['trainable_parameters']}/{base['total_parameters']} "
          f"({base['trainable_parameters']/base['total_parameters']:.1%}) -- {base['trainable_modules']}")

    model, processor = base["model"], base["processor"]
    top_layers, pretrained_top_state = base["top_layers"], base["pretrained_top_state"]
    n_frozen = base["n_frozen_layers"]

    print("Preparing development rows (linguistic context features)...")
    dev_data = prepare_rows("development")
    print(f"  {len(dev_data['rows'])} usable development rows")

    print("Building/loading frozen-activation cache for development (one-time, reused every fold)...")
    dev_hidden_cache, dev_missing = build_frozen_activation_cache(dev_data["rows"], "development", model, processor, n_frozen)
    print(f"  {len(dev_hidden_cache)} cached, {dev_missing} unusable")

    print("STEP 7: speaker-grouped development CV...")
    cv_result = run_grouped_cv(
        dev_data["rows"], dev_hidden_cache, dev_data["ctx"], dev_data["labels"],
        top_layers, pretrained_top_state,
    )
    print(f"  pooled development CV AUC = {cv_result['pooled_auc']}")

    threshold = _select_threshold(cv_result["oof_prob"], cv_result["labels"])

    print("STEP 8: F1 vs F2 ablation (identical development rows)...")
    f1_ablation = run_f1_ablation()
    ablation = compare_f1_f2(dev_data["rows"], cv_result["oof_prob"], dev_data["labels"], f1_ablation)
    print(f"  overall: F1 AUC={ablation['overall']['auc_f1']}, F2 AUC={ablation['overall']['auc_f2']}, delta={ablation['overall']['delta']}")

    print("STEP 10: final freeze fit on ALL development...")
    freeze_result = fit_frozen_final(dev_data["rows"], dev_hidden_cache, dev_data["ctx"], dev_data["labels"], top_layers, pretrained_top_state)
    checkpoint_sha256 = save_checkpoint(freeze_result["top_layers"], freeze_result["head"])
    write_protocol(base, cv_result, freeze_result, checkpoint_sha256, threshold)
    print(f"  protocol + checkpoint frozen (checkpoint sha256={checkpoint_sha256[:16]}...)")

    print("STEP 11: opening validation (one-shot)...")
    val_data = prepare_rows("validation")
    print(f"  {len(val_data['rows'])} usable validation rows")
    val_hidden_cache, val_missing = build_frozen_activation_cache(val_data["rows"], "validation", model, processor, n_frozen)
    print(f"  {len(val_hidden_cache)} cached, {val_missing} unusable")

    val_prob = predict_all(freeze_result["top_layers"], freeze_result["head"], val_data["rows"], val_hidden_cache, val_data["ctx"])

    from benchmarking.candidates.f1_context_wav2vec import by_t3_context_metrics, by_tone_metrics, pooled_metrics

    val_pooled = pooled_metrics(val_prob, val_data["labels"], threshold)
    val_by_tone = by_tone_metrics(val_data["rows"], val_prob, val_data["labels"], threshold)
    val_by_t3 = by_t3_context_metrics(val_data["rows"], val_data["t3_category"], val_prob, val_data["labels"], threshold)

    n_predictions = write_predictions_csv(val_data["rows"], val_data["t3_category"], val_prob, threshold)

    print("High-confidence diagnostic subset (already-defined, not redefined)...")
    from benchmarking.candidates.e2_ompal_development import high_confidence_keys

    val_rows_all_raw, _ = _usable(load_split_rows("validation"))
    hc_keys = high_confidence_keys(val_rows_all_raw)
    hc_mask = np.array([(row["audio_id"], row["syllable_index"]) in hc_keys for row in val_data["rows"]])
    hc_metrics = pooled_metrics(val_prob[hc_mask], val_data["labels"][hc_mask], threshold) if hc_mask.any() else {"n_scored": 0}

    print("Evaluating Candidate E V1 / Candidate E2 on validation (unmodified, for the comparison table only)...")
    from benchmarking.candidates.e2_ompal_development import run_e1_e2_on_development
    from benchmarking.candidates.f1_context_wav2vec import evaluate_e1_e2_on_rows
    from benchmarking.baseline_a import evaluate as evaluate_baseline_a

    e_rows, _e_diag = run_e1_e2_on_development(val_rows_all_raw)
    e1e2 = evaluate_e1_e2_on_rows(e_rows)
    baseline_a = evaluate_baseline_a(val_rows_all_raw)

    return {
        "base": base, "cv_result": cv_result, "threshold": threshold,
        "ablation": ablation, "f1_ablation_pooled_auc": f1_ablation["pooled_auc"],
        "freeze_result": freeze_result, "checkpoint_sha256": checkpoint_sha256,
        "dev_n": len(dev_data["rows"]), "val_n": len(val_data["rows"]),
        "val_pooled": val_pooled, "val_by_tone": val_by_tone, "val_by_t3": val_by_t3,
        "hc_metrics": hc_metrics, "hc_n": int(hc_mask.sum()),
        "n_predictions_written": n_predictions,
        "baseline_a": baseline_a, "e1e2": e1e2,
    }


if __name__ == "__main__":
    from benchmarking.candidates import report_wav2vec_partial_finetune as report

    result = run()
    verdict = report.write_reports(result)
    print(f"Predictions written to {PREDICTIONS_CSV} ({result['n_predictions_written']} rows)")
    print(f"Protocol written to {PROTOCOL_JSON}")
    print(f"Reports written to {DEV_DEV_MD}, {VAL_MD}, {COMPARISON_MD}")
    print(f"Verdict: {verdict}")
