import json
import sqlite3
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from analytics.frex import compute_frex
from analytics.irt import fit_rasch
from analytics.joint_time import fit_joint_mode
from database import connect_db

router = APIRouter()

VALID_MODES = {"speed", "strikes", "free", "review"}


def _student_names() -> Dict[str, str]:
    with connect_db() as db:
        rows = db.execute("SELECT id, name FROM students").fetchall()
    return {row["id"]: row["name"] for row in rows}


def _load_attempts(story_id: Optional[str] = None) -> List[sqlite3.Row]:
    query = "SELECT student_id, mode, question_results FROM vocab_quiz_attempts WHERE student_id IS NOT NULL"
    params: list = []
    if story_id:
        query += " AND story_id = ?"
        params.append(story_id)
    with connect_db() as db:
        return db.execute(query, params).fetchall()


def _accuracy_responses(
    story_id: Optional[str] = None, mode: Optional[str] = None
) -> List[Tuple[str, str, bool]]:
    """(student_id, word, correct) triples — attempts with no student_id
    (recorded before the roster existed) are excluded: per-student
    analysis needs a real join key, not a free-typed name string."""
    responses: List[Tuple[str, str, bool]] = []
    for row in _load_attempts(story_id):
        if mode and row["mode"] != mode:
            continue
        for q in json.loads(row["question_results"] or "[]"):
            responses.append((row["student_id"], q["word"], bool(q["correct"])))
    return responses


def _timed_responses(
    mode: str, story_id: Optional[str] = None
) -> List[Tuple[str, str, bool, float]]:
    responses: List[Tuple[str, str, bool, float]] = []
    for row in _load_attempts(story_id):
        if row["mode"] != mode:
            continue
        for q in json.loads(row["question_results"] or "[]"):
            responses.append((row["student_id"], q["word"], bool(q["correct"]), float(q["timeMs"])))
    return responses


@router.get("/api/analytics/vocab-quiz/irt")
async def get_vocab_quiz_irt(story_id: Optional[str] = None):
    """Item difficulty (per word) and student ability, pooled across every
    quiz mode and story (unless story_id narrows it) — the general-purpose
    view of "which words are hard" and "who's ahead/behind"."""
    responses = _accuracy_responses(story_id=story_id)
    fit = fit_rasch(responses)
    names = _student_names()

    return {
        "nResponses": len(responses),
        "items": [
            {"word": word, "difficulty": difficulty, "nResponses": fit.item_n[word]}
            for word, difficulty in sorted(fit.item_difficulty.items(), key=lambda kv: -kv[1])
        ],
        "students": [
            {
                "studentId": student_id,
                "name": names.get(student_id, "Unknown"),
                "ability": ability,
                "nResponses": fit.student_n[student_id],
            }
            for student_id, ability in sorted(fit.student_ability.items(), key=lambda kv: -kv[1])
        ],
    }


@router.get("/api/analytics/vocab-quiz/joint")
async def get_vocab_quiz_joint_model(
    mode: str = Query(..., description="One of: speed, strikes, free, review"),
    story_id: Optional[str] = None,
):
    """Joint accuracy + response-time model, fit within a single quiz mode
    (time pressure differs too much between modes to pool them)."""
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(VALID_MODES)}")

    responses = _timed_responses(mode, story_id=story_id)
    fit = fit_joint_mode(mode, responses)
    names = _student_names()

    return {
        "mode": fit.mode,
        "nResponses": fit.n_responses,
        "abilitySpeedCorrelation": fit.ability_speed_correlation,
        "items": [
            {
                "word": word,
                "difficulty": fit.item_difficulty.get(word),
                "timeIntensity": time_intensity,
            }
            for word, time_intensity in sorted(
                fit.item_time_intensity.items(), key=lambda kv: -kv[1]
            )
        ],
        "students": [
            {
                "studentId": student_id,
                "name": names.get(student_id, "Unknown"),
                "ability": fit.student_ability.get(student_id),
                "speed": speed,
            }
            for student_id, speed in sorted(fit.student_speed.items(), key=lambda kv: -kv[1])
        ],
    }


@router.get("/api/analytics/vocab-quiz/frex")
async def get_vocab_quiz_frex(
    student_id: Optional[str] = None,
    top: int = Query(default=5, ge=1, le=20),
    story_id: Optional[str] = None,
):
    """Per student, their top characteristic missed words — common enough
    to matter (frequency) and disproportionately theirs versus the rest of
    the class (exclusivity), not just words everyone finds hard."""
    responses = _accuracy_responses(story_id=story_id)
    result = compute_frex(responses, top_n=top)
    names = _student_names()

    student_ids = [student_id] if student_id else sorted(result)
    return [
        {
            "studentId": sid,
            "name": names.get(sid, "Unknown"),
            "words": [
                {
                    "word": cw.word,
                    "frex": cw.frex,
                    "frequency": cw.frequency,
                    "exclusivity": cw.exclusivity,
                    "missCount": cw.miss_count,
                }
                for cw in result.get(sid, [])
            ],
        }
        for sid in student_ids
        if sid in result
    ]
