"""End-to-end demo of BKT + SM-2 working together, through the real HTTP API.

One student, two words, one lesson - every step goes through the same
endpoints the student app calls, and every number the system reports is
checked against an independent, hand-written copy of the published
equations (Corbett & Anderson 1995 BKT; Wozniak 1990 SM-2 as adapted in
analytics/learner_model/srs.py). The scenario is the story shown to a
reviewer:

1. Diagnostic rounds (tier1 MCQ, tier2 typed pinyin, tier3 cloze MCQ):
   word A answered 1-1-1, word B answered 0-1-1.
2. BKT: A reaches STRONG; B stays below the 0.95 mastery threshold and is a
   BKT "weak" word. Only A is enrolled in SM-2 (due one day later).
3. Personalized practice on B (2 corrective successes) -> B becomes STRONG
   and is enrolled in SM-2 too. Practice never advances an SM-2 schedule.
4. Next day: A is "due" (SM-2) in the review queue. A correct review moves
   A's interval 1 -> 6 days.
5. Six days later A is due again; a wrong review resets SM-2 (interval 1,
   ease drops) AND is fed back to BKT, which lowers A's p(learned) and
   re-opens practice for A - the two models hand work to each other.

Set ``LEARNING_FLOW_TRACE=path.json`` to also write the step-by-step trace
used by the demo page.
"""

from __future__ import annotations

import json
import os

import db
from tests.test_bkt_mastery_api import _attempt, _post_attempt, _response

WORD_A = "附近"
WORD_B = "房間"
STORY = "lesson-1"

# Independent copies of the equations, deliberately not imported from the
# production modules so a regression there cannot hide itself here.
P_L0, P_T = 0.20, 0.15
GUESS_SLIP = {"single_choice": (0.20, 0.10), "free_text": (0.05, 0.15)}


def bkt_step(p: float, correct: bool, answer_format: str) -> float:
    g, s = GUESS_SLIP[answer_format]
    if correct:
        posterior = p * (1 - s) / (p * (1 - s) + (1 - p) * g)
    else:
        posterior = p * s / (p * s + (1 - p) * (1 - g))
    return posterior + (1 - posterior) * P_T


def sm2_ease(ease: float, q: int) -> float:
    return max(1.3, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))


def _words(client, student_id: str, today: str | None = None) -> dict:
    params = {"story_id": STORY}
    if today:
        params["today"] = today
    rows = client.get(f"/api/students/{student_id}/vocabulary-mastery", params=params).json()["words"]
    return {row["word"]: row for row in rows}


def _queue(client, student_id: str, today: str) -> list[dict]:
    response = client.get(
        f"/api/students/{student_id}/review-queue",
        params={"story_id": STORY, "include_all": "true", "today": today},
    )
    assert response.status_code == 200, response.text
    return response.json()["queue"]


def _srs(student_id: str) -> dict:
    with db.connect_db() as conn:
        rows = conn.execute(
            "SELECT word_id, reps, ease, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s",
            (student_id,),
        ).fetchall()
    return {row["word_id"]: row for row in rows}


def _diagnostic(round_index: int, mode: str, level: str, kind: str, dimension: str, answers: dict) -> dict:
    results = []
    for word, correct in answers.items():
        result = _response(word, correct, f"diag-{round_index}-{word}", level=level, question_kind=kind)
        result.update({"knowledgeDimension": dimension, "quizId": f"diag-{round_index}"})
        results.append(result)
    attempt = _attempt(f"diag-{round_index}", mode, f"2026-08-1{round_index}T00:00:00Z", results)
    attempt["level"] = level
    return attempt


def _review(attempt_id: str, mode: str, answers: dict, day: str) -> dict:
    results = []
    for word, correct in answers.items():
        result = _response(word, correct, f"{attempt_id}-{word}", eligible=False, question_kind="basic_meaning_mcq")
        result.update({"knowledgeDimension": "meaning", "quizId": attempt_id})
        results.append(result)
    return _attempt(attempt_id, mode, f"{day}T00:00:00Z", results)


def _answer_review_question(client, student_id: str, session_id: str, question: dict, day: str, *, correct: bool):
    with db.connect_db() as conn:
        assessment = conn.execute(
            "SELECT vocab_assessment FROM custom_stories WHERE id = %s",
            (question["sourceStoryId"],),
        ).fetchone()["vocab_assessment"]
    item = next(
        value for value in assessment
        if value["questionType"] == question["questionType"]
        and value["targetWord"] == question["word"]
    )
    accepted = item.get("acceptedAnswers") or [item["correctAnswer"]]
    if correct:
        answer = accepted[0]
    elif question["answerFormat"] == "single_choice":
        answer = next(value for value in item.get("options", []) if value not in accepted)
    else:
        answer = "definitely-wrong-pinyin"
    payload = {"slotId": question["slotId"], "selectedAnswer": answer, "responseTimeMs": 700}
    response = client.post(
        f"/api/students/{student_id}/review-sessions/{session_id}/answers",
        params={"today": day},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json(), item


def test_bkt_and_sm2_collaborate_end_to_end(logged_in_student):
    client, student = logged_in_student
    sid = student["id"]
    trace: list[dict] = []
    expected = {WORD_A: P_L0, WORD_B: P_L0}

    def snapshot(step: str, detail: str, today: str | None = None, queue_day: str | None = None) -> dict:
        words = _words(client, sid, today)
        srs = _srs(sid)
        entry = {"step": step, "detail": detail, "words": {}}
        for word in (WORD_A, WORD_B):
            row = words.get(word, {})
            bkt = (row.get("vocabularyState") or {}).get("bkt") or {}
            schedule = srs.get(word)
            entry["words"][word] = {
                "pLearned": bkt.get("pLearned"),
                "expectedPLearned": round(expected[word], 4),
                "bktStatus": bkt.get("status"),
                "reviewStatus": ((row.get("vocabularyState") or {}).get("review") or {}).get("status"),
                "practiceStatus": ((row.get("vocabularyState") or {}).get("practice") or {}).get("status"),
                "srs": None if schedule is None else {
                    "reps": schedule["reps"], "ease": round(float(schedule["ease"]), 2),
                    "intervalDays": schedule["interval_days"], "dueOn": schedule["due_on"].isoformat(),
                },
            }
        if queue_day:
            entry["reviewQueue"] = [
                {"word": item["word"], "reason": item["reviewReason"]} for item in _queue(client, sid, queue_day)
            ]
        trace.append(entry)
        return entry

    snapshot("0. Start", "No evidence yet: every word starts at the prior P(L0).")

    rounds = (
        (1, "tier1", "easy", "basic_meaning_mcq", "meaning", "single_choice", {WORD_A: True, WORD_B: False}),
        (2, "tier2", "medium", "character_to_pinyin_typing", "pinyin_production", "free_text", {WORD_A: True, WORD_B: True}),
        (3, "tier3", "hard", "context_cloze_mcq", "contextual_recall", "single_choice", {WORD_A: True, WORD_B: True}),
    )
    for index, mode, level, kind, dimension, answer_format, answers in rounds:
        attempt = _diagnostic(index, mode, level, kind, dimension, answers)
        assert _post_attempt(client, attempt, today=f"2026-08-1{index}").status_code == 200
        for word, correct in answers.items():
            expected[word] = bkt_step(expected[word], correct, answer_format)
        marks = ", ".join(f"{w} {'✓' if c else '✗'}" for w, c in answers.items())
        snapshot(f"{index}. Diagnostic round {index} ({kind})", marks, queue_day=f"2026-08-1{index}")

    after_diagnostic = trace[-1]["words"]
    for word in (WORD_A, WORD_B):
        assert abs(after_diagnostic[word]["pLearned"] - expected[word]) < 1e-3, (word, after_diagnostic[word])
    assert after_diagnostic[WORD_A]["bktStatus"] == "STRONG"
    assert after_diagnostic[WORD_B]["reviewStatus"] == "NEEDS_PRACTICE"
    assert after_diagnostic[WORD_A]["srs"] is not None and after_diagnostic[WORD_A]["srs"]["intervalDays"] == 1
    assert after_diagnostic[WORD_B]["srs"] is None
    assert {"word": WORD_B, "reason": "weak"} in trace[-1]["reviewQueue"]

    # Day 4: A is due (SM-2), B is weak (BKT). One review round serves both.
    snapshot("4. Next day: review queue", "SM-2 says 附近 is due; BKT says 房間 is weak.",
             today="2026-08-14", queue_day="2026-08-14")
    assert {"word": WORD_A, "reason": "due"} in trace[-1]["reviewQueue"]
    assert {"word": WORD_B, "reason": "weak"} in trace[-1]["reviewQueue"]

    started = client.post(
        f"/api/students/{sid}/review-sessions", params={"today": "2026-08-14"},
    )
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    due_question = session["currentQuestion"]
    assert due_question["word"] == WORD_A and due_question["reviewReason"] == "due"
    answered, item = _answer_review_question(client, sid, session["sessionId"], due_question, "2026-08-14", correct=True)
    expected[WORD_A] = bkt_step(expected[WORD_A], True, item["answerFormat"])
    weak_question = answered["session"]["currentQuestion"]
    assert weak_question["word"] == WORD_B and weak_question["reviewReason"] == "weak"
    answered, item = _answer_review_question(client, sid, session["sessionId"], weak_question, "2026-08-14", correct=True)
    expected[WORD_B] = bkt_step(expected[WORD_B], True, item["answerFormat"])
    snapshot("5. Practice 房間 ✓ + review 附近 ✓",
             "Practice updates BKT only. The due review updates BKT and moves SM-2 (q=4): interval 1 → 6 days.",
             today="2026-08-14")
    step5 = trace[-1]["words"]
    assert step5[WORD_A]["srs"]["reps"] == 2 and step5[WORD_A]["srs"]["intervalDays"] == 6
    assert step5[WORD_A]["srs"]["ease"] == round(sm2_ease(2.5, 4), 2)
    assert step5[WORD_B]["srs"] is None, "one corrective success must not enroll or schedule the word"

    assert _post_attempt(client, _review("practice-2", "weak_words", {WORD_B: True}, "2026-08-15"),
                         today="2026-08-15").status_code == 200
    expected[WORD_B] = bkt_step(expected[WORD_B], True, "single_choice")
    snapshot("6. Practice 房間 ✓ again",
             "Two corrective successes complete practice → 房間 becomes STRONG → SM-2 enrolls it (due in 1 day).",
             today="2026-08-15")
    step6 = trace[-1]["words"]
    assert step6[WORD_B]["reviewStatus"] == "STRONG"
    assert step6[WORD_B]["srs"] is not None and step6[WORD_B]["srs"]["intervalDays"] == 1

    # Day 10: both are due. A is forgotten, B is remembered.
    snapshot("7. Six days later: review queue", "Both words are due by their SM-2 schedules.",
             today="2026-08-20", queue_day="2026-08-20")
    assert {item["word"] for item in trace[-1]["reviewQueue"]} == {WORD_A, WORD_B}
    started = client.post(
        f"/api/students/{sid}/review-sessions", params={"today": "2026-08-20"},
    )
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    question = session["currentQuestion"]
    while question is not None:
        should_be_correct = question["word"] == WORD_B
        answered, item = _answer_review_question(
            client, sid, session["sessionId"], question, "2026-08-20", correct=should_be_correct,
        )
        expected[question["word"]] = bkt_step(
            expected[question["word"]], should_be_correct, item["answerFormat"],
        )
        question = answered["session"]["currentQuestion"]
    snapshot("8. Review: 附近 ✗, 房間 ✓",
             "附近 forgotten: SM-2 resets (q=2, interval 1, ease drops) and BKT lowers p(learned) and re-opens practice. "
             "房間 remembered: interval 1 → 6.",
             today="2026-08-20", queue_day="2026-08-21")
    step8 = trace[-1]["words"]
    assert step8[WORD_A]["srs"]["reps"] == 0 and step8[WORD_A]["srs"]["intervalDays"] == 1
    assert step8[WORD_A]["srs"]["ease"] == round(sm2_ease(sm2_ease(2.5, 4), 2), 2)
    assert step8[WORD_A]["reviewStatus"] == "NEEDS_PRACTICE"
    assert step8[WORD_B]["srs"]["reps"] == 2 and step8[WORD_B]["srs"]["intervalDays"] == 6
    assert any(item["word"] == WORD_A for item in trace[-1]["reviewQueue"])

    for entry in trace[1:]:
        for word, state in entry["words"].items():
            if state["pLearned"] is not None:
                assert abs(state["pLearned"] - state["expectedPLearned"]) < 1e-3, (entry["step"], word, state)

    print(json.dumps(trace, ensure_ascii=False, indent=2, default=str))
    out = os.getenv("LEARNING_FLOW_TRACE")
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(trace, handle, ensure_ascii=False, indent=2, default=str)
