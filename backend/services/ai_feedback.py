"""Compatibility alias for the speech feedback pipeline.

Keep the historical import path working while exposing the same module object
under the semantic ``services.speech.feedback`` namespace. Module aliasing is
intentional here: existing monkeypatches must continue to affect the live
implementation during tests and application startup.
"""

from importlib import import_module
import sys


_implementation = import_module("services.speech.feedback.pipeline")
sys.modules[__name__] = _implementation
