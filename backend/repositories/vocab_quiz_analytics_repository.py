"""Persistence boundary for vocab-quiz-attempt-derived analytics reads."""


def list_student_question_results(db) -> list[dict]:
    return db.execute(
        "SELECT student_id, student_name, question_results "
        "FROM vocab_quiz_attempts"
    ).fetchall()
