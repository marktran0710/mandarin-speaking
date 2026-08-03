"""Run speaker-safe Mandarin tone benchmark reports from a scored CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from benchmarking.tone_validation import (
    ToneBenchmarkRow,
    build_evaluation_report,
    load_benchmark_csv,
    speaker_disjoint_split,
)
from chinese_tones import calculate_phrase_tone_accuracy, detect_tone
from praat_analyzer import extract_pitch


RAW_REQUIRED_COLUMNS = {
    "recording_id", "speaker_id", "audio_path", "expected_tone", "human_label",
}


def initialize_benchmark_workspace(output_dir: str | Path) -> tuple[Path, bool]:
    """Create a safe, git-ignored manifest workspace without overwriting data."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "audio").mkdir(exist_ok=True)
    manifest = root / "external_manifest.csv"
    created = not manifest.exists()
    if created:
        with manifest.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow([
                "recording_id", "speaker_id", "audio_path", "expected_tone",
                "human_label", "human_score",
            ])
    return manifest, created


def score_audio_manifest(
    input_path: str | Path,
    output_path: str | Path,
    error_path: str | Path,
) -> tuple[int, int]:
    """Run the production Praat/tone scorer over an external audio manifest.

    Audio paths are resolved relative to the manifest. Failed files are never
    assigned a zero pronunciation score; they are excluded and written to a
    separate error CSV so data-quality failures cannot masquerade as learner
    pronunciation errors.
    """

    manifest_path = Path(input_path).resolve()
    output = Path(output_path)
    errors_output = Path(error_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    errors_output.parent.mkdir(parents=True, exist_ok=True)

    scored_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, str]] = []
    seen_recordings: set[str] = set()
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = sorted(RAW_REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Missing required audio-manifest columns: {', '.join(missing)}")

        for line_number, raw in enumerate(reader, start=2):
            recording_id = (raw.get("recording_id") or "").strip()
            speaker_id = (raw.get("speaker_id") or "").strip()
            raw_audio_path = (raw.get("audio_path") or "").strip()
            try:
                if not recording_id or not speaker_id or not raw_audio_path:
                    raise ValueError("recording_id, speaker_id, and audio_path cannot be blank")
                if recording_id in seen_recordings:
                    raise ValueError(f"duplicate recording_id {recording_id!r}")
                seen_recordings.add(recording_id)

                expected_tone = int((raw.get("expected_tone") or "").strip())
                if expected_tone not in {1, 2, 3, 4}:
                    raise ValueError("expected_tone must be 1, 2, 3, or 4")

                audio_path = Path(raw_audio_path)
                if not audio_path.is_absolute():
                    audio_path = manifest_path.parent / audio_path
                audio_path = audio_path.resolve()
                if not audio_path.is_file():
                    raise ValueError(f"audio file not found: {audio_path}")

                contour = extract_pitch(str(audio_path))
                if len(contour) < 4:
                    raise ValueError("too few voiced pitch frames for a reliable tone score")
                system_score = calculate_phrase_tone_accuracy(contour, [expected_tone])
                detection = detect_tone(contour)

                scored_rows.append({
                    "recording_id": recording_id,
                    "speaker_id": speaker_id,
                    "audio_path": raw_audio_path,
                    "expected_tone": expected_tone,
                    "human_label": (raw.get("human_label") or "").strip(),
                    "system_score": round(float(system_score), 6),
                    "detected_tone": detection["detected_tone"],
                    "human_score": (raw.get("human_score") or "").strip(),
                    "pitch_frame_count": len(contour),
                    "detector_confidence": round(float(detection["confidence"]), 6),
                })
            except Exception as error:
                error_rows.append({
                    "line_number": str(line_number),
                    "recording_id": recording_id,
                    "speaker_id": speaker_id,
                    "audio_path": raw_audio_path,
                    "error": str(error),
                })

    scored_fields = [
        "recording_id", "speaker_id", "audio_path", "expected_tone", "human_label",
        "system_score", "detected_tone", "human_score", "pitch_frame_count",
        "detector_confidence",
    ]
    with output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=scored_fields)
        writer.writeheader()
        writer.writerows(scored_rows)

    with errors_output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=["line_number", "recording_id", "speaker_id", "audio_path", "error"],
        )
        writer.writeheader()
        writer.writerows(error_rows)

    if not scored_rows:
        raise ValueError(f"No recordings were scored; inspect {errors_output}")
    return len(scored_rows), len(error_rows)


def _write_split(path: Path, rows: list[ToneBenchmarkRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "recording_id", "speaker_id", "expected_tone", "human_label",
                "system_score", "detected_tone", "human_score",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "recording_id": row.recording_id,
                "speaker_id": row.speaker_id,
                "expected_tone": row.expected_tone,
                "human_label": str(row.human_label).lower(),
                "system_score": row.system_score,
                "detected_tone": row.detected_tone or "",
                "human_score": row.human_score if row.human_score is not None else "",
            })


def _write_report(path: str | Path, report: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _print_summary(report: dict[str, Any]) -> None:
    metrics = report["pass_fail_agreement"]
    def percentage(value: float | None) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    kappa = metrics["cohen_kappa"]
    kappa_text = "n/a" if kappa is None else f"{kappa:.3f}"
    print(
        "Agreement summary: "
        f"n={metrics['n']}, accuracy={percentage(metrics['accuracy'])}, "
        f"F1={percentage(metrics['f1'])}, kappa={kappa_text}, "
        f"disagreements={report['audit']['disagreement_count']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    initialize = subcommands.add_parser("init", help="create a manifest template and audio directory")
    initialize.add_argument("--output-dir", default="private-data", help="private benchmark workspace")

    evaluate = subcommands.add_parser("evaluate", help="write an external benchmark JSON report")
    evaluate.add_argument("--input", required=True, help="scored benchmark CSV")
    evaluate.add_argument("--output", required=True, help="report JSON path")
    evaluate.add_argument("--threshold", type=float, default=70.0, help="pre-selected system pass threshold")

    score = subcommands.add_parser("score", help="run Praat scoring over an external audio manifest")
    score.add_argument("--input", required=True, help="raw audio manifest CSV")
    score.add_argument("--output", required=True, help="scored benchmark CSV")
    score.add_argument("--errors", required=True, help="CSV for missing/unscorable audio")

    run = subcommands.add_parser("run", help="score audio and write a complete external report")
    run.add_argument("--input", required=True, help="raw audio manifest CSV")
    run.add_argument("--output-dir", required=True, help="directory for scored CSV, errors, and JSON report")
    run.add_argument("--threshold", type=float, default=70.0, help="pre-selected system pass threshold")

    split = subcommands.add_parser("split", help="make speaker-disjoint internal train/dev/test CSVs")
    split.add_argument("--input", required=True, help="labelled internal benchmark CSV")
    split.add_argument("--output-dir", required=True)
    split.add_argument("--train-ratio", type=float, default=0.7)
    split.add_argument("--dev-ratio", type=float, default=0.15)
    split.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.command == "init":
        manifest, created = initialize_benchmark_workspace(args.output_dir)
        state = "Created" if created else "Kept existing"
        print(f"{state} manifest: {manifest}")
        print(f"Copy WAV files into: {manifest.parent / 'audio'}")
        print("Add one CSV row per expert-labelled syllable, then run the benchmark command.")
        return

    input_path = Path(args.input)
    if not input_path.is_file():
        parser.exit(
            2,
            f"Error: input CSV not found: {input_path.resolve()}\n"
            "Create a template first with:\n"
            "  python -m scripts.benchmark_tones init --output-dir .\\private-data\n",
        )

    if args.command == "score":
        scored, failed = score_audio_manifest(args.input, args.output, args.errors)
        print(f"Scored {scored} recordings; {failed} failed. Output: {args.output}")
        if failed:
            print(f"Inspect failed rows before evaluation: {args.errors}")
        return

    if args.command == "run":
        output_dir = Path(args.output_dir)
        scored_path = output_dir / "external_scored.csv"
        errors_path = output_dir / "external_errors.csv"
        report_path = output_dir / "external_tone_report.json"
        scored, failed = score_audio_manifest(args.input, scored_path, errors_path)
        report = build_evaluation_report(
            load_benchmark_csv(scored_path), threshold=args.threshold
        )
        _write_report(report_path, report)
        print(f"Scored {scored} recordings; {failed} failed.")
        _print_summary(report)
        print(f"Full report: {report_path}")
        if failed:
            print(f"Inspect excluded recordings: {errors_path}")
        return

    rows = load_benchmark_csv(args.input)
    if args.command == "evaluate":
        report = build_evaluation_report(rows, threshold=args.threshold)
        output = _write_report(args.output, report)
        _print_summary(report)
        print(f"Wrote external benchmark report to {output}")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, split_rows in speaker_disjoint_split(
        rows, train_ratio=args.train_ratio, dev_ratio=args.dev_ratio, seed=args.seed
    ).items():
        _write_split(output_dir / f"{split_name}.csv", split_rows)
    print(f"Wrote speaker-disjoint splits to {output_dir}")


if __name__ == "__main__":
    main()
