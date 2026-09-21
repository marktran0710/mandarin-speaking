"""Compatibility alias for the speech tone domain package."""

from importlib import import_module
import sys


_implementation = import_module("domain.speech.tones")
for _module_name in ("feedback", "reference_contours", "scoring"):
    sys.modules[f"{__name__}.{_module_name}"] = import_module(
        f"domain.speech.tones.{_module_name}"
    )
sys.modules[__name__] = _implementation
