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
        "f1": safe_divide(
            2 * true_positive, 2 * true_positive + false_positive + false_negative
        ),
        "cohen_kappa": safe_divide(
            (accuracy or 0.0) - expected_agreement, 1 - expected_agreement
        ),
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
