# Backend architecture

This is the canonical description of how `backend/` is organized. If you're
adding an endpoint, a database table, or a new algorithm, this document says
where the code goes.

## The rule

```
API Route  ->  Service  ->  Repository  ->  Database
```

Pure algorithms (BKT, SRS, tone/acoustic scoring) sit beside this chain, not
in it:

```
Route  ->  Service  ->  Domain / Analytics algorithm
                  \->  Repository  ->  Database
```

### Route

Owns: HTTP path/method, request parsing, the `Depends(auth....)`
authentication/authorization dependency, mapping a domain exception to an
HTTP status code, and calling **one** service function.

Does not own: SQL, a business decision, an algorithm, or a raw
`HTTPException` raised in the middle of a workflow (raise it only to map a
domain exception the service already raised).

```python
@router.post("/api/vocab-quiz-attempts")
def create_vocab_quiz_attempt(attempt, today=None, identity=Depends(auth.require_student)):
    with connect_db() as db:
        try:
            vocab_quiz_attempt_service.record_attempt(db, attempt, identity.id, ...)
        except vocab_quiz_attempt_service.AttemptConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ...
```

The route opens the `connect_db()` block and hands the connection to the
service - the route owns the *transaction boundary* (how much work commits
together), the service owns what happens inside it.

### Service

Owns: the use case. Orchestrates a repository, a domain/analytics
calculation, and whatever else one request needs, in the right order.
Raises a **domain exception** - a small class carrying `(status_code,
detail)` or a purpose-specific subclass - never `fastapi.HTTPException`
directly (a couple of documented exceptions in the story-quiz-material
cluster mirror pre-existing sibling-file convention; new code shouldn't add
more).

```python
class AttemptConflictError(Exception): ...

def record_attempt(db, attempt, identity_id, *, now, day_seconds):
    ...
    existing = repo.find_attempt_by_id(db, attempt.id)
    if existing is not None and existing.get("student_id") != identity_id:
        raise AttemptConflictError("Quiz attempt already belongs to another student.")
    repo.insert_attempt(db, ...)
    record_attempt_and_rebuild(db, ...)  # BKT
    if attempt.mode == "maintenance_review":
        apply_srs_updates(db, ...)       # SRS
```

### Repository

Owns: SQL. Plain functions that take an **already-open connection** as
their first argument and return rows or mapped dicts - never opens its own
`connect_db()` (that would break the caller's transaction boundary) and
never raises `HTTPException` or decides a business rule ("is this word
weak", "did this attempt already exist" - those are service-layer
decisions, even when they need a repository read to answer).

```python
def find_attempt_by_id(db, attempt_id: str) -> dict | None:
    return db.execute("SELECT * FROM vocab_quiz_attempts WHERE id = %s", (attempt_id,)).fetchone()
```

Row-to-API-shape mappers (`row_to_student`, `row_to_vocab_quiz_attempt`,
etc.) live in `repositories/database.py` alongside the connection pool -
import them into a repository module rather than duplicating them.

### Domain / Analytics

Pure `inputs -> algorithm -> outputs`. No FastAPI import, no
`HTTPException`, no `connect_db()` call. `analytics/bkt.py` and
`analytics/srs.py` are the reference examples - both take plain values in
and return plain values out, and are unit-testable with no app running.
Some analytics functions (`analytics/bkt_mastery.py`,
`analytics/srs_store.py`) do take a `db` connection as a parameter to read
supporting state, which is an accepted, pre-existing pattern in this
codebase for functions that are still fundamentally computing a mastery/
schedule *decision*, not doing CRUD - `tests/test_architecture_contracts.py`
enforces the FastAPI-independence rule, not a hard "never touches db" rule,
for this directory.

### Infrastructure

`repositories/database.py` owns the connection pool (`connect_db()`,
`init_db()`, `close_db()`, `reset_pool_for_tests()`) and the row mappers.
`infrastructure/database/` holds startup bootstrap.

## Directory map

```
backend/
  api/schemas/          Pydantic request/response models
  routers/               32 files - HTTP only, see "Route" above.
                          1 documented exception: health.py's liveness
                          probe queries the DB directly (no business logic
                          to extract; see test_architecture_contracts.py).
  services/               Use-case orchestration.
    speech/               ASR adapters, AI-feedback pipeline, reference voice.
  repositories/           SQL. 19 modules + database.py (pool + mappers).
  analytics/              BKT, SRS, weak-word ranking, review-queue combination.
  domain/
    speech/                Tone/acoustic scoring (tone_decision.py, tones/,
                            acoustics/) - see docs/learning-engine.md.
    vocabulary/             Assessment-answer resolution.
  infrastructure/database/ Connection bootstrap.
  application/             register_routers() - the one place every router
                            gets mounted onto the FastAPI app.
  main.py                  Thin entrypoint (~114 lines): creates the app,
                            calls register_routers(), startup/shutdown hooks.
  tests/                   Includes test_architecture_contracts.py.
```

## Rules for adding new code

**A new endpoint**: add the route to the right router file (or a new one,
registered in `application/router_registry.py`). It should be a handful of
lines: parse the request, open `connect_db()`, call one service function,
map any domain exception it raises to an HTTP status.

**A new repository function**: pure SQL, takes `db` as its first argument,
returns rows/dicts. If a mapper already exists in `repositories/
database.py`, import and reuse it.

**A new service function**: this is where the decision logic goes. If it
needs to reject the request, raise a domain exception (define one for the
module if none exists yet) - don't import `fastapi`.

**A new algorithm** (a new scoring heuristic, a new BKT variant, etc.):
`analytics/` or `domain/`, with no FastAPI/HTTPException/`connect_db()`
dependency. Write it so a unit test can call it directly with plain values.

**Transactions**: one `with connect_db() as db:` block per request is the
default. If a request has a documented reason to split into multiple
transactions (see `services/submission_service.py`'s docstring for a real
example - a scene write must be visible to concurrent readers before a
slow best-effort LLM call runs), keep that as multiple `connect_db()`
blocks and document why. Don't collapse a deliberate split without
understanding why it exists; conversely, don't assume every existing split
is deliberate - `services/student_service.py`'s docstring documents a case
where two transactions were safely collapsed to one.

## Testing expectations

- `tests/test_architecture_contracts.py` runs on every change: no router
  executes SQL directly (except the documented `health.py` case), and no
  domain/analytics/repository module imports FastAPI.
- A repository/service extraction is a pure code-motion refactor: same SQL,
  same status codes, same response shapes. Prove it with the existing
  endpoint's tests before and after, not just a passing test suite (a test
  suite that was already green before your change proves nothing about your
  change - run it, then make the change, then run it again).
- `python -m pytest --collect-only -q` from `backend/` is a fast (a few
  seconds) whole-app import sanity check - if a refactor breaks an import
  anywhere in the app (e.g. a compatibility facade router re-exporting a
  function you moved), this catches it before you run anything slower.
