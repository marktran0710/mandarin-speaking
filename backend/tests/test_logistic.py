"""The hand-rolled logistic regression Candidate B1 is built on.

No oracle library (scikit-learn, statsmodels) is used here even though
scikit-learn happens to be installed in this environment — it is not in
requirements.txt, and a test suite that silently depends on it would pass
here and fail wherever that package is absent. Correctness is instead
checked against closed-form properties of logistic regression and against a
tiny case solved independently by grid search, which needs nothing but
numpy.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.logistic import fit, _sigmoid


class TestSigmoid:
    def test_matches_the_textbook_definition_away_from_the_overflow_edge(self):
        z = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        expected = 1.0 / (1.0 + np.exp(-z))
        assert np.allclose(_sigmoid(z), expected)

    def test_is_bounded_and_stable_for_extreme_inputs(self):
        z = np.array([-1000.0, 1000.0])
        result = _sigmoid(z)
        assert np.all(np.isfinite(result))
        assert result[0] == pytest.approx(0.0, abs=1e-12)
        assert result[1] == pytest.approx(1.0, abs=1e-12)


class TestFit:
    def test_recovers_the_sign_of_a_clearly_informative_feature(self):
        rng = np.random.default_rng(0)
        n = 2000
        x = rng.normal(size=n)
        prob = 1.0 / (1.0 + np.exp(-(2.0 * x - 0.3)))
        y = (rng.uniform(size=n) < prob).astype(float)
        result = fit(x.reshape(-1, 1), y, l2=0.1)
        assert result.converged
        assert result.coefficients[1] > 1.0  # true slope was 2.0
        assert result.coefficients[0] < 0.0  # true intercept was -0.3, same sign

    def test_a_useless_feature_gets_a_coefficient_near_zero(self):
        rng = np.random.default_rng(1)
        n = 3000
        noise = rng.normal(size=n)
        y = (rng.uniform(size=n) < 0.3).astype(float)  # independent of `noise`
        result = fit(noise.reshape(-1, 1), y, l2=1.0)
        assert abs(result.coefficients[1]) < 0.15
        # The intercept should recover roughly logit(0.3).
        assert result.coefficients[0] == pytest.approx(np.log(0.3 / 0.7), abs=0.15)

    def test_predictions_are_monotonic_in_a_monotonic_true_relationship(self):
        rng = np.random.default_rng(2)
        n = 1500
        x = rng.uniform(-3, 3, size=n)
        prob = 1.0 / (1.0 + np.exp(-1.5 * x))
        y = (rng.uniform(size=n) < prob).astype(float)
        result = fit(x.reshape(-1, 1), y, l2=0.5)
        grid = np.linspace(-3, 3, 50).reshape(-1, 1)
        predicted = result.predict_proba(grid)
        assert np.all(np.diff(predicted) >= 0), "probability must rise with x"

    def test_matches_an_independently_grid_searched_two_point_fit(self):
        """A minimal case (two distinct x values, known counts) whose maximum
        a-posteriori coefficients can be found by brute-force grid search
        over the same penalized objective `fit` optimizes — an independent
        check that does not call `fit` at all."""
        x = np.array([[0.0]] * 20 + [[1.0]] * 20)
        y = np.array([0.0] * 16 + [1.0] * 4 + [0.0] * 4 + [1.0] * 16)
        l2 = 0.5

        def penalized_nll(b0, b1):
            eta = b0 + b1 * x[:, 0]
            mu = np.clip(1 / (1 + np.exp(-eta)), 1e-9, 1 - 1e-9)
            nll = -np.sum(y * np.log(mu) + (1 - y) * np.log(1 - mu))
            return nll + 0.5 * l2 * b1**2

        grid = np.linspace(-6, 6, 241)
        best = min(
            ((b0, b1) for b0 in grid for b1 in grid),
            key=lambda pair: penalized_nll(*pair),
        )
        result = fit(x, y, l2=l2)
        assert result.coefficients[0] == pytest.approx(best[0], abs=0.06)
        assert result.coefficients[1] == pytest.approx(best[1], abs=0.06)

    def test_converges_within_the_default_iteration_budget(self):
        rng = np.random.default_rng(3)
        x = rng.normal(size=(500, 9))
        y = (rng.uniform(size=500) < 0.2).astype(float)
        result = fit(x, y)
        assert result.converged

    def test_is_deterministic(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=(300, 3))
        y = (rng.uniform(size=300) < 0.4).astype(float)
        first = fit(x, y)
        second = fit(x, y)
        assert np.array_equal(first.coefficients, second.coefficients)

    def test_rejects_non_binary_labels(self):
        with pytest.raises(ValueError):
            fit(np.zeros((3, 1)), np.array([0, 1, 2]))

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            fit(np.zeros((3, 1)), np.array([0, 1]))
