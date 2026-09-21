"""Praat-backed acoustic analysis capabilities for speech recordings."""

from .audio_features import (
    PARSELMOUTH_IMPORT_ERROR,
    _correct_octave_jumps,
    _formants_from_sound,
    analyze_all,
    analyze_pauses_and_utterances,
    calculate_speech_rate,
    extract_formants,
    extract_pitch,
)
from .pause_fluency import (
    SYLLABLE_PASS_THRESHOLD,
    _extract_pitch_fallback,
    analyze_fluency,
    get_pitch_statistics,
)
from .phrase_rescue import (
    _apply_phrase_rescue,
    _classify_content_word,
    _clean_target_phrases,
    _contour_shape,
    _find_contiguous_token_run,
    _prosody_tokens,
    _reference_curve_for_token,
    _tone_mismatch_diagnosis,
    reference_curve_for_span,
    slice_reference_word_span,
    word_stress_summary,
)
from .prosody_feedback import _word_prosody_feedback
from .verdicts import _combine_word_verdict
from .word_prosody import estimate_word_prosody

__all__ = [
    "PARSELMOUTH_IMPORT_ERROR",
    "SYLLABLE_PASS_THRESHOLD",
    "analyze_all",
    "analyze_fluency",
    "analyze_pauses_and_utterances",
    "calculate_speech_rate",
    "estimate_word_prosody",
    "extract_formants",
    "extract_pitch",
    "get_pitch_statistics",
    "reference_curve_for_span",
    "slice_reference_word_span",
    "word_stress_summary",
]
