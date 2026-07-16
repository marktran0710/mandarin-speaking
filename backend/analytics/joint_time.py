"""Joint accuracy + response-time model, fit separately per quiz mode.

The four vocab-quiz modes (speed/strikes/free/review) put very different
time pressure on a student, so a single pooled time model would blend
"fast because the clock is running" with "fast because it's an untimed
review" — fitting one model per mode instead keeps that pressure a
constant within each fit, which is what makes "student speed" and
"item time-intensity" comparable within a mode.

This mirors the accuracy side (irt.fit_rasch) with a response-time side —
the classic pairing in item-response-theory literature (van der Linden's
hierarchical model of speed and accuracy): log(response time) modeled as
an item's own time-intensity minus how fast the student tends to be,
fit the same way as Rasch (regularized least squares instead of Rasch's
regularized logistic MLE, since time is continuous, not binary).
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import numpy as np

from .irt import Response, fit_rasch

# Same reasoning as irt.DEFAULT_PRIOR_SD: shrink item/student time effects
# enough to keep a lightly-sampled item or student from swinging on one or
# two data points, without meaningfully distorting a well-populated fit.
RIDGE_LAMBDA = 4.0

TimedResponse = Tuple[str, str, bool, float]  # (student_key, item_key, correct, time_ms)


@dataclass
class JointModeFit:
    mode: str
    n_responses: int
    item_difficulty: Dict[str, float]
    student_ability: Dict[str, float]
    item_time_intensity: Dict[str, float]
    student_speed: Dict[str, float]
    # Pearson correlation between ability and speed across students who
    # have both — positive means "faster students are also more accurate
    # in this mode" (mastery), negative means a speed/accuracy tradeoff
    # (rushing). None when too few students overlap to mean anything.
    ability_speed_correlation: Optional[float]


def _fit_time_effects(
    responses: Iterable[TimedResponse],
    ridge_lambda: float = RIDGE_LAMBDA,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Two-way effects model: log(time_ms) = mu + item_effect - student_speed.

    Ridge (not an explicit reference-level constraint) resolves the same
    "which constant do item and student effects share" indeterminacy that
    Rasch's prior resolves for ability/difficulty — an unpenalized fit
    has infinitely many equally-good (item_effect, student_speed) pairs
    that only differ by a constant shift between the two groups.
    """
    responses = list(responses)
    students = sorted({s for s, _, _, _ in responses})
    items = sorted({it for _, it, _, _ in responses})
    s_idx = {s: i for i, s in enumerate(students)}
    i_idx = {it: i for i, it in enumerate(items)}
    n_s, n_i = len(students), len(items)

    n = len(responses)
    # Columns: [intercept, item dummies (n_i), -student dummies (n_s)]
    X = np.zeros((n, 1 + n_i + n_s))
    y = np.zeros(n)
    for row, (s, it, _correct, time_ms) in enumerate(responses):
        X[row, 0] = 1.0
        X[row, 1 + i_idx[it]] = 1.0
        X[row, 1 + n_i + s_idx[s]] = -1.0
        y[row] = np.log(max(time_ms, 1.0))

    penalty = np.eye(X.shape[1]) * ridge_lambda
    penalty[0, 0] = 0.0  # never shrink the intercept
    beta = np.linalg.solve(X.T @ X + penalty, X.T @ y)

    item_time_intensity = {it: float(beta[1 + i_idx[it]]) for it in items}
    # The student column is encoded as -1 (not +1) in X, so the fitted
    # coefficient beta_student already equals "speed" directly: predicted
    # log-time = mu + item_effect + (-1)*beta_student = mu + item_effect
    # - beta_student, i.e. a *larger* beta_student (speed) means *less*
    # time — no further sign flip needed here.
    student_speed = {s: float(beta[1 + n_i + s_idx[s]]) for s in students}
    return item_time_intensity, student_speed


def fit_joint_mode(mode: str, responses: Iterable[TimedResponse]) -> JointModeFit:
    responses = list(responses)
    if not responses:
        return JointModeFit(mode, 0, {}, {}, {}, {}, None)

    accuracy_fit = fit_rasch([(s, it, c) for s, it, c, _t in responses])
    item_time_intensity, student_speed = _fit_time_effects(responses)

    shared_students = sorted(set(accuracy_fit.student_ability) & set(student_speed))
    correlation: Optional[float] = None
    if len(shared_students) >= 3:
        abilities = np.array([accuracy_fit.student_ability[s] for s in shared_students])
        speeds = np.array([student_speed[s] for s in shared_students])
        if abilities.std() > 1e-9 and speeds.std() > 1e-9:
            correlation = float(np.corrcoef(abilities, speeds)[0, 1])

    return JointModeFit(
        mode=mode,
        n_responses=len(responses),
        item_difficulty=accuracy_fit.item_difficulty,
        student_ability=accuracy_fit.student_ability,
        item_time_intensity=item_time_intensity,
        student_speed=student_speed,
        ability_speed_correlation=correlation,
    )
