"""Background job that scores the OMPAL corpus with the production analyzer.

The job is deliberately split from metric computation. Scoring 1,850 files
through Praat takes minutes; recomputing agreement metrics from the stored
result takes milliseconds. Persisting each character's raw *score* rather than
a pass/fail verdict is what lets the report's threshold be changed
interactively without re-running any audio analysis.

Results are appended as JSON Lines so a crash nine minutes into a ten-minute
run does not discard the work, and a re-run resumes rather than restarting.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from benchmarking.ompal_corpus import (
    OmpalUtterance,
    corpus_status,
    download_corpus,
    load_utterances,
)

Analyzer = Callable[[str, str], tuple]

PHASE_IDLE = "idle"
PHASE_DOWNLOADING = "downloading"
PHASE_SCORING = "scoring"
PHASE_COMPLETE = "complete"
PHASE_FAILED = "failed"
PHASE_CANCELLED = "cancelled"


@dataclass
class JobState:
    phase: str = PHASE_IDLE
    done: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    downloaded_bytes: int = 0
    download_total_bytes: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["running"] = self.phase in {PHASE_DOWNLOADING, PHASE_SCORING}
        payload["elapsed_seconds"] = (
            round((self.finished_at or time.time()) - self.started_at, 1)
            if self.started_at
            else None
        )
        return payload


@dataclass
class _Job:
    state: JobState = field(default_factory=JobState)
    cancel_requested: bool = False
    task: asyncio.Task | None = None


_job = _Job()


def get_state() -> dict[str, Any]:
    return _job.state.as_dict()


def request_cancel() -> bool:
    """Ask a running job to stop at the next utterance boundary."""
    if _job.state.phase not in {PHASE_DOWNLOADING, PHASE_SCORING}:
        return False
    _job.cancel_requested = True
    _job.state.message = "Cancelling…"
    return True


def is_running() -> bool:
    return _job.state.phase in {PHASE_DOWNLOADING, PHASE_SCORING}


def flatten_characters(word_prosody: Sequence[dict]) -> list[dict[str, Any]]:
    """Reduce the analyzer's word output to a flat per-character score list.

    OMPAL rates its own word units, which never coincide with jieba's
    tokenization, so characters are the only common ground between the two.
    """
    characters: list[dict[str, Any]] = []
    for word in word_prosody or []:
        for syllable in word.get("syllables") or []:
            character = str(syllable.get("char") or "")
            if not character:
                continue
            characters.append(
                {"char": character, "score": float(syllable.get("score") or 0.0)}
            )
    return characters


def score_utterance(utterance: OmpalUtterance, analyzer: Analyzer) -> dict[str, Any]:
    """Score one utterance, passing its known text so no ASR is involved.

    Supplying the reference transcript isolates the tone scorer: a transcription
    error would otherwise be indistinguishable from a pronunciation error, and
    the corpus already tells us exactly what was said.

    A failure is recorded with its reason rather than raised. An unreadable
    file is a data problem, and converting it into a zero pronunciation score
    would let data quality masquerade as learner error.
    """
    record: dict[str, Any] = {
        "utterance_id": utterance.utterance_id,
        "speaker_id": utterance.speaker_id,
        "is_native": utterance.is_native,
        "system_tone_accuracy": None,
        "system_fluency": None,
        "characters": [],
        "error": None,
    }
    try:
        result = analyzer(str(utterance.wav_path), utterance.text)
        (
            _pitch_contour,
            _formants,
            _speech_rate,
            fluency_score,
            _pitch_statistics,
            word_prosody,
            _detected_tone,
            tone_accuracy,
            _feedback,
            _pause_analysis,
        ) = result
        record["system_tone_accuracy"] = float(tone_accuracy)
        record["system_fluency"] = float(fluency_score)
        record["characters"] = flatten_characters(word_prosody)
        if not record["characters"]:
            record["error"] = "analyzer returned no per-character tone scores"
    except Exception as error:  # noqa: BLE001 - recorded, never silently dropped
        record["error"] = str(error)
    return record


def load_scored(results_path: str | Path) -> list[dict[str, Any]]:
    """Read previously scored rows, tolerating a truncated final line.

    A crash mid-write can leave one partial line; discarding just that line is
    correct, whereas failing the whole read would throw away a complete run.
    """
    path = Path(results_path)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_scoring(
    utterances: Iterable[OmpalUtterance],
    results_path: str | Path,
    *,
    analyzer: Analyzer,
    on_progress: Callable[[int, int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Score every utterance not already present in ``results_path``."""
    utterances = list(utterances)
    path = Path(results_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    already_scored = {row.get("utterance_id") for row in load_scored(path)}
    pending = [item for item in utterances if item.utterance_id not in already_scored]
    scored = failed = 0

    with path.open("a", encoding="utf-8") as target:
        for index, utterance in enumerate(pending, start=1):
            if should_cancel and should_cancel():
                break
            record = score_utterance(utterance, analyzer)
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
            target.flush()
            if record["error"]:
                failed += 1
            else:
                scored += 1
            if on_progress:
                on_progress(len(already_scored) + index, len(utterances), failed)

    return {
        "scored": scored,
        "failed": failed,
        "skipped": len(already_scored),
        "total": len(utterances),
    }


async def _execute(corpus_root: Path, results_path: Path, analyzer: Analyzer) -> None:
    from starlette.concurrency import run_in_threadpool

    state = _job.state
    try:
        if not corpus_status(corpus_root)["downloaded"]:
            state.phase = PHASE_DOWNLOADING
            state.message = "Downloading OMPAL corpus (~330 MB)…"

            def report_download(downloaded: int, total: int) -> None:
                state.downloaded_bytes = downloaded
                state.download_total_bytes = total

            await run_in_threadpool(
                lambda: download_corpus(
                    corpus_root,
                    progress=report_download,
                    should_cancel=lambda: _job.cancel_requested,
                )
            )

        if _job.cancel_requested:
            state.phase = PHASE_CANCELLED
            state.message = "Cancelled before scoring started."
            return

        state.phase = PHASE_SCORING
        state.message = "Loading corpus…"
        utterances = await run_in_threadpool(load_utterances, corpus_root)
        state.total = len(utterances)
        state.message = f"Scoring {len(utterances)} utterances…"

        def report_progress(done: int, total: int, failed: int) -> None:
            state.done = done
            state.total = total
            state.failed = failed

        summary = await run_in_threadpool(
            lambda: run_scoring(
                utterances,
                results_path,
                analyzer=analyzer,
                on_progress=report_progress,
                should_cancel=lambda: _job.cancel_requested,
            )
        )
        state.skipped = summary["skipped"]
        state.failed = summary["failed"]

        if _job.cancel_requested:
            state.phase = PHASE_CANCELLED
            state.message = f"Cancelled after scoring {summary['scored']} utterances."
        else:
            state.phase = PHASE_COMPLETE
            state.message = (
                f"Scored {summary['scored']} utterances "
                f"({summary['failed']} unscorable, {summary['skipped']} already done)."
            )
    except Exception as error:  # noqa: BLE001 - surfaced to the teacher UI
        state.phase = PHASE_FAILED
        state.error = str(error)
        state.message = "Benchmark run failed."
    finally:
        state.finished_at = time.time()
        _job.cancel_requested = False
        _job.task = None


def start(corpus_root: str | Path, results_path: str | Path, analyzer: Analyzer) -> bool:
    """Start a run. Returns False when one is already in flight."""
    if is_running():
        return False
    _job.state = JobState(
        phase=PHASE_DOWNLOADING, message="Starting…", started_at=time.time()
    )
    _job.cancel_requested = False
    _job.task = asyncio.create_task(
        _execute(Path(corpus_root), Path(results_path), analyzer)
    )
    return True


def reset_for_tests() -> None:
    _job.state = JobState()
    _job.cancel_requested = False
    _job.task = None
