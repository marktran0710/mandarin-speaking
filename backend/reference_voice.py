"""Compatibility alias for the speech reference-voice service."""

from importlib import import_module
import sys

_implementation = import_module("services.speech.reference_voice")
sys.modules[__name__] = _implementation
