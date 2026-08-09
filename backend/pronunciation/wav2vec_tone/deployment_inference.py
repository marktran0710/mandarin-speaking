"""Canonical production inference path for the frozen OMPAL tone confirmer.

One entry point, `infer_tone_attempt`, owns the whole validated chain:

    input validation
      -> audio-contract enforcement (mono, 16 kHz, frozen resampler)
      -> token segmentation (forced alignment, original_0ms) if requested
      -> 20-point median-centred semitone F0 trajectory
      -> 83-column design vector
      -> persisted frozen R2 coefficients
      -> exact t_pass, tone gate
      -> PASS / RETRY + structured log payload

Nothing here reimplements scientific logic. The audio loader, the trajectory
extractor, the design matrix and the decision rule are all *imported* from the
frozen research modules; this file adds validation, packaging and enforcement
around them.

The scientific decision function is unchanged from OMPAL_R2_PASS_v1. This module
carries a separate DEPLOYMENT implementation version so that hardening work can
be tracked without implying a new scientific system.

    python -m pronunciation.wav2vec_tone.deployment_inference --build-bundle
    python -m pronunciation.wav2vec_tone.deployment_inference --show
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Frozen scientific chain -- imported, never reimplemented.
from pronunciation.wav2vec_tone.align_ompal_pilot import (  # noqa: E402
    SAMPLE_RATE as ALIGNER_SAMPLE_RATE, align_utterance, load_audio, romanize,
)
from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (  # noqa: E402
    CLASS_WEIGHT, N_POINTS, PITCH_CEILING, PITCH_FLOOR, PITCH_STEP,
    REFERENCE_TONE, SAMPLE_RATE, TONES, design, fit_predict, normalise,
    trajectory_from_segment,
)
from pronunciation.wav2vec_tone.phase_c8_confirmation_policy import (  # noqa: E402
    C_VALUE,
)
from pronunciation.wav2vec_tone.preflight_fresh_validation import (  # noqa: E402
    PASS_MESSAGE, RETRY_MESSAGE, decide,
)

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
OUT_DIR = DATA_DIR / "technical_verification"
FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"
C8_POLICY = DATA_DIR / "ompal_phase_c8_policy_FROZEN.json"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"

BUNDLE_NPZ = OUT_DIR / "frozen_inference_bundle.npz"
BUNDLE_JSON = OUT_DIR / "frozen_inference_bundle.json"

# --- versions --------------------------------------------------------------
SCIENTIFIC_VERSION = "OMPAL_R2_PASS_v1"        # unchanged, never overwritten
DEPLOYMENT_VERSION = "OMPAL_R2_PASS_v1.1"      # implementation hardening only
AUDIO_CONTRACT_VERSION = "OMPAL_AUDIO_CONTRACT_v1"

# --- audio contract, derived from the frozen training pipeline -------------
# align_ompal_pilot.load_audio() is the loader that produced every Train, Dev
# and native-reference token. It defines the contract: mono by channel mean,
# resample_poly to 16 kHz when the source rate differs, float32.
CONTRACT_SAMPLE_RATE = SAMPLE_RATE
CONTRACT_CHANNELS = 1
# Every source utterance behind the frozen features was natively 16 kHz, so the
# model has never seen upsampled audio. Downsampling a richer source to 16 kHz
# discards only bands the model never used; upsampling an 8 kHz source invents
# detail that was never there, and was measured to flip a near-threshold
# verdict. Sources below 16 kHz are therefore refused, not "fixed".
CONTRACT_MIN_SOURCE_RATE = 16000
# Every frozen training utterance was NATIVELY 16 kHz -- the resample branch in
# the training loader never fired. Resampled input is therefore outside the
# distribution the model was fitted on. Measured over all 108 native-reference
# tokens at 44.1 and 48 kHz: 214/216 verdicts unchanged, but 2 flipped on a
# 100 ms token whose short voiced span makes edge detection fragile.
# The strict profile (the default, and what the validation study must use)
# refuses non-native rates rather than absorbing that instability.
CONTRACT_REQUIRE_NATIVE_RATE = True
CONTRACT_RESAMPLER = "scipy.signal.resample_poly (align_ompal_pilot.load_audio)"
CONTRACT_BOUNDARY_POLICY = "original_0ms"
CONTRACT_ALIGNER = "torchaudio MMS_FA CTC forced alignment (with_star=True)"
# Token-duration envelope measured over the 1677 Train+Dev tokens that produced
# the frozen features. Used as a plausibility bound, not as a trimming rule.
CONTRACT_MIN_TOKEN_MS = 60.0
CONTRACT_MAX_TOKEN_MS = 982.0

VALID_TONE_INPUTS = {"1": "1", "2": "2", "3": "3", "4": "4",
                     "T1": "1", "T2": "2", "T3": "3", "T4": "4"}

# --- structured failure codes ----------------------------------------------
FAILURE_CODES = (
    "ok",
    "invalid_expected_tone",
    "unreadable_audio",
    "empty_audio",
    "sample_rate_below_contract",
    "sample_rate_not_native",
    "multichannel_declared",           # informational; downmix is in contract
    "token_duration_out_of_contract",
    "alignment_failed",
    "alignment_span_missing",
    "too_short_for_pitch",
    "insufficient_voiced_frames",
    "praat_error",
    "non_finite_trajectory",
    "feature_schema_mismatch",
    "model_not_loaded",
    "artefact_hash_mismatch",
    "unhandled_exception",
)


class ContractViolation(Exception):
    """Raised only at startup. Inference never raises; it returns RETRY."""


# ===========================================================================
# Feature schema
# ===========================================================================

FEATURE_COLUMN_NAMES = (
    [f"traj_{i:02d}" for i in range(N_POINTS)]
    + [f"tone_T{t}" for t in TONES if t != REFERENCE_TONE]
    + [f"traj_{i:02d}_x_T{t}"
       for t in TONES if t != REFERENCE_TONE for i in range(N_POINTS)]
)


def feature_schema_sha256() -> str:
    return hashlib.sha256("\n".join(FEATURE_COLUMN_NAMES).encode()).hexdigest()


# ===========================================================================
# Input validation
# ===========================================================================

def validate_expected_tone(value) -> str:
    """Return the frozen internal tone label, or raise ValueError.

    The frozen design matrix compares tone labels as strings. An int, float or
    unknown string previously produced an all-zero dummy row and was scored
    through the T1 reference branch with no error (TV-F3). Validation happens
    here, before any feature is constructed.
    """
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(
            f"expected_tone must be a string, got {type(value).__name__}")
    key = value.strip().upper()
    if key not in VALID_TONE_INPUTS:
        raise ValueError(f"expected_tone {value!r} is not one of "
                         f"{sorted(VALID_TONE_INPUTS)}")
    return VALID_TONE_INPUTS[key]


def load_audio_to_contract(path) -> tuple[np.ndarray, dict]:
    """Read any supported file into the frozen training representation.

    Delegates to align_ompal_pilot.load_audio, the exact loader that produced
    the frozen tokens: channel-mean to mono, resample_poly to 16 kHz when the
    source rate differs, float32. Sources already at 16 kHz mono pass through
    untouched, so this cannot alter how frozen material is represented.
    """
    import soundfile as sf

    info = sf.info(str(path))
    audio, original_rate = load_audio(Path(path))
    return audio, {
        "source_sample_rate": int(original_rate),
        "source_channels": int(info.channels),
        "source_format": f"{info.format}/{info.subtype}",
        "resampled": int(original_rate) != CONTRACT_SAMPLE_RATE,
        "delivered_sample_rate": CONTRACT_SAMPLE_RATE,
        "duration_ms": len(audio) / CONTRACT_SAMPLE_RATE * 1000.0,
    }


# ===========================================================================
# Segmentation -- reproduces the frozen training stage
# ===========================================================================

_ALIGNER = {"model": None, "dictionary": None}


def _aligner():
    if _ALIGNER["model"] is None:
        from torchaudio.pipelines import MMS_FA

        _ALIGNER["model"] = MMS_FA.get_model(with_star=True)
        _ALIGNER["dictionary"] = MMS_FA.get_dict(star="*")
    return _ALIGNER["model"], _ALIGNER["dictionary"]


def segment_token(audio, syllable_pinyin: list[str], token_index: int):
    """Cut the target token exactly as build_benchmark_manifest.py did.

    Same aligner, same romanisation, same original_0ms boundary policy, same
    integer sample rounding. Returns (segment, span, detail).
    """
    model, dictionary = _aligner()
    romanized = [romanize(p) for p in syllable_pinyin]
    try:
        spans = align_utterance(model, dictionary, audio, romanized)
    except Exception as error:  # noqa: BLE001
        return None, None, f"alignment_failed: {type(error).__name__}"
    if token_index >= len(spans) or spans[token_index] is None:
        return None, None, "alignment_span_missing"
    start, end, score = spans[token_index]
    begin = max(0, int(round(start * CONTRACT_SAMPLE_RATE)))
    finish = min(len(audio), int(round(end * CONTRACT_SAMPLE_RATE)))
    return audio[begin:finish], (start, end, score), "ok"


# ===========================================================================
# Persisted frozen inference bundle
# ===========================================================================

@dataclass
class FrozenInferenceBundle:
    """Everything needed to score, with no training data present."""

    coefficients: np.ndarray
    intercept: np.ndarray
    imputer_statistics: np.ndarray
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    scaler_var: np.ndarray
    feature_names: list[str]
    metadata: dict
    _model: object = field(default=None, repr=False)
    _imputer: object = field(default=None, repr=False)
    _scaler: object = field(default=None, repr=False)

    # --- construction ------------------------------------------------------
    @staticmethod
    def fit_from_frozen_train(seed: int = 0) -> "FrozenInferenceBundle":
        """Run the existing frozen full-Train fitting procedure, then capture it.

        This is the same procedure fit_predict() performs; nothing about the
        fit is altered. Equivalence is proven in verify_deployment_inference.py.
        """
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        cache = dict(np.load(CACHE, allow_pickle=True))
        if "test" in set(cache["split"].tolist()):
            sys.exit("TEST LOCK VIOLATION in cache")
        stored = np.load(TRAJ_CACHE, allow_pickle=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            trajectory = normalise(stored["learner"], "N2")
        train = cache["split"] == "train"
        base, tones, y = trajectory[train], cache["tone"][train], cache["y"][train]

        imputer = SimpleImputer(strategy="median").fit(base)
        scaler = StandardScaler().fit(imputer.transform(base))
        matrix = design(scaler.transform(imputer.transform(base)), tones)
        model = LogisticRegression(max_iter=8000, C=C_VALUE,
                                   class_weight=CLASS_WEIGHT,
                                   random_state=seed).fit(matrix, y)

        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        c8 = json.loads(C8_POLICY.read_text(encoding="utf-8"))
        metadata = {
            "scientific_version": SCIENTIFIC_VERSION,
            "deployment_version": DEPLOYMENT_VERSION,
            "audio_contract_version": AUDIO_CONTRACT_VERSION,
            "system_sha256": frozen["sha256"],
            "policy_sha256": c8["sha256"],
            "model_config_sha256": hashlib.sha256(json.dumps(
                {"C": C_VALUE, "class_weight": CLASS_WEIGHT,
                 "points": N_POINTS}, sort_keys=True).encode()).hexdigest(),
            "feature_schema_sha256": feature_schema_sha256(),
            "n_features": int(matrix.shape[1]),
            "scientific_config": {
                "representation": "R2 20-point median-centred semitone F0 trajectory",
                "points": N_POINTS,
                "pitch_floor_hz": PITCH_FLOOR,
                "pitch_ceiling_hz": PITCH_CEILING,
                "pitch_time_step_s": PITCH_STEP,
                "expected_tone_encoding": "reference-coded dummies (ref T1) "
                                          "+ trajectory x tone interactions",
                "classifier": "L2 logistic regression",
                "C": C_VALUE,
                "class_weight": CLASS_WEIGHT,
                "solver": "lbfgs",
                "max_iter": 8000,
                "seed": seed,
            },
            "decision_policy": {
                "t_pass": frozen["decision_policy"]["t_pass"],
                "comparison": "score <= t_pass -> PASS",
                "score_semantics": "P(incorrect); low scores PASS",
                "enabled_pass_tones": sorted(
                    t.replace("T", "")
                    for t in frozen["decision_policy"]["enabled_pass_tones"]),
                "t1_rule": "T1 always RETRY",
                "trajectory_unavailable_rule": "always RETRY, never PASS",
                "outputs": ["PASS", "RETRY"],
            },
            "audio_contract": {
                "version": AUDIO_CONTRACT_VERSION,
                "sample_rate": CONTRACT_SAMPLE_RATE,
                "min_source_sample_rate": CONTRACT_MIN_SOURCE_RATE,
                "require_native_rate": CONTRACT_REQUIRE_NATIVE_RATE,
                "channels": CONTRACT_CHANNELS,
                "resampler": CONTRACT_RESAMPLER,
                "boundary_policy": CONTRACT_BOUNDARY_POLICY,
                "aligner": CONTRACT_ALIGNER,
                "min_token_ms": CONTRACT_MIN_TOKEN_MS,
                "max_token_ms": CONTRACT_MAX_TOKEN_MS,
            },
            "training_source_hashes": {
                "manifest_split_sha256": _sha256_file(MANIFEST_SPLIT),
                "feature_cache_sha256": _sha256_file(CACHE),
                "trajectory_cache_sha256": _sha256_file(TRAJ_CACHE),
                "train_rows": int(train.sum()),
                "train_speakers": len(set(cache["speaker"][train].tolist())),
            },
            "software": {
                "python": ".".join(str(v) for v in sys.version_info[:3]),
                "numpy": np.__version__,
            },
            "ompal_test": {"predictions": False, "scores": False,
                           "metrics": False, "rows_in_cache": 0},
        }
        bundle = FrozenInferenceBundle(
            coefficients=np.asarray(model.coef_, dtype=np.float64),
            intercept=np.asarray(model.intercept_, dtype=np.float64),
            imputer_statistics=np.asarray(imputer.statistics_, dtype=np.float64),
            scaler_mean=np.asarray(scaler.mean_, dtype=np.float64),
            scaler_scale=np.asarray(scaler.scale_, dtype=np.float64),
            scaler_var=np.asarray(scaler.var_, dtype=np.float64),
            feature_names=list(FEATURE_COLUMN_NAMES),
            metadata=metadata,
        )
        bundle.metadata["fitted_model_sha256"] = bundle.fitted_model_sha256()
        return bundle

    # --- identity ----------------------------------------------------------
    def fitted_model_sha256(self) -> str:
        """Hash binding weights, schema, preprocessing, policy and config.

        Unlike model_config_sha256 -- which hashes only {C, class_weight,
        points} -- this changes if any fitted number, any feature name, any
        preprocessing statistic or any policy constant changes.
        """
        payload = {
            "coefficients": np.round(self.coefficients, 12).tolist(),
            "intercept": np.round(self.intercept, 12).tolist(),
            "imputer_statistics": np.round(self.imputer_statistics, 12).tolist(),
            "scaler_mean": np.round(self.scaler_mean, 12).tolist(),
            "scaler_scale": np.round(self.scaler_scale, 12).tolist(),
            "feature_names": self.feature_names,
            "scientific_config": self.metadata["scientific_config"],
            "decision_policy": self.metadata["decision_policy"],
            "audio_contract": self.metadata["audio_contract"],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    # --- persistence -------------------------------------------------------
    def save(self) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        np.savez(BUNDLE_NPZ,
                 coefficients=self.coefficients, intercept=self.intercept,
                 imputer_statistics=self.imputer_statistics,
                 scaler_mean=self.scaler_mean, scaler_scale=self.scaler_scale,
                 scaler_var=self.scaler_var,
                 feature_names=np.asarray(self.feature_names, dtype=object))
        payload = dict(self.metadata)
        payload["bundle_npz_sha256"] = _sha256_file(BUNDLE_NPZ)
        BUNDLE_JSON.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=float),
            encoding="utf-8")
        self.metadata = payload

    @staticmethod
    def load() -> "FrozenInferenceBundle":
        if not BUNDLE_NPZ.exists() or not BUNDLE_JSON.exists():
            raise ContractViolation(
                "inference bundle missing -- run --build-bundle")
        arrays = np.load(BUNDLE_NPZ, allow_pickle=True)
        metadata = json.loads(BUNDLE_JSON.read_text(encoding="utf-8"))
        bundle = FrozenInferenceBundle(
            coefficients=arrays["coefficients"], intercept=arrays["intercept"],
            imputer_statistics=arrays["imputer_statistics"],
            scaler_mean=arrays["scaler_mean"], scaler_scale=arrays["scaler_scale"],
            scaler_var=arrays["scaler_var"],
            feature_names=list(arrays["feature_names"].tolist()),
            metadata=metadata)
        bundle.verify_startup()
        bundle._materialise()
        return bundle

    # --- startup integrity -------------------------------------------------
    def verify_startup(self) -> dict:
        """Fail closed on any artefact mismatch. Never serve on a mismatch."""
        checks = {}

        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        recorded = frozen.pop("sha256")
        recomputed = hashlib.sha256(
            json.dumps(frozen, sort_keys=True, default=str).encode()).hexdigest()
        checks["system_sha256"] = (recomputed == recorded
                                   == self.metadata["system_sha256"])

        c8 = json.loads(C8_POLICY.read_text(encoding="utf-8"))
        c8_recorded = c8.pop("sha256")
        c8_recomputed = hashlib.sha256(
            json.dumps(c8, sort_keys=True, default=str).encode()).hexdigest()
        checks["policy_sha256"] = (c8_recomputed == c8_recorded
                                   == self.metadata["policy_sha256"])

        checks["feature_schema_sha256"] = (
            feature_schema_sha256() == self.metadata["feature_schema_sha256"]
            and self.feature_names == list(FEATURE_COLUMN_NAMES))
        checks["fitted_model_sha256"] = (
            self.fitted_model_sha256() == self.metadata["fitted_model_sha256"])
        checks["bundle_npz_sha256"] = (
            self.metadata.get("bundle_npz_sha256") == _sha256_file(BUNDLE_NPZ))

        config = self.metadata["scientific_config"]
        checks["trajectory_config"] = (
            config["points"] == N_POINTS
            and config["pitch_floor_hz"] == PITCH_FLOOR
            and config["pitch_ceiling_hz"] == PITCH_CEILING
            and config["pitch_time_step_s"] == PITCH_STEP)
        checks["threshold"] = (
            self.metadata["decision_policy"]["t_pass"]
            == json.loads(FROZEN.read_text(encoding="utf-8"))
            ["decision_policy"]["t_pass"])
        checks["shapes"] = (
            self.coefficients.shape[1] == len(FEATURE_COLUMN_NAMES)
            and self.imputer_statistics.shape[0] == N_POINTS
            and self.scaler_mean.shape[0] == N_POINTS)

        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise ContractViolation(
                "STARTUP INTEGRITY FAILURE -- refusing to serve predictions. "
                f"Mismatched: {', '.join(failed)}")
        return checks

    # --- scoring -----------------------------------------------------------
    def _materialise(self) -> None:
        """Rebuild the scoring objects from persisted numbers.

        Imputation and scaling are applied inline rather than by rehydrating
        SimpleImputer/StandardScaler: both are exact elementwise operations
        (replace NaN with the stored median; subtract mean, divide by scale) so
        the inline form is bit-identical to the fitted transformers, and it
        avoids depending on sklearn's private fitted-state attributes, which
        change between releases. Bit-identity is asserted over all 1424 Train
        and 322 Dev tokens in verify_deployment_inference.py.

        The classifier itself is a real LogisticRegression carrying the frozen
        coefficients, so predict_proba runs sklearn's own arithmetic.
        """
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(max_iter=8000, C=C_VALUE,
                                   class_weight=CLASS_WEIGHT)
        model.coef_ = self.coefficients
        model.intercept_ = self.intercept
        model.classes_ = np.asarray([0, 1])
        model.n_features_in_ = len(self.feature_names)
        self._model = model

    def _impute_and_scale(self, base: np.ndarray) -> np.ndarray:
        values = np.array(base, dtype=np.float64, copy=True)
        missing = np.isnan(values)
        if missing.any():
            values[missing] = np.take(self.imputer_statistics,
                                      np.nonzero(missing)[1])
        values -= self.scaler_mean
        values /= self.scaler_scale
        return values

    def feature_vector(self, centred_trajectory, tone: str) -> np.ndarray:
        base = np.asarray(centred_trajectory, dtype=float).reshape(1, -1)
        return design(self._impute_and_scale(base),
                      np.asarray([tone], dtype=object))

    def score(self, centred_trajectory, tone: str) -> float:
        matrix = self.feature_vector(centred_trajectory, tone)
        if matrix.shape[1] != len(self.feature_names):
            raise ContractViolation("feature schema mismatch at scoring time")
        return float(self._model.predict_proba(matrix)[0, 1])

    # --- policy ------------------------------------------------------------
    @property
    def t_pass(self) -> float:
        return self.metadata["decision_policy"]["t_pass"]

    @property
    def enabled_tones(self) -> set:
        return set(self.metadata["decision_policy"]["enabled_pass_tones"])


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ===========================================================================
# The single production entry point
# ===========================================================================

_BUNDLE = {"instance": None}


def get_bundle() -> FrozenInferenceBundle:
    if _BUNDLE["instance"] is None:
        _BUNDLE["instance"] = FrozenInferenceBundle.load()
    return _BUNDLE["instance"]


def infer_tone_attempt(audio_path=None, expected_tone=None, *, audio=None,
                       syllable_pinyin=None, token_index=None, item_id=None,
                       bundle=None,
                       require_native_rate: bool = CONTRACT_REQUIRE_NATIVE_RATE) -> dict:
    """Score one learner attempt. Returns PASS/RETRY -- never raises.

    Two supported input modes, both defined by the frozen training contract:

    * pre-segmented -- `audio_path`/`audio` is already one aligned token, cut
      at MMS_FA boundaries with the original_0ms policy (how every Train, Dev
      and native-reference token was produced).
    * align -- pass `syllable_pinyin` and `token_index` with a full utterance;
      the same aligner and boundary policy are reproduced here.

    Any validation, decoding, alignment or extraction failure yields RETRY with
    a structured failure code. No path can return PASS without a usable
    trajectory, a validated tone and a score at or below the frozen threshold.
    """
    started = time.perf_counter()
    result = {
        "scientific_version": SCIENTIFIC_VERSION,
        "deployment_version": DEPLOYMENT_VERSION,
        "audio_contract_version": AUDIO_CONTRACT_VERSION,
        "system_sha256": None, "fitted_model_sha256": None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "item_id": item_id, "expected_tone": None,
        "segmentation_mode": "align" if syllable_pinyin else "pre_segmented",
        "rate_profile": "strict_native" if require_native_rate else "permissive_resample",
        "source_sample_rate": None, "resampled": None,
        "token_duration_ms": None,
        "trajectory_available": False, "raw_score": None,
        "decision": "RETRY", "decision_reason": "not_processed",
        "failure_code": "unhandled_exception", "processing_latency_ms": None,
        "learner_message": RETRY_MESSAGE,
    }
    try:
        active = bundle if bundle is not None else get_bundle()
        result["system_sha256"] = active.metadata["system_sha256"]
        result["fitted_model_sha256"] = active.metadata["fitted_model_sha256"]

        # 1. expected tone -- validated before any feature is constructed
        try:
            tone = validate_expected_tone(expected_tone)
        except ValueError as error:
            result.update(failure_code="invalid_expected_tone",
                          decision_reason=str(error))
            return _finish(result, started)
        result["expected_tone"] = tone

        # 2. audio contract
        if audio is None:
            try:
                audio, meta = load_audio_to_contract(audio_path)
            except Exception as error:  # noqa: BLE001
                result.update(failure_code="unreadable_audio",
                              decision_reason=f"{type(error).__name__}")
                return _finish(result, started)
            result["source_sample_rate"] = meta["source_sample_rate"]
            result["resampled"] = meta["resampled"]
            result["source_format"] = meta["source_format"]
            result["source_channels"] = meta["source_channels"]
            if meta["source_sample_rate"] < CONTRACT_MIN_SOURCE_RATE:
                result.update(
                    failure_code="sample_rate_below_contract",
                    decision_reason=f"{meta['source_sample_rate']} Hz is below "
                                    f"the {CONTRACT_MIN_SOURCE_RATE} Hz minimum; "
                                    f"upsampling cannot restore the band the "
                                    f"frozen model was fitted on")
                return _finish(result, started)
            if require_native_rate and meta["resampled"]:
                result.update(
                    failure_code="sample_rate_not_native",
                    decision_reason=f"{meta['source_sample_rate']} Hz was "
                                    f"resampled to {CONTRACT_SAMPLE_RATE} Hz; the "
                                    f"strict profile requires native "
                                    f"{CONTRACT_SAMPLE_RATE} Hz capture")
                return _finish(result, started)
        else:
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=1).astype(np.float32)
            result["source_sample_rate"] = CONTRACT_SAMPLE_RATE
            result["resampled"] = False

        if len(audio) == 0:
            result.update(failure_code="empty_audio",
                          decision_reason="no samples decoded")
            return _finish(result, started)

        # 3. segmentation -- reproduce the frozen boundary policy
        if syllable_pinyin:
            segment, span, detail = segment_token(
                audio, syllable_pinyin, int(token_index or 0))
            if segment is None:
                code = ("alignment_span_missing"
                        if detail == "alignment_span_missing" else "alignment_failed")
                result.update(failure_code=code, decision_reason=detail)
                return _finish(result, started)
            result["alignment_span_seconds"] = [round(span[0], 4), round(span[1], 4)]
            result["alignment_score"] = round(span[2], 4)
            audio = segment

        duration_ms = len(audio) / CONTRACT_SAMPLE_RATE * 1000.0
        result["token_duration_ms"] = round(duration_ms, 1)
        if not (CONTRACT_MIN_TOKEN_MS <= duration_ms <= CONTRACT_MAX_TOKEN_MS):
            result.update(
                failure_code="token_duration_out_of_contract",
                decision_reason=f"{duration_ms:.0f} ms outside the "
                                f"{CONTRACT_MIN_TOKEN_MS:.0f}-"
                                f"{CONTRACT_MAX_TOKEN_MS:.0f} ms training envelope")
            return _finish(result, started)

        # 4. trajectory
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw, reason = trajectory_from_segment(audio)
        if raw is None:
            result.update(failure_code=reason,
                          decision_reason="trajectory_unavailable")
            return _finish(result, started)
        if not np.all(np.isfinite(raw)):
            result.update(failure_code="non_finite_trajectory",
                          decision_reason="trajectory_unavailable")
            return _finish(result, started)

        centred = raw - np.median(raw)

        # 5. score through the persisted frozen coefficients
        score = active.score(centred, tone)
        result.update(trajectory_available=True, raw_score=score,
                      failure_code="ok")

        # 6. the one frozen policy implementation
        decision, why = decide(score, tone, True, active.t_pass,
                               active.enabled_tones)
        result.update(decision=decision, decision_reason=why,
                      learner_message=PASS_MESSAGE if decision == "PASS"
                      else RETRY_MESSAGE)
    except ContractViolation:
        raise
    except Exception as error:  # noqa: BLE001
        result.update(failure_code="unhandled_exception",
                      decision_reason=f"{type(error).__name__}",
                      decision="RETRY", learner_message=RETRY_MESSAGE)
    return _finish(result, started)


def _finish(result: dict, started: float) -> dict:
    result["processing_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    if result["decision"] != "PASS":
        result["learner_message"] = RETRY_MESSAGE
    return result


def learner_response(result: dict) -> dict:
    """The ONLY shape that may reach a learner client.

    No score, no probability, no produced-tone diagnosis, no failure detail.
    """
    return {"status": result["decision"], "message": result["learner_message"]}


# ===========================================================================
# CLI
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-bundle", action="store_true",
                        help="fit the frozen procedure and persist the bundle")
    parser.add_argument("--show", action="store_true",
                        help="print bundle identity and startup checks")
    args = parser.parse_args()

    if args.build_bundle:
        bundle = FrozenInferenceBundle.fit_from_frozen_train()
        bundle.save()
        print(f"bundle written: {BUNDLE_NPZ.name}, {BUNDLE_JSON.name}")
        print(f"  fitted_model_sha256  {bundle.metadata['fitted_model_sha256']}")
        print(f"  model_config_sha256  {bundle.metadata['model_config_sha256']}")
        print(f"  feature_schema       {bundle.metadata['feature_schema_sha256'][:16]}")
        print(f"  features             {bundle.metadata['n_features']}")
        return

    bundle = FrozenInferenceBundle.load()
    checks = bundle.verify_startup()
    print(f"scientific  {bundle.metadata['scientific_version']}")
    print(f"deployment  {bundle.metadata['deployment_version']}")
    print(f"contract    {bundle.metadata['audio_contract_version']}")
    print(f"fitted_model_sha256 {bundle.metadata['fitted_model_sha256']}")
    print(f"model_config_sha256 {bundle.metadata['model_config_sha256']}")
    print(f"t_pass {bundle.t_pass}  enabled {sorted(bundle.enabled_tones)}")
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] startup {name}")


if __name__ == "__main__":
    main()
