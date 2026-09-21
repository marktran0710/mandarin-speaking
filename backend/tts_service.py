"""Compatibility alias for the external speech TTS adapter."""

from importlib import import_module
import sys

_implementation = import_module("infrastructure.speech.tts")
sys.modules[__name__] = _implementation
