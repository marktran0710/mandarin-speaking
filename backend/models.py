"""Compatibility alias for API schemas.

New code should import from ``api.schemas.models``.  The alias keeps the
historical ``models`` import path working for routers, scripts, and clients
that still load backend modules by their legacy names.
"""

from importlib import import_module
import sys

_implementation = import_module("api.schemas.models")
sys.modules[__name__] = _implementation
