"""Compatibility facade for the speech tone service.

The public import path remains stable for routers, services, and tests while
the implementation now lives under the speech domain package.
"""

from services.speech.tones import *  # noqa: F401,F403
from services.speech.tones import (
    _shape_match_score,
    _smooth_for_directional_scoring,
)
