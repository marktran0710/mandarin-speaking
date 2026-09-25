"""Runtime metadata for the admin-only Learning Engine page.

Every value here is read directly from the modules that actually control
production behavior (analytics/bkt.py, analytics/srs.py,
domain/speech/tone_decision.py, services/pronunciation_scoring.py, the ASR
and AI-feedback provider config) - nothing is duplicated/hand-copied, so the
page can never drift from what the app actually runs. No secrets: provider
sections report only whether a key is configured, never its value.

Provenance tags used throughout (see docs/learning-engine.md):
  STANDARD_ALGORITHM            - textbook algorithm, unmodified
  MODIFIED_STANDARD_ALGORITHM   - a named algorithm with a documented project adaptation
  PUBLISHED_METHOD              - a published technique (not necessarily an academic "algorithm")
  PROJECT_HEURISTIC             - project-specific logic with no external validation
  ENGINEERING_DEFAULT           - a runtime constant chosen for launch, not calibrated
"""
from analytics.bkt import BKT_CONFIG, BKT_MODEL_VERSION
from analytics.srs import (
    DAY_SECONDS,
    FIRST_INTERVAL_DAYS,
    INITIAL_EASE,
    MIN_EASE,
    PASS_QUALITY,
    SECOND_INTERVAL_DAYS,
    SRS_ALGORITHM_VERSION,
)
from domain.speech import tone_decision as td
from services.pronunciation_scoring import SENTENCE_SYLLABLE_PASS_RATIO


def _bkt_section() -> dict:
    return {
        "name": "Bayesian Knowledge Tracing",
        "version": BKT_MODEL_VERSION,
        "provenance": "STANDARD_ALGORITHM",
        "purpose": "Estimate per-word vocabulary mastery from binary correct/incorrect responses, and rank weak words for personalized practice.",
        "parameters": {
            "P_L0_initial_mastery": {
                "value": BKT_CONFIG.initial_mastery,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "P_T_learn_rate": {
                "value": BKT_CONFIG.learn_rate,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "P_G_guess_mcq": {
                "value": BKT_CONFIG.guess_rate,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "P_S_slip_mcq": {
                "value": BKT_CONFIG.slip_rate,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "P_G_guess_typed": {
                "value": BKT_CONFIG.guess_rate_typed,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "P_S_slip_typed": {
                "value": BKT_CONFIG.slip_rate_typed,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "mastery_threshold": {
                "value": BKT_CONFIG.mastery_threshold,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "minimum_observations": {
                "value": BKT_CONFIG.minimum_observations,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "required_diagnostic_rounds": {
                "value": BKT_CONFIG.required_diagnostic_quizzes,
                "provenance": "ENGINEERING_DEFAULT",
            },
            "review_count": {
                "value": BKT_CONFIG.review_count,
                "provenance": "ENGINEERING_DEFAULT",
            },
        },
        "parameterStatus": "provisional",
        "calibrationStatus": "Needs pilot/human-rater calibration - source code labels these ENGINEERING DEFAULTS, not calibrated cutoffs (analytics/bkt.py).",
        "pipeline": [
            "Client response",
            "Server resolves the authoritative assessment answer (never trusts a client-sent correct/incorrect boolean alone)",
            "BKT posterior update (guess/slip pair chosen by answer format)",
            "Learning transition",
            "Mastery status (UNASSESSED / DEVELOPING / NEEDS_PRACTICE / STRONG)",
            "Weak-word ranking for personalized practice",
        ],
        "reference": {
            "citation": "Corbett, A. T., & Anderson, J. R. (1995). Knowledge tracing: Modeling the acquisition of procedural knowledge. User Modeling and User-Adapted Interaction, 4, 253-278.",
            "doi": "10.1007/BF01099821",
            "note": "The equations follow standard BKT. The parameter values above (P(L0), P(T), guess/slip pairs, thresholds) are this project's own runtime configuration, not values recommended by the cited paper.",
        },
    }


def _retention_section() -> dict:
    return {
        "name": "Modified SM-2",
        "version": SRS_ALGORITHM_VERSION,
        "provenance": "MODIFIED_STANDARD_ALGORITHM",
        "purpose": "Schedule future review of vocabulary that has already reached a STRONG BKT state, separately from the BKT mastery estimate itself.",
        "parameters": {
            "initial_ease": {"value": INITIAL_EASE, "provenance": "STANDARD_ALGORITHM"},
            "minimum_ease": {"value": MIN_EASE, "provenance": "STANDARD_ALGORITHM"},
            "first_interval_days": {"value": FIRST_INTERVAL_DAYS, "provenance": "MODIFIED_STANDARD_ALGORITHM"},
            "second_interval_days": {"value": SECOND_INTERVAL_DAYS, "provenance": "MODIFIED_STANDARD_ALGORITHM"},
            "pass_quality_threshold": {"value": PASS_QUALITY, "provenance": "STANDARD_ALGORITHM"},
            "quality_correct": {"value": 4, "provenance": "PROJECT_HEURISTIC"},
            "quality_incorrect": {"value": 2, "provenance": "PROJECT_HEURISTIC"},
            "day_seconds": {"value": DAY_SECONDS, "provenance": "ENGINEERING_DEFAULT"},
        },
        "parameterStatus": "provisional",
        "calibrationStatus": "Uses standard SM-2 constants (ease bounds, 1/6-day first intervals); the binary q=4/q=2 answer mapping is this project's own adaptation of the 0-5 SM-2 self-rating scale and is not separately validated.",
        "easeFormula": "EF' = EF + (0.1 - (5-q) * (0.08 + (5-q)*0.02)), floored at minimum_ease",
        "intervalSequence": "1st success -> first_interval_days; 2nd success -> second_interval_days; thereafter round(previous_interval * ease); any failure resets repetitions to 0 and the interval to first_interval_days.",
        "conceptualSeparation": "BKT answers 'how well is this word currently learned?'. SRS answers 'when should this word be reviewed again?'. A word can be BKT-weak, SRS-due, both, or neither - the review queue tags each entry weak|due rather than merging the two concepts.",
        "reference": {
            "citation": "Wozniak, P. A. (1990). Optimization of learning. SuperMemo / SM-2 family.",
            "note": "This project's binary-response scheduler is a modified SM-2 implementation, not the original algorithm unchanged.",
        },
    }


def _voice_thresholds() -> dict:
    return {
        "SYLLABLE_PASS_THRESHOLD": {
            "value": 58.0,
            "purpose": "Legacy per-syllable score pass bar. This is the ONLY threshold that actually unlocks lesson progression - the diagnostic states below (CORRECT/UNCERTAIN/INCORRECT/INVALID_AUDIO) are shown to students as feedback but explicitly do not drive progression (see domain/speech/tone_decision.py's module docstring).",
            "controlsProgression": True,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "TONE_CONFIRM_THRESHOLD": {
            "value": td.TONE_CONFIRM_THRESHOLD,
            "purpose": "Diagnostic score at/above which a tone is confirmed CORRECT. Diagnostic/feedback only - does not gate progression.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "TONE_ERROR_THRESHOLD": {
            "value": td.TONE_ERROR_THRESHOLD,
            "purpose": "Diagnostic score at/below which a tone is confirmed INCORRECT. Diagnostic/feedback only - does not gate progression.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "SHAPE_STRONG": {
            "value": td.SHAPE_STRONG,
            "purpose": "Shape-similarity score above which contour shape alone is treated as strong evidence for the diagnostic verdict.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "SHAPE_WEAK": {
            "value": td.SHAPE_WEAK,
            "purpose": "Shape-similarity score below which contour shape is treated as weak evidence for the diagnostic verdict.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "DIRECTION_SUPPORT": {
            "value": td.DIRECTION_SUPPORT,
            "purpose": "Directional-agreement score treated as supporting evidence for the target tone in the diagnostic verdict.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "DIRECTION_BAD": {
            "value": td.DIRECTION_BAD,
            "purpose": "Directional-agreement score treated as contradicting the target tone in the diagnostic verdict.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "PHRASE_RESCUE_SHAPE_STRONG": {
            "value": td.PHRASE_RESCUE_SHAPE_STRONG,
            "purpose": "Higher shape bar (stricter than SHAPE_STRONG) letting strong combined-phrase evidence override a borderline/incorrect individual syllable verdict.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "PHRASE_RESCUE_DIRECTION_SUPPORT": {
            "value": td.PHRASE_RESCUE_DIRECTION_SUPPORT,
            "purpose": "Direction bar paired with PHRASE_RESCUE_SHAPE_STRONG for the same override.",
            "controlsProgression": False,
            "provenance": "ENGINEERING_DEFAULT",
        },
        "PHRASE_SHAPE_WEIGHT": {
            "value": 0.50,
            "purpose": "Shape weight in the legacy combined tone_accuracy score (0.50/0.50 with PHRASE_DIRECTIONAL_WEIGHT) that feeds the legacy per-word pass path - distinct from both the diagnostic verdict (not a blend) and the display-only composite below.",
            "controlsProgression": True,
            "provenance": "PROJECT_HEURISTIC",
        },
        "PHRASE_DIRECTIONAL_WEIGHT": {
            "value": 0.50,
            "purpose": "Direction weight paired with PHRASE_SHAPE_WEIGHT.",
            "controlsProgression": True,
            "provenance": "PROJECT_HEURISTIC",
        },
        "DISPLAY_SHAPE_WEIGHT": {
            "value": td.DISPLAY_SHAPE_WEIGHT,
            "purpose": "Shape weight in a third, purely cosmetic composite tone score shown in a learner's progress history. Does not gate anything.",
            "controlsProgression": False,
            "provenance": "PROJECT_HEURISTIC",
        },
        "DISPLAY_DIRECTION_WEIGHT": {
            "value": td.DISPLAY_DIRECTION_WEIGHT,
            "purpose": "Direction weight paired with DISPLAY_SHAPE_WEIGHT.",
            "controlsProgression": False,
            "provenance": "PROJECT_HEURISTIC",
        },
        "SENTENCE_SYLLABLE_PASS_RATIO": {
            "value": SENTENCE_SYLLABLE_PASS_RATIO,
            "purpose": "Fraction of judged syllables in a sentence that must pass for the sentence-level pronunciation verdict to pass.",
            "controlsProgression": True,
            "provenance": "ENGINEERING_DEFAULT",
        },
    }


def _asr_providers() -> list[dict]:
    from config import settings

    order = list(settings.asr_fallback_order)
    configured = {
        "groq": bool(settings.groq_api_key),
        "openai": bool(settings.openai_api_key),
        "gemini": bool(settings.gemini_api_key),
    }
    providers = []
    for name in order:
        if name in configured:
            providers.append({"provider": name, "role": "cloud ASR", "configured": configured[name]})
        else:
            # ctwhisper / vibevoice: local models, "configured" means selected
            # in the fallback order, not gated on an API key.
            providers.append({"provider": name, "role": "local ASR", "configured": True})
    return providers


def _feedback_providers() -> dict:
    from config import settings
    from services.speech.feedback.pipeline import AI_FEEDBACK_PROVIDER

    return {
        "defaultProvider": AI_FEEDBACK_PROVIDER,
        "providers": [
            {"provider": "local", "role": "offline deterministic coaching (CAF engine)", "configured": True},
            {"provider": "groq", "role": "cloud LLM coaching (text only)", "configured": bool(settings.groq_api_key)},
            {"provider": "openai", "role": "cloud LLM coaching (vision-capable)", "configured": bool(settings.openai_api_key)},
            {"provider": "gemini", "role": "cloud LLM coaching (vision-capable)", "configured": bool(settings.gemini_api_key)},
        ],
        "fallbackBehavior": "The requested provider is tried first; on a missing key or a failed call it degrades to the next configured cloud provider, then to the offline local engine, so a student always receives feedback even if every cloud provider is unavailable.",
    }


def _voice_section() -> dict:
    return {
        "pipeline": [
            "Audio upload",
            "Recording quality control (duration / loudness / speech presence / clipping / format)",
            "ASR transcription",
            "Praat/Parselmouth acoustic (pitch contour) extraction",
            "Deterministic shape + directional tone scoring",
            "Feedback-quality gate (poor evidence -> UNCERTAIN/INVALID_AUDIO, never a confident bad score)",
            "AI/local coaching feedback",
            "Pronunciation mastery + sentence-level verdict",
            "Speaking-progress persistence",
        ],
        "acousticEngine": {
            "technology": "Praat via python-parselmouth",
            "purpose": "F0/pitch and related acoustic measurement",
            "provenance": "PUBLISHED_METHOD",
            "reference": {
                "citation": "Boersma, P. (1993). Accurate short-term analysis of the fundamental frequency and the harmonics-to-noise ratio of a sampled sound. Proceedings of the Institute of Phonetic Sciences, 17, 97-110.",
                "note": "This reference supports the acoustic pitch-extraction technique only. The project's tone shape/direction scoring formulas built on top of the extracted contour are project-specific and are NOT defined by this paper.",
            },
        },
        "toneScoring": {
            "provenance": "PROJECT_HEURISTIC",
            "note": (
                "Deterministic contour shape/direction scoring built on the Praat-extracted pitch contour. "
                "The diagnostic verdict (CORRECT/UNCERTAIN/INCORRECT/INVALID_AUDIO) is NOT a weighted blend - "
                "it's rule/branch logic over the shape and direction scores as separate signals. Two other, "
                "separate weighted combinations exist elsewhere: a legacy 0.50/0.50 shape+direction composite "
                "that does feed lesson-progression pass/fail, and a purely cosmetic 0.70/0.30 composite shown "
                "only in progress history. See docs/learning-engine.md for exact per-tone formulas. Every "
                "verdict payload the API returns ships threshold_validated=false explicitly."
            ),
        },
        "qualityGate": {
            "reasons": sorted(td.UNUSABLE_RECORDING_REASONS),
            "principle": "Poor evidence is not the same as bad pronunciation - unusable audio is reported as INVALID_AUDIO/UNCERTAIN rather than a confident low score.",
        },
        "thresholds": _voice_thresholds(),
        "asrProviders": _asr_providers(),
        "feedbackProviders": _feedback_providers(),
        "calibrationStatus": "Needs human-rater calibration - none of the thresholds above have been validated against human tone judgments.",
    }


def get_learning_engine_metadata() -> dict:
    return {
        "bkt": _bkt_section(),
        "retention": _retention_section(),
        "voice": _voice_section(),
    }
