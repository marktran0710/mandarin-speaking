"""The one place that holds every weight and threshold of the pronunciation score.

ENGINEERING DEFAULTS. None of these numbers is calibrated against human
raters, and none may be described as validated. They are named and versioned so
a calibration pass can move them from one place, and so every stored evaluation
can say exactly which policy produced it. Changing a default means bumping
``VERSION``.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from typing import Mapping, Optional

VERSION = "pronunciation-score-v1"

_WEIGHT_ENV = {
    "tone": "PRONUNCIATION_WEIGHT_TONE",
    "segmental": "PRONUNCIATION_WEIGHT_SEGMENTAL",
    "fluency": "PRONUNCIATION_WEIGHT_FLUENCY",
    "intelligibility": "PRONUNCIATION_WEIGHT_INTELLIGIBILITY",
}


@dataclass(frozen=True)
class DimensionWeights:
    """Relative weights. They need not sum to 1: the score renormalises over
    whichever dimensions could actually be measured."""

    tone: float = 0.40
    segmental: float = 0.30
    fluency: float = 0.20
    intelligibility: float = 0.10

    def __post_init__(self) -> None:
        values = self.as_dict().values()
        if any(value < 0 for value in values):
            raise ValueError("Pronunciation weights must not be negative.")
        if not any(value > 0 for value in values):
            raise ValueError("At least one pronunciation weight must be positive.")

    def as_dict(self) -> dict[str, float]:
        return {
            "tone": self.tone,
            "segmental": self.segmental,
            "fluency": self.fluency,
            "intelligibility": self.intelligibility,
        }


@dataclass(frozen=True)
class ContourSimilarityParams:
    """Shape x size similarity of one word's pitch contour.

    Mirrors ``DEFAULT_SIMILARITY_PARAMS`` in the frontend's modelSimilarity.ts
    so the percentage a student already sees and the stored score agree. See
    docs/model-similarity-evaluation.md for what was and was not checked.
    """

    r_floor: float = 0.4
    r_full: float = 0.85
    rho_zero: float = 0.2
    rho_full: float = 0.6
    min_reference_span: float = 3.0
    samples_per_word: int = 20
    #: Student-window shifts tried per word, as a fraction of the word's span.
    window_shifts: tuple[float, ...] = (-0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15)
    #: A reference word whose pitch moves less than this has no shape to
    #: correlate; it is scored on how level the student kept their pitch.
    flat_reference_range: float = 1.0
    #: Student pitch range (semitones) that still counts as level ...
    flat_full_credit_range: float = 2.0
    #: ... and the range at which level credit has fallen to zero.
    flat_zero_credit_range: float = 4.0
    #: Unvoiced stretch (ms) beyond which a contour is not interpolated across.
    max_voiced_gap_ms: float = 100.0


@dataclass(frozen=True)
class DirectionParams:
    """When a syllable's pitch counts as rising, falling, dipping or level.

    All in semitones against the speaker's own median, so they hold for any
    voice range.
    """

    #: Fewer voiced points than this cannot support any direction.
    min_points: int = 4
    #: A 10th-90th percentile spread below this is level.
    flat_range: float = 1.5
    dip_min: float = 1.0
    dip_fraction: float = 0.3
    slope_min: float = 1.0
    slope_fraction: float = 0.5


@dataclass(frozen=True)
class RhythmParams:
    """Timing is always judged relative to the utterance's own speed, because a
    textbook recording may be intentionally slower than natural speech."""

    #: A syllable this many times longer or shorter than the reference share
    #: earns no rhythm credit.
    zero_ratio_factor: float = 2.5
    #: Overall speaking-rate ratio (student / reference) that earns full credit.
    #: Wide on the slow side because learners are often slower than a teacher.
    rate_band: tuple[float, float] = (0.6, 1.6)
    #: Beyond the band, credit reaches zero after a further factor of this.
    rate_zero_factor: float = 2.0
    #: A pause the reference does not make is choppy speech ...
    extra_pause_penalty: float = 0.34
    #: ... while skipping a textbook pause is only faster speech.
    missing_pause_penalty: float = 0.1
    #: Pauses within this many syllable gaps of each other count as the same pause.
    pause_match_gaps: int = 1
    #: Articulation rate (syllables/s) outside this range is not plausibly the
    #: requested sentence spoken at all.
    plausible_rate: tuple[float, float] = (0.8, 9.0)
    #: Relative weight of each timing measure inside the fluency dimension.
    rhythm_weight: float = 0.5
    pause_weight: float = 0.3
    duration_weight: float = 0.2


@dataclass(frozen=True)
class FlagParams:
    """When a measured difference becomes a flagged issue."""

    #: A contour flag needs the contour similarity itself to be below this.
    similarity_max: float = 0.6
    short_ratio: float = 0.5
    long_ratio: float = 2.0
    #: Same direction as the reference but the size factor below this = too narrow.
    narrow_range_factor: float = 0.6
    #: Below this voiced fraction a syllable's evidence is downgraded.
    min_voiced_ratio: float = 0.5
    #: Below this alignment confidence every issue is capped at weak evidence.
    low_alignment_confidence: float = 0.5
    #: A contour issue with similarity below this is high severity (else medium).
    high_severity_similarity: float = 0.3
    #: A timing issue this many times off the reference share is medium severity.
    medium_duration_ratio: float = 3.0


@dataclass(frozen=True)
class PronunciationScoringPolicy:
    version: str = VERSION
    weights: DimensionWeights = field(default_factory=DimensionWeights)
    similarity: ContourSimilarityParams = field(default_factory=ContourSimilarityParams)
    direction: DirectionParams = field(default_factory=DirectionParams)
    rhythm: RhythmParams = field(default_factory=RhythmParams)
    flags: FlagParams = field(default_factory=FlagParams)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "PronunciationScoringPolicy":
        env = os.environ if environ is None else environ
        defaults = DimensionWeights()
        values: dict[str, float] = {}
        for key, env_name in _WEIGHT_ENV.items():
            raw = env.get(env_name)
            if raw is None or str(raw).strip() == "":
                values[key] = getattr(defaults, key)
                continue
            try:
                values[key] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{env_name} must be a number, got {raw!r}.") from exc
        return replace(cls(), weights=DimensionWeights(**values))

    def to_dict(self) -> dict:
        snapshot = asdict(self)
        snapshot["weights"] = self.weights.as_dict()
        return snapshot
