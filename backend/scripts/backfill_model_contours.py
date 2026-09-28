"""Backfill ``sentenceModelContour`` for scenes whose teacher recording was
uploaded before the field existed.

Examples::

    python -m scripts.backfill_model_contours            # dry run
    python -m scripts.backfill_model_contours --apply

Only frames that already have a local model recording and no contour yet are
touched. The contour is display-only (the student pitch chart's "model voice"
line); scoring curves are left exactly as they are.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args()

    from psycopg.types.json import Jsonb

    from db import connect_db
    from services.media import _AUDIO_TIER_SUFFIXES, UPLOAD_DIR
    from services.speech.reference_voice import extract_sentence_model_contour

    with connect_db() as db:
        rows = db.execute("SELECT id, frames FROM custom_stories ORDER BY id").fetchall()

    updated_stories = 0
    for row in rows:
        frames = list(row["frames"] or [])
        changed = False
        for index, frame in enumerate(frames):
            for suffix in _AUDIO_TIER_SUFFIXES:
                if frame.get(f"sentenceModelContour{suffix}"):
                    continue
                audio_url = frame.get(f"listenAudioUrl{suffix}") or ""
                text = (
                    frame.get(f"listenScript{suffix}") or frame.get(f"suggestedAnswer{suffix}") or ""
                ).strip()
                if not audio_url.startswith("/uploads/") or not text:
                    continue
                relative = audio_url.removeprefix("/uploads/").replace("/", os.sep)
                audio_path = os.path.abspath(os.path.join(UPLOAD_DIR, relative))
                if not os.path.exists(audio_path):
                    print(f"  skip {row['id']} frame {index}: missing {audio_url}")
                    continue
                try:
                    contour = extract_sentence_model_contour(audio_path, text)
                except Exception as exc:  # noqa: BLE001 — report and keep going
                    print(f"  fail {row['id']} frame {index}: {exc}")
                    continue
                frame = dict(frame)
                frame[f"sentenceModelContour{suffix}"] = json.dumps(contour, ensure_ascii=False)
                frames[index] = frame
                changed = True
                print(f"  ok   {row['id']} frame {index}: {len(contour['tokens'])} tokens")
        if changed:
            updated_stories += 1
            if args.apply:
                with connect_db() as db:
                    db.execute(
                        "UPDATE custom_stories SET frames = %s WHERE id = %s",
                        (Jsonb(frames), row["id"]),
                    )

    mode = "updated" if args.apply else "would update (dry run)"
    print(f"{mode}: {updated_stories} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
