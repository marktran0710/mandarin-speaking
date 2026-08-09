"""Run non-destructive technical QC over downloaded NTU audio.

This check only measures whether a file can be decoded and basic signal health;
it never assigns tone, correctness, transcript or phone labels.  It emits an
auditable JSON/CSV report so annotation and KPI gating can use the same input
inventory.  ``soundfile`` handles WAV/FLAC/OGG and, when libsndfile supports
it, MP3.  Files such as M4A require an external decoder and are reported as
``decoder_unavailable`` rather than being silently dropped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    import soundfile as sf
except ImportError:  # pragma: no cover - clear error for minimal installs
    sf = None  # type: ignore[assignment]

AUDIO_EXTENSIONS = {".wav", ".m4a", ".mp3", ".flac", ".ogg", ".aac", ".webm"}
DEFAULT_BLOCK_FRAMES = 262_144


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_file(path: Path, root: Path, block_frames: int = DEFAULT_BLOCK_FRAMES) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    item: dict[str, Any] = {
        "audio_path": relative,
        "extension": path.suffix.lower(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "decode_status": "decoder_unavailable",
        "sample_rate_hz": None,
        "channels": None,
        "frames": None,
        "duration_ms": None,
        "subtype": None,
        "peak_abs": None,
        "rms_dbfs": None,
        "silence_ratio": None,
        "clipping_ratio": None,
        "qc_status": "needs_review",
        "qc_reasons": [],
    }
    if sf is None:
        item["qc_reasons"] = ["soundfile_not_installed"]
        return item
    try:
        with sf.SoundFile(path) as audio:
            item.update({
                "decode_status": "decoded",
                "sample_rate_hz": int(audio.samplerate),
                "channels": int(audio.channels),
                "frames": int(audio.frames),
                "duration_ms": round(float(audio.frames) / audio.samplerate * 1000, 3),
                "subtype": audio.subtype,
            })
            peak = 0.0
            sum_sq = 0.0
            count = 0
            silent = 0
            clipped = 0
            for block in audio.blocks(blocksize=block_frames, dtype="float32", always_2d=True):
                if block.size == 0:
                    continue
                abs_block = abs(block)
                peak = max(peak, float(abs_block.max()))
                sum_sq += float((block * block).sum())
                count += int(block.size)
                silent += int((abs_block.max(axis=1) < 1e-4).sum())
                clipped += int((abs_block.max(axis=1) >= 0.999).sum())
            item["peak_abs"] = round(peak, 6)
            item["rms_dbfs"] = round(20 * math.log10(max(math.sqrt(sum_sq / count), 1e-12)), 3) if count else None
            frame_count = int(item["frames"] or 0)
            item["silence_ratio"] = round(silent / frame_count, 6) if frame_count else None
            item["clipping_ratio"] = round(clipped / frame_count, 6) if frame_count else None
            reasons: list[str] = []
            if frame_count == 0:
                reasons.append("empty_audio")
            if item["duration_ms"] is not None and item["duration_ms"] < 500:
                reasons.append("very_short_under_500ms")
            if item["silence_ratio"] is not None and item["silence_ratio"] >= 0.98:
                reasons.append("near_silence")
            if item["clipping_ratio"] is not None and item["clipping_ratio"] >= 0.01:
                reasons.append("possible_clipping_over_1pct")
            if item["sample_rate_hz"] not in (16000, 22050, 24000, 44100, 48000):
                reasons.append("unusual_sample_rate")
            item["qc_reasons"] = reasons
            item["qc_status"] = "needs_review" if reasons else "technical_pass"
    except Exception as exc:  # decoder errors are data, not process crashes
        item["qc_reasons"] = ["decode_error:" + type(exc).__name__]
    return item


def scan(root: Path) -> dict[str, Any]:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)
    rows = [inspect_file(path, root) for path in files]
    by_hash: dict[str, list[str]] = {}
    for row in rows:
        by_hash.setdefault(row["sha256"], []).append(row["audio_path"])
    for row in rows:
        duplicates = by_hash.get(row["sha256"], [])
        row["duplicate_paths"] = [p for p in duplicates if p != row["audio_path"]]
        if row["duplicate_paths"]:
            row["qc_reasons"] = list(row["qc_reasons"]) + ["duplicate_content"]
            row["qc_status"] = "needs_review"
    decoded = [row for row in rows if row["decode_status"] == "decoded"]
    return {
        "schema_version": "ntu-audio-qc-v1",
        "root": str(root),
        "file_count": len(rows),
        "decoded_count": len(decoded),
        "decoder_unavailable_count": sum(row["decode_status"] != "decoded" for row in rows),
        "technical_pass_count": sum(row["qc_status"] == "technical_pass" for row in rows),
        "needs_review_count": sum(row["qc_status"] != "technical_pass" for row in rows),
        "duplicate_group_count": sum(len(paths) > 1 for paths in by_hash.values()),
        "sample_rate_counts": {str(rate): sum(row["sample_rate_hz"] == rate for row in rows) for rate in sorted({row["sample_rate_hz"] for row in rows if row["sample_rate_hz"] is not None})},
        "channel_counts": {str(ch): sum(row["channels"] == ch for row in rows) for ch in sorted({row["channels"] for row in rows if row["channels"] is not None})},
        "rows": rows,
        "labeling_note": "Technical QC only; tone, correctness, transcript and phone labels remain unassigned.",
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    rows = report["rows"]
    fields = [key for key in rows[0] if key != "qc_reasons"]
    fields += ["qc_reasons"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            copy = dict(row)
            copy["qc_reasons"] = ";".join(copy["qc_reasons"])
            writer.writerow(copy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("backend/reports/ntu_audio_qc.json"))
    args = parser.parse_args()
    if not args.root.exists():
        parser.error(f"Audio root does not exist: {args.root}")
    report = scan(args.root)
    write_report(report, args.output)
    print(json.dumps({key: report[key] for key in ("file_count", "decoded_count", "decoder_unavailable_count", "technical_pass_count", "needs_review_count", "duplicate_group_count")}, indent=2))
    print(f"Wrote {args.output} and {args.output.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
