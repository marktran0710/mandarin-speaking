"""Run the manifest's learner recordings through the live analysis pipeline.

Calls ``services.speech_analysis._do_analyze`` exactly as a story-speaking
request would when the target sentence is known (``transcription`` and
``scene_target_text`` both set to the reference text, no ASR, no AI
feedback). Nothing is written to the database and no threshold or verdict
logic is touched - this only records what the current system outputs.

Two configurations are run so the effect of a teacher recording is visible:

* ``template``  - no reference audio; the system's synthetic tone shapes.
* ``native``    - reference curves extracted from OMPAL's native recording of
  the same sentence with ``extract_scene_reference_curves``, the same helper
  the app uses when a teacher uploads a model sentence.

Example, from ``backend/``::

    python -m scripts.research.ompal.run_system --out output/ompal --workers 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET_KEY", "offline-ompal-validation-only-not-a-secret")

CONFIGS = ("template", "native")
_reference_cache: dict[str, dict] = {}


def _reference_curves(wav: str, text: str) -> dict:
    from services.speech.reference_voice import extract_scene_reference_curves

    if wav not in _reference_cache:
        try:
            _reference_cache[wav] = extract_scene_reference_curves(wav, text)
        except Exception:  # an unusable native clip falls back to templates
            _reference_cache[wav] = {}
    return _reference_cache[wav]


def _analyze(item: dict) -> dict:
    from services.speech_analysis import _do_analyze

    audio = Path(item["wav"]).read_bytes()
    outputs: dict = {"id": item["id"]}
    for config in CONFIGS:
        curves = None
        if config == "native":
            curves = _reference_curves(item["native_reference_wav"], item["text"]) or None
        try:
            result = asyncio.run(_do_analyze(
                audio,
                transcription=item["text"],
                asr_model="",
                ai_provider="none",
                scene_target_text=item["text"],
                reference_word_curves=curves,
            )).model_dump()
        except Exception as exc:
            outputs[config] = {"error": repr(exc)}
            continue
        quality = result.get("feedback_quality") or {}
        outputs[config] = {
            "reference_curves_used": bool(curves),
            "tone_accuracy": result.get("tone_accuracy"),
            "speech_rate": result.get("speech_rate"),
            "fluency_score": result.get("fluency_score"),
            "feedback_status": quality.get("status"),
            "can_score_pronunciation": quality.get("can_score_pronunciation"),
            "mastery": result.get("pronunciation_mastery") or {},
            "words": [
                {key: word.get(key) for key in ("token", "verdict", "tone_accuracy", "judged")}
                for word in result.get("word_prosody") or []
            ],
        }
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=Path("output/ompal"), type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="Only the first N utterances (smoke run).")
    args = parser.parse_args()
    os.chdir(BACKEND)
    manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]
    with Pool(args.workers) as pool:
        results = pool.map(_analyze, manifest, chunksize=4)
    (args.out / "system_outputs.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    errors = {c: sum(1 for r in results if "error" in r.get(c, {})) for c in CONFIGS}
    print(json.dumps({"utterances": len(results), "errors": errors}))


if __name__ == "__main__":
    main()
