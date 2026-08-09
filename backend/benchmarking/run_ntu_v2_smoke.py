"""Run a bounded, auditable smoke pass of NTU audio through Experimental V2.

This command checks that downloaded WAV files can reach the existing V2
character/phone/tone projection.  It deliberately does *not* calculate a
benchmark score: NTU recordings do not ship with produced-tone, phone-boundary
or audio-QC gold labels.  Rows therefore carry ``gold_status=missing``.

Example (from the repository root)::

    python backend/benchmarking/run_ntu_v2_smoke.py \
      --audio-root backend/private-data/ntu_speech_bank \
      --level beginner --limit 3 \
      --output backend/reports/ntu_v2_smoke.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


BEGINNER = "他們都很忙。我家有四口人：爸爸媽媽哥哥和我。我家還有一隻小黑狗和一隻大花貓。我父親是一個有名的大夫。我母親是中學英語老師。他們都非常忙。我哥哥是大學生，學中文。他個子很高、比較胖。他的同學都叫他胖子。他的女朋友很漂亮，是日本人。我的小狗叫黑黑。小貓的名字呢，是花花。你看，這是我們家。我們家的房子不大也不小。有四個房間。還有一個非常好看的小花園。我的房間不太大。裡邊有一張小桌子兩把椅子和一張床。"
INTERMEDIATE = "今天早上我有一節聽力課。大概昨天夜裡沒睡好，所以起晚了。這下我急壞了，因為開學才半個多月，我已經遲到過兩次了！老師不但記住了我的名字，而且還說，下一次我要是再遲到的話，他就不讓我進教室了。"


def _load_transcript_catalog(path: Path, level: str) -> str:
    """Load the UTF-8 public passage instead of embedding a lossy copy."""
    if not path.exists():
        raise SystemExit(f"Transcript catalog does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    transcript = str((payload.get("texts") or {}).get(level) or "").strip()
    if not transcript:
        raise SystemExit(f"Transcript catalog has no {level!r} passage: {path}")
    return transcript


def _chars(result: Any) -> list[dict[str, Any]]:
    return list(getattr(result, "character_prosody", []) or [])


async def _run(audio: Path, transcript: str) -> dict[str, Any]:
    # Lazy imports keep ``--help`` usable even when the server dependencies
    # are not installed in a data-preparation environment.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import main  # type: ignore
    from routers.analysis_v2 import build_character_prosody

    started = time.perf_counter()
    content = audio.read_bytes()
    row: dict[str, Any] = {
        "audio_path": audio.as_posix(),
        "audio_bytes": len(content),
        "transcript_level": "provided_by_user",
        "gold_status": "missing",
        "audio_qc_status": "needs_review",
        "phone_boundary_status": "needs_annotation",
        "tone_label_status": "needs_annotation",
    }
    try:
        result = await main._do_analyze(content, transcript, "")
        records = build_character_prosody(result, transcript)
        row.update(
            {
                "status": "success",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "word_count": len(getattr(result, "word_prosody", []) or []),
                "pitch_points": len(getattr(result, "pitch_contour", []) or []),
                "detected_tone": getattr(result, "detected_tone", None),
                "character_count": len(records),
                "tone_status_counts": {
                    status: sum(1 for record in records if record.get("tone_status") == status)
                    for status in sorted({record.get("tone_status") for record in records})
                },
                "character_prosody": records,
            }
        )
    except Exception as exc:  # keep the corpus smoke pass fail-soft
        row.update(
            {
                "status": "failed",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
    return row


async def _main(args: argparse.Namespace) -> int:
    root = args.audio_root.resolve()
    if not root.exists():
        raise SystemExit(f"Audio root does not exist: {root}")
    transcript = _load_transcript_catalog(args.transcript_catalog.resolve(), args.level)
    candidates = sorted(path for path in root.rglob("*.wav") if path.is_file())
    if args.max_bytes:
        candidates = [path for path in candidates if path.stat().st_size <= args.max_bytes]
    candidates = candidates[: args.limit]
    rows: list[dict[str, Any]] = []
    for audio in candidates:
        print(f"Analyzing {audio.name} ...", flush=True)
        rows.append(await _run(audio, transcript))
    summary = {
        "analysis_version": "phoneme_tone_v2",
        "analysis_schema_version": "analysis_v2.character_phone.v1",
        "model_version": "praat-character-projection.v1",
        "level": args.level,
        "candidate_count": len(candidates),
        "success_count": sum(row.get("status") == "success" for row in rows),
        "failure_count": sum(row.get("status") == "failed" for row in rows),
        "gold_status": "missing",
        "release_eligible": False,
        "note": "Smoke output validates execution only; it is not a KPI benchmark.",
        "rows": rows,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} smoke rows to {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-root", type=Path, default=Path("backend/private-data/ntu_speech_bank"))
    parser.add_argument("--level", choices=("beginner", "intermediate"), default="beginner")
    parser.add_argument(
        "--transcript-catalog",
        type=Path,
        default=Path("backend/benchmarking/ntu_transcript_catalog.json"),
        help="UTF-8 JSON catalog containing the beginner/intermediate passages",
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--output", type=Path, default=Path("backend/reports/ntu_v2_smoke.json"))
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
