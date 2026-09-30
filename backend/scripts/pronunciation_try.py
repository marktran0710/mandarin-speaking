"""Try the pronunciation evaluator on two local recordings - no database, no story.

    python -m scripts.pronunciation_try --reference teacher.wav --student me.wav \\
        --text "友美，妳這個週末要做什麼？"

Prints the deterministic score, the measured per-syllable evidence and the
feedback. With a key in backend/.env the feedback comes from the configured
model (default gpt-6-luna); ``--no-llm`` forces the deterministic local feedback.
Only the score and issue summary are ever sent to the model, never the audio.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from services.pronunciation.config import FeedbackConfig  # noqa: E402
from services.pronunciation.evaluator import EvaluationError, evaluate_pronunciation  # noqa: E402
from services.pronunciation.feedback import LocalFeedbackProvider, build_feedback_provider  # noqa: E402
from services.pronunciation.reference_cache import InMemoryReferenceStore  # noqa: E402


def _print_report(evaluation, show_json: bool) -> None:
    score = evaluation.score
    print()
    if score.status != "scored":
        print(f"NOT SCORED - {score.reason}")
    else:
        print(f"SCORE  {score.total} / 100" + ("   (renormalised over measured dimensions)" if score.renormalized else ""))
        for dimension in score.dimensions:
            if dimension.points is None:
                print(f"  {dimension.key:<16} unavailable")
            else:
                print(f"  {dimension.key:<16} {dimension.points:>3} / {dimension.max_points}")

    comparison = evaluation.comparison
    if comparison is not None:
        print("\nMEASURED")
        for label, value in (
            ("tone similarity", comparison.tone_similarity),
            ("rhythm", comparison.rhythm_similarity),
            ("pauses", comparison.pause_similarity),
            ("speaking rate vs reference", comparison.speaking_rate_ratio),
            ("alignment confidence", comparison.alignment_confidence),
        ):
            print(f"  {label:<28} {value}")
        print("\nSYLLABLES   (reference -> student pitch)")
        for s in comparison.syllables:
            sim = "  -  " if s.tone_similarity is None else f"{s.tone_similarity:.2f}"
            print(
                f"  {s.hanzi} {s.pinyin:<6} {s.reference_direction:>8} -> {s.student_direction:<8}"
                f" sim={sim}  dur x{s.duration_ratio or 0:.2f}  {','.join(s.flags) or 'ok'}"
                + (f"  [{s.evidence}]" if s.flags else "")
            )

    feedback = evaluation.feedback
    print(f"\nFEEDBACK  ({feedback.source}{' / ' + feedback.model if feedback.model else ''}"
          f"{' - fell back: ' + feedback.fallback_reason if feedback.fallback_reason else ''})")
    print(f"  {feedback.summary}")
    for focus in feedback.focus_words:
        print(f"  - {focus.word}: {focus.feedback}")
    print(f"  Tip: {feedback.practice_tip}")
    if feedback.adjustments:
        print(f"  (sanitised: {', '.join(feedback.adjustments)})")
    if show_json:
        print("\nPROVENANCE")
        print(json.dumps(evaluation.provenance(), ensure_ascii=False, indent=2))


async def _run(args: argparse.Namespace) -> int:
    with open(args.student, "rb") as handle:
        student_audio = handle.read()
    config = FeedbackConfig.from_env()
    provider = LocalFeedbackProvider() if args.no_llm else build_feedback_provider(config)
    if args.no_llm or not config.enabled:
        print("Feedback: local (no model)")
    else:
        print(f"Feedback model: {config.model}")
    try:
        evaluation = await evaluate_pronunciation(
            student_audio=student_audio,
            reference_audio_path=args.reference,
            reference_key=f"file:{os.path.basename(args.reference)}",
            expected_text=args.text,
            provider=provider,
            store=InMemoryReferenceStore(),
        )
    except EvaluationError as exc:
        print(f"Cannot evaluate: {exc.code} - {exc}")
        return 2
    _print_report(evaluation, args.provenance)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", required=True, help="teacher/model recording (wav)")
    parser.add_argument("--student", required=True, help="student recording (wav)")
    parser.add_argument("--text", required=True, help="the sentence both recordings say")
    parser.add_argument("--no-llm", action="store_true", help="use deterministic local feedback only")
    parser.add_argument("--provenance", action="store_true", help="also print the provenance record")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
