"""Seed synthetic student quiz data for exercising the BKT/PFA pipeline.

DEV/TEST ONLY. This generates *synthetic* learners so you can run the
knowledge-tracing analytics end to end while building — fit parameters,
prequential evaluation, the admin ``/api/admin/analytics/knowledge-state``
report. It is **not** a way to obtain research-valid parameters: synthetic
responses carry no real learning signal, so any parameters fit on them are
only good for checking that the machinery runs. Real calibration must come
from a genuine pilot (see the TODO in ``analytics/bkt.py`` and the frozen
validation study), and the student-facing grading params in ``BKT_CONFIG``
are deliberately left untouched by this script.

The generator does give each response a mild, deterministic learning curve
(low early, rising with exposure and a per-student latent ability) so the fit
sees both correct and incorrect outcomes and does not collapse to a trivial
solution — enough to reach the pilot's "evidence_ready" thresholds.

Examples::

    python -m scripts.seed_bkt_test_data                       # 25 students -> dev DB
    python -m scripts.seed_bkt_test_data --students 25 --rounds 6
    python -m scripts.seed_bkt_test_data --clean               # remove prior seed rows first
    python -m scripts.seed_bkt_test_data --database-url postgresql://mandarin:mandarin@127.0.0.1:5433/mandarin

All rows this script writes are tagged with the ``seed-stu-`` id prefix so
``--clean`` can remove exactly its own data and nothing else.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEED_ID_PREFIX = "seed-stu-"

# A dozen HSK1-level words stand in for distinct BKT concepts. Ten is the
# pilot's MIN_CONCEPTS floor; twelve leaves headroom.
CONCEPTS = ["你好", "謝謝", "老師", "學生", "朋友", "學習", "房間", "家人", "吃飯", "喝水", "看書", "說話"]

TIER_MODES = ["tier1", "tier2", "tier3"]


def _eligible_result(word: str, correct: bool, exposure: int, *, level: str = "easy") -> dict:
    """The exact question-result shape the analytics normalizer counts as a
    clean BKT observation (mirrors tests/test_knowledge_analytics.py)."""
    return {
        "word": word,
        "conceptId": word,
        "correct": correct,
        "level": level,
        "itemId": f"item-{word}-{exposure}",
        "questionKind": "translation",
        "isBktEligible": True,
        # Unique per exposure so diagnostic-exposure de-duplication keeps each
        # attempt as its own observation instead of folding them together.
        "diagnosticExposureId": f"exposure-{word}-{exposure}",
        "bktValidationStatus": "APPROVED",
    }


def _p_correct(ability: float, difficulty: float, exposure: int) -> float:
    """A gentle learning curve: starts near the guess floor and rises toward
    the learner's ability as exposures accumulate."""
    learned = 1.0 - math.exp(-0.45 * exposure)  # 0 -> 1 across exposures
    p = 0.15 + (ability - difficulty) * learned
    return min(0.97, max(0.05, p))


def _looks_local(url: str) -> bool:
    return "@127.0.0.1" in url or "@localhost" in url or "@::1" in url


def seed(url: str, students: int, rounds: int, rng: random.Random) -> dict:
    story_id = "seed-story"
    concept_difficulty = {c: rng.uniform(-0.15, 0.15) for c in CONCEPTS}

    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            student_rows, attempt_rows = [], []
            for s in range(students):
                sid = f"{SEED_ID_PREFIX}{s:03d}"
                student_rows.append((sid, f"Seed Student {s:03d}", "seed-not-a-real-password"))
                ability = rng.uniform(0.35, 0.90)
                for r in range(rounds):  # each round = one quiz attempt (session)
                    results = []
                    for c in CONCEPTS:
                        p = _p_correct(ability, concept_difficulty[c], r + 1)
                        results.append(_eligible_result(c, rng.random() < p, r + 1))
                    completed_at = f"2026-{1 + (r % 9):02d}-{1 + (s % 27):02d}T{(r % 24):02d}:00:00Z"
                    attempt_rows.append((
                        f"{sid}-r{r}", story_id, f"Seed Student {s:03d}", sid,
                        TIER_MODES[r % 3], completed_at,
                        len(results), sum(1 for x in results if x["correct"]),
                        1000 * len(results), Jsonb(results),
                    ))

            cur.executemany(
                "INSERT INTO students (id, name, password) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                student_rows,
            )
            cur.executemany(
                "INSERT INTO vocab_quiz_attempts "
                "(id, story_id, student_name, student_id, mode, completed_at, "
                " total_questions, correct_count, total_time_ms, question_results) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                attempt_rows,
            )
        conn.commit()

    total_responses = len(attempt_rows) * len(CONCEPTS)
    return {
        "students": students,
        "concepts": len(CONCEPTS),
        "attempts": len(attempt_rows),
        "responses": total_responses,
    }


def clean(url: str) -> int:
    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM vocab_quiz_attempts WHERE student_id LIKE %s",
                (SEED_ID_PREFIX + "%",),
            )
            removed = cur.rowcount
            cur.execute("DELETE FROM students WHERE id LIKE %s", (SEED_ID_PREFIX + "%",))
        conn.commit()
    return removed


def main() -> int:
    default_url = os.getenv(
        "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5433/mandarin"
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=default_url, help="target DB (default: %(default)s)")
    parser.add_argument("--students", type=int, default=25)
    parser.add_argument("--rounds", type=int, default=6, help="quiz attempts per student (exposures per concept)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible data")
    parser.add_argument("--clean", action="store_true", help="delete existing seed-stu- rows first")
    parser.add_argument("--force", action="store_true", help="allow a non-localhost database URL")
    args = parser.parse_args()

    url = args.database_url
    # Never let a stray production URL be seeded by accident.
    safe_dbname = url.rsplit("/", 1)[-1]
    if not _looks_local(url) and not args.force:
        print(f"Refusing to seed a non-local database ({safe_dbname}). Pass --force if you are sure.", file=sys.stderr)
        return 2

    print(f"Target database: …/{safe_dbname}")

    if args.clean:
        removed = clean(url)
        print(f"Cleaned {removed} prior seed attempt rows (and their students).")

    summary = seed(url, args.students, args.rounds, random.Random(args.seed))
    print(
        "Seeded {students} students x {concepts} concepts x {r} rounds "
        "= {attempts} attempts, {responses} eligible responses.".format(r=args.rounds, **summary)
    )
    print(
        "\nExercise the pipeline (admin session required):\n"
        "  GET /api/admin/analytics/knowledge-state?model=compare\n"
        "  GET /api/admin/analytics/bkt-question-audit\n"
        "Re-run with --clean to reset. This data is synthetic — do NOT freeze "
        "any parameters fit on it into BKT_CONFIG."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
