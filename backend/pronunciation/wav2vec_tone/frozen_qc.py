"""Frozen QC feature definitions and the pre-registered RMS threshold.

Everything here is fixed before the confirmation labels exist. Editing a
formula or the threshold after seeing those labels would turn a confirmation
into another development round, so this module is the contract.

FEATURE DEFINITIONS
-------------------

rms_relative_db  (primary)
    token_rms      = sqrt(mean(x_token^2)) over every sample of the 0 ms
                     segment, silence included -- no gating, no trimming.
    utterance_rms  = sqrt(mean(x_utt^2)) over the ENTIRE utterance waveform,
                     silence included, computed on the same 16 kHz mono signal.
    value          = 20 * log10(token_rms / utterance_rms)
    units          = decibels relative to the utterance's own level. Positive
                     means the token is louder than its utterance average.
    floor          = if either RMS is 0 the value is NaN, never a substituted
                     number. No epsilon is added, because an epsilon would
                     manufacture a finite value for digital silence.
    rationale      = both terms share the recording gain, so gain cancels.
                     This is what makes it different from absolute rms_dbfs,
                     which scored higher in development precisely because it
                     also measured how loudly a speaker was recorded.

local_snr_db  (secondary)
    noise_rms      = RMS of the longest run of >=120 ms of 10 ms frames that
                     sit >=12 dB below the utterance's 75th-percentile frame
                     energy, with the token's own span excluded.
    value          = 20 * log10(token_rms / noise_rms)
    availability   = if no such run exists, the value is NaN. Neighbouring
                     speech is never used as a noise reference; an unavailable
                     SNR is reported as unavailable.

alignment_score, duration_seconds, voiced_proportion
    Taken unchanged from ompal_alignment_pilot.csv as the aligner produced
    them. Not recomputed here, so they cannot drift.

THRESHOLD
---------

RMS_THRESHOLD_DB was derived mechanically from the 38 development stable-label
tokens only (24 STABLE_ACCEPT, 14 STABLE_REJECT), never from the 9 ambiguous
cases and never from the confirmation set: among all observed values, the
least restrictive T with >=95% ACCEPT among retained and >=10 retained.

On development it retains 11 of 38 (29%) at 100% precision. Recorded here in
advance: 29% is already below the 50% retention that the operational rule is
asked to meet, so a retention failure in confirmation would repeat development
rather than contradict it. That is not a reason to move T.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000

# Frozen 2026-08-08, before any confirmation judgment existed.
RMS_THRESHOLD_DB = 3.1043
RMS_THRESHOLD_PROVENANCE = {
    "derived_from": "development stable labels only (24 accept / 14 reject)",
    "rule": "least restrictive T with >=95% precision and >=10 retained",
    "development_retained": 11,
    "development_retention_rate": 11 / 38,
    "development_precision": 1.0,
    "ambiguous_used": False,
}

# Pre-registered decision criteria. Signal and rule are judged separately.
SIGNAL_CRITERIA = {
    "min_auc": 0.75,
    "direction_must_match_development": True,
    "min_duplicate_agreement": 0.90,
    "not_explained_by_single_stratum": True,
}
RULE_CRITERIA = {"min_retained_accept_rate": 0.95, "min_retention": 0.50}

NOISE_MIN_MS = 120
NOISE_GAP_DB = 12.0
CLIP_THRESHOLD = 0.98


def token_rms(segment: np.ndarray) -> float:
    """Plain RMS over every sample, silence included."""
    if not len(segment):
        return float("nan")
    return float(np.sqrt(np.mean(np.asarray(segment, dtype=np.float64) ** 2)))


def rms_relative_db(segment: np.ndarray, utterance: np.ndarray) -> float:
    """Token level relative to its own utterance, in dB. NaN if undefined."""
    numerator = token_rms(segment)
    denominator = token_rms(utterance)
    if not (numerator > 0 and denominator > 0):
        return float("nan")
    return float(20.0 * np.log10(numerator / denominator))


def noise_reference_rms(utterance: np.ndarray, span: tuple[int, int]) -> float | None:
    """RMS of the longest sustained silence outside the token, or None."""
    window = int(0.010 * SAMPLE_RATE)
    if len(utterance) < window * 10:
        return None
    frames = [utterance[i:i + window]
              for i in range(0, len(utterance) - window, window)]
    energies = np.asarray([float(np.sqrt(np.mean(f ** 2)) + 1e-12) for f in frames])
    positions = np.arange(len(frames)) * window
    inside = (positions >= span[0] - window) & (positions < span[1])
    if not (~inside).any():
        return None
    speech_level = float(np.percentile(energies[~inside], 75))
    quiet = (energies < speech_level / (10 ** (NOISE_GAP_DB / 20))) & (~inside)

    best, current, best_run, run = [], [], 0, 0
    for index, is_quiet in enumerate(quiet):
        if is_quiet:
            run += 1
            current.append(index)
            if run > best_run:
                best_run, best = run, list(current)
        else:
            run, current = 0, []
    if best_run * 10 < NOISE_MIN_MS:
        return None
    return float(np.sqrt(np.mean(np.concatenate([frames[i] for i in best]) ** 2)))


def local_snr_db(segment: np.ndarray, utterance: np.ndarray,
                 span: tuple[int, int]) -> float:
    """Segmental SNR against a real silence reference, else NaN."""
    noise = noise_reference_rms(utterance, span)
    signal = token_rms(segment)
    if noise is None or not (noise > 0 and signal > 0):
        return float("nan")
    return float(20.0 * np.log10(signal / noise))


def qc_keep(rms_relative: float) -> bool | None:
    """The frozen rule. None when the feature is undefined."""
    if not np.isfinite(rms_relative):
        return None
    return bool(rms_relative >= RMS_THRESHOLD_DB)
