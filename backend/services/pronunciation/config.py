"""Environment configuration for the pronunciation feedback model.

Read at call time rather than import time so a changed ``.env`` value or a test
override takes effect without re-importing the module. Nothing here is a secret
default: with no key the LLM is simply disabled and local feedback is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _clean(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip().strip('"').strip("'")
    return cleaned or None


@dataclass(frozen=True)
class FeedbackConfig:
    api_key: Optional[str] = None
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 25.0
    language: str = "English"
    max_issues: int = 3

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "FeedbackConfig":
        env = os.environ if environ is None else environ
        api_key = _clean(env.get("PRONUNCIATION_FEEDBACK_API_KEY")) or _clean(env.get("OPENAI_API_KEY"))
        base_url = _clean(env.get("PRONUNCIATION_FEEDBACK_BASE_URL")) or DEFAULT_BASE_URL
        timeout = _clean(env.get("PRONUNCIATION_FEEDBACK_TIMEOUT_SECONDS"))
        return cls(
            api_key=api_key,
            model=_clean(env.get("PRONUNCIATION_FEEDBACK_MODEL")) or DEFAULT_MODEL,
            base_url=base_url.rstrip("/"),
            timeout_seconds=float(timeout) if timeout else cls.timeout_seconds,
            language=_clean(env.get("PRONUNCIATION_FEEDBACK_LANGUAGE")) or cls.language,
        )
