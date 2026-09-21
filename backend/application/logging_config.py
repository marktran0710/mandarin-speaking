"""Structured logging: console + rotating file handler.

A file handler alongside the console one - a PowerShell window's scrollback
is gone the moment it closes or scrolls past its buffer, so a crash or an
overnight incident during an unattended classroom session had nothing to
review after the fact. 10MB x 5 backups keeps this bounded without a
separate log-rotation job.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

# backend/ is this file's grandparent (backend/application/logging_config.py),
# matching the log location main.py used before this module existed.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


def configure_logging() -> logging.Logger:
    log_dir = Path(os.getenv("LOG_DIR", _BACKEND_DIR / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
    return logging.getLogger("speaking_app")
