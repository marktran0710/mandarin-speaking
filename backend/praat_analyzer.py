"""Compatibility facade for the speech acoustics service.

The historical top-level import path remains stable while the implementation
is grouped under ``services.speech.acoustics`` by responsibility.
"""

from domain.speech.acoustics import *  # noqa: F401,F403
from domain.speech.acoustics import (
    _apply_phrase_rescue,
    _classify_content_word,
    _combine_word_verdict,
    _contour_shape,
    _correct_octave_jumps,
    _clean_target_phrases,
    _find_contiguous_token_run,
    _prosody_tokens,
    _reference_curve_for_token,
    _word_prosody_feedback,
)
