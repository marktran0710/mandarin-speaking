"""FREX-style characteristic-error identification for the vocab quiz.

Adapts the FREX (FRequency + EXclusivity) metric from structural topic
modeling — there it ranks which words best characterize a topic; here it
ranks which missed words best characterize a *student's* weak spots,
among the words that student has actually missed at least once:

- frequency: the word's population miss rate (misses / exposures across
  every student) — a word everyone struggles with is worth flagging
  regardless of who's asking, since it's a curriculum problem, not a
  personal one.
- exclusivity: this student's share of that word's total misses across
  the class — a word only ever missed by this one student is a genuinely
  personal weak spot, not shared noise.

FREX combines the two as a weighted harmonic mean of each metric's rank
within the student's own candidate set (same construction as the STM
FREX formula), so a word has to do reasonably well on *both* axes to
surface — a word that's merely common but not exclusive to this student
(everyone misses it), or exclusive but negligible (one fluke miss on an
easy word) should score lower.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .irt import Response

# STM's own papers favor exclusivity somewhat over frequency (their
# default is 0.7) — a word unique to this student is the more actionable
# signal for a teacher than "this word is just hard for everyone."
DEFAULT_EXCLUSIVITY_WEIGHT = 0.7


@dataclass
class CharacteristicWord:
    word: str
    frex: float
    frequency: float  # population miss rate for this word, 0-1
    exclusivity: float  # this student's share of the word's total misses, 0-1
    miss_count: int  # how many times this student has missed it


def _ecdf_ranks(values: Dict[str, float]) -> Dict[str, float]:
    """Percentile rank of each key's value within this dict, in (0, 1]."""
    ordered = sorted(values, key=lambda k: values[k])
    n = len(ordered)
    return {word: (i + 1) / n for i, word in enumerate(ordered)}


def compute_frex(
    responses: Iterable[Response],
    weight: float = DEFAULT_EXCLUSIVITY_WEIGHT,
    top_n: int = 5,
) -> Dict[str, List[CharacteristicWord]]:
    """responses: (student_key, word, correct) triples, one per exposure.

    Returns, per student, their top_n characteristic weak words — words
    they've missed at least once, ranked by FREX. A student who hasn't
    missed anything gets an empty list.
    """
    responses = list(responses)
    total_count: Counter = Counter()
    miss_count: Counter = Counter()
    student_miss: Counter = Counter()  # (student, word) -> count
    students = set()

    for student, word, correct in responses:
        students.add(student)
        total_count[word] += 1
        if not correct:
            miss_count[word] += 1
            student_miss[(student, word)] += 1

    frequency = {
        word: miss_count[word] / total_count[word] for word in total_count
    }

    result: Dict[str, List[CharacteristicWord]] = {}
    for student in students:
        candidates = [
            word
            for (owner, word), count in student_miss.items()
            if owner == student and count > 0
        ]
        if not candidates:
            result[student] = []
            continue

        exclusivity = {w: student_miss[(student, w)] / miss_count[w] for w in candidates}
        exclusivity_rank = _ecdf_ranks(exclusivity)
        frequency_rank = _ecdf_ranks({w: frequency[w] for w in candidates})

        scored = []
        for word in candidates:
            er, fr = exclusivity_rank[word], frequency_rank[word]
            frex = 1.0 / (weight / er + (1 - weight) / fr)
            scored.append(
                CharacteristicWord(
                    word=word,
                    frex=frex,
                    frequency=frequency[word],
                    exclusivity=exclusivity[word],
                    miss_count=student_miss[(student, word)],
                )
            )
        scored.sort(key=lambda c: c.frex, reverse=True)
        result[student] = scored[:top_n]

    return result
