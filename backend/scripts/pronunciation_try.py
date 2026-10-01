"""Try Wav2Vec2 + Praat rubrics on two recordings, without a database.

python -m scripts.pronunciation_try --reference teacher.wav --student me.wav --text "你好嗎"

Wav2Vec2 scores Pronunciation, Praat scores Fluency and Prosody, and GPT-6 Luna
explains the measurements. There is no overall score.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from services.pronunciation.evaluator import EvaluationError
from services.pronunciation.presenter import present_evaluation
from services.pronunciation.reference_cache import InMemoryReferenceStore
from services.pronunciation.rubric_evaluator import evaluate_rubric_pronunciation

async def _run(args):
    with open(args.student, "rb") as handle:
        audio = handle.read()
    try:
        evaluation = await evaluate_rubric_pronunciation(
            student_audio=audio, reference_audio_path=args.reference,
            reference_key=f"file:{os.path.basename(args.reference)}", expected_text=args.text,
            store=InMemoryReferenceStore(),
        )
    except EvaluationError as exc:
        print(f"Cannot evaluate: {exc.code} - {exc}")
        return 2
    result = present_evaluation(evaluation, include_debug=args.provenance)
    for key, dimension in result["dimensions"].items():
        value = "not assessed" if dimension["score"] is None else f'{dimension["score"]}/5'
        print(f"{key}: {value}")
        print(dimension.get("feedback") or dimension["reason"])
        print(json.dumps(dimension["measurements"], ensure_ascii=False, indent=2))
    print(result["feedback"]["summary"])
    print(result["feedback"]["practice_tip"])
    print("pronunciation errors:", json.dumps(result.get("pronunciation_errors", []), ensure_ascii=False))
    print("tone errors:", json.dumps(result.get("tone_errors", []), ensure_ascii=False))
    if args.provenance:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--student", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--provenance", action="store_true")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
