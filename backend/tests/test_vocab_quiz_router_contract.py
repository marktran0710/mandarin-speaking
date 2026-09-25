from inspect import iscoroutinefunction

import security.auth as auth
from fastapi.routing import APIRoute

from routers import vocab_quiz
from routers import vocab_quiz_analytics, vocab_quiz_attempts, vocab_quiz_mastery, vocab_quiz_progression


EXPECTED_OPERATIONS = {
    ("GET", "/api/vocab-quiz-attempts"),
    ("POST", "/api/vocab-quiz-attempts"),
    ("POST", "/api/vocab-quiz-responses"),
    ("GET", "/api/students/{student_id}/weak-words"),
    ("GET", "/api/students/{student_id}/review-queue"),
    ("GET", "/api/students/{student_id}/vocabulary-mastery"),
    ("GET", "/api/students/{student_id}/vocabulary-progression"),
    ("GET", "/api/students/{student_id}/vocabulary-mastery/{word_id:path}/seen-items"),
    ("GET", "/api/vocab-quiz-attempts/weak-words"),
    ("GET", "/api/analytics/vocab-quiz/frex"),
}


def _operations(routes):
    return {
        (method, route.path)
        for route in routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def _dependency_calls(dependant):
    yield dependant.call
    for child in dependant.dependencies:
        yield from _dependency_calls(child)


def test_facade_exposes_exact_vocab_quiz_operations_without_duplicates():
    operations = [
        (method, route.path)
        for route in vocab_quiz.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    ]
    assert set(operations) == EXPECTED_OPERATIONS
    assert len(operations) == len(set(operations))
    assert _operations(vocab_quiz_attempts.router.routes) == {
        ("GET", "/api/vocab-quiz-attempts"),
        ("POST", "/api/vocab-quiz-attempts"),
        ("POST", "/api/vocab-quiz-responses"),
    }
    assert _operations(vocab_quiz_mastery.router.routes) == EXPECTED_OPERATIONS - {
        ("GET", "/api/vocab-quiz-attempts"),
        ("POST", "/api/vocab-quiz-attempts"),
        ("POST", "/api/vocab-quiz-responses"),
        ("GET", "/api/analytics/vocab-quiz/frex"),
        ("GET", "/api/students/{student_id}/vocabulary-progression"),
    }
    assert _operations(vocab_quiz_progression.router.routes) == {
        ("GET", "/api/students/{student_id}/vocabulary-progression"),
    }
    assert _operations(vocab_quiz_analytics.router.routes) == {
        ("GET", "/api/analytics/vocab-quiz/frex")
    }


def test_facade_preserves_auth_chain_and_endpoint_shapes():
    assert vocab_quiz.router.dependencies[0].dependency is auth.get_current_identity
    student_only_operations = {
        ("POST", "/api/vocab-quiz-attempts"),
        ("POST", "/api/vocab-quiz-responses"),
        ("GET", "/api/vocab-quiz-attempts/weak-words"),
    }
    for route in vocab_quiz.router.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = set(_dependency_calls(route.dependant))
        assert auth.get_current_identity in calls
        if any((method, route.path) in student_only_operations for method in route.methods):
            assert auth.require_student in calls

    seen_route = next(
        route
        for route in vocab_quiz.router.routes
        if isinstance(route, APIRoute) and route.path.endswith("{word_id:path}/seen-items")
    )
    assert "{word_id:path}" in seen_route.path
    assert iscoroutinefunction(vocab_quiz.record_vocab_quiz_response)
    assert iscoroutinefunction(vocab_quiz.get_student_review_queue)
