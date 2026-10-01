"""Independent pilot rubrics. Defaults are engineering thresholds, NOT validated.

Each dimension selects the highest level whose criteria all pass; there is no
weighted total. The full policy and decision evidence travel with every result.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from statistics import fmean, median, pstdev

from domain.pronunciation.types import UtteranceFeatures

VERSION = "pronunciation-rubric-v1"
POLICY_ENV = "PRONUNCIATION_RUBRIC_POLICY_JSON"


def _geometric_mean(values):
    return math.exp(fmean(math.log(value) for value in values))

FLUENCY_RUBRIC = {
    5: "Fluent speech with stable rate and no unnecessary pauses.",
    4: "Generally fluent with a few short unnecessary pauses.",
    3: "Moderately fluent with several pauses or noticeable rate deviations.",
    2: "Disfluent with frequent or long pauses or large rate deviations.",
    1: "Extensive pauses or rate deviations substantially interrupt production.",
}
PROSODY_RUBRIC = {
    5: "Pitch movement and rhythm are very close to the reference.",
    4: "Pitch movement and rhythm have only minor deviations.",
    3: "Noticeable deviations, with an acceptable overall pattern.",
    2: "Frequent deviations in pitch movement or rhythm.",
    1: "Large deviations substantially disrupt the reference prosodic pattern.",
}


@dataclass(frozen=True)
class RubricPolicy:
    version: str = VERSION
    validation_status: str = "uncalibrated_engineering_defaults"
    # Maximum deviations for levels 5, 4, 3, 2; worse selects level 1.
    fluency_limits: dict[str, tuple[float, ...]] = field(default_factory=lambda: {
        "excess_pause_ratio": (.05, .12, .25, .40),
        "unnecessary_pause_fraction": (0, .10, .25, .50),
        "mean_unnecessary_pause_duration": (.25, .50, .85, 1.50),
        "speech_rate_log_deviation": (.25, .45, .70, 1.0),
    })
    # Minimum similarity for levels 5, 4, 3, 2; worse selects level 1.
    prosody_limits: dict[str, tuple[float, ...]] = field(default_factory=lambda: {
        key: (.90, .75, .55, .30) for key in (
            "pitch_contour_similarity", "pitch_movement_similarity",
            "pitch_range_similarity", "rhythm_similarity", "speaking_rate_stability",
        )
    })
    # Minimum similarity for Wav2Vec2 initial/final segments and Praat F0 tone
    # evidence, in levels 5, 4, 3 and 2. These are calibration starting points.
    pronunciation_limits: dict[str, tuple[float, ...]] = field(default_factory=lambda: {
        "initial_similarity": (.92, .84, .72, .58),
        "final_similarity": (.92, .84, .72, .58),
        "tone_similarity": (.90, .78, .60, .38),
    })
    pause_duration_tolerance_seconds: float = .15
    pitch_distance_scale_semitones: float = 4.0
    pitch_range_floor_semitones: float = .5
    min_alignment_confidence: float = .5
    min_pitch_syllable_coverage: float = .6

    def __post_init__(self):
        if self.version != VERSION:
            raise ValueError(f"Rubric version is fixed at {VERSION}")
        if self.validation_status != "uncalibrated_engineering_defaults":
            raise ValueError("Teacher calibration must be evidenced before changing validation status")
        expected = RubricPolicy.__dataclass_fields__
        for name, lower in (("fluency_limits", False), ("prosody_limits", True), ("pronunciation_limits", True)):
            defaults = expected[name].default_factory()
            actual = getattr(self, name)
            if set(actual) != set(defaults):
                raise ValueError(f"{name} must specify all supported criteria")
            for values in actual.values():
                if len(values) != 4 or any(not math.isfinite(v) or v < 0 for v in values):
                    raise ValueError(f"{name} requires four finite nonnegative thresholds")
                if list(values) != sorted(values, reverse=lower):
                    raise ValueError(f"{name} thresholds have the wrong order")
                if lower and any(v > 1 for v in values):
                    raise ValueError("Similarity thresholds must be in [0, 1]")
        for name in ("pitch_distance_scale_semitones", "pitch_range_floor_semitones"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.pause_duration_tolerance_seconds) or self.pause_duration_tolerance_seconds < 0:
            raise ValueError("Pause tolerance must be finite and nonnegative")
        if any(not 0 <= v <= 1 for v in (self.min_alignment_confidence, self.min_pitch_syllable_coverage)):
            raise ValueError("Coverage and confidence must be in [0, 1]")

    @classmethod
    def from_env(cls):
        data = json.loads(os.environ.get(POLICY_ENV) or "{}")
        if not isinstance(data, dict):
            raise ValueError("Rubric policy must be a JSON object")
        return cls(**data)

    def to_dict(self):
        return asdict(self)


def _decision(
    key,
    measurements,
    limits,
    rubric,
    *,
    minimum=False,
    unavailable=None,
    degraded_features=None,
    evidence_quality="full",
    evidence_reasons=(),
    fallback_level=3,
):
    if unavailable:
        return {"key": key, "score": None, "out_of": 5, "source": "praat",
                "rubric_level": None, "rubric_description": None, "reason": unavailable,
                "measurements": measurements, "criteria": []}
    degraded_features = set(degraded_features or ())
    criteria = []
    for name, thresholds in limits.items():
        value = measurements[name]
        if name in degraded_features:
            # Keep the raw measurement, but do not turn missing evidence into a
            # false perfect score. Level 3 is the rubric's neutral middle band
            # until the recording is re-measured or thresholds are calibrated.
            level = fallback_level
            evidence = "degraded"
        else:
            level = next((5 - i for i, threshold in enumerate(thresholds)
                          if value >= threshold), None) if minimum else next(
                (5 - i for i, threshold in enumerate(thresholds) if value <= threshold), None)
            level = level or 1
            evidence = "measured"
        criteria.append({"feature": name, "value": value, "level": level,
                         "thresholds_levels_5_to_2": list(thresholds),
                         "comparison": ">=" if minimum else "<=",
                         "evidence": evidence})
    score = min(c["level"] for c in criteria)
    limiting = ", ".join(c["feature"] for c in criteria if c["level"] == score)
    reason = f"Level {score}: limiting criteria: {limiting}. All criteria must meet a level."
    if evidence_reasons:
        reason += " Evidence quality is degraded: " + ", ".join(evidence_reasons) + "."
    return {"key": key, "score": score, "out_of": 5, "source": "praat",
            "rubric_level": score, "rubric_description": rubric[score],
            "reason": reason, "measurements": measurements, "criteria": criteria,
            "evidence_quality": evidence_quality,
            "evidence_reasons": list(evidence_reasons)}


def _speech_seconds(features):
    return (features.syllables[-1].end_ms - features.syllables[0].start_ms) / 1000


def _resample_pitch(features: UtteranceFeatures, sample_count: int = 7) -> list[list[float]]:
    """Read each syllable at matching normalized time points, keeping gaps."""
    result = []
    for syllable in features.syllables:
        points = syllable.f0_points
        if len(points) < 2:
            result.append([])
            continue
        times = [point[0] for point in points]
        samples = []
        for index in range(sample_count):
            at = times[0] + (times[-1] - times[0]) * (index + .5) / sample_count
            right = next((i for i, time in enumerate(times) if time >= at), len(times) - 1)
            left = max(0, right - 1)
            gap = times[right] - times[left]
            fraction = (at - times[left]) / gap if gap > 0 else 0
            samples.append(points[left][1] + fraction * (points[right][1] - points[left][1]))
        result.append(samples)
    return result


def score_fluency(student: UtteranceFeatures, reference: UtteranceFeatures, policy: RubricPolicy):
    count = len(student.syllables)
    speaking = _speech_seconds(student)
    articulation = student.articulation_ms / 1000
    pauses = [p.duration_ms / 1000 for p in student.pauses]
    # A gap is expected if it exists in the reference or is a script phrase boundary.
    allowed = {}
    for pause in reference.pauses:
        allowed[pause.after_syllable] = allowed.get(pause.after_syllable, 0) + pause.duration_ms / 1000
    punctuation = set("，、。！？；：,.!?;:")
    cursor = 0
    for index, syllable in enumerate(student.syllables[:-1]):
        position = student.expected_text.find(syllable.expected.hanzi, cursor)
        cursor = position + 1
        next_char = student.syllables[index + 1].expected.hanzi
        end = student.expected_text.find(next_char, cursor)
        if any(c in punctuation for c in student.expected_text[cursor:end]):
            allowed.setdefault(index, policy.pause_duration_tolerance_seconds)
    student_gaps = {}
    for pause in student.pauses:
        student_gaps[pause.after_syllable] = student_gaps.get(pause.after_syllable, 0) + pause.duration_ms / 1000
    excess = [max(0, seconds - allowed[gap] - policy.pause_duration_tolerance_seconds)
              if gap in allowed else seconds for gap, seconds in student_gaps.items()]
    unnecessary = [seconds for seconds in excess if seconds > 0]
    reference_rate = len(reference.syllables) / _speech_seconds(reference)
    rate = count / speaking
    measurements = {
        "total_speech_duration": student.duration_ms / 1000,
        "speaking_duration": speaking, "articulation_duration": articulation,
        "speech_rate": rate, "articulation_rate": count / articulation,
        "syllable_count": count, "syllable_count_source": "target_script_estimate",
        "pause_count": len(pauses), "total_pause_duration": sum(pauses),
        "mean_pause_duration": fmean(pauses) if pauses else 0,
        "pause_ratio": sum(pauses) / speaking,
        "reference_speech_rate": reference_rate,
        "alignment_confidence": min(student.alignment.confidence, reference.alignment.confidence),
        "unnecessary_pause_count": len(unnecessary),
        "unnecessary_pause_fraction": len(unnecessary) / count,
        "mean_unnecessary_pause_duration": fmean(unnecessary) if unnecessary else 0,
        "excess_pause_ratio": sum(unnecessary) / speaking,
        "speech_rate_log_deviation": abs(math.log(rate / reference_rate)),
    }
    unreliable = min(student.alignment.confidence, reference.alignment.confidence) < policy.min_alignment_confidence
    evidence_reasons = ("alignment_confidence_below_policy_minimum",) if unreliable else ()
    return _decision("fluency", measurements, policy.fluency_limits, FLUENCY_RUBRIC,
                     evidence_quality="degraded" if unreliable else "full",
                     evidence_reasons=evidence_reasons)


def _durations(features):
    return [max(0, syllable.duration_ms - sum(max(0, min(syllable.end_ms, p.end_ms)
             - max(syllable.start_ms, p.start_ms)) for p in features.pauses))
            for syllable in features.syllables]


def score_prosody(student: UtteranceFeatures, reference: UtteranceFeatures, policy: RubricPolicy):
    # Syllable medians form the sentence pitch envelope, rather than a lexical
    # tone correctness score. Both recordings are already in relative semitones.
    paired = [(i, median([v for _, v in s.f0_points]), median([v for _, v in r.f0_points]))
              for i, (s, r) in enumerate(zip(student.syllables, reference.syllables))
              if s.f0_points and r.f0_points]
    pairs = [(stu, ref) for _, stu, ref in paired]
    coverage = len(pairs) / len(student.syllables)
    stu, ref = [p[0] for p in pairs], [p[1] for p in pairs]
    contour_error = fmean(abs(s - r) for s, r in pairs) if pairs else 0
    contour_student = _resample_pitch(student)
    contour_reference = _resample_pitch(reference)
    contour_point_error = fmean(
        abs(a - b) for s, r in zip(contour_student, contour_reference)
        if s and r for a, b in zip(s, r)
    ) if any(contour_student) and any(contour_reference) else 0
    consecutive = [(stu - previous_stu, ref - previous_ref)
                   for (previous_i, previous_stu, previous_ref), (i, stu, ref) in zip(paired, paired[1:])
                   if i == previous_i + 1]
    movement_error = fmean(abs(a - b) for a, b in consecutive) if consecutive else 0
    st_values = [v for syllable in student.syllables for _, v in syllable.f0_points]
    ref_values = [v for syllable in reference.syllables for _, v in syllable.f0_points]
    def pitch_range(values):
        ordered = sorted(values)
        return ordered[int(.95 * (len(ordered) - 1))] - ordered[int(.05 * (len(ordered) - 1))] if ordered else 0
    # Positive-pitch percentile range ignores a few tracker outliers.
    st_range, ref_range = pitch_range(st_values), pitch_range(ref_values)
    st_durations, ref_durations = _durations(student), _durations(reference)
    valid_durations = bool(st_durations and ref_durations) and all(
        d > 0 for d in st_durations + ref_durations
    )
    logs = [math.log((s / sum(st_durations)) / (r / sum(ref_durations)))
            for s, r in zip(st_durations, ref_durations)] if valid_durations else []
    timing_error = fmean(abs(v) for v in logs) if logs else 0
    duration_rms_error = math.sqrt(fmean(v * v for v in logs)) if logs else 0
    student_shape = [math.log(d / _geometric_mean(st_durations)) for d in st_durations] if valid_durations else []
    reference_shape = [math.log(d / _geometric_mean(ref_durations)) for d in ref_durations] if valid_durations else []
    rate_stability_error = abs(pstdev(student_shape) - pstdev(reference_shape)) if logs else 0
    measurements = {
        "pitch_unit": "semitones_relative_to_own_median",
        "pitch_range": st_range, "reference_pitch_range": ref_range,
        "pitch_syllable_coverage": coverage, "pitch_envelope": stu, "reference_pitch_envelope": ref,
        "pitch_contour_samples": contour_student, "reference_pitch_contour_samples": contour_reference,
        "pitch_contour_mean_absolute_error": contour_error,
        "pitch_sample_mean_absolute_error": contour_point_error,
        "pitch_movement_mean_absolute_error": movement_error,
        "pitch_contour_similarity": math.exp(-contour_point_error / policy.pitch_distance_scale_semitones),
        "pitch_movement_similarity": math.exp(-movement_error / policy.pitch_distance_scale_semitones),
        "pitch_range_similarity": math.exp(-abs(math.log((st_range + policy.pitch_range_floor_semitones)
                                    / (ref_range + policy.pitch_range_floor_semitones)))),
        "syllable_durations_ms": st_durations, "reference_syllable_durations_ms": ref_durations,
        "relative_syllable_timing_log_ratios": logs,
        "rhythm_similarity": math.exp(-timing_error),
        "syllable_duration_similarity": math.exp(-duration_rms_error),
        "alignment_confidence": min(student.alignment.confidence, reference.alignment.confidence),
        "speaking_rate_stability": math.exp(-rate_stability_error),
    }
    unreliable = min(student.alignment.confidence, reference.alignment.confidence) < policy.min_alignment_confidence
    evidence_reasons = []
    degraded_features = set()
    if unreliable:
        evidence_reasons.append("alignment_confidence_below_policy_minimum")
        degraded_features.update({
            "pitch_contour_similarity", "pitch_movement_similarity", "pitch_range_similarity",
        })
    if coverage < policy.min_pitch_syllable_coverage:
        evidence_reasons.append("pitch_syllable_coverage_below_policy_minimum")
        degraded_features.update({
            "pitch_contour_similarity", "pitch_movement_similarity", "pitch_range_similarity",
        })
    if len(pairs) < 2:
        evidence_reasons.append("fewer_than_two_paired_pitch_syllables")
        degraded_features.update({
            "pitch_contour_similarity", "pitch_movement_similarity", "pitch_range_similarity",
        })
    if not valid_durations:
        evidence_reasons.append("invalid_syllable_duration_evidence")
        degraded_features.update({"rhythm_similarity", "speaking_rate_stability"})
    return _decision("prosody", measurements, policy.prosody_limits, PROSODY_RUBRIC,
                     minimum=True, degraded_features=degraded_features,
                     evidence_quality="degraded" if evidence_reasons else "full",
                     evidence_reasons=tuple(evidence_reasons))
