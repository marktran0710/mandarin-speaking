"""Persistence boundary for vocab-quiz-attempt-derived analytics reads."""


def list_student_question_results(db) -> list[dict]:
    return db.execute(
        "SELECT student_id, student_name, question_results "
        "FROM vocab_quiz_attempts "
        "WHERE NOT EXISTS (SELECT 1 FROM students s WHERE s.id = vocab_quiz_attempts.student_id AND s.is_test_account)"
    ).fetchall()
