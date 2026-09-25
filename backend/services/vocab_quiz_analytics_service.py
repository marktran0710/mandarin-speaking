"""Use-case orchestration for the vocab-quiz FREX (characteristic missed
words) analytics endpoint."""
from analytics.frex import compute_frex
from repositories import vocab_quiz_analytics_repository as repo


def get_frex(db, top: int) -> list[dict]:
    top = max(1, min(top, 50))
    rows = repo.list_student_question_results(db)

    responses = []
    names: dict[str, str] = {}
    for row in rows:
        student_id = row.get("student_id") or row.get("student_name")
        if not student_id:
            continue
        names[student_id] = row.get("student_name") or student_id
        for result in row.get("question_results") or []:
            word = result.get("word") if isinstance(result, dict) else None
            if word:
                responses.append((student_id, word, bool(result.get("correct"))))

    ranked = compute_frex(responses, top_n=top)
    return [
        {
            "studentId": student_id,
            "studentName": names.get(student_id, student_id),
            "words": [word.__dict__ for word in words],
        }
        for student_id, words in ranked.items()
    ]
