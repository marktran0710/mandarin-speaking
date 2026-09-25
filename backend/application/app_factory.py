"""Builds the FastAPI app: metadata, compression/CORS/security/timing
middleware. Router registration and lifespan handlers are wired onto the
returned app separately (see router_registry.py, lifespan.py) so each
concern stays in one file with one reason to change.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from application.middleware import add_security_headers, log_request_timing

OPENAPI_TAGS = [
    {
        "name": "admin",
        "description": "Administration endpoints for managing application data and settings.",
    },
]


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS")
    if configured_origins:
        return [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]

    # Vite picks the next free port when 5173 is taken (5174, 5175, 5176…),
    # so allow the common dev fallbacks to avoid CORS-blocked /api calls.
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://localhost:3000",
    ]


def get_cors_origin_regex() -> str | None:
    """Allow the local pilot UI to use the computer as a LAN server.

    A production deployment should set CORS_ORIGINS explicitly. The fallback
    only accepts HTTP origins on loopback/private IPv4 ranges and the local
    development ports used by this project.
    """
    if os.getenv("CORS_ORIGINS"):
        return None
    return (
        r"^https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}):(?:3000|5173|5174|5175|5176|9000)$"
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mandarin Speaking Practice API",
        version="1.0.0",
        description=(
            "Backend API for the Mandarin Speaking Practice application. "
            "It supports learning content, speech analysis, audio submissions, "
            "and teacher review workflows."
        ),
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Middleware order matters: registered here outermost-last, so a request
    # passes through GZip -> CORS -> security headers -> request timing, and
    # the response passes back through in reverse. Compress large JSON
    # responses (the list endpoints especially - JSON gzips very well).
    # minimum_size skips tiny bodies where compression is not worth it;
    # compresslevel 6 balances ratio against the small production CPU. Added
    # before CORS so CORS stays the outermost middleware.
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_origin_regex=get_cors_origin_regex(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Client-Role"],
    )
    app.middleware("http")(add_security_headers)
    # Added after add_security_headers, so it is the outermost middleware and
    # times the whole request.
    app.middleware("http")(log_request_timing)

    return app
