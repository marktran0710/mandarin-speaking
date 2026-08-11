"""Per-syllable diagnostic features explaining WHY the tone scorer disagrees
with OMPAL's experts — not a second scorer, and not a step toward one.

``error_analysis.py`` establishes THAT the system disagrees with the human
panel and on which words. This module explains it, by attaching to each of
those same words the acoustic facts the frozen scorer already computed
internally but never wrote down: how long the syllable was, how much of it was
voiced, what its F0 actually did, and where in the utterance it sat.

The one rule every function here answers to: **the score must not move**.
`run_extraction` calls the exact same frozen entry point the cached results
came from (`praat_analyzer.analyze_all`), and before writing a single
diagnostic row it verifies that every re-computed character score and
pass/fail verdict is identical to what is already cached in
``private-data/ompal-scored.jsonl``. A mismatch anywhere aborts the run — see
`FrozenScoreMismatchError`. Everything beyond score/pass is measured
independently, read-only, by calling the same internal helpers
(`_aligner`, `_prosody_tokens`, `_load_sound`, `_intensity_contour_from_sound`,
`chinese_tones.normalize_pitch_contour`) a second time on the same audio —
never a re-implementation that could quietly drift from what scoring does.

What is honestly unavailable stays NA. The aligner never exposes a confidence
number for the boundaries it chooses (`tone_scoring.alignment.SyllableSpan`
carries only start/end), so `alignment_confidence` is NA throughout; the
closest available proxy — how far a syllable's duration sits from the
utterance's expected syllable duration, the same quantity the aligner's own
duration prior penalises — is reported separately as
`duration_plausibility_ratio` and never relabelled as a confidence score.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from benchmarking.agreement import majority_label
from benchmarking.error_analysis import NA
from benchmarking.ompal_corpus import OmpalUtterance, align_system_characters
from benchmarking.ompal_runner import flatten_characters
from benchmarking.stats import roc_auc, summary_stats

# ── Reused, unmodified, from the frozen scoring path ──────────────────────
# Imported rather than reimplemented so a diagnostic span or F0 reading can
# never quietly disagree with what the scorer itself used.
from chinese_tones import normalize_pitch_contour
from praat_analyzer import (
    PITCH_TIME_STEP,
    _aligner,
    _intensity_contour_from_sound,
    _load_sound,
    _prosody_tokens,
    analyze_all,
)

FIELDNAMES = [
    "audio_id",
    "speaker_id",
    "is_native",
    "join_source",
    "word",
    "pinyin",
    "expected_tone",
    "confusion_group",  # TP / TN / FP / FN — always populated (Step 3)
    "human_majority_tone_correct",
    "individual_rater_labels",
    "rater_panel_size",
    "system_tone_correct",
    "system_character_score",
    "threshold",
    "word_character_count",
    "syllable_index",
    "syllable_count",
    "utterance_position_normalized",
    "syllable_start_time",
    "syllable_end_time",
    "duration_seconds",
    "voiced_frame_count",
    "voiced_duration_seconds",
    "voiced_fraction",
    "f0_mean",
    "f0_median",
    "f0_min",
    "f0_max",
    "f0_range",
    "f0_start",
    "f0_mid",
    "f0_end",
    "f0_slope_full",
    "f0_slope_first_half",
    "f0_slope_second_half",
    "normalized_f0_start",
    "normalized_f0_mid",
    "normalized_f0_end",
    "energy_mean",
    "rms",
    "alignment_start",
    "alignment_end",
    "alignment_confidence",
    "alignment_source",
    "duration_plausibility_ratio",
    "diagnostic_status",
    "contour_match_score",
    "score_provenance",
    "audio_path",
]

CONFUSION_TP = "TP"
CONFUSION_TN = "TN"
CONFUSION_FP = "FP"
CONFUSION_FN = "FN"

#: Spans could not be recovered 1:1 against the scored characters for this
#: utterance (see ``_syllable_spans``) — every timing/F0/energy column is NA.
ALIGNMENT_UNAVAILABLE = "unavailable"
ALIGNMENT_ENERGY = "energy_aligner"


class FrozenScoreMismatchError(RuntimeError):
    """Raised when a re-computed score disagrees with the cached one.

    This is the one failure mode this module treats as fatal to the whole
    run: if it can happen, every other number in the diagnostics file is
    suspect, so nothing is written past this point. See the module docstring.
    """


@dataclass
class ExtractionResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    verified_utterances: int = 0
    span_unavailable_utterances: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (id, reason)


def _pypinyin_text(char: str) -> str:
    try:
        from pypinyin import Style, pinyin

        result = pinyin(char, style=Style.TONE, strict=False)
        return result[0][0] if result else NA
    except Exception:  # pragma: no cover - diagnostic convenience only
        return NA


def _frames_in_span(pitch_contour: Sequence[tuple[float, float]], start: float, end: float):
    return [(float(t), float(f)) for t, f in pitch_contour if start <= float(t) <= end]


def _slope(frames: Sequence[tuple[float, float]]) -> float | None:
    if len(frames) < 2:
        return None
    (t0, f0), (t1, f1) = frames[0], frames[-1]
    if t1 == t0:
        return None
    return (f1 - f0) / (t1 - t0)


def _f0_features(frames: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """F0 descriptive features over one syllable's voiced frames.

    Computed over the syllable's full [start, end] span, not the tone
    scorer's onset-skipped scoring window — the scorer trims the first ~12%
    of a word's frames to dodge coarticulation from the previous syllable
    before COMPUTING ITS SCORE, but that is a scoring decision, and this
    module measures the syllable as recorded, not as scored. The score itself
    is taken verbatim from the frozen pipeline, never recomputed here.
    """
    if len(frames) < 2:
        return {
            key: NA
            for key in (
                "f0_mean", "f0_median", "f0_min", "f0_max", "f0_range",
                "f0_start", "f0_mid", "f0_end",
                "f0_slope_full", "f0_slope_first_half", "f0_slope_second_half",
                "normalized_f0_start", "normalized_f0_mid", "normalized_f0_end",
            )
        }
    values = sorted(f for _, f in frames)
    n = len(frames)
    mid_index = n // 2
    half = max(1, n // 2)
    first_half, second_half = frames[:half], frames[half:] or frames[-2:]

    normalized = normalize_pitch_contour(frames)
    if len(normalized) >= 3:
        norm_start, norm_mid, norm_end = (
            float(normalized[0]), float(normalized[len(normalized) // 2]), float(normalized[-1]),
        )
    else:
        norm_start = norm_mid = norm_end = NA

    return {
        "f0_mean": sum(values) / n,
        "f0_median": values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2,
        "f0_min": values[0],
        "f0_max": values[-1],
        "f0_range": values[-1] - values[0],
        "f0_start": frames[0][1],
        "f0_mid": frames[mid_index][1],
        "f0_end": frames[-1][1],
        "f0_slope_full": _slope(frames) or NA,
        "f0_slope_first_half": _slope(first_half) or NA,
        "f0_slope_second_half": _slope(second_half) or NA,
        "normalized_f0_start": norm_start,
        "normalized_f0_mid": norm_mid,
        "normalized_f0_end": norm_end,
    }


def _energy_features(
    sound, intensity_contour: Sequence[tuple[float, float]], start: float, end: float
) -> dict[str, Any]:
    """Mean intensity (Praat, dB) and raw RMS within one syllable's span.

    Neither feeds the tone score. They exist to test goal item 5 — whether
    false rejections concentrate in quiet/short recordings — using the same
    RMS definition ``main._assess_recording_quality`` already uses for
    recording-level QC, applied here per syllable instead of per recording.
    """
    dip = [value for t, value in intensity_contour if start <= t <= end]
    energy_mean = sum(dip) / len(dip) if dip else NA
    try:
        total = float(sound.get_total_duration())
        clipped_start, clipped_end = max(0.0, start), min(total, end)
        if clipped_end <= clipped_start:
            rms = NA
        else:
            part = sound.extract_part(
                from_time=clipped_start, to_time=clipped_end, preserve_times=False
            )
            samples = part.values[0]
            rms = float((sum(sample * sample for sample in samples) / len(samples)) ** 0.5) if len(samples) else NA
    except Exception:  # pragma: no cover - defensive against edge-length spans
        rms = NA
    return {"energy_mean": energy_mean, "rms": rms}


def _syllable_spans(pitch_contour, text: str, intensity) -> list[tuple[float, float]] | None:
    """Recover the same per-syllable spans the frozen scorer used internally.

    Calls the identical aligner function (`praat_analyzer._aligner`) with the
    identical inputs `estimate_word_prosody` would have used — same
    tokenisation, same pitch contour, same intensity contour — so the result
    is not a re-implementation but the same computation run a second time.
    Returns None when the count does not match the transcript's syllable
    count (the same condition under which the scorer itself falls back to
    equal division per word rather than per-syllable spans), since in that
    case there is no reliable 1:1 correspondence to the flattened character
    list to report span data against.
    """
    tokens = _prosody_tokens(text)
    total_chars = sum(max(len(t), 1) for t in tokens)
    if not tokens or len(pitch_contour) < 2:
        return None
    spans = _aligner().align(pitch_contour, total_chars, intensity)
    if len(spans) != total_chars:
        return None
    return [(span.start, span.end) for span in spans]


def _confusion_group(human_correct: bool, system_correct: bool) -> str:
    if human_correct and system_correct:
        return CONFUSION_TP
    if not human_correct and not system_correct:
        return CONFUSION_TN
    if not human_correct and system_correct:
        return CONFUSION_FP
    return CONFUSION_FN


def extract_utterance_rows(
    utterance: OmpalUtterance,
    cached_row: dict[str, Any] | None,
    *,
    threshold: float,
    panel_size: int = 3,
) -> tuple[list[dict[str, Any]], bool]:
    """Diagnostic rows for one utterance, verified against its cached score.

    Returns ``(rows, span_available)``. Raises ``FrozenScoreMismatchError`` if
    the re-computed character scores disagree with the cache — the caller
    (`run_extraction`) treats that as fatal to the whole run.
    """
    if cached_row is None or cached_row.get("error"):
        return [], False

    (
        pitch_contour, _formants, _speech_rate, _fluency, _pitch_stats,
        word_prosody, _detected_tone, _tone_accuracy, _feedback, _pause,
    ) = analyze_all(str(utterance.wav_path), utterance.text)

    new_characters = flatten_characters(word_prosody)
    cached_characters = cached_row.get("characters") or []
    if len(new_characters) != len(cached_characters):
        raise FrozenScoreMismatchError(
            f"{utterance.utterance_id}: character count changed "
            f"({len(cached_characters)} cached vs {len(new_characters)} now)"
        )
    for index, (new, old) in enumerate(zip(new_characters, cached_characters)):
        if new["char"] != old.get("char"):
            raise FrozenScoreMismatchError(
                f"{utterance.utterance_id}[{index}]: char changed "
                f"{old.get('char')!r} -> {new['char']!r}"
            )
        if bool(new["judged"]) != bool(old.get("judged", True)):
            raise FrozenScoreMismatchError(
                f"{utterance.utterance_id}[{index}] {new['char']}: judged changed "
                f"{old.get('judged')} -> {new['judged']}"
            )
        if abs(float(new["score"]) - float(old.get("score") or 0.0)) > 1e-6:
            raise FrozenScoreMismatchError(
                f"{utterance.utterance_id}[{index}] {new['char']}: score changed "
                f"{old.get('score')} -> {new['score']}"
            )
        old_passed = float(old.get("score") or 0.0) >= threshold
        new_passed = float(new["score"]) >= threshold
        if old_passed != new_passed:
            raise FrozenScoreMismatchError(
                f"{utterance.utterance_id}[{index}] {new['char']}: pass/fail changed "
                f"at threshold {threshold}"
            )

    characters = [
        (str(entry.get("char") or ""), float(entry.get("score") or 0.0) >= threshold)
        for entry in new_characters
    ]
    word_verdicts = align_system_characters(utterance.words, characters)
    if word_verdicts is None:
        return [], False

    # Flat per-syllable record, in the same character order as `characters`,
    # carrying the diagnostic-layer fields (Phase 2) straight from
    # word_prosody rather than through flatten_characters, which discards them.
    flat_syllables: list[dict[str, Any]] = []
    for word in word_prosody or []:
        for syllable in word.get("syllables") or []:
            flat_syllables.append(syllable)

    spans = _syllable_spans(pitch_contour, utterance.text, intensity=None)
    # `intensity=None` above only affects which BOUNDARY CANDIDATES the
    # aligner considers, not whether `use_spans` was true for the *scored*
    # run (already verified via the character-level equality above); a
    # second recomputation with the intensity contour follows immediately
    # below once the sound is loaded, to match the scorer's own call exactly.
    sound = None
    intensity_contour: list[tuple[float, float]] = []
    if spans is not None:
        try:
            sound = _load_sound(str(utterance.wav_path))
            intensity_contour = _intensity_contour_from_sound(sound)
            spans = _syllable_spans(pitch_contour, utterance.text, intensity_contour)
        except Exception:
            spans = None

    span_available = spans is not None and len(spans) == len(flat_syllables)
    if span_available:
        durations = [end - start for start, end in spans]
        mean_duration = sum(durations) / len(durations) if durations else 0.0
    utterance_start = float(pitch_contour[0][0]) if pitch_contour else 0.0
    utterance_end = float(pitch_contour[-1][0]) if pitch_contour else 1.0
    utterance_span = max(utterance_end - utterance_start, 1e-6)

    rows: list[dict[str, Any]] = []
    position = 0
    for word, system_passed in zip(utterance.words, word_verdicts):
        panel = word.rater_tone_labels
        word_entries = new_characters[position : position + len(word.text)]
        # A word the analyzer declined to judge (too few pitch frames — see
        # `segment_judged` in estimate_word_prosody) scores a placeholder 0.0,
        # not a measurement. `error_analysis.build_rows` already excludes
        # these from TP/TN/FP/FN for exactly that reason; this row builder
        # must apply the identical exclusion, or "the system had nothing to
        # say" silently becomes "the system said wrong" in every downstream
        # count — the same conflation the four-state diagnosis (tone_decision.py)
        # exists to prevent, reintroduced here if this check were skipped.
        if not all(bool(entry.get("judged", True)) for entry in word_entries):
            position += len(word.text)
            continue
        if word.has_neutral_tone or len(panel) != panel_size:
            position += len(word.text)
            continue
        human_correct = majority_label(panel)
        if human_correct is None:
            position += len(word.text)
            continue

        char_scores = [
            round(float(entry.get("score") or 0.0), 1)
            for entry in new_characters[position : position + len(word.text)]
        ]
        for offset in range(len(word.text)):
            global_index = position + offset
            row: dict[str, Any] = {
                "audio_id": utterance.utterance_id,
                "speaker_id": utterance.speaker_id,
                "is_native": utterance.is_native,
                "join_source": utterance.join_source,
                "word": word.text[offset],
                "pinyin": _pypinyin_text(word.text[offset]),
                "expected_tone": (
                    word.expected_tones[offset]
                    if offset < len(word.expected_tones)
                    else NA
                ),
                "confusion_group": _confusion_group(bool(human_correct), bool(system_passed)),
                "human_majority_tone_correct": int(human_correct),
                "individual_rater_labels": "".join(str(int(label)) for label in panel),
                "rater_panel_size": len(panel),
                "system_tone_correct": int(system_passed),
                "system_character_score": (
                    char_scores[offset] if offset < len(char_scores) else NA
                ),
                "threshold": threshold,
                "word_character_count": len(word.text),
                "syllable_index": global_index,
                "syllable_count": len(flat_syllables),
                "utterance_position_normalized": NA,
                "syllable_start_time": NA,
                "syllable_end_time": NA,
                "duration_seconds": NA,
                "voiced_frame_count": NA,
                "voiced_duration_seconds": NA,
                "voiced_fraction": NA,
                "energy_mean": NA,
                "rms": NA,
                "alignment_start": NA,
                "alignment_end": NA,
                "alignment_confidence": NA,
                "alignment_source": ALIGNMENT_UNAVAILABLE,
                "duration_plausibility_ratio": NA,
                "diagnostic_status": NA,
                "contour_match_score": NA,
                "score_provenance": NA,
                "audio_path": str(utterance.wav_path),
            }
            row.update({key: NA for key in (
                "f0_mean", "f0_median", "f0_min", "f0_max", "f0_range",
                "f0_start", "f0_mid", "f0_end",
                "f0_slope_full", "f0_slope_first_half", "f0_slope_second_half",
                "normalized_f0_start", "normalized_f0_mid", "normalized_f0_end",
            )})

            if global_index < len(flat_syllables):
                syllable = flat_syllables[global_index]
                row["diagnostic_status"] = syllable.get("diagnostic_status", NA)
                row["contour_match_score"] = syllable.get("contour_match_score", NA)
                row["score_provenance"] = syllable.get("score_provenance", NA)

            if span_available and global_index < len(spans):
                start, end = spans[global_index]
                duration = end - start
                frames = _frames_in_span(pitch_contour, start, end)
                voiced_duration = len(frames) * PITCH_TIME_STEP
                row.update({
                    "utterance_position_normalized": round(
                        (start - utterance_start) / utterance_span, 4
                    ),
                    "syllable_start_time": round(start, 4),
                    "syllable_end_time": round(end, 4),
                    "duration_seconds": round(duration, 4),
                    "voiced_frame_count": len(frames),
                    "voiced_duration_seconds": round(voiced_duration, 4),
                    "voiced_fraction": (
                        round(min(voiced_duration / duration, 1.0), 4) if duration > 0 else NA
                    ),
                    "alignment_start": round(start, 4),
                    "alignment_end": round(end, 4),
                    "alignment_source": ALIGNMENT_ENERGY,
                    "duration_plausibility_ratio": (
                        round(duration / mean_duration, 4) if mean_duration > 0 else NA
                    ),
                })
                row.update(_f0_features(frames))
                if sound is not None:
                    row.update(_energy_features(sound, intensity_contour, start, end))

            rows.append(row)
        position += len(word.text)

    return rows, span_available


def run_extraction(
    utterances: Sequence[OmpalUtterance],
    cached_rows_by_id: dict[str, dict[str, Any]],
    *,
    threshold: float,
    log: Any = sys.stderr,
) -> ExtractionResult:
    """Extract diagnostics for every utterance, aborting on any score drift."""
    result = ExtractionResult()
    for position, utterance in enumerate(utterances, start=1):
        cached_row = cached_rows_by_id.get(utterance.utterance_id)
        try:
            rows, span_available = extract_utterance_rows(
                utterance, cached_row, threshold=threshold
            )
        except FrozenScoreMismatchError:
            raise
        except Exception as error:  # noqa: BLE001 - recorded, run continues
            result.failures.append((utterance.utterance_id, str(error)))
            continue
        result.rows.extend(rows)
        result.verified_utterances += 1
        if not span_available:
            result.span_unavailable_utterances += 1
        if log is not None and position % 100 == 0:
            print(
                f"  {position}/{len(utterances)} utterances "
                f"({len(result.rows)} rows, {len(result.failures)} failures)",
                file=log,
            )
    return result


def write_csv(rows: Sequence[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# ── Analysis (Steps 3-9): all read the extracted rows, none touch scoring ──


def _numeric(rows: Iterable[dict[str, Any]], field_name: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(field_name)
        if isinstance(value, (int, float)) and value != NA:
            values.append(float(value))
    return values


def group_comparison(
    rows: Sequence[dict[str, Any]], feature: str
) -> dict[str, dict[str, Any]]:
    """Step 3: descriptive stats for one feature, split by confusion group."""
    by_group: dict[str, list[dict[str, Any]]] = {
        CONFUSION_TP: [], CONFUSION_TN: [], CONFUSION_FP: [], CONFUSION_FN: [],
    }
    for row in rows:
        group = row.get("confusion_group")
        if group in by_group:
            by_group[group].append(row)
    return {
        group: summary_stats(_numeric(subset, feature))
        for group, subset in by_group.items()
    }


def per_tone_diagnostics(rows: Sequence[dict[str, Any]], feature: str) -> dict[str, Any]:
    """Step 4: the same group comparison, split by expected tone 1-4."""
    by_tone: dict[str, Any] = {}
    for tone in (1, 2, 3, 4):
        subset = [row for row in rows if row.get("expected_tone") == tone]
        by_tone[str(tone)] = {
            "n": len(subset),
            "false_rejection_rate": _confusion_rate(subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
            "false_acceptance_rate": _confusion_rate(subset, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
            "feature": group_comparison(subset, feature),
        }
    return by_tone


def _confusion_rate(
    rows: Sequence[dict[str, Any]], numerator_group: str, denominator_groups: set[str]
) -> float | None:
    denominator = sum(1 for row in rows if row.get("confusion_group") in denominator_groups)
    if denominator == 0:
        return None
    numerator = sum(1 for row in rows if row.get("confusion_group") == numerator_group)
    return numerator / denominator


def position_effect(rows: Sequence[dict[str, Any]], bins: int = 5) -> dict[str, Any]:
    """Step 5: false-rejection/acceptance rate by normalized utterance position."""
    edges = [i / bins for i in range(bins + 1)]
    result: dict[str, Any] = {}
    positioned = [row for row in rows if isinstance(row.get("utterance_position_normalized"), (int, float))]
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        subset = [
            row for row in positioned
            if low <= row["utterance_position_normalized"] < high
            or (index == bins - 1 and row["utterance_position_normalized"] == high)
        ]
        label = f"{low:.1f}-{high:.1f}"
        result[label] = {
            "n": len(subset),
            "false_rejection_rate": _confusion_rate(subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
            "false_acceptance_rate": _confusion_rate(subset, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
        }
    also_by_syllable_index: dict[str, Any] = {}
    max_index = max((row.get("syllable_index", 0) for row in rows), default=0)
    for index in range(min(max_index + 1, 12)):  # first syllables; long tail merged below
        subset = [row for row in rows if row.get("syllable_index") == index]
        if not subset:
            continue
        also_by_syllable_index[str(index)] = {
            "n": len(subset),
            "false_rejection_rate": _confusion_rate(subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
        }
    return {"by_normalized_position": result, "by_syllable_index": also_by_syllable_index}


def duration_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Step 6, first half: report the actual duration distribution before
    committing to bins, since the corpus's own spread should decide them."""
    return summary_stats(_numeric(rows, "duration_seconds"))


def duration_bins(
    rows: Sequence[dict[str, Any]], edges: Sequence[float]
) -> dict[str, Any]:
    """Step 6: accuracy / FR / FA per duration bin, and by tone within each."""
    labelled = list(edges) + [float("inf")]
    result: dict[str, Any] = {}
    for index in range(len(labelled) - 1):
        low, high = labelled[index], labelled[index + 1]
        label = f"{low:.2f}-{high:.2f}s" if high != float("inf") else f">{low:.2f}s"
        subset = [
            row for row in rows
            if isinstance(row.get("duration_seconds"), (int, float))
            and low <= row["duration_seconds"] < high
        ]
        by_tone = {}
        for tone in (1, 2, 3, 4):
            tone_subset = [row for row in subset if row.get("expected_tone") == tone]
            if not tone_subset:
                continue
            by_tone[str(tone)] = {
                "n": len(tone_subset),
                "false_rejection_rate": _confusion_rate(tone_subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
                "false_acceptance_rate": _confusion_rate(tone_subset, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
            }
        result[label] = {
            "n": len(subset),
            "accuracy": (
                sum(1 for r in subset if r["confusion_group"] in (CONFUSION_TP, CONFUSION_TN)) / len(subset)
                if subset else None
            ),
            "false_rejection_rate": _confusion_rate(subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
            "false_acceptance_rate": _confusion_rate(subset, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
            "by_tone": by_tone,
        }
    return result


def voicing_effect(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Step 7: outcome by voiced-fraction tercile — the closest available
    voicing-quality signal (no separate weak-voicing flag exists upstream)."""
    voiced = sorted(
        (row for row in rows if isinstance(row.get("voiced_fraction"), (int, float))),
        key=lambda row: row["voiced_fraction"],
    )
    if not voiced:
        return {"note": "no rows had a usable alignment; nothing to report"}
    third = max(1, len(voiced) // 3)
    buckets = {
        "low_voicing (bottom third)": voiced[:third],
        "mid_voicing": voiced[third : 2 * third],
        "high_voicing (top third)": voiced[2 * third :],
    }
    return {
        name: {
            "n": len(subset),
            "voiced_fraction_range": (
                round(subset[0]["voiced_fraction"], 3), round(subset[-1]["voiced_fraction"], 3),
            ) if subset else None,
            "false_rejection_rate": _confusion_rate(subset, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
            "false_acceptance_rate": _confusion_rate(subset, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
        }
        for name, subset in buckets.items()
    }


def score_discrimination(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Step 8: does the continuous score separate human-correct from
    human-incorrect at all, before any threshold is applied. Diagnostic only."""
    def auc_for(subset: Sequence[dict[str, Any]]) -> dict[str, Any]:
        scored = [
            row for row in subset
            if isinstance(row.get("system_character_score"), (int, float))
        ]
        if not scored:
            return {"n": 0, "auc": None}
        return {
            "n": len(scored),
            "auc": roc_auc(
                [row["system_character_score"] for row in scored],
                [bool(row["human_majority_tone_correct"]) for row in scored],
            ),
        }

    result = {"overall": auc_for(rows)}
    for tone in (1, 2, 3, 4):
        result[f"tone_{tone}"] = auc_for(
            [row for row in rows if row.get("expected_tone") == tone]
        )
    return result


def unanimous_subset(
    rows: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Step 9: repeat the headline analyses restricted to 000/111 rater panels.

    Separates "the scorer is wrong" from "the humans themselves disagreed" —
    a panel split 2-1 is a genuinely ambiguous item, and folding it into the
    same analysis as a unanimous one would blur the two failure modes.
    """
    unanimous = [
        row for row in rows
        if row.get("individual_rater_labels") in ("000", "111")
    ]
    return unanimous, {
        "n": len(unanimous),
        "accuracy": (
            sum(1 for r in unanimous if r["confusion_group"] in (CONFUSION_TP, CONFUSION_TN))
            / len(unanimous)
        ) if unanimous else None,
        "false_rejection_rate": _confusion_rate(unanimous, CONFUSION_FN, {CONFUSION_TP, CONFUSION_FN}),
        "false_acceptance_rate": _confusion_rate(unanimous, CONFUSION_FP, {CONFUSION_TN, CONFUSION_FP}),
        "auc": score_discrimination(unanimous)["overall"],
    }
