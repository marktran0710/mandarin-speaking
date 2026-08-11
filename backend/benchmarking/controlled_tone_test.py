"""CANDIDATE D — small, approved, controlled synthetic-audio smoke test.

    python -m benchmarking.controlled_tone_test

Goal (per the task that introduced this module): sanity-check the iFLYTEK
ISE adapter's field mapping and compare it against the current frozen local
tone scorer, using clean synthetic TTS audio where segmental content is held
constant and lexical tone is the only thing that varies. **This is not the
OMPAL validation study** -- it is a small, controlled diagnostic using audio
we generated ourselves.

DATA SAFETY, restated for this module specifically:

- **No OMPAL audio is read, referenced, or sent anywhere in this module.**
  Every audio file used here is synthesized fresh by `tts_service.py`
  (edge-tts) into `benchmarking/external/controlled_tone_test/audio/`, a
  directory this module owns entirely.
- `final_test` does not exist in this module's vocabulary at all -- there is
  no OMPAL split loading here, so there is nothing to guard with
  `FinalTestLockedError`; the guard that matters for this module is simply
  "never import or touch `private-data/ompal/`", which is verified by a
  test asserting the string doesn't appear in this file.
- Calling the real iFLYTEK API (STEP 4) requires `IFLYTEK_APP_ID`,
  `IFLYTEK_API_KEY`, `IFLYTEK_API_SECRET` in the environment. If they are
  not set, this module does NOT fabricate a result -- every iFLYTEK-derived
  field is written as NA and the report says plainly that the live call was
  not made, per the same discipline as the rest of this validation program:
  no invented numbers, ever.
"""

from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pypinyin import Style, pinyin

import tts_service
from praat_analyzer import analyze_all, extract_pitch
from benchmarking.external.iflytek_ise import (
    IflytekCredentials,
    IseResult,
    evaluate_utterance,
    map_tone_correctness,
)
from benchmarking.ompal_runner import flatten_characters
from benchmarking.ompal_report import PRODUCTION_THRESHOLD

AUDIO_DIR = Path("benchmarking/external/controlled_tone_test/audio")
PROVENANCE_CSV = Path("benchmarking/external/controlled_tone_test/audio_provenance.csv")

REPORT_PATH = Path("benchmarking/results/controlled_tone_test.md")
PREDICTIONS_CSV = Path("benchmarking/results/controlled_tone_predictions.csv")
ERRORS_CSV = Path("benchmarking/results/controlled_tone_errors.csv")

TTS_VOICE = tts_service.DEFAULT_ZH_VOICE  # "zh-TW-HsiaoChenNeural" -- same voice production uses
TARGET_SAMPLE_RATE = 16000  # matches iFLYTEK's requirement and this project's OMPAL convention

#: The two clean tone families named in the task. Same base syllable
#: (segmental content constant), one real character per tone 1-4.
TEST_FAMILIES: dict[str, tuple[str, str, str, str]] = {
    "ma": ("媽", "麻", "馬", "罵"),
    "shi": ("詩", "時", "史", "是"),
}


def _pinyin_tone3(char: str) -> str:
    result = pinyin(char, style=Style.TONE3, neutral_tone_with_five=True)
    return result[0][0] if result else ""


def _resample_to_16k(pcm: np.ndarray, source_rate: int) -> np.ndarray:
    """Linear-interpolation resample -- same simple approach
    `pronunciation/wav2vec_tone/extract_embeddings.py`'s `load_audio_16k_mono`
    already uses elsewhere in this project for the same purpose."""
    if source_rate == TARGET_SAMPLE_RATE:
        return pcm
    duration = len(pcm) / source_rate
    target_length = max(1, int(round(duration * TARGET_SAMPLE_RATE)))
    return np.interp(
        np.linspace(0.0, len(pcm) - 1, target_length),
        np.arange(len(pcm)),
        pcm,
    ).astype(np.float32)


# ---------------------------------------------------------------------------
# STEP 1 + 2 -- generate synthetic audio, build the crossed test-case design
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioProvenance:
    audio_file: str
    source: str
    generated_or_recorded: str
    text: str
    pinyin: str
    produced_tone: int


async def generate_audio_set() -> list[AudioProvenance]:
    """One recording per (family, tone) -- 8 files total. Skips synthesis
    for a file that already exists on disk, so re-running this is cheap."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    provenance: list[AudioProvenance] = []
    for family, characters in TEST_FAMILIES.items():
        for tone, character in enumerate(characters, start=1):
            audio_path = AUDIO_DIR / f"{family}{tone}.wav"
            if not audio_path.exists():
                mp3_bytes = await tts_service.synthesize_sentence_mp3(character, voice=TTS_VOICE)
                pcm, source_rate = tts_service.decode_mp3_to_pcm(mp3_bytes)
                pcm_16k = _resample_to_16k(pcm, source_rate)
                tts_service.write_wav(str(audio_path), pcm_16k, TARGET_SAMPLE_RATE)
            provenance.append(AudioProvenance(
                audio_file=str(audio_path),
                source=f"edge-tts ({TTS_VOICE})",
                generated_or_recorded="generated",
                text=character,
                pinyin=_pinyin_tone3(character),
                produced_tone=tone,
            ))
    with PROVENANCE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AudioProvenance.__dataclass_fields__))
        writer.writeheader()
        for entry in provenance:
            writer.writerow(asdict(entry))
    return provenance


@dataclass(frozen=True)
class TestCase:
    case_id: str
    family: str
    audio_file: str
    audio_character: str
    audio_pinyin: str
    audio_tone: int
    reference_character: str
    reference_pinyin: str
    reference_tone: int
    expected_tone_correct: int


def build_test_cases(provenance: list[AudioProvenance]) -> list[TestCase]:
    """Fully-crossed 4x4 design per family (produced tone x reference tone):
    32 cases total, 8 matched (diagonal) + 24 mismatched (off-diagonal),
    each of the 4 target/reference tones appearing exactly 8 times (2
    matched + 6 mismatched) across the two families -- a balanced design
    without any case-by-case hand selection."""
    by_family: dict[str, list[AudioProvenance]] = {}
    for entry in provenance:
        family = next(name for name, chars in TEST_FAMILIES.items() if entry.text in chars)
        by_family.setdefault(family, []).append(entry)

    cases: list[TestCase] = []
    for family, entries in by_family.items():
        entries_by_tone = {entry.produced_tone: entry for entry in entries}
        for produced_tone, audio_entry in sorted(entries_by_tone.items()):
            for reference_tone, reference_entry in sorted(entries_by_tone.items()):
                case_id = f"{family}_p{produced_tone}_r{reference_tone}"
                cases.append(TestCase(
                    case_id=case_id,
                    family=family,
                    audio_file=audio_entry.audio_file,
                    audio_character=audio_entry.text,
                    audio_pinyin=audio_entry.pinyin,
                    audio_tone=produced_tone,
                    reference_character=reference_entry.text,
                    reference_pinyin=reference_entry.pinyin,
                    reference_tone=reference_tone,
                    expected_tone_correct=int(produced_tone == reference_tone),
                ))
    return cases


# ---------------------------------------------------------------------------
# STEP 3 -- local F0 sanity check (diagnostic only, never filters a case)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class F0Summary:
    f0_start: float | None
    f0_mid: float | None
    f0_end: float | None
    f0_range: float | None
    duration: float | None
    voiced_frame_count: int


def verify_f0(audio_path: str) -> F0Summary:
    contour = extract_pitch(audio_path)
    if len(contour) < 2:
        return F0Summary(None, None, None, None, None, len(contour))
    times = [point[0] for point in contour]
    freqs = [point[1] for point in contour]
    mid_index = len(freqs) // 2
    return F0Summary(
        f0_start=float(freqs[0]),
        f0_mid=float(freqs[mid_index]),
        f0_end=float(freqs[-1]),
        f0_range=float(max(freqs) - min(freqs)),
        duration=float(times[-1] - times[0]),
        voiced_frame_count=len(contour),
    )


# ---------------------------------------------------------------------------
# STEP 4 -- iFLYTEK (real call if credentials exist; NA, not fabricated,
# otherwise)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IflytekOutcome:
    ran: bool
    reason_not_run: str | None
    raw_response: str | None
    tone_score: float | None
    phone_score: float | None
    mono_tone: str | None
    perr_msg: str | None
    perr_level_msg: str | None
    is_yun: str | None
    dp_message: str | None
    derived_external_tone_correct: int | None


def run_iflytek_case(case: TestCase, credentials: IflytekCredentials | None) -> IflytekOutcome:
    if credentials is None:
        return IflytekOutcome(
            ran=False, reason_not_run="no IFLYTEK_* credentials in environment",
            raw_response=None, tone_score=None, phone_score=None, mono_tone=None,
            perr_msg=None, perr_level_msg=None, is_yun=None, dp_message=None,
            derived_external_tone_correct=None,
        )
    result = evaluate_utterance(
        Path(case.audio_file), case.reference_character, credentials=credentials, dry_run=False,
    )
    if not isinstance(result, IseResult):
        return IflytekOutcome(
            ran=False, reason_not_run="evaluate_utterance did not return a parsed IseResult",
            raw_response=None, tone_score=None, phone_score=None, mono_tone=None,
            perr_msg=None, perr_level_msg=None, is_yun=None, dp_message=None,
            derived_external_tone_correct=None,
        )
    if not result.syllables:
        return IflytekOutcome(
            ran=True, reason_not_run="response parsed but contained no <syll> nodes",
            raw_response=result.raw_response, tone_score=result.tone_score,
            phone_score=result.phone_score, mono_tone=None, perr_msg=None,
            perr_level_msg=None, is_yun=None, dp_message=None,
            derived_external_tone_correct=None,
        )
    syllable = result.syllables[0]  # one syllable per case, by construction
    yun_phones = [phone for phone in syllable.phones if phone.is_yun == "1"]
    yun_phone = yun_phones[0] if len(yun_phones) == 1 else None
    return IflytekOutcome(
        ran=True, reason_not_run=None,
        raw_response=result.raw_response,
        tone_score=result.tone_score,
        phone_score=result.phone_score,
        mono_tone=syllable.mono_tone,
        perr_msg=yun_phone.perr_msg if yun_phone else None,
        perr_level_msg=yun_phone.perr_level_msg if yun_phone else None,
        is_yun=yun_phone.is_yun if yun_phone else None,
        dp_message=syllable.dp_message,
        derived_external_tone_correct=map_tone_correctness(syllable),
    )


# ---------------------------------------------------------------------------
# STEP 5 -- current frozen local scorer (analyze_all, unmodified)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalOutcome:
    current_score: float | None
    judged: bool
    current_pass_fail: int | None  # None (NA) when judged is False


def run_local_scorer_case(case: TestCase) -> LocalOutcome:
    (
        _pitch_contour, _formants, _speech_rate, _fluency, _pitch_stats,
        word_prosody, _detected_tone, _tone_accuracy, _feedback, _pause,
    ) = analyze_all(case.audio_file, case.reference_character)
    characters = flatten_characters(word_prosody)
    if not characters:
        return LocalOutcome(current_score=None, judged=False, current_pass_fail=None)
    entry = characters[0]  # one character per case, by construction
    if not entry["judged"]:
        return LocalOutcome(current_score=entry["score"], judged=False, current_pass_fail=None)
    return LocalOutcome(
        current_score=entry["score"], judged=True,
        current_pass_fail=int(entry["score"] >= PRODUCTION_THRESHOLD),
    )


# ---------------------------------------------------------------------------
# STEP 6 + 7 -- comparison metrics and A/B/C/D error categories
# ---------------------------------------------------------------------------


def error_category(expected: int, current: int | None, external: int | None) -> str:
    if external is None:
        return "IFLYTEK_NOT_RUN"
    if current is None:
        return "CURRENT_NOT_JUDGED"
    current_correct = current == expected
    external_correct = external == expected
    if not current_correct and external_correct:
        return "A_current_wrong_iflytek_correct"
    if current_correct and not external_correct:
        return "B_current_correct_iflytek_wrong"
    if not current_correct and not external_correct:
        return "C_both_wrong"
    return "D_both_correct"


def confusion_metrics(expected: list[int], predicted: list[int | None]) -> dict[str, Any]:
    """Accuracy / balanced accuracy / sensitivity / specificity / FRR / FAR
    against KNOWN test-construction ground truth (not human ratings this
    time). Rows where `predicted` is None (NA -- not judged / not run) are
    excluded, matching this whole program's established judged-exclusion
    discipline."""
    pairs = [(e, p) for e, p in zip(expected, predicted) if p is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "accuracy": None, "balanced_accuracy": None, "sensitivity": None,
                "specificity": None, "false_rejection_rate": None, "false_acceptance_rate": None}
    tp = sum(1 for e, p in pairs if e == 1 and p == 1)
    tn = sum(1 for e, p in pairs if e == 0 and p == 0)
    fp = sum(1 for e, p in pairs if e == 0 and p == 1)
    fn = sum(1 for e, p in pairs if e == 1 and p == 0)
    sensitivity = tp / (tp + fn) if (tp + fn) else None
    specificity = tn / (tn + fp) if (tn + fp) else None
    balanced_accuracy = (
        (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None
    )
    return {
        "n": n,
        "accuracy": (tp + tn) / n,
        "balanced_accuracy": balanced_accuracy,
        "sensitivity": sensitivity,
        "specificity": specificity,
        # A learner's-eye framing, consistent with the rest of this program:
        # false rejection = a correct (expected=1) case wrongly marked wrong;
        # false acceptance = an incorrect (expected=0) case wrongly marked right.
        "false_rejection_rate": fn / (tp + fn) if (tp + fn) else None,
        "false_acceptance_rate": fp / (tn + fp) if (tn + fp) else None,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    provenance = asyncio.run(generate_audio_set())
    cases = build_test_cases(provenance)

    try:
        credentials = IflytekCredentials.from_env()
    except RuntimeError as error:
        credentials = None
        credentials_error = str(error)
    else:
        credentials_error = None

    rows: list[dict[str, Any]] = []
    for case in cases:
        f0 = verify_f0(case.audio_file)
        iflytek = run_iflytek_case(case, credentials)
        local = run_local_scorer_case(case)
        category = error_category(case.expected_tone_correct, local.current_pass_fail, iflytek.derived_external_tone_correct)
        rows.append({
            **asdict(case),
            **asdict(f0),
            "raw_iflytek_response": iflytek.raw_response,
            "iflytek_ran": iflytek.ran,
            "iflytek_not_run_reason": iflytek.reason_not_run,
            "tone_score": iflytek.tone_score,
            "phone_score": iflytek.phone_score,
            "mono_tone": iflytek.mono_tone,
            "perr_msg": iflytek.perr_msg,
            "perr_level_msg": iflytek.perr_level_msg,
            "is_yun": iflytek.is_yun,
            "dp_message": iflytek.dp_message,
            "derived_external_tone_correct": iflytek.derived_external_tone_correct,
            "current_score": local.current_score,
            "current_judged": local.judged,
            "current_pass_fail": local.current_pass_fail,
            "error_category": category,
        })

    expected = [row["expected_tone_correct"] for row in rows]
    current_predicted = [row["current_pass_fail"] for row in rows]
    external_predicted = [row["derived_external_tone_correct"] for row in rows]

    overall = {
        "current": confusion_metrics(expected, current_predicted),
        "iflytek": confusion_metrics(expected, external_predicted),
    }
    by_target_tone: dict[int, dict[str, Any]] = {}
    for tone in (1, 2, 3, 4):
        tone_rows = [row for row in rows if row["reference_tone"] == tone]
        by_target_tone[tone] = {
            "current": confusion_metrics(
                [r["expected_tone_correct"] for r in tone_rows],
                [r["current_pass_fail"] for r in tone_rows],
            ),
            "iflytek": confusion_metrics(
                [r["expected_tone_correct"] for r in tone_rows],
                [r["derived_external_tone_correct"] for r in tone_rows],
            ),
        }

    _write_predictions_csv(rows)
    _write_errors_csv(rows)

    return {
        "rows": rows,
        "n_cases": len(rows),
        "credentials_available": credentials is not None,
        "credentials_error": credentials_error,
        "overall": overall,
        "by_target_tone": by_target_tone,
    }


_PREDICTIONS_FIELDNAMES = [
    "case_id", "family", "audio_file", "audio_character", "audio_pinyin", "audio_tone",
    "reference_character", "reference_pinyin", "reference_tone", "expected_tone_correct",
    "f0_start", "f0_mid", "f0_end", "f0_range", "duration", "voiced_frame_count",
    "iflytek_ran", "iflytek_not_run_reason", "tone_score", "phone_score", "mono_tone",
    "perr_msg", "perr_level_msg", "is_yun", "dp_message", "derived_external_tone_correct",
    "current_score", "current_judged", "current_pass_fail", "error_category",
    "raw_iflytek_response",
]


def _write_predictions_csv(rows: list[dict[str, Any]], path: Path = PREDICTIONS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_PREDICTIONS_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in _PREDICTIONS_FIELDNAMES})


def _write_errors_csv(rows: list[dict[str, Any]], path: Path = ERRORS_CSV) -> None:
    """Every case with its A/B/C/D (or IFLYTEK_NOT_RUN) category, plus the F0
    diagnostic summary and raw iFLYTEK error fields -- per STEP 7."""
    fieldnames = [
        "case_id", "error_category", "family",
        "reference_character", "reference_tone", "audio_character", "audio_tone",
        "expected_tone_correct", "current_pass_fail", "current_score",
        "derived_external_tone_correct", "perr_msg", "perr_level_msg", "is_yun", "mono_tone", "dp_message",
        "f0_start", "f0_mid", "f0_end", "f0_range", "duration",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


if __name__ == "__main__":
    from benchmarking import report_controlled_tone_test

    result = run()
    report_controlled_tone_test.write_report(result)
    print(f"{result['n_cases']} cases run.")
    print(f"iFLYTEK credentials available: {result['credentials_available']}")
    print(f"Predictions written to {PREDICTIONS_CSV}")
    print(f"Errors written to {ERRORS_CSV}")
    print(f"Report written to {REPORT_PATH}")
