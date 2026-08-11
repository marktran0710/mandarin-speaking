"""A deterministic, speaker-disjoint split of the OMPAL learner population.

Every prior number in this validation has been computed over the *whole*
corpus, which is fine for auditing the current scorer but wrong for
comparing candidate models: a model selected or tuned on data that includes
the utterances it is later "tested" on will look better than it is, and
because OMPAL rates each speaker's recordings from a single elicitation
session, even splitting by *utterance* rather than by *speaker* leaks —
a speaker's voice, pace, and error patterns repeat across their own
recordings. The split here is by speaker, so no voice appears on both sides
of any boundary.

Native speakers (only 3, and carrying no per-rater labels — see
`OmpalUtterance.has_per_rater_labels`) are excluded entirely; splitting a
population of 3 further would leave partitions too small to mean anything,
and Baseline A's comparison is against the non-native learners this corpus
was built to assess.

The split is a pure function of (speaker list, seed, ratios) — same inputs,
same output, forever. That is what makes `final_test` meaningful as a lock:
anyone can verify a candidate model's authors never had the labels by
re-deriving the split themselves.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

DEFAULT_SEED = 20260810
DEFAULT_RATIOS = {"development": 0.6, "validation": 0.2, "final_test": 0.2}
DEFAULT_SPLIT_PATH = Path("benchmarking/splits/ompal_speaker_split.json")

SPLIT_NAMES = ("development", "validation", "final_test")


@dataclass(frozen=True)
class SpeakerSplit:
    seed: int
    ratios: dict[str, float]
    development: tuple[str, ...]
    validation: tuple[str, ...]
    final_test: tuple[str, ...]

    def split_of(self, speaker_id: str) -> str | None:
        for name in SPLIT_NAMES:
            if speaker_id in getattr(self, name):
                return name
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ratios": self.ratios,
            "final_test_locked": True,
            "final_test_policy": (
                "No candidate model may use final_test labels for training, "
                "threshold selection, feature selection, or model selection. "
                "It is read only once, at the end, to report a number that "
                "was never optimised against."
            ),
            "speakers": {
                "development": list(self.development),
                "validation": list(self.validation),
                "final_test": list(self.final_test),
            },
        }


def create_speaker_split(
    speaker_ids: Sequence[str],
    *,
    seed: int = DEFAULT_SEED,
    ratios: dict[str, float] = None,
) -> SpeakerSplit:
    """Deterministically assign every speaker to exactly one partition.

    Determinism comes from two things together: sorting the input before
    shuffling (so the result cannot depend on dict/filesystem iteration
    order, which is not guaranteed stable across machines or Python
    versions) and using a `random.Random` instance seeded once, never the
    module-global `random` state another part of the process might have
    already advanced.
    """
    ratios = dict(ratios or DEFAULT_RATIOS)
    if abs(sum(ratios.values()) - 1.0) > 1e-9:
        raise ValueError(f"split ratios must sum to 1.0, got {ratios}")
    if set(ratios) != set(SPLIT_NAMES):
        raise ValueError(f"ratios must cover exactly {SPLIT_NAMES}, got {sorted(ratios)}")

    ordered = sorted(set(speaker_ids))
    if len(ordered) != len(speaker_ids):
        raise ValueError("duplicate speaker_id in input")

    rng = random.Random(seed)
    shuffled = list(ordered)
    rng.shuffle(shuffled)

    total = len(shuffled)
    # Largest-remainder rounding, so every speaker is assigned exactly once
    # and the partition sizes sum to `total` even when ratios * total is not
    # integral (46 speakers * 0.2 = 9.2, for instance).
    raw = {name: ratios[name] * total for name in SPLIT_NAMES}
    counts = {name: int(raw[name]) for name in SPLIT_NAMES}
    remainder = total - sum(counts.values())
    for name in sorted(SPLIT_NAMES, key=lambda n: raw[n] - counts[n], reverse=True)[:remainder]:
        counts[name] += 1

    cursor = 0
    parts: dict[str, tuple[str, ...]] = {}
    for name in SPLIT_NAMES:
        parts[name] = tuple(shuffled[cursor : cursor + counts[name]])
        cursor += counts[name]

    return SpeakerSplit(seed=seed, ratios=ratios, **parts)


def load_split(path: Path = DEFAULT_SPLIT_PATH) -> SpeakerSplit:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    speakers = payload["speakers"]
    return SpeakerSplit(
        seed=payload["seed"],
        ratios=payload["ratios"],
        development=tuple(speakers["development"]),
        validation=tuple(speakers["validation"]),
        final_test=tuple(speakers["final_test"]),
    )


def write_split(split: SpeakerSplit, path: Path = DEFAULT_SPLIT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(split.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def grouped_kfold(
    speaker_ids: Sequence[str], k: int, *, seed: int = DEFAULT_SEED
) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Deterministic k-fold over speakers: no speaker appears in both the
    train and held-out side of any fold.

    For a candidate model developed entirely within one split (e.g.
    `development`), this is what lets cross-validation estimate how the model
    generalises to an unseen *speaker* rather than merely an unseen
    *recording* — the same leakage concern the top-level speaker split exists
    to prevent, one level down.

    Returns a list of `(train_speakers, held_out_speakers)` pairs, one per
    fold. Sizes are as equal as `len(speaker_ids)` allows (largest-remainder,
    same rule `create_speaker_split` uses).
    """
    if k < 2:
        raise ValueError("k must be at least 2")
    ordered = sorted(set(speaker_ids))
    if len(ordered) != len(speaker_ids):
        raise ValueError("duplicate speaker_id in input")
    if len(ordered) < k:
        raise ValueError(f"need at least {k} speakers for {k} folds, got {len(ordered)}")

    rng = random.Random(seed)
    shuffled = list(ordered)
    rng.shuffle(shuffled)

    base = len(shuffled) // k
    remainder = len(shuffled) % k
    fold_sizes = [base + (1 if i < remainder else 0) for i in range(k)]

    folds: list[tuple[str, ...]] = []
    cursor = 0
    for size in fold_sizes:
        folds.append(tuple(shuffled[cursor : cursor + size]))
        cursor += size

    result = []
    for i in range(k):
        held_out = folds[i]
        train = tuple(speaker for j, fold in enumerate(folds) if j != i for speaker in fold)
        result.append((train, held_out))
    return result
