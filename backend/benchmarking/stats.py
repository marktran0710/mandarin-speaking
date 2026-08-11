"""Shared statistical primitives for benchmark agreement reporting.

These are deliberately dependency-free and operate on plain sequences rather
than on any particular row/record type, so both the tone benchmark (system
score vs. human label) and the inter-rater analysis (human vs. human) can use
exactly the same maths. Two agreement numbers are only comparable when they
were computed the same way.
"""

from __future__ import annotations

import math
from typing import Sequence


def safe_divide(numerator: float, denominator: float) -> float | None:
    """Return None instead of raising when the denominator is zero.

    A missing metric must stay visibly missing; substituting 0.0 would let an
    undefined rate read as a real, good-looking measurement.
    """
    return numerator / denominator if denominator else None


def confusion_counts(
    predicted: Sequence[bool], actual: Sequence[bool]
) -> tuple[int, int, int, int]:
    """Return (true_positive, true_negative, false_positive, false_negative)."""
    if len(predicted) != len(actual):
        raise ValueError("predicted and actual must be the same length")
    true_positive = true_negative = false_positive = false_negative = 0
    for prediction, truth in zip(predicted, actual):
        if truth and prediction:
            true_positive += 1
        elif not truth and not prediction:
            true_negative += 1
        elif not truth and prediction:
            false_positive += 1
        else:
            false_negative += 1
    return true_positive, true_negative, false_positive, false_negative


def binary_agreement(
    predicted: Sequence[bool], actual: Sequence[bool]
) -> dict[str, float | int | None]:
    """Agreement between two binary judgements.

    ``cohen_kappa`` measures agreement beyond what the two marginal rates
    would produce by chance. It prevents a high accuracy on an imbalanced
    corpus (e.g. one where almost every syllable is correct) from being
    mistaken for a useful scoring system. Cohen's kappa is symmetric, so this
    same function serves both system-vs-human and human-vs-human comparisons.
    """
    true_positive, true_negative, false_positive, false_negative = confusion_counts(
        predicted, actual
    )
    total = true_positive + true_negative + false_positive + false_negative
    accuracy = safe_divide(true_positive + true_negative, total)
    positive_rate_actual = safe_divide(true_positive + false_negative, total) or 0.0
    positive_rate_predicted = safe_divide(true_positive + false_positive, total) or 0.0
    expected_agreement = (
        positive_rate_actual * positive_rate_predicted
        + (1 - positive_rate_actual) * (1 - positive_rate_predicted)
    )
    return {
        "n": total,
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "accuracy": accuracy,
        "precision": safe_divide(true_positive, true_positive + false_positive),
        "recall": safe_divide(true_positive, true_positive + false_negative),
        # Recall's counterpart on the negative class: of the items the human
        # marked incorrect, how many did the system also mark incorrect. On a
        # corpus where most syllables are correct this is the number a high
        # accuracy most easily hides.
        "specificity": safe_divide(true_negative, true_negative + false_positive),
        "f1": safe_divide(
            2 * true_positive, 2 * true_positive + false_positive + false_negative
        ),
        "cohen_kappa": safe_divide(
            (accuracy or 0.0) - expected_agreement, 1 - expected_agreement
        ),
        # Mean of recall and specificity. Plain accuracy on this corpus can
        # look moderate while the system is doing nothing but predicting the
        # majority class; balanced accuracy is 0.5 in exactly that case, where
        # accuracy is not.
        "balanced_accuracy": _mean_or_none(
            safe_divide(true_positive, true_positive + false_negative),
            safe_divide(true_negative, true_negative + false_positive),
        ),
        "matthews_correlation": matthews_correlation(
            true_positive, true_negative, false_positive, false_negative
        ),
        **error_rates(true_positive, true_negative, false_positive, false_negative),
    }


def _mean_or_none(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if len(present) == len(values) else None


def matthews_correlation(
    true_positive: int, true_negative: int, false_positive: int, false_negative: int
) -> float | None:
    """Matthews correlation coefficient: -1 (total disagreement) to +1
    (perfect agreement), 0 for a system with no better than chance relation
    to the labels regardless of class balance.

    Unlike accuracy or F1, MCC uses all four confusion-matrix cells
    symmetrically, so it does not flatter a system that is only good at the
    majority class — the exact failure mode a corpus this imbalanced (most
    syllables rated correct) makes easy to hide behind a high accuracy.
    """
    numerator = true_positive * true_negative - false_positive * false_negative
    denominator = math.sqrt(
        (true_positive + false_positive)
        * (true_positive + false_negative)
        * (true_negative + false_positive)
        * (true_negative + false_negative)
    )
    return safe_divide(numerator, denominator)


def error_rates(
    true_positive: int, true_negative: int, false_positive: int, false_negative: int
) -> dict[str, float | int | None]:
    """False acceptance and false rejection, with their denominators stated.

    Both are named from the *learner's* point of view, which is the only
    reading that matters for a teaching tool, and each carries the denominator
    it was divided by so the rate can never be quoted against the wrong base:

    * false acceptance — the human marked the item incorrect and the system let
      it pass. Denominator: everything the human marked incorrect.
    * false rejection — the human marked the item correct and the system failed
      it. Denominator: everything the human marked correct.

    Positive class is "correct/pass" throughout, matching ``binary_agreement``.
    """
    human_incorrect = true_negative + false_positive
    human_correct = true_positive + false_negative
    return {
        "false_acceptance_count": false_positive,
        "false_acceptance_rate": safe_divide(false_positive, human_incorrect),
        "false_acceptance_denominator": human_incorrect,
        "false_rejection_count": false_negative,
        "false_rejection_rate": safe_divide(false_negative, human_correct),
        "false_rejection_denominator": human_correct,
    }


def rank(values: Sequence[float]) -> list[float]:
    """Average ranks, with ties sharing their mean rank (for Spearman)."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[order[position]] = average_rank
        start = end
    return ranks


def pearson(first: Sequence[float], second: Sequence[float]) -> float | None:
    """Pearson correlation, or None when it is undefined (n < 2 or no spread)."""
    if len(first) != len(second):
        raise ValueError("pearson inputs must be the same length")
    if len(first) < 2:
        return None
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    numerator = sum((a - first_mean) * (b - second_mean) for a, b in zip(first, second))
    first_scale = math.sqrt(sum((a - first_mean) ** 2 for a in first))
    second_scale = math.sqrt(sum((b - second_mean) ** 2 for b in second))
    return safe_divide(numerator, first_scale * second_scale)


def spearman(first: Sequence[float], second: Sequence[float]) -> float | None:
    """Rank correlation.

    Used instead of an absolute error whenever the two scales are not
    comparable (e.g. a 1-5 human rubric against a 0-100 system score). It
    answers "does the system order learners the same way a teacher does"
    without inventing a linear mapping between the scales that nobody
    validated.
    """
    return pearson(rank(first), rank(second))


def roc_auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Area under the ROC curve, via the rank-sum (Mann-Whitney U) identity.

    AUC equals the probability that a randomly chosen positive item scores
    higher than a randomly chosen negative one. That probability has a closed
    form in terms of ranks — no threshold sweep needed, and ties are handled
    correctly by reusing the same average-rank ``rank`` function Spearman
    uses, rather than by a separate curve-integration implementation that
    could disagree with it:

        AUC = (sum of ranks of positive-labelled scores - n_pos*(n_pos+1)/2)
              / (n_pos * n_neg)

    This is diagnostic only — it asks whether the continuous score has any
    discriminative signal at all, independent of where a threshold is drawn.
    It is not a proposal to change the threshold.

    Returns None when either class is empty (undefined) or n < 2.
    """
    if len(scores) != len(labels):
        raise ValueError("roc_auc inputs must be the same length")
    n_positive = sum(1 for label in labels if label)
    n_negative = len(labels) - n_positive
    if n_positive == 0 or n_negative == 0:
        return None
    ranks = rank(list(scores))
    positive_rank_sum = sum(r for r, label in zip(ranks, labels) if label)
    return safe_divide(
        positive_rank_sum - n_positive * (n_positive + 1) / 2.0,
        n_positive * n_negative,
    )


def summary_stats(values: Sequence[float]) -> dict[str, float | int | None]:
    """N, mean, SD, median and IQR for one feature — the descriptive table
    every group comparison in the diagnostic report is built from.

    Quartiles use linear interpolation between the two nearest ranks (the
    same convention as numpy's default), so a report built from this function
    reproduces exactly if someone re-derives it with numpy.
    """
    values = sorted(float(v) for v in values)
    n = len(values)
    if n == 0:
        return {
            "n": 0, "mean": None, "sd": None, "median": None,
            "q1": None, "q3": None, "iqr": None, "min": None, "max": None,
        }

    def quantile(q: float) -> float:
        if n == 1:
            return values[0]
        position = q * (n - 1)
        lower = int(math.floor(position))
        upper = min(lower + 1, n - 1)
        fraction = position - lower
        return values[lower] + (values[upper] - values[lower]) * fraction

    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / n) if n > 1 else 0.0
    q1, q3 = quantile(0.25), quantile(0.75)
    return {
        "n": n, "mean": mean, "sd": sd, "median": quantile(0.5),
        "q1": q1, "q3": q3, "iqr": q3 - q1, "min": values[0], "max": values[-1],
    }
