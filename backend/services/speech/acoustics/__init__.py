"""Compatibility alias for the speech acoustics domain package."""

from importlib import import_module
import sys


_implementation = import_module("domain.speech.acoustics")
for _module_name in (
    "audio_features",
    "pause_fluency",
    "phrase_rescue",
    "prosody_feedback",
    "verdicts",
    "word_prosody",
):
    sys.modules[f"{__name__}.{_module_name}"] = import_module(
        f"domain.speech.acoustics.{_module_name}"
    )
sys.modules[__name__] = _implementation
