"""Create auditable, non-gold preannotations for verified NTU recordings.

The NTU corpus has transcripts and learner metadata, but no teacher-confirmed
tones, character timings, phone boundaries, or human audio-QC labels.  This
command runs the Experimental V2 projection and writes suggested character /
phone rows with an explicit ``needs_review`` status.  It must never be used as
the sealed KPI set or converted into gold labels automatically.

Example (repository root)::

    python backend/benchmarking/preannotate_ntu_v2.py \
      --sidecar backend/private-data/ntu_american_verified_sidecar.csv \
      --audio-root backend/private-data/ntu_speech_bank \
      --converted-root backend/private-data/ntu_speech_bank_wav \
      --output backend/reports/ntu_v2_preannotations.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

try:  # optional for metadata-only preparation environments
    import soundfile as sf
except ImportError:  # pragma: no cover
    sf = None  # type: ignore[assignment]

from annotation_schema import ANNOTATION_COLUMNS, blank_annotation_row


def _id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def load_sidecar(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle) if row.get("audio_path")]


def load_transcripts(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    texts = payload.get("texts", payload)
    if not isinstance(texts, dict):
        raise ValueError("transcript catalog must contain a texts mapping")
    result = {str(key): str(value).strip() for key, value in texts.items() if str(value).strip()}
    missing = [key for key in ("beginner", "intermediate") if key not in result]
    if missing:
        raise ValueError(f"transcript catalog missing: {', '.join(missing)}")
    return result


def resolve_audio(name: str, audio_root: Path, converted_root: Path | None = None) -> Path | None:
    """Resolve a sidecar path, preferring a decoded WAV when available."""

    stem = Path(name).stem
    if converted_root:
        exact = converted_root / f"{stem}.wav"
        if exact.is_file():
            return exact
        candidates = sorted(converted_root.glob(f"{stem}.*"))
        if candidates:
            return candidates[0]
    direct = audio_root / name
    if direct.is_file():
        return direct
    candidates = sorted(audio_root.glob(f"{stem}.*"))
    return candidates[0] if candidates else None


def _audio_metadata(path: Path) -> dict[str, Any]:
    if sf is None:
        return {"audio_qc_status": "needs_review", "audio_qc_reasons": "soundfile_not_installed"}
    try:
        with sf.SoundFile(path) as audio:
            duration_ms = round(float(audio.frames) / audio.samplerate * 1000, 3)
            return {
                "audio_duration_ms": duration_ms,
                "sample_rate_hz": int(audio.samplerate),
                "audio_qc_status": "needs_review",
                "audio_qc_expected_usable": "",
                "audio_qc_reasons": "technical metadata only; human review required",
            }
    except Exception as exc:
        return {
            "audio_qc_status": "needs_review",
            "audio_qc_reasons": f"decode_error:{type(exc).__name__}",
        }


def _project_rows(item: dict[str, str], audio: Path, records: Iterable[dict[str, Any]], model_version: str, schema_version: str) -> list[dict[str, Any]]:
    """Flatten V2 character/phone projections into review-ready schema rows."""

    transcript = item.get("transcript", "")
    recording_id = item.get("audio_path", audio.name)
    parent_id = _id("audio", recording_id)
    base = {
        "corpus": "NTU Speech Corpus for L2 Mandarin",
        "source_url": "https://sites.google.com/site/tehsinphono/resources/mandarin-learners-speech-bank",
        "audio_path": recording_id,
        "speaker_id": item.get("speaker_id", ""),
        "recording_id": recording_id,
        "learner_l1": item.get("learner_l1", ""),
        "level": item.get("level", ""),
        "transcript": transcript,
        "dataset_split": "unassigned",
        "is_sealed_test": False,
        "model_version": model_version,
        "schema_version": schema_version,
        "annotation_version": "ntu-v2-preannotation-v1",
        "annotator_id": "automated-preannotation",
        "review_status": "needs_review",
        "notes": "System projection only; not gold and not release-eligible.",
    }
    rows: list[dict[str, Any]] = []
    audio_row = blank_annotation_row({**base, "annotation_id": parent_id, **_audio_metadata(audio), "row_type": "audio", "audio_qc_status": "needs_review"})
    rows.append(audio_row)
    for record in records:
        char_index = int(record.get("char_index", len(rows)))
        char_id = _id("character", recording_id, str(char_index))
        probs = record.get("tone_probabilities") or {}
        char_row = blank_annotation_row({
            **base,
            "annotation_id": char_id,
            "parent_id": parent_id,
            "row_type": "character",
            "character_index": char_index,
            "character": record.get("char", ""),
            "pinyin": record.get("pinyin", ""),
            "expected_tone": f"T{record['expected_tone']}" if record.get("expected_tone") else "",
            "char_start_ms": round(float(record.get("start_time", 0)) * 1000, 3),
            "char_end_ms": round(float(record.get("end_time", 0)) * 1000, 3),
            # A non-empty projected interval is not evidence that an
            # aligner found a correct character boundary.  Keep this blank so
            # preannotations cannot inflate the character-alignment KPI.
            "alignment_success": "",
            "human_usable_boundary": "",
            "char_alignment_status": f"{record.get('character_boundary_source', 'auto_projection')}_needs_review",
            "tone_label_status": "auto_predicted_needs_review",
            "produced_tone": f"T{record['detected_tone']}" if record.get("detected_tone") else "Unknown",
            "tone_confidence": record.get("tone_confidence", ""),
            "tone_probability_t1": probs.get("1", ""),
            "tone_probability_t2": probs.get("2", ""),
            "tone_probability_t3": probs.get("3", ""),
            "tone_probability_t4": probs.get("4", ""),
            "tone_probability_t5": probs.get("5", ""),
            "notes": (
                "Auto-projected from V2; tone probabilities are uncalibrated relative evidence. "
                "Reviewer must confirm boundaries, tone and correctness."
            ),
        })
        rows.append(char_row)
        for phone_index, phone in enumerate(record.get("phones", []) or []):
            phone_id = _id("phone", recording_id, str(char_index), str(phone_index))
            phone_row = blank_annotation_row({
                **base,
                "annotation_id": phone_id,
                "parent_id": char_id,
                "row_type": "phone",
                "character_index": char_index,
                "character": record.get("char", ""),
                "pinyin": record.get("pinyin", ""),
                "phone_index": phone_index,
                "phone": phone.get("phone", ""),
                "phone_expected": phone.get("phone", ""),
                "phone_start_ms": round(float(phone.get("start_time", 0)) * 1000, 3),
                "phone_end_ms": round(float(phone.get("end_time", 0)) * 1000, 3),
                "phone_boundary_status": "auto_proposed_needs_review",
                "phone_gold_source": "system_projection_not_gold",
                "phone_confidence": phone.get("boundary_confidence", 0.0),
                "notes": (
                    f"Phone boundary source: {phone.get('boundary_source', 'proportional_within_character')}; "
                    "not acoustically aligned and must be replaced with a gold boundary."
                ),
            })
            rows.append(phone_row)
    return rows


async def _run_one(item: dict[str, str], audio: Path, timeout_seconds: float) -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import main  # type: ignore
    from routers.analysis_v2 import SCHEMA_VERSION, MODEL_VERSION, build_character_prosody

    transcript = item.get("transcript", "")
    started = time.perf_counter()
    base = {"audio_path": item.get("audio_path", audio.name), "source_audio": str(audio), "status": "failed", "gold_status": "not_gold"}
    try:
        # Corpus preparation must be fail-soft: an aligner/model stall on one
        # long recording cannot block all remaining review candidates.
        metrics = await asyncio.wait_for(
            main._do_analyze(audio.read_bytes(), transcript, ""),
            timeout=timeout_seconds,
        )
        records = build_character_prosody(metrics, transcript)
        rows = _project_rows(item, audio, records, MODEL_VERSION, SCHEMA_VERSION)
        return {
            **base,
            "status": "success",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "character_count": sum(row.get("row_type") == "character" for row in rows),
            "phone_count": sum(row.get("row_type") == "phone" for row in rows),
            "rows": rows,
        }
    except Exception as exc:  # fail-soft so one corrupt recording cannot stop corpus preparation
        return {**base, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error_type": type(exc).__name__, "error": str(exc), "rows": []}


async def _main(args: argparse.Namespace) -> int:
    items = load_sidecar(args.sidecar)
    transcripts = load_transcripts(args.transcripts)
    selected: list[tuple[dict[str, str], Path]] = []
    for item in items:
        key = item.get("transcript_key", "")
        if key in transcripts:
            item = {**item, "transcript": transcripts[key]}
        audio = resolve_audio(item.get("audio_path", ""), args.audio_root, args.converted_root)
        if audio is None:
            continue
        selected.append((item, audio))
    if args.limit:
        selected = selected[: args.limit]
    results: list[dict[str, Any]] = []
    for item, audio in selected:
        print(f"Preannotating {audio.name} ...", flush=True)
        results.append(await _run_one(item, audio, args.timeout_seconds))
    all_rows = [row for result in results for row in result.get("rows", [])]
    summary = {
        "analysis_version": "phoneme_tone_v2",
        "analysis_schema_version": "analysis_v2.character_phone.v2",
        "candidate_count": len(selected),
        "success_count": sum(result.get("status") == "success" for result in results),
        "failure_count": sum(result.get("status") != "success" for result in results),
        "gold_status": "not_gold",
        "release_eligible": False,
        "review_required": True,
        "note": "Preannotations are model suggestions; replace with human gold labels before KPI gating.",
        "results": results,
        "rows": all_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    fields = list(ANNOTATION_COLUMNS)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {len(results)} recording results and {len(all_rows)} review rows to {args.output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", type=Path, default=Path("backend/private-data/ntu_american_verified_sidecar.csv"))
    parser.add_argument("--transcripts", type=Path, default=Path("backend/benchmarking/ntu_transcript_catalog.json"))
    parser.add_argument("--audio-root", type=Path, default=Path("backend/private-data/ntu_speech_bank"))
    parser.add_argument("--converted-root", type=Path, default=Path("backend/private-data/ntu_speech_bank_wav"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=30.0,
                        help="Per-recording analysis limit; failures remain review rows, never block the batch")
    parser.add_argument("--output", type=Path, default=Path("backend/reports/ntu_v2_preannotations.json"))
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
