"""Read-only check that placement data flows into BKT mastery correctly.

For every student with completed placement evidence, this recomputes the
chapter priors and each word's p(learned) with an independent, hand-written
BKT update (it does not call analytics.learner_model.bkt.core), then compares
the result against

* the ``student_vocab_mastery`` cache (observed words), and
* the live ``get_vocabulary_mastery`` projection (observed and unseen words).

It also reports chapters whose placement prior was skipped (not exactly 7
distinct placement items, or the story has no lesson_number 5-8).

Run from ``backend/``::

    python -m scripts.verify_placement_bkt              # all placement students
    python -m scripts.verify_placement_bkt SIM001 -v    # one student, per word

Exit code is 1 when any mismatch is found. Nothing is written.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from analytics.learner_model.bkt.core import BKT_CONFIG, TYPED_QUESTION_TYPES  # noqa: E402
from analytics.learner_model.bkt.mastery import (  # noqa: E402
    _group_response_history,
    _ordered_responses,
    get_vocabulary_mastery,
)
from analytics.learner_model.bkt.placement_prior import (  # noqa: E402
    PLACEMENT_CHAPTERS,
    PLACEMENT_PRIOR_SHRINKAGE_K,
    PLACEMENT_QUESTIONS_PER_CHAPTER,
    PLACEMENT_RESOLVER_VERSIONS,
    get_published_word_chapters,
)
from db import connect_db  # noqa: E402

TOLERANCE = 1e-9


def _update(p: float, correct: bool, question_type: str | None) -> float:
    """Textbook BKT step, written out independently of bkt.core."""
    c = BKT_CONFIG
    typed = str(question_type or "").strip().lower() in TYPED_QUESTION_TYPES
    guess, slip = (c.guess_rate_typed, c.slip_rate_typed) if typed else (c.guess_rate, c.slip_rate)
    if correct:
        posterior = p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)
    else:
        posterior = p * slip / (p * slip + (1 - p) * (1 - guess))
    return posterior + (1 - posterior) * c.learn_rate


def _placement_rows(db, student_id: str) -> list[dict]:
    return db.execute(
        """
        SELECT r.word_id, r.item_id, r.correct, r.evidence_origin, s.lesson_number AS chapter
        FROM vocab_quiz_responses AS r
        JOIN placement_test_attempts AS a
          ON a.id = r.attempt_id AND a.student_id = r.student_id AND a.status = 'completed'
        LEFT JOIN custom_stories AS s ON s.id = r.lesson_id
        WHERE r.student_id = %s AND r.bkt_eligible = TRUE AND r.activity_type = 'diagnostic'
          AND r.diagnostic_exposure_id LIKE 'placement:%%' AND r.resolver_version = ANY(%s)
        """,
        (student_id, list(PLACEMENT_RESOLVER_VERSIONS)),
    ).fetchall()


def _chapter_priors(rows: list[dict]) -> tuple[dict[int, float], dict[int, str], set[str]]:
    by_chapter: dict[int, set[str]] = defaultdict(set)
    correct: dict[int, int] = defaultdict(int)
    skipped: dict[int, str] = {}
    origins = {row["evidence_origin"] for row in rows}
    for row in rows:
        if row["chapter"] not in PLACEMENT_CHAPTERS:
            skipped.setdefault(-1, "placement rows whose story has no lesson_number 5-8")
            continue
        by_chapter[row["chapter"]].add(row["item_id"])
        correct[row["chapter"]] += bool(row["correct"])
    priors: dict[int, float] = {}
    if len(origins) != 1:
        return priors, {0: f"mixed evidence origins {sorted(origins)}; all priors skipped"}, set()
    n = PLACEMENT_QUESTIONS_PER_CHAPTER
    weight = n / (n + PLACEMENT_PRIOR_SHRINKAGE_K)
    for chapter in PLACEMENT_CHAPTERS:
        items = by_chapter.get(chapter, set())
        if len(items) != n:
            skipped[chapter] = f"{len(items)} placement items (needs exactly {n})"
            continue
        priors[chapter] = weight * correct[chapter] / n + (1 - weight) * BKT_CONFIG.initial_mastery
    return priors, skipped, {row["word_id"] for row in rows}


def verify_student(db, student_id: str, verbose: bool) -> int:
    placement = _placement_rows(db, student_id)
    priors, skipped, tested_words = _chapter_priors(placement)
    history = _group_response_history(_ordered_responses(db, student_id))
    live = {row["wordId"]: row for row in get_vocabulary_mastery(db, student_id)}
    cache = {
        row["word_id"]: row
        for row in db.execute(
            "SELECT word_id, p_learned, observation_count FROM student_vocab_mastery WHERE student_id = %s",
            (student_id,),
        ).fetchall()
    }
    word_chapters = get_published_word_chapters(db, set(live) | set(history))
    for word_id, row in live.items():
        word_chapters.setdefault(word_id, row.get("lessonNumber"))

    prior_text = ", ".join(f"ch{c}={p:.4f}" for c, p in sorted(priors.items())) or "none"
    print(f"{student_id}: {len(placement)} placement answers, priors: {prior_text}")
    for chapter, reason in sorted(skipped.items()):
        print(f"  WARN prior skipped {'' if chapter < 1 else f'ch{chapter} '}- {reason}")

    mismatches = 0
    for word_id in sorted(set(live) | set(history)):
        rows = history.get(word_id, [])
        start = BKT_CONFIG.initial_mastery
        if word_id not in tested_words:
            start = priors.get(word_chapters.get(word_id), start)
        expected = start
        for row in rows:
            expected = _update(expected, bool(row["correct"]), row.get("question_type"))
        problems = []
        got_live = live.get(word_id)
        if got_live is not None and abs(got_live["pLearned"] - expected) > TOLERANCE:
            problems.append(f"live={got_live['pLearned']:.6f}")
        got_cache = cache.get(word_id)
        if rows and got_cache is None:
            problems.append("missing from cache")
        elif rows and abs(got_cache["p_learned"] - expected) > TOLERANCE:
            problems.append(f"cache={got_cache['p_learned']:.6f}")
        elif not rows and got_cache is not None:
            problems.append("unseen word present in cache")
        mismatches += bool(problems)
        if problems or verbose:
            answers = "".join("1" if row["correct"] else "0" for row in rows) or "-"
            status = "BAD " + ", ".join(problems) if problems else "OK"
            print(f"  {status:<32} {word_id:<24} start={start:.4f} answers={answers:<6} expected={expected:.6f}")
    print(f"  -> {mismatches} mismatch(es) across {len(set(live) | set(history))} words")
    return mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("student_ids", nargs="*", help="Defaults to every student with completed placement evidence")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print every word, not only mismatches")
    args = parser.parse_args(argv)
    with connect_db() as db:
        student_ids = args.student_ids or [
            row["student_id"]
            for row in db.execute(
                "SELECT DISTINCT r.student_id FROM vocab_quiz_responses AS r "
                "JOIN placement_test_attempts AS a ON a.id = r.attempt_id AND a.status = 'completed' "
                "WHERE r.diagnostic_exposure_id LIKE 'placement:%%' ORDER BY r.student_id"
            ).fetchall()
        ]
        total = sum(verify_student(db, student_id, args.verbose) for student_id in student_ids)
        db.rollback()
    print(f"\n{len(student_ids)} student(s) checked, {total} mismatch(es).")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
