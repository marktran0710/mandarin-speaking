"""Persistence boundary for the admin console's roster-overview read.

Pure CRUD only. Takes an already-open connection so the caller controls the
transaction boundary.
"""


def fetch_roster_overview(db):
    """Batch the admin console's three landing reads over one pipelined
    round-trip. Returns (student_rows, teacher_rows, attempt_rows).
    """
    with db.pipeline():
        students_cur = db.execute("SELECT * FROM students ORDER BY lower(name)")
        teachers_cur = db.execute("SELECT * FROM teachers ORDER BY lower(name)")
        attempts_cur = db.execute(
            "SELECT * FROM vocab_quiz_attempts ORDER BY completed_at DESC"
        )
    return students_cur.fetchall(), teachers_cur.fetchall(), attempts_cur.fetchall()
