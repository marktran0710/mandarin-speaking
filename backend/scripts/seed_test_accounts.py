"""Seed a mixed roster of test students for exercising the app end to end,
in particular the placement test's cold-start sampling and BKT pipeline.

Of ``--students`` total accounts, ``--synthetic-ratio`` (default 80%) are
auto-generated with a mild per-learner ability curve and pre-filled placement
-test-shaped diagnostic responses, so the analytics pipeline (parameter fit,
knowledge-state report) has volume to exercise. The rest are created empty,
with a known login/password, so a human can sign in through the real UI and
try the placement test (and everything else) as an actual student would.

Every account this script creates is flagged ``is_test_account`` (excluded
from a teacher's roster/submissions, still visible to admin tooling) and
prefixed ``test-stu-`` in its id. ``--clean`` removes exactly those accounts
and everything they own via ``purge_test_accounts``; nothing else is touched.

Synthetic responses are tagged ``evidence_origin = 'synthetic'`` so they can
never be counted as real calibration evidence (see the TODO in
``analytics/bkt.py`` and ``scripts/seed_bkt_test_data.py``'s longer synthetic
-vs-real writeup) — this script is for pipeline/UI testing, not calibration.

Examples::

    python -m scripts.seed_test_accounts                        # 25 total: 20 synthetic + 5 for manual login
    python -m scripts.seed_test_accounts --students 50
    python -m scripts.seed_test_accounts --clean                # remove this script's own accounts
    python -m scripts.seed_test_accounts --database-url postgresql://mandarin:mandarin@127.0.0.1:5433/mandarin
"""

from __future__ import annotations

import argparse
import math
import os
import random
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402
from analytics.bkt_mastery import response_rows_for_attempt, upsert_raw_responses  # noqa: E402
from db import connect_db  # noqa: E402
from scripts.purge_test_accounts import purge  # noqa: E402

ID_PREFIX = "test-stu-"
MANUAL_LOGIN_PASSWORD = "123456"

# Stand-in HSK1-level concepts for the synthetic diagnostic responses. Not
# tied to any published story, so this script has no app/ML boot dependency.
CONCEPTS = ["你好", "謝謝", "老師", "學生", "朋友", "學習", "房間", "家人", "吃飯", "喝水"]


def _looks_local(url: str) -> bool:
    return "@127.0.0.1" in url or "@localhost" in url or "@::1" in url


def _p_correct(ability: float, difficulty: float, exposure: int) -> float:
    """Mild learning curve: starts near the guess floor, rises with exposure."""
    learned = 1.0 - math.exp(-0.45 * exposure)
    return min(0.97, max(0.05, 0.15 + (ability - difficulty) * learned))


def _placement_result(word: str, correct: bool, exposure: int) -> dict:
    """The exact shape resolve_assessment_response would hand back for a
    placement-test (know-it/tier1) answer — see PlacementTestPage.tsx and
    analytics/bkt_question_validation.classify_bkt_response."""
    return {
        "word": word,
        "conceptId": word,
        "correct": correct,
        # quiz_level tracks quiz_mode 1:1 post-migration-0033 (both "tier1"
        # here) — NOT the story-text difficulty label ("easy"/PlacementTest's
        # own client-side field name); classify_bkt_response's
        # ROUND_LEVEL_MISMATCH check is strict about this.
        "level": "tier1",
        "mode": "tier1",
        "itemId": f"item-{word}-{exposure}",
        "questionKind": "basic_meaning_mcq",
        "roundType": "know_it",
        "knowledgeDimension": "meaning",
        "activityType": "diagnostic",
        "isBktEligible": True,
        "authoritativeResolved": True,
        "resolverVersion": "seed-test-accounts-v1",
        "bktValidationStatus": "APPROVED",
        "diagnosticExposureId": f"exposure-{word}-{exposure}",
        "answeredAt": f"2026-01-{1 + (exposure % 27):02d}T00:00:00Z",
        "questionIndex": exposure,
    }


def _seed_synthetic_student(db, index: int, rng: random.Random, concept_difficulty: dict[str, float]) -> str:
    student_id = f"{ID_PREFIX}synthetic-{index:03d}"
    name = f"Test Student {index:03d}"
    db.execute(
        "INSERT INTO students (id, name, password, is_test_account) VALUES (%s, %s, %s, TRUE)",
        (student_id, name, auth.hash_password(secrets.token_urlsafe(24))),
    )
    ability = rng.uniform(0.35, 0.90)
    results = []
    for exposure, word in enumerate(CONCEPTS, start=1):
        p = _p_correct(ability, concept_difficulty[word], exposure)
        results.append(_placement_result(word, rng.random() < p, exposure))
    attempt = {
        "id": f"{student_id}-placement",
        "storyId": "seed-placement-test",
        "baseStoryId": "seed-placement-test",
        "level": "tier1",
        "mode": "tier1",
        "completedAt": "2026-01-01T00:00:00Z",
    }
    rows = response_rows_for_attempt(attempt, student_id, results)
    for row in rows:
        row["evidence_origin"] = "synthetic"
    upsert_raw_responses(db, rows)
    return student_id


def _seed_manual_student(db, index: int) -> str:
    student_id = f"{ID_PREFIX}manual-{index:03d}"
    name = f"Test Login {index:03d}"
    db.execute(
        "INSERT INTO students (id, name, password, is_test_account) VALUES (%s, %s, %s, TRUE)",
        (student_id, name, auth.hash_password(MANUAL_LOGIN_PASSWORD)),
    )
    return student_id


def seed(*, total: int, synthetic_ratio: float, seed_value: int | None) -> dict:
    rng = random.Random(seed_value)
    synthetic_count = round(total * synthetic_ratio)
    manual_count = total - synthetic_count
    concept_difficulty = {c: rng.uniform(-0.15, 0.15) for c in CONCEPTS}

    synthetic_ids: list[str] = []
    manual_ids: list[str] = []
    with connect_db() as db:
        for i in range(synthetic_count):
            synthetic_ids.append(_seed_synthetic_student(db, i, rng, concept_difficulty))
        for i in range(manual_count):
            manual_ids.append(_seed_manual_student(db, i))
    return {"synthetic": synthetic_ids, "manual": manual_ids}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--students", type=int, default=25)
    parser.add_argument("--synthetic-ratio", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for a reproducible run.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--clean", action="store_true", help="Remove this script's prior accounts (via purge_test_accounts), then exit.")
    parser.add_argument("--force", action="store_true", help="Allow a non-localhost database URL.")
    args = parser.parse_args()

    url = args.database_url
    if not url:
        raise SystemExit("No database URL. Pass --database-url or set DATABASE_URL.")
    if not _looks_local(url) and not args.force:
        raise SystemExit("Refusing to touch a non-localhost database without --force.")
    os.environ["DATABASE_URL"] = url

    if args.clean:
        removed = purge(url, apply=True)
        print(f"Removed {len(removed)} test account(s).")
        return

    result = seed(total=args.students, synthetic_ratio=args.synthetic_ratio, seed_value=args.seed)
    print(f"Seeded {len(result['synthetic'])} synthetic student(s) with placement-test responses.")
    print(f"Seeded {len(result['manual'])} empty account(s) for manual login (password: {MANUAL_LOGIN_PASSWORD}):")
    for student_id in result["manual"]:
        print(f"  {student_id}")
    print("\nAll accounts are flagged is_test_account: hidden from teacher views, purgeable via scripts/purge_test_accounts.py.")


if __name__ == "__main__":
    main()
