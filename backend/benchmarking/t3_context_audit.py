"""T3-specific phonological/acoustic audit (Candidate E2-T3 groundwork).

    python -m benchmarking.t3_context_audit

**Candidate E V1 remains frozen.** This module imports
`benchmarking.candidates.contour_scorer_v2` read-only (STEP 5, to see how
the FROZEN scorer reacts to these contexts) and never edits it, never
touches `candidate_e_protocol.json`, and never changes T1/T2/T4 formulas.

**No OMPAL data anywhere.** Every audio file here is synthesized fresh by
`tts_service.py` (edge-tts), across multiple Mandarin voices (prioritizing
zh-TW, per the task) so no single voice's idiosyncrasies can determine the
findings.

STEP 3/4 are measurement and DESCRIPTIVE classification only — nothing in
this module labels a shape "correct" or "incorrect". STEP 5 runs the frozen
Candidate E V1 scorer to see how ITS OWN existing (already-frozen)
fall-then-rise requirement reacts to these shapes, which is evaluation of
the existing rule, not a correctness judgment on the audio.
"""

from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pypinyin import Style, pinyin

import tts_service
from praat_analyzer import extract_pitch
import chinese_tones
from benchmarking.candidates.contour_scorer_v2 import score_segment_v2, apply_onset_skip

AUDIO_DIR = Path("benchmarking/external/t3_context_audio")

CONTEXT_CSV = Path("benchmarking/results/t3_controlled_context.csv")
SHAPE_DISTRIBUTION_CSV = Path("benchmarking/results/t3_shape_distribution.csv")
AUDIT_MD = Path("benchmarking/results/t3_context_audit.md")
DESIGN_MD = Path("benchmarking/results/candidate_e2_t3_design.md")

#: zh-TW voices only, per "prioritizing zh-TW voices" and to avoid mixing in
#: zh-CN/zh-HK dialectal norms as a confound -- this whole project already
#: standardizes on Taiwan Mandarin (`taiwan_pinyin.apply()` in
#: chinese_tones.py). All three zh-TW neural voices edge-tts currently
#: offers are used, so "a single voice" can never determine a finding.
VOICES = ("zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural")

#: Same four characters the earlier controlled tone test used (媽麻馬罵,
#: ma1/ma2/ma3/ma4) -- reused deliberately for continuity with
#: Candidate D/E's existing controlled evidence, not because they're the
#: only valid choice.
BASE_CHARS = {1: "媽", 2: "麻", 3: "馬", 4: "罵"}
#: Fixed marker characters placed after a base character to create a
#: "base + following-tone-N" context, used identically for every base tone
#: so the following-tone variable is isolated (same marker regardless of
#: which base tone precedes it).
FOLLOWING_MARKERS = {1: "天", 2: "人", 3: "好", 4: "是"}
#: A single, neutral T1 syllable placed BEFORE the base character to create
#: a phrase-final context (base tone realized in sentence/phrase-final
#: position, preceded by a fixed T1 syllable).
PHRASE_INITIAL = "三"  # sān, T1

CONTEXTS = ("isolated", "plus_t1", "plus_t2", "plus_t3", "plus_t4", "phrase_final")


def _text_for(base_tone: int, context: str) -> tuple[str, int, int | None, int | None]:
    """Returns (text, position_of_base_in_text, preceding_tone, following_tone)."""
    base = BASE_CHARS[base_tone]
    if context == "isolated":
        return base, 0, None, None
    if context == "phrase_final":
        return PHRASE_INITIAL + base, 1, 1, None
    following_tone = int(context.rsplit("_t", 1)[1])
    return base + FOLLOWING_MARKERS[following_tone], 0, None, following_tone


def _pinyin_tone3(char: str) -> str:
    result = pinyin(char, style=Style.TONE3, neutral_tone_with_five=True)
    return result[0][0] if result else ""


def _resample_to_16k(pcm: np.ndarray, source_rate: int, target_rate: int = 16000) -> np.ndarray:
    if source_rate == target_rate:
        return pcm
    duration = len(pcm) / source_rate
    target_length = max(1, int(round(duration * target_rate)))
    return np.interp(
        np.linspace(0.0, len(pcm) - 1, target_length), np.arange(len(pcm)), pcm,
    ).astype(np.float32)


@dataclass(frozen=True)
class ContextItem:
    voice: str
    locale: str
    base_tone: int
    context: str
    text: str
    pinyin_full: str
    base_char: str
    base_pinyin: str
    position_index: int
    n_syllables: int
    preceding_tone: int | None
    following_tone: int | None
    audio_path: str


def build_item_list() -> list[ContextItem]:
    items = []
    for voice in VOICES:
        locale = "-".join(voice.split("-")[:2])
        for base_tone in (1, 2, 3, 4):
            for context in CONTEXTS:
                text, position, preceding, following = _text_for(base_tone, context)
                base_char = BASE_CHARS[base_tone]
                audio_path = AUDIO_DIR / f"{voice}_{base_tone}_{context}.wav"
                items.append(ContextItem(
                    voice=voice, locale=locale, base_tone=base_tone, context=context,
                    text=text, pinyin_full=_pinyin_tone3(text),
                    base_char=base_char, base_pinyin=_pinyin_tone3(base_char),
                    position_index=position, n_syllables=len(text),
                    preceding_tone=preceding, following_tone=following,
                    audio_path=str(audio_path),
                ))
    return items


# ---------------------------------------------------------------------------
# STEP 2 -- synthesize audio (skips files that already exist, so re-running
# this module is cheap)
# ---------------------------------------------------------------------------


async def generate_audio(items: list[ContextItem]) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(items):
        path = Path(item.audio_path)
        if path.exists():
            continue
        mp3_bytes = await tts_service.synthesize_sentence_mp3(item.text, voice=item.voice)
        pcm, source_rate = tts_service.decode_mp3_to_pcm(mp3_bytes)
        pcm_16k = _resample_to_16k(pcm, source_rate)
        tts_service.write_wav(str(path), pcm_16k, 16000)
        if (i + 1) % 20 == 0:
            print(f"  generated {i + 1}/{len(items)}")


# ---------------------------------------------------------------------------
# STEP 3 -- extract T3 (and control) shape WITHOUT scoring
# ---------------------------------------------------------------------------


def _linear_slope(seg: np.ndarray) -> float:
    n = len(seg)
    if n < 2:
        return 0.0
    x = np.arange(n)
    return float(np.polyfit(x, seg, 1)[0]) * (n - 1)


def _quarter_points(seg: np.ndarray) -> tuple[float, float, float, float, float]:
    n = len(seg)
    idx = lambda frac: min(n - 1, max(0, int(round(frac * (n - 1)))))
    return (
        float(seg[idx(0.0)]), float(seg[idx(0.25)]), float(seg[idx(0.5)]),
        float(seg[idx(0.75)]), float(seg[idx(1.0)]),
    )


def measure_item(item: ContextItem) -> dict[str, Any]:
    """Whole-file extraction (each file's OWN base-tone syllable is what we
    isolate -- for `isolated` and `plus_*` contexts, the base syllable is
    the FIRST syllable, so we take the first half of the file's frames as
    an approximate isolation; for `phrase_final`, the base is the SECOND
    syllable, so we take the second half). This is an approximation (no
    forced alignment is used, deliberately -- STEP 3 asks only to MEASURE,
    and a heuristic half-split keeps this simple and auditable rather than
    depending on `estimate_word_prosody`'s alignment machinery, which the
    T3 finding already showed can distort short syllables)."""
    raw_contour = extract_pitch(item.audio_path)
    if len(raw_contour) < 4:
        return {"error": "too few pitch frames"}

    if item.n_syllables == 1:
        syllable_contour = raw_contour
    elif item.position_index == 0:
        half = len(raw_contour) // 2
        syllable_contour = raw_contour[:half] if half >= 4 else raw_contour
    else:
        half = len(raw_contour) // 2
        syllable_contour = raw_contour[half:] if len(raw_contour) - half >= 4 else raw_contour

    normalized_full = chinese_tones.normalize_pitch_contour(syllable_contour)
    if len(normalized_full) < 4:
        return {"error": "too few normalized frames"}
    smoothed = chinese_tones._smooth_for_directional_scoring(normalized_full)

    start, q1, mid, q3, end = _quarter_points(smoothed)
    half_n = len(smoothed) // 2
    first_half, second_half = smoothed[: half_n + 1], smoothed[half_n:]
    full_slope = _linear_slope(smoothed)
    first_slope = _linear_slope(first_half)
    second_slope = _linear_slope(second_half)
    min_idx = int(np.argmin(smoothed))
    max_idx = int(np.argmax(smoothed))

    voiced_fraction = len(syllable_contour) / max(1, len(raw_contour)) if item.n_syllables > 1 else 1.0

    return {
        "n_raw_frames_whole_file": len(raw_contour),
        "n_frames_this_syllable": len(syllable_contour),
        "f0_start": round(start, 4),
        "f0_quarter": round(q1, 4),
        "f0_mid": round(mid, 4),
        "f0_three_quarter": round(q3, 4),
        "f0_end": round(end, 4),
        "first_half_slope": round(first_slope, 4),
        "second_half_slope": round(second_slope, 4),
        "full_slope": round(full_slope, 4),
        "f0_min_location_frac": round(min_idx / max(1, len(smoothed) - 1), 3),
        "f0_max_location_frac": round(max_idx / max(1, len(smoothed) - 1), 3),
        "range": round(float(np.max(smoothed) - np.min(smoothed)), 4),
        "duration_seconds": round(raw_contour[-1][0] - raw_contour[0][0], 4),
        "voiced_fraction_of_file": round(voiced_fraction, 3),
        "normalized_trajectory": [round(float(v), 4) for v in smoothed.tolist()],
        "error": "",
    }


# ---------------------------------------------------------------------------
# STEP 4 -- descriptive shape classification (NOT correct/incorrect)
# ---------------------------------------------------------------------------

#: Deterministic thresholds for the descriptive categories -- fixed here,
#: before looking at per-context/per-voice breakdowns, and applied
#: identically regardless of the item's nominal tone or context. A slope
#: magnitude below FLAT_SLOPE_EPS on BOTH halves is "low-flat"; a fall then
#: rise (both magnitudes above the eps) is "fall-rise"; a fall then a
#: further/continued fall (or non-rise) is "mostly-falling"; a rise then a
#: further rise (or non-fall) is "mostly-rising"; anything else (e.g.
#: rise-then-fall, the mirror image of a dip) is "other".
FLAT_SLOPE_EPS = 0.05


def classify_shape(first_slope: float, second_slope: float) -> str:
    first_flat = abs(first_slope) < FLAT_SLOPE_EPS
    second_flat = abs(second_slope) < FLAT_SLOPE_EPS
    if first_flat and second_flat:
        return "low-flat"
    if first_slope < -FLAT_SLOPE_EPS and second_slope > FLAT_SLOPE_EPS:
        return "fall-rise"
    if second_slope < -FLAT_SLOPE_EPS and first_slope > FLAT_SLOPE_EPS:
        return "rise-fall"
    if first_slope < -FLAT_SLOPE_EPS and not (second_slope > FLAT_SLOPE_EPS):
        return "mostly-falling"
    if first_slope > FLAT_SLOPE_EPS and not (second_slope < -FLAT_SLOPE_EPS):
        return "mostly-rising"
    if second_slope < -FLAT_SLOPE_EPS:
        return "mostly-falling"
    if second_slope > FLAT_SLOPE_EPS:
        return "mostly-rising"
    return "other"


# ---------------------------------------------------------------------------
# STEP 5 -- run the FROZEN Candidate E V1 scorer (read-only) on these tokens
# ---------------------------------------------------------------------------


def run_frozen_candidate_e(measurement: dict[str, Any], tone: int) -> dict[str, Any]:
    if measurement.get("error") or "normalized_trajectory" not in measurement:
        return {"candidate_e_score": None, "candidate_e_provenance": "not_measured"}
    seg = np.array(measurement["normalized_trajectory"])
    score, provenance = score_segment_v2(seg, tone)
    return {"candidate_e_score": round(score, 2), "candidate_e_provenance": provenance}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    items = build_item_list()
    print(f"Generating audio ({len(items)} items across {len(VOICES)} voices)...")
    asyncio.run(generate_audio(items))

    print("Measuring (STEP 3) + classifying (STEP 4) + scoring with frozen Candidate E (STEP 5)...")
    rows: list[dict[str, Any]] = []
    for item in items:
        measurement = measure_item(item)
        shape = (
            classify_shape(measurement["first_half_slope"], measurement["second_half_slope"])
            if not measurement.get("error")
            else "unmeasured"
        )
        frozen_result = run_frozen_candidate_e(measurement, item.base_tone)
        row = {**asdict(item), **measurement, "shape_category": shape, **frozen_result}
        row.pop("normalized_trajectory", None)  # kept in a sidecar, not the flat CSV
        rows.append(row)

    trajectories = {
        f"{item.voice}_{item.base_tone}_{item.context}": measure_item(item).get("normalized_trajectory")
        for item in items
    }
    trajectory_path = AUDIO_DIR / "normalized_trajectories.json"
    trajectory_path.write_text(json.dumps(trajectories, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_context_csv(rows)
    distribution = _build_shape_distribution(rows)
    _write_distribution_csv(distribution)

    return {"rows": rows, "distribution": distribution, "trajectory_path": str(trajectory_path)}


_CONTEXT_CSV_FIELDS = [
    "voice", "locale", "base_tone", "context", "text", "pinyin_full", "base_char", "base_pinyin",
    "position_index", "n_syllables", "preceding_tone", "following_tone", "audio_path",
    "n_raw_frames_whole_file", "n_frames_this_syllable",
    "f0_start", "f0_quarter", "f0_mid", "f0_three_quarter", "f0_end",
    "first_half_slope", "second_half_slope", "full_slope",
    "f0_min_location_frac", "f0_max_location_frac", "range", "duration_seconds",
    "voiced_fraction_of_file", "shape_category",
    "candidate_e_score", "candidate_e_provenance", "error",
]


def _write_context_csv(rows: list[dict[str, Any]], path: Path = CONTEXT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CONTEXT_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in _CONTEXT_CSV_FIELDS})


def _build_shape_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from collections import Counter

    dist = []
    # By (base_tone, context)
    groups: dict[tuple[int, str], list[str]] = {}
    for row in rows:
        groups.setdefault((row["base_tone"], row["context"]), []).append(row["shape_category"])
    for (tone, context), shapes in sorted(groups.items()):
        counts = Counter(shapes)
        total = len(shapes)
        for shape, count in sorted(counts.items()):
            dist.append({
                "grouping": "tone_x_context", "base_tone": tone, "context": context, "voice": "ALL",
                "shape_category": shape, "count": count, "total": total,
                "fraction": round(count / total, 3),
            })
    # By (base_tone, voice) -- across all contexts
    groups2: dict[tuple[int, str], list[str]] = {}
    for row in rows:
        groups2.setdefault((row["base_tone"], row["voice"]), []).append(row["shape_category"])
    for (tone, voice), shapes in sorted(groups2.items()):
        counts = Counter(shapes)
        total = len(shapes)
        for shape, count in sorted(counts.items()):
            dist.append({
                "grouping": "tone_x_voice", "base_tone": tone, "context": "ALL", "voice": voice,
                "shape_category": shape, "count": count, "total": total,
                "fraction": round(count / total, 3),
            })
    return dist


def _write_distribution_csv(rows: list[dict[str, Any]], path: Path = SHAPE_DISTRIBUTION_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    from benchmarking import report_t3_context_audit

    result = run()
    report_t3_context_audit.write_audit_report(result, AUDIT_MD)
    report_t3_context_audit.write_design_doc(result, DESIGN_MD)
    print(f"Context CSV: {CONTEXT_CSV}")
    print(f"Shape distribution CSV: {SHAPE_DISTRIBUTION_CSV}")
    print(f"Audit report: {AUDIT_MD}")
    print(f"Design doc: {DESIGN_MD}")
