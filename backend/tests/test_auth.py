"""JWT session cookie: issuing, decoding, and the identity dependencies.

Unit-level - exercises auth.py directly, not through HTTP, so these run
without a database and don't need the `client` fixture.
"""
import os
import sys
import time

import jwt
import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth


def test_issue_then_decode_round_trips_role_and_id():
    token = auth.issue_token("student", "abc-123")
    identity = auth.decode_token(token)
    assert identity.role == "student"
    assert identity.id == "abc-123"


def test_issue_rejects_unknown_role():
    with pytest.raises(ValueError):
        auth.issue_token("admin", "abc-123")


def test_issue_rejects_empty_subject_id():
    with pytest.raises(ValueError):
        auth.issue_token("teacher", "")


def test_decode_rejects_a_token_signed_with_a_different_key():
    forged = jwt.encode(
        {"role": "teacher", "sub": "someone", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        "a-completely-different-secret",
        algorithm=auth.JWT_ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(forged)
    assert exc_info.value.status_code == 401


def test_decode_rejects_an_expired_token():
    expired = jwt.encode(
        {
            "role": "student",
            "sub": "abc-123",
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 1,
        },
        auth.JWT_SECRET_KEY,
        algorithm=auth.JWT_ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(expired)
    assert exc_info.value.status_code == 401


def test_decode_rejects_a_token_with_no_role_claim():
    tokenless_role = jwt.encode(
        {"sub": "abc-123", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        auth.JWT_SECRET_KEY,
        algorithm=auth.JWT_ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(tokenless_role)
    assert exc_info.value.status_code == 401


def test_decode_rejects_garbage():
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token("not-a-jwt-at-all")
    assert exc_info.value.status_code == 401


def test_get_current_identity_requires_a_cookie():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_identity(session_token=None)
    assert exc_info.value.status_code == 401


def test_get_current_identity_decodes_a_present_cookie():
    token = auth.issue_token("teacher", "t-1")
    identity = auth.get_current_identity(session_token=token)
    assert identity == auth.Identity(role="teacher", id="t-1")


def test_require_student_rejects_a_teacher_identity():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_student(identity=auth.Identity(role="teacher", id="t-1"))
    assert exc_info.value.status_code == 403


def test_require_student_accepts_a_student_identity():
    identity = auth.Identity(role="student", id="s-1")
    assert auth.require_student(identity=identity) is identity


def test_require_teacher_rejects_a_student_identity():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_teacher(identity=auth.Identity(role="student", id="s-1"))
    assert exc_info.value.status_code == 403
