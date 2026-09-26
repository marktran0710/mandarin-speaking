"""Run a live BKT smoke test from published assessment facts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import uuid
from typing import Any

import httpx

MODES = ("tier1", "tier2", "tier3")


def _require_ok(response: httpx.Response, action: str) -> None:
    if response.is_error:
        raise RuntimeError(f"{action} failed with HTTP {response.status_code}: {response.text[:500]}")


def find_published_triplet(stories: list[dict[str, Any]], requested_word: str | None = None):
    """Return a published story, word id, and its three round items."""
    for story in stories:
        story_status = str(story.get("status") or story.get("publicationStatus") or "").lower()
        if story_status and story_status not in {"published", "active", "approved"}:
            continue
        assessment = story.get("vocabAssessment") or story.get("vocab_assessment")
        if not isinstance(assessment, list):
            continue
        by_word: dict[str, dict[int, dict[str, Any]]] = {}
        for item in assessment:
            if not isinstance(item, dict) or not item.get("questionId"):
                continue
            item_status = str(item.get("status") or item.get("publicationStatus") or "").lower()
            if item_status and item_status not in {"published", "active", "approved"}:
                continue
            word_id = str(item.get("wordId") or "")
            target = str(item.get("targetWord") or "")
            try:
                round_number = int(item.get("round"))
            except (TypeError, ValueError):
                continue
            if word_id and target and round_number in {1, 2, 3}:
                by_word.setdefault(word_id, {})[round_number] = item
        for word_id, rounds in by_word.items():
            if set(rounds) == {1, 2, 3} and (requested_word is None or rounds[1].get("targetWord") == requested_word):
                return story, word_id, {f"tier{n}": rounds[n] for n in (1, 2, 3)}
    suffix = f" for word {requested_word!r}" if requested_word else ""
    raise RuntimeError(f"No published assessment has all three rounds{suffix}")


def _selection(item: dict[str, Any], mode: str) -> str:
    if mode == "tier2":
        return str(item.get("pinyin") or (item.get("acceptedAnswers") or [""])[0])
    return str(item.get("correctAnswer") or (item.get("options") or [""])[0])


def _response(item: dict[str, Any], mode: str, correct: bool) -> dict[str, Any]:
    answer = _selection(item, mode)
    wrong = next((str(value) for value in item.get("options", []) if str(value) != answer), "__wrong_answer__")
    return {"word": item.get("targetWord") or item.get("wordId"), "conceptId": item.get("wordId"),
            "correct": False, "timeMs": 1200, "itemId": item["questionId"],
            "selectedAnswer": answer if correct else wrong, "presentedOptions": item.get("options") or [],
            # Use the published item's version and approval marker. The
            # deliberately false `correct` field above remains a smoke-test
            # guard: the server must resolve correctness from this item.
            "itemVersion": item.get("itemVersion") or item.get("version"),
            "bktValidationStatus": item.get("bktValidationStatus") or "APPROVED"}


def _attempt(attempt_id: str, story_id: str, mode: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"id": attempt_id, "storyId": story_id, "baseStoryId": story_id, "studentName": "Manual BKT Smoke Student",
            "mode": mode, "level": mode, "completedAt": datetime.now(timezone.utc).isoformat(),
            "totalQuestions": 1, "correctCount": 0, "totalTimeMs": result["timeMs"], "questionResults": [result]}


def run(base_url: str, student_id: str, password: str, word: str | None = None) -> dict[str, Any]:
    prefix = f"manual-bkt-{uuid.uuid4().hex[:10]}"
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=20.0) as client:
        _require_ok(client.post("/api/students/login", json={"studentId": student_id, "password": password}), "Student login")
        stories_response = client.get("/api/custom-stories")
        _require_ok(stories_response, "List published stories")
        payload = stories_response.json()
        story, word_id, items = find_published_triplet(payload, word)
        story_id = str(story["id"])
        for index, mode in enumerate(MODES, 1):
            result = _response(items[mode], mode, correct=index != 2)
            _require_ok(client.post("/api/vocab-quiz-attempts", json=_attempt(f"{prefix}-{mode}", story_id, mode, result)), f"Create {mode} attempt")
        mastery_response = client.get(f"/api/students/{student_id}/vocabulary-mastery")
        _require_ok(mastery_response, "Read vocabulary mastery")
        target = items["tier1"].get("targetWord")
        mastery = next((row for row in mastery_response.json().get("words", []) if row.get("word") == target), None)
        review_response = client.get(f"/api/students/{student_id}/weak-words", params={"story_id": story_id, "include_all": "true"})
        _require_ok(review_response, "Read weak-word review")
        review = review_response.json()
        if not review.get("unlocked"):
            raise RuntimeError(f"Diagnostic did not unlock after three rounds: {review}")
        weak = next((row for row in review.get("words", []) if row.get("word") == target), None)
        if weak is None:
            raise RuntimeError(f"Published smoke word was not selected for review: {review}")
    return {"studentId": student_id, "storyId": story_id, "wordId": word_id, "word": target, "mastery": mastery, "weakWord": weak}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--word")
    args = parser.parse_args()
    try:
        result = run(args.base_url, args.student_id, args.password, args.word)
    except (httpx.HTTPError, RuntimeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
