"""Create an auditable manifest from the NTU Mandarin Learners Speech Bank.

The public page provides recordings and reading passages, but not learner tone
correctness labels or gold phone boundaries.  This importer therefore marks
those fields as ``needs_annotation`` rather than inventing labels.  It is safe
to run after downloading the Google Drive folders into a local directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

try:  # package import (pytest/module use)
    from benchmarking.annotation_schema import blank_annotation_row
except ModuleNotFoundError:  # direct ``python path/to/import_ntu_speech_bank.py``
    from annotation_schema import blank_annotation_row

SOURCE_URL = "https://sites.google.com/site/tehsinphono/resources/mandarin-learners-speech-bank"
AUDIO_EXTENSIONS = {".wav", ".m4a", ".mp3", ".flac", ".ogg"}


def _speaker_id(path: Path) -> str:
    # NTU downloads are often flattened and use identifiers such as S1,
    # JF2, or ``text2_S11`` in the filename.  Do not fall back to the corpus
    # directory (which would incorrectly assign every file to one speaker).
    for index, part in enumerate(reversed(path.parts)):
        # Strip the extension from the filename; otherwise ``M3.mp3`` can
        # accidentally match the ``MP3`` codec suffix as a speaker id.
        if index == 0:
            part = Path(part).stem
        named = re.search(r"(?:speaker|spk)[-_ ]?(\d+)", part, re.IGNORECASE)
        if named:
            return named.group(1)
        matches = re.findall(r"(?<![A-Za-z0-9])([A-Za-z]{1,3}\d+)(?![A-Za-z0-9])", part, re.IGNORECASE)
        if matches:
            return matches[-1].upper()
    return "unknown"


def _group_label(path: Path) -> tuple[str, str]:
    text = "/".join(path.parts).lower()
    language = next((name for name in ("american", "japanese", "french", "spanish") if name in text), "unknown")
    level = "intermediate" if "intermediate" in text else "beginner" if "beginner" in text else "unknown"
    return language, level


def load_sidecar(path: Path | Iterable[Path] | None) -> dict[str, dict[str, str]]:
    """Load one or more sidecars, preserving auditable precedence.

    Multiple sidecars are useful when a corpus has a verified public-source
    mapping plus a separate local mapping (for example, American named files).
    Later files override earlier rows for the same path, so callers can make
    precedence explicit.  Missing files are ignored to keep metadata-only
    preparation fail-soft.
    """
    if path is None:
        return {}
    paths = [path] if isinstance(path, Path) else list(path)
    result: dict[str, dict[str, str]] = {}
    for sidecar_path in paths:
        if not sidecar_path or not sidecar_path.exists():
            continue
        with sidecar_path.open(encoding="utf-8", newline="") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                key = (row.get("audio_path") or row.get("path") or row.get("file") or "").replace("\\", "/")
                if key:
                    result[key] = row
                    result[Path(key).name] = row
    return result


def load_transcript_catalog(path: Path | None) -> dict[str, str]:
    """Load named public passages without silently guessing a passage."""
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    texts = payload.get("texts", {})
    return {str(key): str(value) for key, value in texts.items() if value}


def build_manifest(
    root: Path,
    sidecar: Path | None = None,
    transcript_catalog: Path | None = None,
) -> list[dict[str, Any]]:
    lookup = load_sidecar(sidecar)
    catalog = load_transcript_catalog(transcript_catalog)
    rows: list[dict[str, Any]] = []
    for audio in sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS):
        relative = audio.relative_to(root).as_posix()
        metadata = lookup.get(relative, lookup.get(audio.name, {}))
        language, level = _group_label(audio)
        transcript_key = (metadata.get("transcript_key") or "").strip().lower()
        catalog_transcript = catalog.get(transcript_key, "")
        recording_id = metadata.get("recording_id") or relative
        annotation_id = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]
        row = blank_annotation_row({
            "annotation_id": annotation_id,
            "recording_id": recording_id,
            "corpus": "NTU Speech Corpus for L2 Mandarin",
            "source_url": SOURCE_URL,
            "audio_path": relative,
            "speaker_id": metadata.get("speaker_id") or _speaker_id(audio),
            "learner_l1": metadata.get("learner_l1") or language,
            "level": metadata.get("level") or level,
            "transcript": metadata.get("transcript") or metadata.get("text") or catalog_transcript,
            "expected_pinyin": metadata.get("expected_pinyin") or "",
            "expected_tone": metadata.get("expected_tone") or "",
            "produced_tone": "",
            "correct_incorrect": "",
            "phone_boundary_status": "needs_annotation",
            "tone_label_status": "needs_annotation",
            "audio_qc_status": "needs_review",
            "consent_note": "Corpus page states participants consented to publication; retain source citation.",
        })
        # Keep the historical ``level`` field and preserve sidecar metadata;
        # all annotation-only fields remain blank/default until reviewed.
        rows.append(row)
    return rows


def write_manifest(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["corpus", "source_url", "audio_path", "speaker_id"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Downloaded NTU Speech Bank directory")
    parser.add_argument(
        "--sidecar",
        type=Path,
        action="append",
        help="Optional CSV with transcript/speaker metadata (repeat for multiple sidecars)",
    )
    parser.add_argument(
        "--transcript-catalog",
        type=Path,
        help="Optional UTF-8 JSON catalog; sidecar rows may select a passage with transcript_key",
    )
    parser.add_argument("--output", type=Path, default=Path("backend/private-data/ntu_speech_bank_manifest.csv"))
    args = parser.parse_args()
    if not args.root.exists():
        parser.error(f"Audio root does not exist: {args.root}")
    rows = build_manifest(args.root, args.sidecar, args.transcript_catalog)
    write_manifest(rows, args.output)
    print(f"Wrote {len(rows)} audio rows to {args.output}")
    print("Tone/correctness and phone labels remain needs_annotation; this manifest is not a release benchmark by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
