"""Compatibility alias for the repository database adapter."""

from importlib import import_module
import sys


_implementation = import_module("repositories.database")
sys.modules[__name__] = _implementation
