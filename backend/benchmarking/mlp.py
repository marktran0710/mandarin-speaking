"""A small, dependency-free one-hidden-layer MLP classifier.

Candidate F1 combines a low-dimensional PCA'd Wav2Vec2 embedding with a
handful of categorical/continuous linguistic-context features (and, for F1b,
Praat features) — a plain linear model (Candidate B1/C1's own logistic
regression, `benchmarking/logistic.py`) cannot represent an interaction
between an embedding subspace and a context flag, which is exactly the
hypothesis Candidate F1 exists to test. scikit-learn/PyTorch are not used
here for the same reason `benchmarking/logistic.py` gives: every research
candidate's exact optimization stays behind one dependency-free, auditable
implementation, in the same spirit as `benchmarking/stats.py`.

Gradient descent (not Newton's method — the loss surface is not convex with
a hidden layer) from a deterministic, seeded initialization. The
architecture is FIXED — one hidden layer, one hidden width, one learning
rate, one iteration budget, one L2 strength — chosen once, before any
Candidate F1 result existed, and never searched or tuned against a result,
per the task's explicit "no architecture search" instruction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Small and fixed. With ~30-70 input dimensions and a few thousand training
#: rows per tone, 16 hidden units gives the model room to represent a
#: handful of embedding-x-context interactions without approaching the
#: parameter count where a few thousand rows would risk overfitting a
#: 1-hidden-layer net. Not tuned — chosen once, before any Candidate F1
#: result existed.
DEFAULT_HIDDEN_UNITS = 16
DEFAULT_L2 = 1.0
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_MAX_ITER = 3000
DEFAULT_TOLERANCE = 1e-7
#: Fixed weight-initialization seed — the one source of randomness in this
#: fitter, pinned so the same input always yields the same output.
DEFAULT_SEED = 20260810
_PROB_EPSILON = 1e-9


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    positive = z >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
    exp_z = np.exp(z[~positive])
    out[~positive] = exp_z / (1.0 + exp_z)
    return out


def class_weights(labels: np.ndarray) -> np.ndarray:
    """`sample_weight` giving each class equal total weight — the standard
    "balanced" scheme (weight = n_samples / (n_classes * n_class_count)) —
    computed from whatever `labels` array is passed in. Callers are
    responsible for passing only the TRAINING fold's labels, never anything
    that includes a held-out fold, so class imbalance is always handled
    from training-fold information only."""
    labels = np.asarray(labels, dtype=float)
    n = len(labels)
    n_pos = float(np.sum(labels == 1.0))
    n_neg = float(np.sum(labels == 0.0))
    weight_pos = n / (2.0 * n_pos) if n_pos > 0 else 0.0
    weight_neg = n / (2.0 * n_neg) if n_neg > 0 else 0.0
    return np.where(labels == 1.0, weight_pos, weight_neg)


@dataclass(frozen=True)
class MLPFit:
    """One hidden layer (ReLU) + one sigmoid output unit."""

    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    iterations: int
    converged: bool
    final_loss: float

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        features = np.asarray(features, dtype=float)
        hidden = np.maximum(0.0, features @ self.w1 + self.b1)
        logits = hidden @ self.w2 + self.b2
        return _sigmoid(logits.ravel())


def fit(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    sample_weight: np.ndarray | None = None,
    hidden_units: int = DEFAULT_HIDDEN_UNITS,
    l2: float = DEFAULT_L2,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    max_iter: int = DEFAULT_MAX_ITER,
    tolerance: float = DEFAULT_TOLERANCE,
    seed: int = DEFAULT_SEED,
) -> MLPFit:
    features = np.asarray(features, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if features.ndim != 2:
        raise ValueError("features must be a 2D array (n_samples, n_features)")
    if len(features) != len(labels):
        raise ValueError("features and labels must have the same length")

    n, p = features.shape
    weight = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    weight_sum = max(float(weight.sum()), _PROB_EPSILON)

    rng = np.random.default_rng(seed)
    w1 = rng.normal(0.0, np.sqrt(2.0 / max(p, 1)), size=(p, hidden_units))
    b1 = np.zeros(hidden_units)
    w2 = rng.normal(0.0, np.sqrt(2.0 / hidden_units), size=(hidden_units, 1))
    b2 = np.zeros(1)

    previous_loss = np.inf
    converged = False
    loss = float("nan")
    iteration = 0
    for iteration in range(1, max_iter + 1):
        z1 = features @ w1 + b1
        h = np.maximum(0.0, z1)
        z2 = (h @ w2 + b2).ravel()
        mu = np.clip(_sigmoid(z2), _PROB_EPSILON, 1 - _PROB_EPSILON)

        bce = -float(np.sum(weight * (labels * np.log(mu) + (1 - labels) * np.log(1 - mu)))) / weight_sum
        l2_term = 0.5 * l2 * (np.sum(w1 ** 2) + np.sum(w2 ** 2)) / n
        loss = bce + l2_term

        dz2 = ((weight * (mu - labels)) / weight_sum).reshape(-1, 1)
        dw2 = h.T @ dz2 + l2 * w2 / n
        db2 = dz2.sum(axis=0)
        dh = dz2 @ w2.T
        dz1 = dh * (z1 > 0)
        dw1 = features.T @ dz1 + l2 * w1 / n
        db1 = dz1.sum(axis=0)

        w1 = w1 - learning_rate * dw1
        b1 = b1 - learning_rate * db1
        w2 = w2 - learning_rate * dw2
        b2 = b2 - learning_rate * db2

        if abs(previous_loss - loss) < tolerance:
            converged = True
            break
        previous_loss = loss

    return MLPFit(w1=w1, b1=b1, w2=w2, b2=b2, iterations=iteration, converged=converged, final_loss=loss)
