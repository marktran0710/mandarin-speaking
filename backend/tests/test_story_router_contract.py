from fastapi.routing import APIRoute

from main import app
from routers import stories
from routers.story_crud import router as story_crud_router
from routers.story_quiz_materials import router as story_quiz_materials_router
from routers.story_quiz_pools import router as story_quiz_pools_router


EXPECTED_STORY_OPERATIONS = {
    ("GET", "/api/custom-stories"),
    ("POST", "/api/custom-stories"),
    ("DELETE", "/api/custom-stories/{story_id}"),
    ("PATCH", "/api/custom-stories/{story_id}/vocabulary-metadata"),
    ("POST", "/api/custom-stories/{story_id}/quiz-vocabulary"),
    ("PUT", "/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}"),
    ("DELETE", "/api/custom-stories/{story_id}/quiz-vocabulary/{word_id}"),
    ("PUT", "/api/custom-stories/{story_id}/quiz-exclusions"),
    ("PUT", "/api/custom-stories/{story_id}/quiz-pending-approvals"),
    ("PUT", "/api/custom-stories/{story_id}/quiz-question"),
    ("PATCH", "/api/custom-stories/{story_id}/vocabulary-distractors"),
    ("PATCH", "/api/custom-stories/{story_id}/vocabulary-cloze"),
    ("PATCH", "/api/custom-stories/{story_id}/vocabulary-synonym"),
}


def _operations(routes):
    return {
        (method, route.path)
        for route in routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/api/custom-stories")
    }


def test_story_routes_are_registered_without_duplicates():
    app_operations = [
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/custom-stories")
        for method in route.methods
        if (method, route.path) in EXPECTED_STORY_OPERATIONS
    ]

    assert set(app_operations) == EXPECTED_STORY_OPERATIONS
    assert len(app_operations) == len(set(app_operations))
    assert _operations(stories.router.routes) == EXPECTED_STORY_OPERATIONS


def test_story_routers_keep_story_access_auth_dependency():
    for router in (
        story_crud_router,
        story_quiz_materials_router,
        story_quiz_pools_router,
    ):
        assert any(
            dependency.dependency.__name__ == "require_story_access"
            for dependency in router.dependencies
        )

    for route in app.routes:
        if isinstance(route, APIRoute) and _operations([route]) & EXPECTED_STORY_OPERATIONS:
            dependency_names = {
                dependency.call.__name__
                for dependency in route.dependant.dependencies
                if dependency.call is not None
            }
            assert "require_story_access" in dependency_names
