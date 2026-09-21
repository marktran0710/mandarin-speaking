"""Compatibility alias for the tone-verdict domain policy.

The implementation lives in ``domain.speech.tone_decision``.  This module is
deliberately kept as a facade because the legacy import path is used by
routers, services, and tests, and module identity matters for monkeypatching.
"""

from importlib import import_module
import sys

_implementation = import_module("domain.speech.tone_decision")
sys.modules[__name__] = _implementation
