"""Teacher-facing endpoints for the OMPAL external validation benchmark.

Scoring is a long background job (minutes), so it is started and polled rather
than awaited inside a request. The report is computed separately and on demand,
which keeps the pass threshold adjustable without re-running any audio.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

import auth

from benchmarking import ompal_runner
from benchmarking.ompal_corpus import corpus_status, load_utterances
from benchmarking.ompal_report import PRODUCTION_THRESHOLD, build_report
from praat_analyzer import analyze_all

router = APIRouter(dependencies=[Depends(auth.require_teacher_or_admin)])

_PRIVATE_ROOT = Path(
    os.getenv("BENCHMARK_DATA_DIR", Path(__file__).resolve().parent.parent / "private-data")
)
CORPUS_ROOT = _PRIVATE_ROOT / "ompal"
RESULTS_PATH = _PRIVATE_ROOT / "ompal-scored.jsonl"


def _analyzer(path: str, transcription: str):
    """Score with the same Praat path the application uses for students.

    The reference transcript is supplied, so no ASR runs: a transcription
    error would otherwise be indistinguishable from a pronunciation error.
    """
    return analyze_all(path, transcription)


@router.get("/api/benchmark/ompal/status")
async def get_benchmark_status():
    """Corpus availability plus the current job state, polled by the UI."""
    scored = ompal_runner.load_scored(RESULTS_PATH)
    return {
        "corpus": corpus_status(CORPUS_ROOT),
        "job": ompal_runner.get_state(),
        "scored_count": len(scored),
        "has_results": bool(scored),
        "production_threshold": PRODUCTION_THRESHOLD,
    }


@router.post("/api/benchmark/ompal/run")
async def start_benchmark_run():
    """Download the corpus if needed, then score every utterance.

    Returns 409 rather than queueing a second run: two jobs appending to the
    same results file would interleave their output.
    """
    if not ompal_runner.start(CORPUS_ROOT, RESULTS_PATH, _analyzer):
        raise HTTPException(status_code=409, detail="A benchmark run is already in progress.")
    return {"started": True, "job": ompal_runner.get_state()}


@router.post("/api/benchmark/ompal/cancel")
async def cancel_benchmark_run():
    """Stop at the next utterance boundary; already-scored work is kept."""
    if not ompal_runner.request_cancel():
        raise HTTPException(status_code=409, detail="No benchmark run is in progress.")
    return {"cancelling": True, "job": ompal_runner.get_state()}


@router.get("/api/benchmark/ompal/report")
async def get_benchmark_report(
    threshold: float = Query(PRODUCTION_THRESHOLD, ge=0.0, le=100.0),
    audit_limit: int = Query(50, ge=1, le=500),
):
    """Compute the agreement report from already-scored results."""
    scored = ompal_runner.load_scored(RESULTS_PATH)
    if not scored:
        raise HTTPException(
            status_code=404,
            detail="No benchmark results yet. Run the benchmark first.",
        )
    if not corpus_status(CORPUS_ROOT)["downloaded"]:
        raise HTTPException(
            status_code=409,
            detail="The scored results exist but the corpus is missing, so they cannot be interpreted.",
        )
    utterances = load_utterances(CORPUS_ROOT)
    return build_report(
        utterances, scored, threshold=threshold, audit_limit=audit_limit
    )
