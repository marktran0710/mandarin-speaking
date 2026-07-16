"""Item Response Theory (Rasch / 1PL) for the vocabulary quiz.

Fits P(correct) = sigmoid(ability[student] - difficulty[item]) by maximum
a posteriori estimation. A Gaussian prior on both ability and difficulty
does two jobs at once: it's what keeps a student who has answered every
question correctly so far from getting an ability estimate that diverges
to +infinity (plain MLE would do exactly that — there's no finite
maximizer for a perfect record), and it anchors the model, since a plain
Rasch likelihood is only identified up to a shared additive constant
(adding 1 to every ability and every difficulty leaves every prediction
unchanged) — the prior's pull toward zero picks one specific anchor.
"""

from collections import Counter
from typing import Dict, Iterable, Tuple

import numpy as np
from scipy.optimize import minimize

# Weakly informative: a 2-logit spread between students/items is already a
# large practical difference (sigmoid(2) ≈ 0.88 vs sigmoid(0) = 0.5), so a
# prior this wide barely constrains a well-populated fit while still being
# enough to pull an extreme (perfect/zero score) estimate back to something
# finite.
DEFAULT_PRIOR_SD = 1.5

Response = Tuple[str, str, bool]  # (student_key, item_key, correct)


class RaschFit:
    def __init__(
        self,
        item_difficulty: Dict[str, float],
        student_ability: Dict[str, float],
        item_n: Dict[str, int],
        student_n: Dict[str, int],
    ):
        self.item_difficulty = item_difficulty
        self.student_ability = student_ability
        self.item_n = item_n
        self.student_n = student_n


def fit_rasch(responses: Iterable[Response], prior_sd: float = DEFAULT_PRIOR_SD) -> RaschFit:
    responses = list(responses)
    if not responses:
        return RaschFit({}, {}, {}, {})

    students = sorted({s for s, _, _ in responses})
    items = sorted({it for _, it, _ in responses})
    s_idx = {s: i for i, s in enumerate(students)}
    i_idx = {it: i for i, it in enumerate(items)}
    n_s, n_i = len(students), len(items)

    s_ids = np.array([s_idx[s] for s, _, _ in responses])
    i_ids = np.array([i_idx[it] for _, it, _ in responses])
    y = np.array([1.0 if c else 0.0 for _, _, c in responses])

    def neg_log_posterior(params: np.ndarray) -> float:
        theta, b = params[:n_s], params[n_s:]
        z = theta[s_ids] - b[i_ids]
        # log p(y|z) summed, via the numerically stable log(1+exp(z)) form.
        log_lik = np.sum(y * z - np.logaddexp(0, z))
        log_prior = -0.5 * (np.sum(theta**2) + np.sum(b**2)) / prior_sd**2
        return -(log_lik + log_prior)

    def grad(params: np.ndarray) -> np.ndarray:
        theta, b = params[:n_s], params[n_s:]
        z = theta[s_ids] - b[i_ids]
        p = 1.0 / (1.0 + np.exp(-z))
        resid = y - p
        grad_theta = np.zeros(n_s)
        grad_b = np.zeros(n_i)
        np.add.at(grad_theta, s_ids, resid)
        np.add.at(grad_b, i_ids, -resid)
        grad_theta -= theta / prior_sd**2
        grad_b -= b / prior_sd**2
        return -np.concatenate([grad_theta, grad_b])

    x0 = np.zeros(n_s + n_i)
    result = minimize(neg_log_posterior, x0, jac=grad, method="L-BFGS-B")
    theta_hat, b_hat = result.x[:n_s], result.x[n_s:]

    item_n = Counter(it for _, it, _ in responses)
    student_n = Counter(s for s, _, _ in responses)

    return RaschFit(
        item_difficulty={it: float(b_hat[i_idx[it]]) for it in items},
        student_ability={s: float(theta_hat[s_idx[s]]) for s in students},
        item_n=dict(item_n),
        student_n=dict(student_n),
    )
