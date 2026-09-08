"""Run a small, repeatable BKT smoke test against a live backend.

This is intentionally separate from pytest: it exercises the deployed HTTP
boundary with a real student session and prints the resulting mastery state.
Use a dedicated test student because the script creates three quiz attempts;
it never creates or deletes accounts and it does not touch the database
directly.

Run from ``backend/``::

    python scripts/manual_bkt_smoke.py \
      --base-url http://127.0.0.1:8000 \
      --student-id <test-student-id> \
      --password <test-student-password>

The three attempts use one word across translation, reverse, and listening
items. A successful run proves login, server-side eligibility, persistence,
per-question-type observations, mastery rebuilding, and weak-word ranking.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import uuid
from typing import Any

import httpx


QUESTION_TYPES = ("translation", "reverse", "listening")
MODES = ("tier1", "tier2", "tier3")


def _response(word: str, question_kind: str, item_id: str, correct: bool) -> dict[str, Any]:
    target_options = [word, "喝茶", "咖啡", "水"]
    if question_kind == "translation":
        correct_answer = "afternoon tea"
        options = [correct_answer, "tea shop", "water", "coffee"]
    else:
        correct_answer = word
        options = target_options
    return {
        "word": word,
        "conceptId": word,
        "correct": correct,
        "timeMs": 1200,
        "itemId": item_id,
        "questionKind": question_kind,
        "level": "easy",
        "baseStoryId": "manual-bkt-smoke",
        "itemVersion": "manual-v1",
        "isBktEligible": True,
        "diagnosticExposureId": f"{item_id}:exposure",
        "bktValidationStatus": "APPROVED",
        "selectedAnswer": correct_answer if correct else options[1],
        "correctAnswer": correct_answer,
        "presentedOptions": options,
        "questionPrompt": word if question_kind != "reverse" else "afternoon tea",
    }


def _attempt(attempt_id: str, mode: str, question_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attempt_id,
        "storyId": "manual-bkt-smoke",
        "studentName": "Manual BKT Smoke Student",
        "mode": mode,
        "baseStoryId": "manual-bkt-smoke",
        "level": "easy",
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "totalQuestions": 1,
        "correctCount": int(question_result["correct"]),
        "totalTimeMs": question_result["timeMs"],
        "questionResults": [question_result],
    }


def _require_ok(response: httpx.Response, action: str) -> None:
    if response.is_error:
        detail = response.text[:500]
        raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {detail}")


def run(base_url: str, student_id: str, password: str, word: str) -> dict[str, Any]:
    prefix = f"manual-bkt-{uuid.uuid4().hex[:10]}"
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=20.0) as client:
        login = client.post(
            "/api/students/login",
            json={"studentId": student_id, "password": password},
        )
        _require_ok(login, "Student login")

        for index, (mode, question_kind) in enumerate(zip(MODES, QUESTION_TYPES), start=1):
            result = _response(
                word,
                question_kind,
                f"{prefix}-item-{index}",
                correct=index != 2,
            )
            attempt = _attempt(f"{prefix}-{mode}", mode, result)
            created = client.post("/api/vocab-quiz-attempts", json=attempt)
            _require_ok(created, f"Create {mode} attempt")

        mastery_response = client.get(f"/api/students/{student_id}/vocabulary-mastery")
        _require_ok(mastery_response, "Read vocabulary mastery")
        mastery = next(
            (row for row in mastery_response.json().get("words", []) if row.get("word") == word),
            None,
        )
        if mastery is None:
            raise RuntimeError(f"No mastery row was rebuilt for {word!r}")

        review_response = client.get(
            f"/api/students/{student_id}/weak-words",
            params={"story_id": "manual-bkt-smoke", "include_all": "true"},
        )
        _require_ok(review_response, "Read weak-word review")
        review = review_response.json()
        if not review.get("unlocked"):
            raise RuntimeError(f"Diagnostic did not unlock after three modes: {review}")
        if word not in {row.get("word") for row in review.get("words", [])}:
            raise RuntimeError(f"The smoke word was not selected for review: {review}")

    return {
        "studentId": student_id,
        "word": word,
        "attemptPrefix": prefix,
        "mastery": mastery,
        "weakWord": next(row for row in review["words"] if row.get("word") == word),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--word", default="下午茶")
    args = parser.parse_args()
    try:
        result = run(args.base_url, args.student_id, args.password, args.word)
    except (httpx.HTTPError, RuntimeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
