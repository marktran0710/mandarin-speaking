"""Inter-rater agreement: how well the human experts agree with each other.

This exists to make the system's own agreement score interpretable. A system
that matches a teacher panel at kappa 0.58 sounds mediocre in isolation, but
if the teachers themselves only agree with each other at 0.60 then the system
is performing at human level and 0.58 is close to the practical ceiling.
Reporting the system number without this one invites a false conclusion in
either direction.

``mean_pairwise_cohen_kappa`` is the headline ceiling because it is computed
with the same function as the system-vs-panel figure (see
:func:`benchmarking.stats.binary_agreement`), which makes the two directly
comparable. Fleiss' kappa is reported alongside it as the conventional
whole-panel statistic.
"""

from __future__ import annotations

from itertools import combinations
from typing import Sequence

from benchmarking.stats import binary_agreement

RaterLabels = Sequence[Sequence[bool]]


def _validate(raters: RaterLabels) -> list[list[bool]]:
    rows = [list(rater) for rater in raters]
    if rows:
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("every rater must label exactly the same items")
    return rows


def majority_label(labels: Sequence[bool]) -> bool | None:
    """Consensus judgement of a rater panel for one item.

    An even split resolves to ``False``: a tie means the panel did not agree
    the syllable was produced correctly, and resolving ties toward "correct"
    would inflate the pass rate the system is then measured against.
    """
    labels = list(labels)
    if not labels:
        return None
    return sum(1 for label in labels if label) * 2 > len(labels)


def mean_pairwise_kappa(raters: RaterLabels) -> float | None:
    """Mean Cohen's kappa across every unique pair of raters.

    Returns None when there are fewer than two raters, or when no pair
    produced a defined kappa (which happens if every rater was unanimous
    across every item, leaving no variation to correct for).
    """
    rows = _validate(raters)
    if len(rows) < 2:
        return None
    kappas = [
        value
        for first, second in combinations(rows, 2)
        if (value := binary_agreement(first, second)["cohen_kappa"]) is not None
    ]
    if not kappas:
        return None
    return sum(kappas) / len(kappas)


def fleiss_kappa(raters: RaterLabels) -> float | None:
    """Fleiss' kappa over a fixed panel of raters judging binary items.

    Returns None when chance agreement is total (every item received the same
    label from everyone). Reporting 0.0 in that case would wrongly suggest the
    raters disagreed, when in fact the data simply carries no variation.
    """
    rows = _validate(raters)
    rater_count = len(rows)
    if rater_count < 2 or not rows[0]:
        return None
    item_count = len(rows[0])

    positive_per_item = [
        sum(1 for rater in rows if rater[index]) for index in range(item_count)
    ]
    # Proportion of rater-pairs per item that agreed, averaged over items.
    pairs_per_item = rater_count * (rater_count - 1)
    observed = sum(
        (positive * (positive - 1) + (rater_count - positive) * (rater_count - positive - 1))
        / pairs_per_item
        for positive in positive_per_item
    ) / item_count

    positive_rate = sum(positive_per_item) / (item_count * rater_count)
    expected = positive_rate**2 + (1 - positive_rate) ** 2
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def rater_agreement_summary(raters: RaterLabels) -> dict[str, float | int | None]:
    """The human ceiling, plus enough panel shape to judge its weight."""
    rows = _validate(raters)
    rater_count = len(rows)
    item_count = len(rows[0]) if rows else 0
    unanimous = sum(
        1
        for index in range(item_count)
        if len({rater[index] for rater in rows}) == 1
    )
    return {
        "rater_count": rater_count,
        "item_count": item_count,
        "mean_pairwise_cohen_kappa": mean_pairwise_kappa(rows),
        "fleiss_kappa": fleiss_kappa(rows),
        "unanimous_item_count": unanimous,
        "unanimous_rate": unanimous / item_count if item_count else None,
    }
