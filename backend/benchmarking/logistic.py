"""A small, dependency-free penalized logistic regression.

Candidate B1 needs to fit ~8 logistic regressions (one per expected tone,
times cross-validation folds) over a few thousand rows and nine features.
That is well within reach of plain Newton's method, and scikit-learn — while
installed in this environment — is not declared in `requirements.txt`;
depending on it here would make this "simple, interpretable" research
candidate quietly rely on an undeclared package. This module exists so it
does not have to, in the same spirit as `benchmarking/stats.py`'s own
dependency-free primitives.

The model: standard L2-penalized logistic regression, fit by Newton-Raphson
on the penalized negative log-likelihood. The intercept is never penalized
(only the feature coefficients are), which is the conventional choice — the
intercept sets the base rate, not a discriminative direction, so shrinking it
would bias probability estimates on an imbalanced label mix for no benefit.

The L2 strength is a small, FIXED constant chosen for numerical stability
(9 standardized features on ~2,000 rows is well short of separation risk,
but a tiny ridge keeps the Hessian comfortably invertible if a fold happens
to be more collinear). It is not tuned, searched, or selected — doing so
would need a nested cross-validation loop this task explicitly asked to
avoid ("no large hyperparameter search").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_L2 = 1.0
DEFAULT_MAX_ITER = 50
DEFAULT_TOLERANCE = 1e-8
#: Clip probabilities away from the boundary so the Hessian never carries a
#: literal zero weight (mu*(1-mu)=0), which would make it singular.
_PROB_EPSILON = 1e-9


@dataclass(frozen=True)
class LogisticFit:
    """Coefficients from a fitted model. `coefficients[0]` is the intercept;
    `coefficients[1:]` line up with the feature columns as given to `fit`."""

    coefficients: np.ndarray
    iterations: int
    converged: bool

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        design = np.column_stack([np.ones(len(features)), features])
        return _sigmoid(design @ self.coefficients)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    # Numerically stable logistic: avoids overflow in exp for large |z| by
    # branching on the sign, the standard trick for this function.
    out = np.empty_like(z, dtype=float)
    positive = z >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
    exp_z = np.exp(z[~positive])
    out[~positive] = exp_z / (1.0 + exp_z)
    return out


def fit(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    l2: float = DEFAULT_L2,
    max_iter: int = DEFAULT_MAX_ITER,
    tolerance: float = DEFAULT_TOLERANCE,
) -> LogisticFit:
    """Fit intercept + one coefficient per column of `features` to `labels`
    (0/1). Deterministic: Newton's method from a zero start has no random
    component, so the same input always yields the same output — there is no
    seed to fix here, unlike a gradient-descent or sampling-based fitter.
    """
    features = np.asarray(features, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if features.ndim != 2:
        raise ValueError("features must be a 2D array (n_samples, n_features)")
    if len(features) != len(labels):
        raise ValueError("features and labels must have the same length")
    if not set(np.unique(labels)) <= {0.0, 1.0}:
        raise ValueError("labels must be binary 0/1")

    n, p = features.shape
    design = np.column_stack([np.ones(n), features])  # +1 for the intercept
    penalty = l2 * np.eye(p + 1)
    penalty[0, 0] = 0.0  # never penalize the intercept

    beta = np.zeros(p + 1)
    previous_loss = np.inf
    converged = False
    iteration = 0
    for iteration in range(1, max_iter + 1):
        eta = design @ beta
        mu = np.clip(_sigmoid(eta), _PROB_EPSILON, 1 - _PROB_EPSILON)

        # Penalized negative log-likelihood, for the convergence check.
        loss = -np.sum(labels * np.log(mu) + (1 - labels) * np.log(1 - mu))
        loss += 0.5 * l2 * np.sum(beta[1:] ** 2)

        gradient = design.T @ (mu - labels) + penalty @ beta
        weights = mu * (1 - mu)
        hessian = (design * weights[:, None]).T @ design + penalty

        step = np.linalg.solve(hessian, gradient)
        beta = beta - step

        if abs(previous_loss - loss) < tolerance:
            converged = True
            break
        previous_loss = loss

    return LogisticFit(coefficients=beta, iterations=iteration, converged=converged)
