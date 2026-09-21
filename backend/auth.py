"""Compatibility alias for the security boundary.

New code should import from ``security.auth``.  Keep this module so existing
routers, scripts, and tests continue to resolve the historical import path.
"""

from importlib import import_module
import sys

_implementation = import_module("security.auth")
sys.modules[__name__] = _implementation
