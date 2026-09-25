"""Persistence boundary for the PFA/BKT pilot analytics reads."""


def find_student_names(db, student_ids: list[str]) -> list[dict]:
    if not student_ids:
        return []
    return db.execute(
        "SELECT id, name FROM students WHERE id = ANY(%s)",
        (student_ids,),
    ).fetchall()


def list_published_stories_for_audit(db) -> list[dict]:
    return db.execute(
        "SELECT id, title, published, lesson_number, frames, quiz_approved_snapshot "
        "FROM custom_stories WHERE published = TRUE "
        "ORDER BY lesson_number NULLS LAST, created_at, id"
    ).fetchall()


def list_quiz_attempts_for_audit(db) -> list[dict]:
    return db.execute(
        "SELECT id, student_id, student_name, mode, completed_at, question_results "
        "FROM vocab_quiz_attempts"
    ).fetchall()
