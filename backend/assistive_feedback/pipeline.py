"""Orchestrates the additive assistive-feedback layer for one utterance.

**Read-only, additive, and defensive by construction**: every step here
mirrors the SAME re-derivation pattern `diagnostics.py`'s
`extract_utterance_rows` already uses for offline diagnostics (recompute
spans/context from the same frozen functions, never touch the live scoring
path) -- just invoked online instead of offline. If anything here raises,
`compute_assistive_feedback` returns `None` and the caller must treat that
exactly like `_contextual_tone_plan`'s own "diagnostics degrade to unknown,
never the student's score" contract: the legacy response is unaffected.

Nothing in this module writes to `word_prosody[].passed`,
`praat_analyzer.SYLLABLE_PASS_THRESHOLD`, or any Candidate F1/E2 state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Sequence

from assistive_feedback import e2_scoring, f1_artifact, policy as policy_module
from assistive_feedback import research_log
from assistive_feedback.policy import STUDENT_FACING_MESSAGE, STUDENT_FACING_NAME

#: Explicit deployment gate, same discipline `routers/tone_attempt.py`
#: already uses for `OMPAL_STUDY_MODE` ("mounting it is an explicit
#: deployment act rather than a side effect of importing a module"). Off by
#: default: this task's own instructions end with "Do not run a real-user
#: study yet." Stays off globally even after this pre-pilot plumbing task --
#: see `PILOT_ENV_FLAG` for the separate, additional gate a pilot session
#: needs.
ENV_FLAG = "ENABLE_ASSISTIVE_FEEDBACK"

#: STEP 6: the pilot-scoped override. Enabling assistive feedback for a
#: pilot session requires BOTH this env var (an operator's deliberate
#: deployment decision, exactly like `ENV_FLAG` above) AND the individual
#: request explicitly carrying `study_phase="pilot"` (the learner's own
#: session opted in via `?pilot=1` -- see `src/utils/pilotSession.ts`).
#: Neither one alone turns anything on; `ENV_FLAG` unset + this unset (the
#: default) behaves exactly as before this task -- nothing changes for
#: ordinary production traffic no matter what any request sends.
PILOT_ENV_FLAG = "ENABLE_ASSISTIVE_FEEDBACK_PILOT_OVERRIDE"

_encoder = None  # lazy singleton -- avoid reloading the Wav2Vec2 checkpoint per request
_policy = None  # lazy singleton -- avoid re-reading the protocol JSON per request


def is_enabled(study_phase: str | None = None) -> bool:
    if os.environ.get(ENV_FLAG) == "1":
        return True
    return study_phase == "pilot" and os.environ.get(PILOT_ENV_FLAG) == "1"


@dataclass(frozen=True)
class RequestIdentity:
    """STEP 1-7 of the pre-pilot plumbing: the join keys a research-log
    event needs, threaded in from the request (never fabricated here).
    Every field defaults to empty/None -- an ordinary, non-pilot request
    that sends none of this still works exactly as before; it simply
    produces no log rows (`participant_id` empty means "nothing to log",
    checked in `_maybe_log`)."""

    participant_id: str = ""
    item_id: str = ""
    session_id: str = ""
    attempt_id: str = ""
    attempt_number: int = 1
    attempt_type: research_log.AttemptType = "WHOLE_SENTENCE_INITIAL"
    study_phase: str = ""


def _get_encoder():
    global _encoder
    if _encoder is None:
        from benchmarking.candidates.wav2vec_frozen_logistic import FrozenEncoder

        _encoder = FrozenEncoder()
    return _encoder


def _get_policy() -> policy_module.Policy:
    global _policy
    if _policy is None:
        _policy = policy_module.load_policy()
    return _policy


def _get_artifact():
    return f1_artifact.load_and_verify()


def compute_assistive_feedback(
    pitch_contour: Sequence[tuple[float, float]],
    transcription: str,
    pinyin_hint: str,
    audio_path: str,
    identity: RequestIdentity | None = None,
) -> list[dict[str, Any]] | None:
    """One record per judged Han character (student-facing shape,
    unchanged), or `None` if the layer could not run for this utterance
    (missing artifact, too little audio, etc.) -- NEVER raises to the
    caller. When `identity.participant_id` is set, ALSO writes one
    research-log record per syllable (STEP 7) -- a side effect on the log
    only; the returned list is identical either way, so passing an identity
    can never change what the student sees."""
    identity = identity or RequestIdentity()
    if not is_enabled(identity.study_phase):
        return None
    try:
        return _compute(pitch_contour, transcription, pinyin_hint, audio_path, identity)
    except Exception:  # noqa: BLE001 - additive diagnostic layer, must never break the main response
        return None


def _compute(
    pitch_contour: Sequence[tuple[float, float]], transcription: str, pinyin_hint: str, audio_path: str,
    identity: RequestIdentity,
) -> list[dict[str, Any]] | None:
    from benchmarking.candidates.f1_context_wav2vec import CONTEXT_FEATURE_NAMES, build_context_vector
    from chinese_tones import parse_pinyin_tones, word_tones
    from praat_analyzer import _aligner, _prosody_tokens
    from tone_context import _is_han, han_break_flags, plan_expected_tones

    if len(pitch_contour) < 2:
        return None

    han_chars = [c for c in transcription if _is_han(c)]
    if not han_chars:
        return None

    hint_tones = parse_pinyin_tones(pinyin_hint) if pinyin_hint else []
    if len(hint_tones) == len(han_chars):
        underlying_tones = hint_tones
    else:
        underlying_tones = [word_tones(c)[0] for c in han_chars]

    tokens = _prosody_tokens(transcription)
    token_indices: list[int] = []
    for token_index, token in enumerate(tokens):
        token_indices.extend(token_index for c in token if _is_han(c))
    if len(token_indices) != len(han_chars):
        token_indices = list(range(len(han_chars)))  # degrade to "every char its own token"

    breaks = han_break_flags(transcription)
    plan = plan_expected_tones(han_chars, underlying_tones, token_indices, breaks)
    if len(plan) != len(han_chars):
        return None

    spans = _aligner().align(list(pitch_contour), len(han_chars), intensity=None)
    if len(spans) != len(han_chars):
        return None

    artifact = _get_artifact()
    if artifact.context_feature_names != list(CONTEXT_FEATURE_NAMES):
        return None  # artifact was exported with a different feature order than this code expects -- refuse, don't guess

    encoder = _get_encoder()
    pol = _get_policy()

    utterance_start = float(pitch_contour[0][0])
    utterance_span = max(float(pitch_contour[-1][0]) - utterance_start, 1e-6)

    results: list[dict[str, Any]] = []
    for i, expected in enumerate(plan):
        start, end = spans[i].start, spans[i].end
        position_normalized = (start - utterance_start) / utterance_span

        e2_score, e2_provenance, e2_matched_tone = e2_scoring.score_syllable_e2(pitch_contour, start, end, expected)

        embedding = encoder.embed_span(audio_path, start, end)
        f1_probability = None
        if embedding is not None:
            context_vector = build_context_vector(plan, i, position_normalized)
            f1_probability = artifact.predict_proba(embedding, context_vector)

        group = policy_module.e2_group(expected)
        state = policy_module.classify(pol, f1_probability, e2_score, group)

        if identity.participant_id:
            # STEP 7: the full research-log event -- includes the raw scores
            # and category the STUDENT-facing `results` entry below
            # deliberately omits. This is a log side effect only; it never
            # changes `results`, so identity being present/absent can never
            # change what a student sees.
            research_log.log_attempt(research_log.AttemptLogRecord(
                attempt_id=identity.attempt_id or f"{identity.item_id}:{identity.attempt_number}",
                participant_id=identity.participant_id,
                item_id=identity.item_id,
                syllable_index=i,
                character=han_chars[i],
                policy_state=state,
                f1_risk_score=f1_probability,
                e2_diagnostic_category=group,
                e2_score=e2_score,
                expected_tone=expected.underlying_tone,
                accepted_surface_tones=list(expected.accepted_surface_tones),
                session_id=identity.session_id,
                attempt_number=identity.attempt_number,
                attempt_type=identity.attempt_type,
                study_phase=identity.study_phase,
                feedback_enabled=True,
            ))

        results.append({
            "syllable_index": i,
            "character": han_chars[i],
            "expected_underlying_tone": expected.underlying_tone,
            "accepted_surface_tones": list(expected.accepted_surface_tones),
            "context_rule": expected.rule,
            "realization": expected.realization,
            "assistive_state": state,
            "assistive_state_label": STUDENT_FACING_NAME[state],
            "assistive_message": STUDENT_FACING_MESSAGE[state],
            "e2_diagnostic_category": group,
            "explanation": {
                "e2_provenance": e2_provenance,
                "e2_matched_tone": e2_matched_tone,
                "boundary_before": expected.boundary_before,
                "boundary_after": expected.boundary_after,
            },
        })
    return results
