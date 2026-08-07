"""Load the tone dataset and split it so a speaker never crosses the split.

Speaker-independent splitting is the point, not a detail. A tone classifier
that has heard a speaker during training can recognise that voice's habits
rather than the tone, and it will look excellent in testing and fail on the
first new learner. Splitting by recording instead of by speaker is the single
easiest way to produce a number that means nothing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

REQUIRED_COLUMNS = ("audio_path", "speaker_id", "pinyin", "tone")
VALID_TONES = (1, 2, 3, 4)


@dataclass(frozen=True)
class ToneSample:
    """One labelled syllable recording."""

    audio_path: Path
    speaker_id: str
    pinyin: str
    tone: int


def load_dataset(csv_path: str | Path) -> List[ToneSample]:
    """Read the dataset CSV, validating every row.

    Audio paths are resolved relative to the CSV, so a dataset directory can be
    moved without editing it. A malformed row raises with its line number
    rather than being skipped: silently dropping rows changes the class balance
    and nobody notices.
    """
    path = Path(csv_path).resolve()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{path} is missing required column(s): {', '.join(missing)}. "
                f"Expected header: {','.join(REQUIRED_COLUMNS)}"
            )

        samples: List[ToneSample] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                audio = (row.get("audio_path") or "").strip()
                speaker = (row.get("speaker_id") or "").strip()
                pinyin = (row.get("pinyin") or "").strip()
                raw_tone = (row.get("tone") or "").strip()
                if not audio or not speaker:
                    raise ValueError("audio_path and speaker_id cannot be blank")
                tone = int(raw_tone)
                if tone not in VALID_TONES:
                    raise ValueError(
                        f"tone must be one of {VALID_TONES}, got {raw_tone!r}"
                    )
                resolved = Path(audio)
                if not resolved.is_absolute():
                    resolved = path.parent / resolved
                samples.append(
                    ToneSample(resolved, speaker, pinyin, tone)
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"{path} line {line_number}: {error}") from error

    if not samples:
        raise ValueError(f"{path} contains no rows")
    return samples


def speaker_independent_split(
    samples: Sequence[ToneSample], test_ratio: float = 0.25, seed: int = 0
) -> Tuple[List[ToneSample], List[ToneSample]]:
    """Split by speaker, never by recording.

    Speakers are shuffled with a fixed seed and assigned whole to one side, so
    the split is reproducible and no speaker is ever divided. Both sides are
    guaranteed at least one speaker; with fewer than two speakers in the
    dataset a speaker-independent split is impossible and this raises rather
    than returning a split that only looks valid.
    """
    import random

    speakers = sorted({sample.speaker_id for sample in samples})
    if len(speakers) < 2:
        raise ValueError(
            f"speaker-independent split needs at least 2 speakers, found "
            f"{len(speakers)}. A split within one speaker measures voice "
            f"familiarity, not tone recognition."
        )
    if not 0.0 < test_ratio < 1.0:
        raise ValueError("test_ratio must be between 0 and 1")

    random.Random(seed).shuffle(speakers)
    test_count = max(1, min(len(speakers) - 1, round(len(speakers) * test_ratio)))
    test_speakers = set(speakers[:test_count])

    train = [s for s in samples if s.speaker_id not in test_speakers]
    test = [s for s in samples if s.speaker_id in test_speakers]
    return train, test


def tone_distribution(samples: Sequence[ToneSample]) -> Dict[int, int]:
    counts = {tone: 0 for tone in VALID_TONES}
    for sample in samples:
        counts[sample.tone] += 1
    return counts


def describe(samples: Sequence[ToneSample]) -> str:
    speakers = len({s.speaker_id for s in samples})
    return (
        f"{len(samples)} samples, {speakers} speakers, "
        f"tones {tone_distribution(samples)}"
    )
