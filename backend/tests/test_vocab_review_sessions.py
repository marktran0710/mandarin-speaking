from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from analytics.learner_model.srs import SrsState
from analytics.learner_model.srs_store import (
    complete_review_activity,
    reserve_review_activity,
    upsert_srs_state,
)
from db import connect_db
from services.vocab_review_session_service import _mix_queue


def _assessment_items(word_id="hello-word", target_word="你好"):
    return [
        {
            "questionId": "review-hello-meaning",
            "wordId": word_id,
            "targetWord": target_word,
            "pinyin": "nǐ hǎo",
            "simpleEnglishMeaning": "hello",
            "round": 1,
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
            "prompt": "What does 你好 mean?",
            "options": ["hello", "goodbye"],
            "correctAnswer": "hello",
            "acceptedAnswers": ["hello"],
            "explanation": "你好 is a greeting.",
        },
        {
            "questionId": "review-hello-pinyin",
            "wordId": word_id,
            "targetWord": target_word,
            "pinyin": "nǐ hǎo",
            "simpleEnglishMeaning": "hello",
            "round": 2,
            "questionType": "character_to_pinyin_typing",
            "answerFormat": "free_text",
            "prompt": "Type the pinyin for 你好.",
            "options": [],
            "correctAnswer": "nǐ hǎo",
            "acceptedAnswers": ["nǐ hǎo"],
            "explanation": "The tones are third tone, then third tone.",
        },
        {
            "questionId": "review-hello-context",
            "wordId": word_id,
            "targetWord": target_word,
            "pinyin": "nǐ hǎo",
            "simpleEnglishMeaning": "hello",
            "round": 3,
            "questionType": "context_cloze_mcq",
            "answerFormat": "single_choice",
            "prompt": "___，老师！",
            "options": ["你好", "再见"],
            "correctAnswer": "你好",
            "acceptedAnswers": ["你好"],
            "explanation": "你好 fits a greeting to the teacher.",
        },
    ]


def _publish_lesson(story_id: str, *, word_id="hello-word", target_word="你好") -> None:
    with connect_db() as db:
        db.execute(
            """INSERT INTO custom_stories (id, title, frames, published, vocab_assessment)
               VALUES (%s, 'Review session lesson', %s, TRUE, %s)""",
            (story_id, Jsonb([]), Jsonb(_assessment_items(word_id, target_word))),
        )


def _complete_diagnostics(client, story_id: str, *, correct: bool, word="你好") -> None:
    answers = {
        "tier1": ("review-hello-meaning", "hello" if correct else "goodbye", ["hello", "goodbye"]),
        "tier2": ("review-hello-pinyin", "nǐ hǎo" if correct else "ni hao", []),
        "tier3": ("review-hello-context", "你好" if correct else "再见", ["你好", "再见"]),
    }
    for index, (mode, (item_id, selected, options)) in enumerate(answers.items(), start=1):
        response = client.post("/api/vocab-quiz-attempts", json={
            "id": f"{story_id}-{mode}-{uuid4()}",
            "storyId": story_id,
            "studentName": "Student",
            "mode": mode,
            "level": mode,
            "completedAt": f"2026-09-0{index}T00:00:00Z",
            "totalQuestions": 1,
            "correctCount": int(correct),
            "totalTimeMs": 800,
            "questionResults": [{
                "word": word,
                "correct": correct,
                "timeMs": 800,
                "itemId": item_id,
                "selectedAnswer": selected,
                "presentedOptions": options,
                "quizId": f"{story_id}-{mode}-{uuid4()}",
            }],
        })
        assert response.status_code == 200, response.text


def test_session_mix_uses_two_due_then_one_weak_and_never_repeats_a_word():
    queue = [
        {"wordId": f"due-{index}", "reviewReason": "due"} for index in range(5)
    ] + [
        {"wordId": f"weak-{index}", "reviewReason": "weak"} for index in range(4)
    ]

    selected = _mix_queue(queue, 12)

    assert [row["reviewReason"] for row in selected[:9]] == [
        "due", "due", "weak", "due", "due", "weak", "due", "weak", "weak",
    ]
    assert len({row["wordId"] for row in selected}) == len(selected)


def test_review_activity_shuffle_bag_reserves_until_answer_and_uses_each_once(logged_in_student):
    _client, student = logged_in_student
    with connect_db() as db:
        upsert_srs_state(
            db,
            student["id"],
            "bag-word",
            SrsState(reps=1, ease=2.5, interval_days=1, due_on=datetime.now(timezone.utc)),
        )

        first = reserve_review_activity(db, student["id"], "bag-word", seed="fixed-test-seed")
        assert reserve_review_activity(db, student["id"], "bag-word", seed="ignored-after-persist") == first
        seen = [first]
        assert complete_review_activity(db, student["id"], "bag-word", first) is True

        for _ in range(2):
            activity = reserve_review_activity(db, student["id"], "bag-word")
            assert activity not in seen
            seen.append(activity)
            assert complete_review_activity(db, student["id"], "bag-word", activity) is True

        assert set(seen) == {"meaning", "pinyin", "context"}
        bag = db.execute(
            "SELECT review_activity_bag FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], "bag-word"),
        ).fetchone()["review_activity_bag"]
        assert bag["cycle"] == 1
        assert bag["remaining"] == []
        assert bag["pendingActivity"] is None

        next_cycle = reserve_review_activity(db, student["id"], "bag-word")
        next_bag = db.execute(
            "SELECT review_activity_bag FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], "bag-word"),
        ).fetchone()["review_activity_bag"]
        assert next_bag["cycle"] == 2
        assert next_bag["remaining"][0] == next_cycle


def test_weak_session_resumes_and_answer_retry_is_idempotent(logged_in_student):
    client, student = logged_in_student
    story_id = f"review-weak-{uuid4()}"
    _publish_lesson(story_id)
    _complete_diagnostics(client, story_id, correct=False)

    started = client.post(f"/api/students/{student['id']}/review-sessions")
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    assert session["questionCount"] == 1
    question = session["currentQuestion"]
    assert question["reviewReason"] == "weak"
    assert question["dimension"] == "meaning"
    assert "correctAnswer" not in question
    assert "acceptedAnswers" not in question

    resumed = client.post(f"/api/students/{student['id']}/review-sessions")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["session"]["sessionId"] == session["sessionId"]
    assert resumed.json()["session"]["currentQuestion"]["slotId"] == question["slotId"]

    payload = {"slotId": question["slotId"], "selectedAnswer": "goodbye", "responseTimeMs": 900}
    answer_url = f"/api/students/{student['id']}/review-sessions/{session['sessionId']}/answers"
    first = client.post(answer_url, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["result"]["correct"] is False
    assert first.json()["session"]["status"] == "completed"

    retry = client.post(answer_url, json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["result"] == first.json()["result"]
    changed_retry = client.post(answer_url, json={**payload, "selectedAnswer": "hello"})
    assert changed_retry.status_code == 409

    with connect_db() as db:
        count = db.execute(
            "SELECT count(*) AS count FROM vocab_quiz_responses WHERE student_id = %s AND quiz_id LIKE %s",
            (student["id"], f"review-{session['sessionId']}-%"),
        ).fetchone()["count"]
    assert count == 1


def test_due_failure_lapses_once_and_remains_due_after_bkt_drops(logged_in_student, monkeypatch):
    from dataclasses import replace
    import routers.vocab_quiz_attempts as attempt_routes

    monkeypatch.setattr(
        attempt_routes,
        "settings",
        replace(attempt_routes.settings, app_env="development", srs_day_seconds=86400.0),
    )
    client, student = logged_in_student
    story_id = f"review-due-{uuid4()}"
    _publish_lesson(story_id)
    _complete_diagnostics(client, story_id, correct=True)
    with connect_db() as db:
        upsert_srs_state(
            db,
            student["id"],
            "hello-word",
            SrsState(
                reps=2,
                ease=2.5,
                interval_days=6,
                due_on=date(2026, 10, 1),
                last_reviewed_on=date(2026, 9, 28),
            ),
        )

    started = client.post(f"/api/students/{student['id']}/review-sessions", params={"today": "2026-10-03"})
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    question = session["currentQuestion"]
    assert question["reviewReason"] == "due"
    assert question["dimension"] in {"meaning", "pinyin", "context"}
    before_mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    before_word = next(row for row in before_mastery if row["word"] == question["word"])
    before_dimension = before_word["vocabularyState"]["bkt"]["dimensions"][question["dimension"]]["pLearned"]
    answer_url = f"/api/students/{student['id']}/review-sessions/{session['sessionId']}/answers"
    answer_payload = {"slotId": question["slotId"], "selectedAnswer": "definitely-wrong", "responseTimeMs": 700}
    failed = client.post(answer_url, params={"today": "2026-10-03"}, json=answer_payload)
    assert failed.status_code == 200, failed.text
    assert failed.json()["result"]["correct"] is False

    with connect_db() as db:
        srs = db.execute(
            "SELECT reps FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], "hello-word"),
        ).fetchone()
        events = db.execute(
            "SELECT count(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s AND event_type = 'maintenance_failure'",
            (student["id"], "hello-word"),
        ).fetchone()["count"]
    assert srs["reps"] == 0
    assert events == 1
    after_word = next(
        row for row in client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
        if row["word"] == question["word"]
    )
    assert after_word["vocabularyState"]["bkt"]["dimensions"][question["dimension"]]["pLearned"] < before_dimension
    with connect_db() as db:
        bag = db.execute(
            "SELECT review_activity_bag FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], "hello-word"),
        ).fetchone()["review_activity_bag"]
    assert bag["pendingActivity"] is None
    assert len(bag["remaining"]) == 2

    replay = client.post(answer_url, params={"today": "2026-10-03"}, json=answer_payload)
    assert replay.status_code == 200, replay.text
    with connect_db() as db:
        replayed_events = db.execute(
            "SELECT count(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s AND event_type = 'maintenance_failure'",
            (student["id"], "hello-word"),
        ).fetchone()["count"]
    assert replayed_events == 1

    due_queue = client.get(
        f"/api/students/{student['id']}/review-queue",
        params={"scope": "all_learned", "today": "2026-10-04"},
    )
    assert due_queue.status_code == 200, due_queue.text
    assert [(row["wordId"], row["reviewReason"]) for row in due_queue.json()["queue"]] == [
        ("hello-word", "due"),
    ], due_queue.json()
    # The weak BKT state does not block an enrolled item from coming due.
    next_session = client.post(
        f"/api/students/{student['id']}/review-sessions", params={"today": "2026-10-04"},
    )
    assert next_session.status_code == 200, next_session.text
    next_question = next_session.json()["session"]["currentQuestion"]
    assert next_question["reviewReason"] == "due"
    assert next_question["dimension"] != question["dimension"]
    with connect_db() as db:
        saved_bag = db.execute(
            "SELECT review_activity_bag FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], "hello-word"),
        ).fetchone()["review_activity_bag"]
    assert saved_bag["pendingActivity"] == next_question["dimension"]



def test_stale_review_slot_conflicts_without_recording_a_wrong_answer(logged_in_student):
    client, student = logged_in_student
    story_id = f"review-stale-{uuid4()}"
    _publish_lesson(story_id, word_id="stale-word", target_word="再见")
    _complete_diagnostics(client, story_id, correct=False, word="再见")
    started = client.post(f"/api/students/{student['id']}/review-sessions")
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    question = session["currentQuestion"]
    assert question["sourceStoryId"] == story_id

    updated_items = _assessment_items("stale-word", "再见")
    updated_items[0]["pinyin"] = "zài jiàn"
    with connect_db() as db:
        db.execute(
            "UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s",
            (Jsonb(updated_items), story_id),
        )
        version = db.execute(
            "SELECT vocabulary_version FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()["vocabulary_version"]
        before = db.execute(
            "SELECT count(*) AS count FROM vocab_quiz_responses WHERE student_id = %s",
            (student["id"],),
        ).fetchone()["count"]
    assert version > 1

    stale_answer = client.post(
        f"/api/students/{student['id']}/review-sessions/{session['sessionId']}/answers",
        json={"slotId": question["slotId"], "selectedAnswer": "hello", "responseTimeMs": 500},
    )
    assert stale_answer.status_code == 409
    assert stale_answer.json()["detail"]["code"] == "STALE_VOCABULARY"
    with connect_db() as db:
        after = db.execute(
            "SELECT count(*) AS count FROM vocab_quiz_responses WHERE student_id = %s",
            (student["id"],),
        ).fetchone()["count"]
    assert after == before
