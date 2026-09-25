"""Use-case orchestration for the admin console's landing data.

Coordinates the admin repository with the same row-to-API-shape mappers the
standalone students/teachers/vocab-quiz-attempts endpoints use, so the
console stays field-for-field compatible with those.
"""
from repositories import admin_repository as repo
from repositories import story_repository
from repositories.database import row_to_student, row_to_teacher, row_to_vocab_quiz_attempt
from repositories.database import row_to_custom_story


def get_roster_overview(db) -> dict:
    students, teachers, attempts = repo.fetch_roster_overview(db)
    return {
        "students": [row_to_student(row) for row in students],
        "teachers": [row_to_teacher(row) for row in teachers],
        "quizAttempts": [row_to_vocab_quiz_attempt(row) for row in attempts],
    }


def list_content_bank(db, *, limit: int, skip: int) -> list[dict]:
    rows = story_repository.list_stories(db, published_only=False, limit=limit, skip=skip)
    return [row_to_custom_story(row) for row in rows]
