from analytics.frex import compute_frex


@router.get("/api/analytics/vocab-quiz/frex")
def get_vocab_quiz_frex(
    top: int = 5,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Return characteristic missed words grouped by student."""
    top = max(1, min(top, 50))
    with connect_db() as db:
        rows = db.execute(
            "SELECT student_id, student_name, question_results "
            "FROM vocab_quiz_attempts"
        ).fetchall()

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
