"""Compatibility alias for the speech transcription pipeline."""

from importlib import import_module
import sys


_implementation = import_module("services.speech.asr.transcription")
sys.modules[__name__] = _implementation
