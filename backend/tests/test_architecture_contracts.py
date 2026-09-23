"""Enforces the Route -> Service -> Repository -> DB layering so it doesn't
quietly drift back to routes owning SQL (see docs/backend-architecture.md).

Deliberately mechanical and narrow to avoid false positives / brittleness:
- The router check flags a literal ``.execute(`` call, not the word "SQL" or
  "SELECT" (which can legitimately appear in a docstring or comment
  explaining what a repository call does).
- The domain/analytics check flags a real FastAPI import or HTTPException
  usage, not any mention of the word "fastapi".

A router opening ``connect_db()`` and handing the connection to a service is
the intended pattern (the router owns the transaction boundary) and is not
flagged - only routers that still execute SQL statements themselves are.
"""
import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# routers/frontend.py serves the built SPA (mimetypes, static file paths) -
# it never touches the database and is not part of the API surface this
# contract is about. routers/health.py's liveness/readiness probe needs to
# prove DB connectivity directly (a repository wrapper around `SELECT 1`
# would add a layer with no behavior); it has no business logic or data
# model, so it's exempt from the "no SQL in routes" rule this test enforces.
ROUTER_EXCLUSIONS = {"frontend.py", "health.py"}


def _iter_python_files(directory: Path):
    if not directory.is_dir():
        return
    yield from sorted(directory.rglob("*.py"))


def _source_lines_with_execute_calls(path: Path) -> list[int]:
    """Line numbers of any ``<expr>.execute(`` call in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ):
            hits.append(node.lineno)
    return hits


def test_routers_do_not_execute_sql_directly():
    """HIGH-severity violation per the architecture audit: a route running a
    SQL statement itself instead of delegating to a repository through a
    service. See BACKEND_ARCHITECTURE_PLAN.md / docs/backend-architecture.md."""
    routers_dir = BACKEND_ROOT / "routers"
    violations = {}
    for path in _iter_python_files(routers_dir):
        if path.name in ROUTER_EXCLUSIONS:
            continue
        hits = _source_lines_with_execute_calls(path)
        if hits:
            violations[str(path.relative_to(BACKEND_ROOT))] = hits
    assert not violations, (
        "Router(s) still execute SQL directly instead of going through a "
        f"repository/service: {violations}"
    )


def _imports_fastapi_or_raises_http_exception(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "fastapi" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "fastapi":
                return True
        elif isinstance(node, ast.Name) and node.id == "HTTPException":
            return True
    return False


def test_pure_domain_and_analytics_modules_do_not_import_fastapi():
    """Pure algorithm code (BKT, SRS, tone/acoustic scoring) must stay
    testable and reusable without a running app - no FastAPI, no
    HTTPException, no HTTP-shaped control flow."""
    violations = []
    for subdir in ("domain", "analytics"):
        for path in _iter_python_files(BACKEND_ROOT / subdir):
            if _imports_fastapi_or_raises_http_exception(path):
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert not violations, f"Domain/analytics module(s) depend on FastAPI: {violations}"


def test_repository_modules_do_not_import_fastapi():
    """Repositories are a persistence boundary, not an HTTP one."""
    violations = []
    for path in _iter_python_files(BACKEND_ROOT / "repositories"):
        if _imports_fastapi_or_raises_http_exception(path):
            violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert not violations, f"Repository module(s) depend on FastAPI: {violations}"
