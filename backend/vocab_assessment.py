"""Compatibility alias for vocabulary assessment domain rules."""

from importlib import import_module
import sys

_implementation = import_module("domain.vocabulary.assessment")
sys.modules[__name__] = _implementation
