"""One-off: re-score the full OMPAL corpus with the CURRENT frozen pipeline.

Not part of the validation module's public API — a short-lived script to
produce a fresh, timestamped cache after discovering the existing
``private-data/ompal-scored.jsonl`` predates two merged pipeline changes
(the M1 energy aligner and the 10ms pitch-resolution increase). See
``benchmarking/results/tone_diagnostic_summary.md`` for the full account.

The original file is left untouched.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from praat_analyzer import analyze_all
from benchmarking.ompal_corpus import load_utterances
from benchmarking.ompal_runner import run_scoring

CORPUS = Path("private-data/ompal")
OUT = Path("private-data/ompal-scored-2026-08-10.jsonl")


def _analyzer(path, transcription):
    return analyze_all(path, transcription)


def _progress(done, total, failed):
    if done % 50 == 0 or done == total:
        print(f"{done}/{total} scored, {failed} failed", file=sys.stderr, flush=True)


def main():
    utterances = load_utterances(CORPUS)
    print(f"{len(utterances)} utterances to score -> {OUT}", file=sys.stderr)
    started = time.time()
    result = run_scoring(utterances, OUT, analyzer=_analyzer, on_progress=_progress)
    print(f"done in {time.time() - started:.0f}s: {result}", file=sys.stderr)


if __name__ == "__main__":
    main()
