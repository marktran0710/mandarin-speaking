"""Phase TV -- technical verification of the frozen OMPAL_R2_PASS_v1 system.

This asks one question only:

    does the frozen implementation behave correctly, deterministically, safely
    and reproducibly as an engineered system?

It does NOT ask whether Mandarin teachers agree with the judgements. A green
run here supports "the frozen implementation behaves as specified" and nothing
about assessment validity for real learners. Human criterion validation is
still required and is deliberately postponed.

Read-only with respect to the model, the policy, the OMPAL manifests and every
human-validation artefact. The only writes are verification reports under
data/technical_verification/ and reports/technical_verification/.

    python -m pronunciation.wav2vec_tone.verify_frozen_system
    python -m pronunciation.wav2vec_tone.verify_frozen_system --quick
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
import tracemalloc
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (  # noqa: E402
    MIN_VOICED_FRAMES, N_POINTS, PITCH_CEILING, PITCH_FLOOR, PITCH_STEP,
    REFERENCE_TONE, SAMPLE_RATE, TONES, design, fit_predict, normalise,
    trajectory_from_segment,
)
from pronunciation.wav2vec_tone.phase_c8_confirmation_policy import (  # noqa: E402
    C_VALUE, CLASS_WEIGHT, pass_mask,
)
from pronunciation.wav2vec_tone.preflight_fresh_validation import (  # noqa: E402
    PASS_MESSAGE, RETRY_MESSAGE, decide,
)

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
REPORTS_DIR = HERE.parents[1] / "reports" / "technical_verification"
OUT_DIR = DATA_DIR / "technical_verification"
SCRATCH = OUT_DIR / "scratch_audio"

FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"
C8_POLICY = DATA_DIR / "ompal_phase_c8_policy_FROZEN.json"
C6_PROTOCOL = DATA_DIR / "ompal_phase_c6_protocol_FROZEN.json"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"

EXPECTED_SYSTEM_HASH_PREFIX = "8101bcaf8c92e1e3"
EXPECTED_DESIGN_COLUMNS = 83
DETERMINISM_REPETITIONS = 20
STRESS_CALLS = 500

# ---------------------------------------------------------------------------
# Pre-registered metamorphic tolerances. Fixed here BEFORE any result was
# inspected. A transformation that does not change the speech content should
# not materially move the contour; these bounds detect implementation
# sensitivity, they are not a claim about acoustic equivalence.
# ---------------------------------------------------------------------------
METAMORPHIC_TOLERANCE = {
    "amplitude_x0.8": {"trajectory_st": 0.05, "score": 0.010},
    "amplitude_x1.2": {"trajectory_st": 0.05, "score": 0.010},
    "leading_silence_100ms": {"trajectory_st": 0.25, "score": 0.050},
    "trailing_silence_100ms": {"trajectory_st": 0.25, "score": 0.050},
    "lossless_wav_rewrite": {"trajectory_st": 1e-9, "score": 1e-9},
}
# Every metamorphic case must preserve the decision, regardless of tolerance.
METAMORPHIC_DECISION_MUST_HOLD = True

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_INFO = "INFO"

matrix: list[dict] = []
_counter = {"n": 0}


def record(category, description, expected, observed, ok, severity=SEVERITY_HIGH,
           notes="", diagnostic_only=False) -> bool:
    """Add one row to the verification matrix and echo it."""
    _counter["n"] += 1
    test_id = f"TV{_counter['n']:03d}"
    result = "DIAGNOSTIC" if diagnostic_only else ("PASS" if ok else "FAIL")
    matrix.append({
        "test_id": test_id,
        "category": category,
        "input": description,
        "expected_behaviour": expected,
        "observed_behaviour": observed,
        "result": result,
        "severity": severity if not ok and not diagnostic_only else (
            SEVERITY_INFO if diagnostic_only else ""),
        "notes": notes,
    })
    flag = {"PASS": "PASS", "FAIL": "FAIL", "DIAGNOSTIC": "DIAG"}[result]
    print(f"  [{flag}] {test_id} {description}"
          + (f"  -- {observed}" if observed else ""))
    return bool(ok)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json_without(payload: dict, drop: str) -> str:
    """Recompute the self-hash the way the artefact itself computed it."""
    body = {k: v for k, v in payload.items() if k != drop}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


# ===========================================================================
# 1. Frozen artefact integrity
# ===========================================================================

def section_artifact_integrity() -> dict:
    print("\n1. FROZEN ARTEFACT INTEGRITY")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    recomputed = sha256_json_without(frozen, "sha256")
    recorded = frozen["sha256"]

    ok = record("artifact integrity", "fresh_validation_system_FROZEN.json self-hash",
                f"sha256 == {recorded[:16]}", f"recomputed {recomputed[:16]}",
                recomputed == recorded, SEVERITY_BLOCKING)
    if not ok:
        sys.exit("STOP TECHNICAL VERIFICATION: frozen system artefact has changed")

    record("artifact integrity", "system hash matches the expected published prefix",
           EXPECTED_SYSTEM_HASH_PREFIX, recorded[:16],
           recorded.startswith(EXPECTED_SYSTEM_HASH_PREFIX), SEVERITY_BLOCKING)
    if not recorded.startswith(EXPECTED_SYSTEM_HASH_PREFIX):
        sys.exit("STOP TECHNICAL VERIFICATION: system hash is not the frozen one")

    c8 = json.loads(C8_POLICY.read_text(encoding="utf-8"))
    c8_recomputed = sha256_json_without(c8, "sha256")
    record("artifact integrity", "ompal_phase_c8_policy_FROZEN.json self-hash",
           f"sha256 == {c8['sha256'][:16]}", f"recomputed {c8_recomputed[:16]}",
           c8_recomputed == c8["sha256"], SEVERITY_BLOCKING)
    record("artifact integrity", "C8 policy hash matches the value recorded in the system file",
           frozen["hashes"]["c8_policy_sha256"][:16], c8["sha256"][:16],
           frozen["hashes"]["c8_policy_sha256"] == c8["sha256"], SEVERITY_BLOCKING)

    c6 = json.loads(C6_PROTOCOL.read_text(encoding="utf-8"))
    c6_recomputed = sha256_json_without(c6, "sha256")
    record("artifact integrity", "ompal_phase_c6_protocol_FROZEN.json self-hash",
           f"sha256 == {c6.get('sha256', '')[:16]}", f"recomputed {c6_recomputed[:16]}",
           c6_recomputed == c6.get("sha256"), SEVERITY_BLOCKING)
    record("artifact integrity", "C6 representation hash matches the system file",
           frozen["hashes"]["c6_representation_sha256"][:16], c6.get("sha256", "")[:16],
           frozen["hashes"]["c6_representation_sha256"] == c6.get("sha256"),
           SEVERITY_BLOCKING)

    # The recorded "model hash" is a hash of the training CONFIGURATION only.
    model_hash = hashlib.sha256(json.dumps(
        {"C": C_VALUE, "class_weight": CLASS_WEIGHT, "points": N_POINTS},
        sort_keys=True).encode()).hexdigest()
    record("artifact integrity", "C8 model hash reproduces from the frozen config triple",
           c8["model_hash"][:16], model_hash[:16],
           model_hash == c8["model_hash"], SEVERITY_BLOCKING,
           "hash covers {C, class_weight, points} only -- see TV finding on artefact binding")

    record("artifact integrity", "trajectory configuration matches the frozen representation",
           f"points={frozen['representation']['points']} floor={frozen['representation']['pitch_floor_hz']} "
           f"ceiling={frozen['representation']['pitch_ceiling_hz']} step={frozen['representation']['pitch_time_step_s']}",
           f"points={N_POINTS} floor={PITCH_FLOOR} ceiling={PITCH_CEILING} step={PITCH_STEP}",
           (N_POINTS == frozen["representation"]["points"]
            and PITCH_FLOOR == frozen["representation"]["pitch_floor_hz"]
            and PITCH_CEILING == frozen["representation"]["pitch_ceiling_hz"]
            and PITCH_STEP == frozen["representation"]["pitch_time_step_s"]),
           SEVERITY_BLOCKING)

    record("artifact integrity", "classifier constants match the frozen classifier block",
           f"C={frozen['classifier']['C']} class_weight={frozen['classifier']['class_weight']}",
           f"C={C_VALUE} class_weight={CLASS_WEIGHT}",
           (C_VALUE == frozen["classifier"]["C"]
            and CLASS_WEIGHT == frozen["classifier"]["class_weight"]),
           SEVERITY_BLOCKING)

    record("artifact integrity", "t_pass agrees between the system file and the C8 policy",
           str(frozen["decision_policy"]["t_pass"]), str(c8["t_pass"]),
           frozen["decision_policy"]["t_pass"] == c8["t_pass"], SEVERITY_BLOCKING)

    enabled_system = {t.replace("T", "") for t in frozen["decision_policy"]["enabled_pass_tones"]}
    record("artifact integrity", "enabled PASS tones agree between the two frozen artefacts",
           "".join(sorted(enabled_system)), c8["enabled_tones"],
           "".join(sorted(enabled_system)) == c8["enabled_tones"], SEVERITY_BLOCKING)

    # Content hashes of the arrays the deployed model is actually fitted on.
    cache = dict(np.load(CACHE, allow_pickle=True))
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    train = cache["split"] == "train"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        trajectory = normalise(stored["learner"], "N2")
    training_hashes = {
        "train_trajectory_sha256": sha256_array(trajectory[train]),
        "train_tone_sha256": hashlib.sha256(
            "".join(cache["tone"][train].tolist()).encode()).hexdigest(),
        "train_label_sha256": sha256_array(cache["y"][train]),
        "manifest_split_sha256": sha256_file(MANIFEST_SPLIT),
        "feature_cache_sha256": sha256_file(CACHE),
        "trajectory_cache_sha256": sha256_file(TRAJ_CACHE),
    }
    record("artifact integrity", "training inputs are hashable and stable within the run",
           "six content hashes computed", training_hashes["train_trajectory_sha256"][:16],
           all(len(v) == 64 for v in training_hashes.values()), SEVERITY_MEDIUM,
           "these hashes are recorded in golden_reference.json to bind future runs")

    record("artifact integrity", "train split shape matches the frozen C8 record",
           "1424 rows / 32 speakers", f"{int(train.sum())} rows / "
           f"{len(set(cache['speaker'][train].tolist()))} speakers",
           int(train.sum()) == 1424
           and len(set(cache["speaker"][train].tolist())) == 32, SEVERITY_BLOCKING)

    return {"frozen": frozen, "c8": c8, "c6": c6,
            "training_hashes": training_hashes,
            "config_model_hash": model_hash}


# ===========================================================================
# Deployed system under test
# ===========================================================================

DESIGN_COLUMN_NAMES = (
    [f"traj_{i:02d}" for i in range(N_POINTS)]
    + [f"tone_T{t}" for t in TONES if t != REFERENCE_TONE]
    + [f"traj_{i:02d}_x_T{t}"
       for t in TONES if t != REFERENCE_TONE for i in range(N_POINTS)]
)


class DeployedSystem:
    """The frozen configuration fitted once, exactly as fit_predict fits it.

    The research code refits the classifier on every scored utterance. Fitting
    once and reusing the fitted objects is the only way a server can serve
    this; TV004 proves the two give bit-identical scores, so this wrapper is a
    verification convenience, not a change to the model.
    """

    def __init__(self, seed: int = 0):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        cache = dict(np.load(CACHE, allow_pickle=True))
        stored = np.load(TRAJ_CACHE, allow_pickle=True)
        if "test" in set(cache["split"].tolist()):
            sys.exit("TEST LOCK VIOLATION in cache")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            trajectory = normalise(stored["learner"], "N2")
        train = cache["split"] == "train"
        self.train_base = trajectory[train]
        self.train_tones = cache["tone"][train]
        self.train_y = cache["y"][train]

        self.imputer = SimpleImputer(strategy="median").fit(self.train_base)
        self.scaler = StandardScaler().fit(self.imputer.transform(self.train_base))
        train_matrix = design(
            self.scaler.transform(self.imputer.transform(self.train_base)),
            self.train_tones)
        self.n_columns = train_matrix.shape[1]
        self.model = LogisticRegression(
            max_iter=8000, C=C_VALUE, class_weight=CLASS_WEIGHT,
            random_state=seed).fit(train_matrix, self.train_y)

    def matrix_for(self, base: np.ndarray, tones: np.ndarray) -> np.ndarray:
        return design(self.scaler.transform(self.imputer.transform(base)), tones)

    def score_batch(self, base: np.ndarray, tones: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(self.matrix_for(base, tones))[:, 1]

    def score_one(self, centred: np.ndarray, tone: str) -> float:
        return float(self.score_batch(np.asarray(centred, dtype=float).reshape(1, -1),
                                      np.asarray([tone], dtype=object))[0])

    def coefficient_hash(self) -> str:
        return hashlib.sha256(
            np.ascontiguousarray(np.round(self.model.coef_, 12)).tobytes()
            + np.ascontiguousarray(np.round(self.model.intercept_, 12)).tobytes()
        ).hexdigest()

    def infer(self, audio, tone, t_pass: float, enabled: set) -> dict:
        """The full production chain, with every failure surfaced as a code."""
        started = time.perf_counter()
        out = {"trajectory_available": False, "raw_score": float("nan"),
               "decision": "RETRY", "decision_reason": "not_processed",
               "failure_code": "", "exception": "", "trajectory": None}
        try:
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim > 1:                      # stereo or multichannel
                out["failure_code"] = "multichannel_input"
                out["decision_reason"] = "trajectory_unavailable"
                out["latency_ms"] = (time.perf_counter() - started) * 1000
                return out
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw, reason = trajectory_from_segment(audio)
            if raw is None:
                out["failure_code"] = reason
                out["decision"], out["decision_reason"] = decide(
                    float("nan"), tone, False, t_pass, enabled)
                out["latency_ms"] = (time.perf_counter() - started) * 1000
                return out
            if not np.all(np.isfinite(raw)):
                out["failure_code"] = "non_finite_trajectory"
                out["decision"], out["decision_reason"] = decide(
                    float("nan"), tone, False, t_pass, enabled)
                out["latency_ms"] = (time.perf_counter() - started) * 1000
                return out
            centred = raw - np.median(raw)
            score = self.score_one(centred, tone)
            out.update(trajectory_available=True, raw_score=score,
                       trajectory=centred)
            out["decision"], out["decision_reason"] = decide(
                score, tone, True, t_pass, enabled)
        except Exception as error:                  # noqa: BLE001
            out["exception"] = f"{type(error).__name__}: {error}"
            out["failure_code"] = "unhandled_exception"
            out["decision"], out["decision_reason"] = "RETRY", "processing_error"
        out["latency_ms"] = (time.perf_counter() - started) * 1000
        return out


def section_deployment_equivalence(system: DeployedSystem, reference) -> None:
    """Fitting once must reproduce the research path exactly."""
    print("\n1b. DEPLOYMENT-PATH EQUIVALENCE")
    base = np.stack([r["centred"] for r in reference if r["centred"] is not None])
    tones = np.asarray([r["tone"] for r in reference if r["centred"] is not None],
                       dtype=object)
    research, _ = fit_predict(system.train_base, system.train_tones, system.train_y,
                              base, tones, C_VALUE, 0)
    served = system.score_batch(base, tones)
    delta = float(np.max(np.abs(research - served)))
    record("determinism", "fit-once serving reproduces fit_predict bit-for-bit",
           "max |delta| == 0", f"max |delta| = {delta:.3e}",
           delta == 0.0, SEVERITY_BLOCKING,
           "authorises the fit-once wrapper used for the rest of this suite")

    seeded, _ = fit_predict(system.train_base, system.train_tones, system.train_y,
                            base, tones, C_VALUE, 20260808)
    seed_delta = float(np.max(np.abs(research - seeded)))
    record("determinism", "seed does not influence the frozen solver (lbfgs)",
           "max |delta| == 0 between seed 0 and seed 20260808",
           f"max |delta| = {seed_delta:.3e}", seed_delta == 0.0, SEVERITY_HIGH,
           "confirms the D0 preflight seed 20260808 scores identically to the C8 seed 0")


# ===========================================================================
# Technical reference set
# ===========================================================================

def build_reference_set(system: DeployedSystem, per_tone: int = 3) -> list[dict]:
    """Fixed non-Test technical reference set: native reference tokens only."""
    import soundfile as sf

    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] == "native_reference"]
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION")
    by_tone: dict[str, list] = {t: [] for t in TONES}
    for row in sorted(rows, key=lambda r: r["token_id"]):
        by_tone[row["expected_tone"]].append(row)

    reference = []
    for tone in TONES:
        for row in by_tone[tone][:per_tone]:
            path = DATA_DIR / row["extracted_token_path"]
            audio, sample_rate = sf.read(str(path), dtype="float32")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw, reason = trajectory_from_segment(np.asarray(audio, dtype=np.float32))
            reference.append({
                "ref_id": f"REF_{row['token_id']}",
                "token_id": row["token_id"], "tone": tone, "path": path,
                "audio": np.asarray(audio, dtype=np.float32),
                "file_sample_rate": int(sample_rate),
                "centred": None if raw is None else raw - np.median(raw),
                "status": reason,
            })
    return reference


# ===========================================================================
# 3. Decision-policy unit tests
# ===========================================================================

def section_policy(t_pass: float, enabled: set) -> None:
    print("\n2. DECISION-POLICY UNIT TESTS")
    sweep = np.concatenate([
        np.linspace(0.0, 1.0, 1001),
        np.asarray([t_pass, t_pass - 1e-12, t_pass + 1e-12, 0.0, 1.0]),
    ])

    t1_decisions = {decide(float(s), "1", True, t_pass, enabled)[0] for s in sweep}
    record("policy", "T1 never returns PASS across a 1006-point score sweep",
           "{RETRY}", str(sorted(t1_decisions)), t1_decisions == {"RETRY"},
           SEVERITY_BLOCKING)

    unavailable = {tone: decide(float("nan"), tone, False, t_pass, enabled)
                   for tone in TONES}
    record("policy", "trajectory unavailable returns RETRY for every expected tone",
           "RETRY/trajectory_unavailable x4",
           str({k: v[0] for k, v in unavailable.items()}),
           all(v == ("RETRY", "trajectory_unavailable") for v in unavailable.values()),
           SEVERITY_BLOCKING)

    # A NaN score must never slip through the comparison as PASS.
    nan_decisions = {tone: decide(float("nan"), tone, True, t_pass, enabled)[0]
                     for tone in TONES}
    record("policy", "NaN score with trajectory marked available still never PASSes",
           "{RETRY}", str(sorted(set(nan_decisions.values()))),
           set(nan_decisions.values()) == {"RETRY"}, SEVERITY_BLOCKING,
           "NaN <= t_pass is False in IEEE 754, so the rule fails safe")

    below = [decide(float(s), tone, True, t_pass, enabled)
             for tone in ("2", "3", "4") for s in np.linspace(0.0, t_pass, 200)]
    record("policy", "T2/T3/T4 with score satisfying the frozen PASS rule return PASS",
           "PASS for all 600 admissible scores",
           f"{sum(1 for d, _ in below if d == 'PASS')}/600 PASS",
           all(d == "PASS" for d, _ in below), SEVERITY_BLOCKING)

    above = [decide(float(s), tone, True, t_pass, enabled)
             for tone in ("2", "3", "4")
             for s in np.linspace(np.nextafter(t_pass, 1.0), 1.0, 200)]
    record("policy", "T2/T3/T4 with score outside the frozen PASS rule return RETRY",
           "RETRY for all 600 inadmissible scores",
           f"{sum(1 for d, _ in above if d == 'RETRY')}/600 RETRY",
           all(d == "RETRY" for d, _ in above), SEVERITY_BLOCKING)

    outputs = {d for d, _ in below + above} | t1_decisions | set(nan_decisions.values())
    record("policy", "only PASS and RETRY are ever emitted",
           "{PASS, RETRY}", str(sorted(outputs)), outputs <= {"PASS", "RETRY"},
           SEVERITY_BLOCKING)

    # Cross-implementation check: the scalar policy used by the serving chain
    # must agree with the vectorised pass_mask used to derive the policy.
    rng = np.random.default_rng(0)
    n = 4000
    scores = rng.random(n)
    tones = rng.choice(np.asarray(TONES, dtype=object), n)
    available = rng.random(n) > 0.15
    vector = pass_mask(scores, tones, available, t_pass, enabled)
    scalar = np.asarray([decide(float(s), str(t), bool(a), t_pass, enabled)[0] == "PASS"
                         for s, t, a in zip(scores, tones, available)])
    disagreements = int((vector != scalar).sum())
    record("policy", "scalar decide() and vectorised pass_mask() agree on 4000 cases",
           "0 disagreements", f"{disagreements} disagreements",
           disagreements == 0, SEVERITY_BLOCKING,
           "the derivation code and the serving code implement one rule")


# ===========================================================================
# 4. Threshold boundary tests
# ===========================================================================

def section_threshold(t_pass: float, enabled: set) -> str:
    print("\n3. THRESHOLD BOUNDARY")
    exactly = decide(t_pass, "2", True, t_pass, enabled)[0]
    operator = "<=" if exactly == "PASS" else "<"
    record("threshold", "comparison operator at the threshold identified",
           "documented, not assumed", f"score {operator} t_pass -> PASS",
           exactly == "PASS", SEVERITY_BLOCKING,
           "source of truth: pass_mask() uses scores <= t_pass; a score is "
           "P(incorrect), so LOW scores PASS")

    below, above = np.nextafter(t_pass, 0.0), np.nextafter(t_pass, 1.0)
    cases = [
        ("one ULP below t_pass", below, "PASS"),
        ("exactly t_pass", t_pass, "PASS"),
        ("one ULP above t_pass", above, "RETRY"),
        ("0.422730 (literal below)", 0.422730, "PASS"),
        ("0.422740 (literal at)", 0.422740, "PASS"),
        ("0.422750 (literal above)", 0.422750, "RETRY"),
        ("0.4227 (the abbreviated value)", 0.4227, "PASS"),
    ]
    for label, value, want in cases:
        got = decide(float(value), "2", True, t_pass, enabled)[0]
        record("threshold", f"{label} -> {want}", want, got, got == want,
               SEVERITY_BLOCKING, f"score={value!r}")

    record("threshold", "one ULP separates the last PASS from the first RETRY",
           "no ambiguous interval", f"ULP = {above - below:.3e}",
           decide(below, "2", True, t_pass, enabled)[0] == "PASS"
           and decide(above, "2", True, t_pass, enabled)[0] == "RETRY",
           SEVERITY_BLOCKING)

    # The float literal in the two artefacts must be the same float, not just
    # the same printed text.
    frozen_value = json.loads(FROZEN.read_text(encoding="utf-8"))["decision_policy"]["t_pass"]
    c8_value = json.loads(C8_POLICY.read_text(encoding="utf-8"))["t_pass"]
    record("threshold", "t_pass parses to an identical IEEE double in both artefacts",
           "bitwise identical", f"{frozen_value!r} vs {c8_value!r}",
           frozen_value.hex() == c8_value.hex(), SEVERITY_BLOCKING)

    record("threshold", "the abbreviated 0.4227 is NOT the frozen threshold",
           "frozen value is 0.42274", f"0.4227 != {t_pass}", 0.4227 != t_pass,
           SEVERITY_MEDIUM,
           "documentation that quotes 0.4227 is rounded; the implementation uses 0.42274")
    return operator


# ===========================================================================
# 5-6. Determinism and process-restart reproducibility
# ===========================================================================

def section_determinism(system, reference, t_pass, enabled, repetitions) -> dict:
    print(f"\n4. DETERMINISM ({repetitions} repetitions)")
    runs = []
    for _ in range(repetitions):
        runs.append([system.infer(item["audio"], item["tone"], t_pass, enabled)
                     for item in reference])

    traj_delta = score_delta = 0.0
    decision_changes = failure_changes = 0
    for index in range(len(reference)):
        first = runs[0][index]
        for other in runs[1:]:
            current = other[index]
            if first["trajectory"] is not None and current["trajectory"] is not None:
                traj_delta = max(traj_delta, float(
                    np.max(np.abs(first["trajectory"] - current["trajectory"]))))
            first_score = first["raw_score"]
            if math.isfinite(first_score) and math.isfinite(current["raw_score"]):
                score_delta = max(score_delta, abs(first_score - current["raw_score"]))
            decision_changes += first["decision"] != current["decision"]
            failure_changes += first["failure_code"] != current["failure_code"]

    record("determinism", f"F0 trajectory identical across {repetitions} runs",
           "max |delta| == 0", f"max |delta| = {traj_delta:.3e}",
           traj_delta == 0.0, SEVERITY_BLOCKING)
    record("determinism", f"R2 raw score identical across {repetitions} runs",
           "max |delta| == 0", f"max |delta| = {score_delta:.3e}",
           score_delta == 0.0, SEVERITY_BLOCKING)
    record("determinism", f"PASS/RETRY verdict identical across {repetitions} runs",
           "0 changes", f"{decision_changes} changes", decision_changes == 0,
           SEVERITY_BLOCKING)
    record("determinism", f"failure code identical across {repetitions} runs",
           "0 changes", f"{failure_changes} changes", failure_changes == 0,
           SEVERITY_BLOCKING)

    return {"trajectory_max_delta": traj_delta, "score_max_delta": score_delta,
            "decision_changes": decision_changes,
            "baseline": [{"ref_id": reference[i]["ref_id"],
                          "tone": reference[i]["tone"],
                          "trajectory_available": runs[0][i]["trajectory_available"],
                          "raw_score": runs[0][i]["raw_score"],
                          "decision": runs[0][i]["decision"],
                          "failure_code": runs[0][i]["failure_code"]}
                         for i in range(len(reference))]}


def section_restart(baseline: list[dict], system: DeployedSystem) -> None:
    print("\n5. PROCESS-RESTART REPRODUCIBILITY")
    child = subprocess.run(
        [sys.executable, "-m", "pronunciation.wav2vec_tone.verify_frozen_system",
         "--child-scores"],
        cwd=str(HERE.parents[1]), capture_output=True, text=True, timeout=900)
    if child.returncode != 0:
        record("determinism", "cold child process completes the same reference set",
               "exit 0", f"exit {child.returncode}: {child.stderr.strip()[-200:]}",
               False, SEVERITY_BLOCKING)
        return
    payload = json.loads(child.stdout.strip().splitlines()[-1])

    record("determinism", "restarted process reports the same frozen system hash",
           payload["system_sha256"][:16],
           json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"][:16],
           payload["system_sha256"] == json.loads(
               FROZEN.read_text(encoding="utf-8"))["sha256"], SEVERITY_BLOCKING)

    record("determinism", "restarted process fits identical model coefficients",
           system.coefficient_hash()[:16], payload["coefficient_hash"][:16],
           payload["coefficient_hash"] == system.coefficient_hash(), SEVERITY_BLOCKING)

    deltas, changed = [], 0
    for parent_row, child_row in zip(baseline, payload["rows"]):
        if math.isfinite(parent_row["raw_score"]) and child_row["raw_score"] is not None:
            deltas.append(abs(parent_row["raw_score"] - child_row["raw_score"]))
        changed += parent_row["decision"] != child_row["decision"]
    worst = max(deltas) if deltas else 0.0
    record("determinism", "scores survive a process restart within tolerance",
           "max |delta| == 0", f"max |delta| = {worst:.3e}", worst == 0.0,
           SEVERITY_BLOCKING)
    record("determinism", "a server restart cannot change a learner decision",
           "0 decision changes", f"{changed} changes", changed == 0,
           SEVERITY_BLOCKING)


def child_scores_mode() -> None:
    """Cold-process worker for the restart test: prints one JSON line."""
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    t_pass = frozen["decision_policy"]["t_pass"]
    enabled = {t.replace("T", "") for t in frozen["decision_policy"]["enabled_pass_tones"]}
    system = DeployedSystem()
    reference = build_reference_set(system)
    rows = []
    for item in reference:
        out = system.infer(item["audio"], item["tone"], t_pass, enabled)
        rows.append({"ref_id": item["ref_id"], "decision": out["decision"],
                     "raw_score": None if not math.isfinite(out["raw_score"])
                     else out["raw_score"],
                     "failure_code": out["failure_code"]})
    print(json.dumps({"system_sha256": frozen["sha256"],
                      "coefficient_hash": system.coefficient_hash(),
                      "rows": rows}))


# ===========================================================================
# 9-10. Trajectory construction and model-input dimensionality
# ===========================================================================

def section_trajectory(system, reference) -> None:
    print("\n6. F0 TRAJECTORY CONSTRUCTION")
    import parselmouth

    usable = [r for r in reference if r["centred"] is not None]
    record("trajectory", "every reference trajectory has exactly 20 points",
           f"{N_POINTS} points", f"{ {len(r['centred']) for r in usable} }",
           all(len(r["centred"]) == N_POINTS for r in usable), SEVERITY_BLOCKING)
    record("trajectory", "every trajectory value is finite",
           "all finite", f"{sum(1 for r in usable if np.all(np.isfinite(r['centred'])))}"
           f"/{len(usable)} clean",
           all(np.all(np.isfinite(r["centred"])) for r in usable), SEVERITY_BLOCKING)

    worst_centre = max(abs(float(np.median(r["centred"]))) for r in usable)
    record("trajectory", "median-centred contour is centred on zero",
           "|median| < 1e-12", f"worst |median| = {worst_centre:.3e}",
           worst_centre < 1e-12, SEVERITY_HIGH)

    # Independent re-derivation of one token, without reusing the module code.
    item = usable[0]
    pitch = parselmouth.Sound(item["audio"].astype(np.float64), SAMPLE_RATE).to_pitch(
        time_step=PITCH_STEP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
    frequencies = pitch.selected_array["frequency"]
    times = np.asarray(pitch.xs(), dtype=float)
    voiced = np.isfinite(frequencies) & (frequencies > 0)
    voiced_times, voiced_values = times[voiced], frequencies[voiced]
    manual_semitones = 12.0 * np.log2(voiced_values)
    span = voiced_times[-1] - voiced_times[0]
    grid = voiced_times[0] + np.linspace(0.0, 1.0, N_POINTS) * span
    manual = np.interp(grid, voiced_times, manual_semitones)
    manual_centred = manual - np.median(manual)
    delta = float(np.max(np.abs(manual_centred - item["centred"])))
    record("trajectory", "independent re-derivation reproduces the module trajectory",
           "max |delta| == 0", f"max |delta| = {delta:.3e}", delta == 0.0,
           SEVERITY_BLOCKING,
           "semitone conversion 12*log2(Hz), time-normalised over the voiced span")

    record("trajectory", "sample grid is monotonically increasing over the voiced span",
           "strictly increasing", f"span = {span * 1000:.1f} ms",
           bool(np.all(np.diff(grid) > 0)), SEVERITY_HIGH)

    # Hz/semitone mixing check: raw Hz sits near 12*log2(100..300) = 80..99 ST,
    # so a centred contour whose values reach into the tens indicates a raw-Hz
    # value leaked into a semitone slot.
    worst_magnitude = max(float(np.max(np.abs(r["centred"]))) for r in usable)
    record("trajectory", "no raw-Hz value leaked into the semitone contour",
           "max |centred semitone| < 24", f"max = {worst_magnitude:.2f} ST",
           worst_magnitude < 24.0, SEVERITY_HIGH,
           "a leaked Hz value would appear as a 60-500 magnitude in a +/-24 ST field")

    print("\n7. MODEL-INPUT DIMENSIONALITY")
    record("dimensionality", "fitted design matrix has the frozen column count",
           f"{EXPECTED_DESIGN_COLUMNS} columns", f"{system.n_columns} columns",
           system.n_columns == EXPECTED_DESIGN_COLUMNS, SEVERITY_BLOCKING,
           "20 trajectory + 3 reference-coded tone dummies + 60 interactions")
    record("dimensionality", "fitted coefficient vector matches the design width",
           f"{EXPECTED_DESIGN_COLUMNS}", f"{system.model.coef_.shape[1]}",
           system.model.coef_.shape[1] == EXPECTED_DESIGN_COLUMNS, SEVERITY_BLOCKING)
    record("dimensionality", "the named column list is the same width",
           f"{EXPECTED_DESIGN_COLUMNS} names", f"{len(DESIGN_COLUMN_NAMES)} names",
           len(DESIGN_COLUMN_NAMES) == EXPECTED_DESIGN_COLUMNS, SEVERITY_BLOCKING)

    # Ordering by name, not by count: build a probe whose trajectory values are
    # distinguishable per position and verify every column against its formula.
    probe = np.arange(1.0, N_POINTS + 1.0).reshape(1, -1)
    mismatched = []
    for tone in TONES:
        scaled = system.scaler.transform(system.imputer.transform(probe))
        built = design(scaled, np.asarray([tone], dtype=object))[0]
        expected = np.zeros(EXPECTED_DESIGN_COLUMNS)
        expected[:N_POINTS] = scaled[0]
        non_reference = [t for t in TONES if t != REFERENCE_TONE]
        for position, candidate in enumerate(non_reference):
            active = 1.0 if tone == candidate else 0.0
            expected[N_POINTS + position] = active
            start = N_POINTS + 3 + position * N_POINTS
            expected[start:start + N_POINTS] = scaled[0] * active
        for column, (got, want) in enumerate(zip(built, expected)):
            if abs(got - want) > 1e-12:
                mismatched.append((tone, DESIGN_COLUMN_NAMES[column]))
    record("dimensionality", "every design column matches its name and formula",
           "0 mismatched columns", f"{len(mismatched)} mismatched",
           not mismatched, SEVERITY_BLOCKING,
           "checked per tone for all 83 columns, by position and by name")


# ===========================================================================
# 8. Expected-tone routing
# ===========================================================================

def section_tone_routing(system, reference, t_pass, enabled) -> None:
    print("\n8. EXPECTED-TONE ROUTING")
    item = next(r for r in reference if r["centred"] is not None)

    activations = {}
    for tone in TONES:
        row = system.matrix_for(item["centred"].reshape(1, -1),
                                np.asarray([tone], dtype=object))[0]
        dummies = row[N_POINTS:N_POINTS + 3]
        activations[tone] = dummies.tolist()

    record("tone routing", "T1 activates no dummy (it is the reference level)",
           "[0, 0, 0]", str(activations["1"]),
           activations["1"] == [0.0, 0.0, 0.0], SEVERITY_BLOCKING)
    for position, tone in enumerate(("2", "3", "4")):
        want = [1.0 if i == position else 0.0 for i in range(3)]
        record("tone routing", f"T{tone} activates exactly the T{tone} dummy column",
               str(want), str(activations[tone]), activations[tone] == want,
               SEVERITY_BLOCKING, "detects a shifted tone index")

    interactions = {}
    for tone in TONES:
        row = system.matrix_for(item["centred"].reshape(1, -1),
                                np.asarray([tone], dtype=object))[0]
        blocks = {t: row[N_POINTS + 3 + i * N_POINTS:N_POINTS + 3 + (i + 1) * N_POINTS]
                  for i, t in enumerate(("2", "3", "4"))}
        interactions[tone] = {t: bool(np.any(v != 0)) for t, v in blocks.items()}
    routing_ok = (
        not any(interactions["1"].values())
        and all(interactions[t][t] and sum(interactions[t].values()) == 1
                for t in ("2", "3", "4")))
    record("tone routing", "exactly the matching trajectory-x-tone block is populated",
           "one active interaction block per non-reference tone",
           str({t: [k for k, v in b.items() if v] for t, b in interactions.items()}),
           routing_ok, SEVERITY_BLOCKING)

    scores = {tone: system.score_one(item["centred"], tone) for tone in TONES}
    record("tone routing", "expected tone actually changes the score for fixed audio",
           "4 distinct scores", ", ".join(f"T{t}={s:.4f}" for t, s in scores.items()),
           len({round(s, 9) for s in scores.values()}) == 4, SEVERITY_BLOCKING,
           "software routing test only -- NOT a pronunciation result")

    # The dtype trap: the design code compares tone labels as strings. This is
    # an input-validation gap, not a routing error -- routing is correct for
    # every label the frozen contract actually defines (TV053-TV058).
    numeric = system.matrix_for(item["centred"].reshape(1, -1), np.asarray([2]))[0]
    numeric_dummies = numeric[N_POINTS:N_POINTS + 3].tolist()
    silently_routed_to_t1 = numeric_dummies == [0.0, 0.0, 0.0]
    record("input validation",
           "integer expected-tone is rejected rather than routed to the T1 branch",
           "rejected or raised", f"accepted; dummies = {numeric_dummies}",
           not silently_routed_to_t1, SEVERITY_MEDIUM,
           "design() compares tone labels as strings, so an int label activates "
           "no dummy and is scored as if it were T1. The policy layer still "
           "refuses PASS because int 2 is not in the enabled string set (TV060), "
           "so it fails safe today -- but nothing enforces that coupling")

    numeric_decision = decide(scores["2"], 2, True, t_pass, enabled)[0]
    record("fail-safe", "integer expected-tone cannot produce PASS through the policy",
           "RETRY", numeric_decision, numeric_decision == "RETRY", SEVERITY_HIGH)


# ===========================================================================
# 11. Audio input robustness matrix
# ===========================================================================

def build_robustness_cases(reference) -> list[dict]:
    import soundfile as sf

    SCRATCH.mkdir(parents=True, exist_ok=True)
    clean = next(r for r in reference if r["centred"] is not None)
    audio = clean["audio"]
    cases = []

    def wav(name, samples, rate=SAMPLE_RATE, subtype=None):
        path = SCRATCH / f"TVROB_{name}.wav"
        sf.write(path, samples, rate, subtype=subtype)
        return path

    cases.append({"name": "normal_valid_wav", "path": clean["path"], "tone": clean["tone"]})
    cases.append({"name": "mono_16k", "path": wav("mono", audio), "tone": clean["tone"]})
    cases.append({"name": "stereo_input",
                  "path": wav("stereo", np.stack([audio, audio], axis=1)),
                  "tone": clean["tone"]})
    cases.append({"name": "digital_silence",
                  "path": wav("silence", np.zeros(int(0.25 * SAMPLE_RATE), dtype=np.float32)),
                  "tone": "2"})
    cases.append({"name": "very_short_10ms",
                  "path": wav("short10ms", audio[:int(0.01 * SAMPLE_RATE)]),
                  "tone": clean["tone"]})
    cases.append({"name": "empty_audio",
                  "path": wav("empty", np.zeros(0, dtype=np.float32)),
                  "tone": clean["tone"]})
    cases.append({"name": "clipped_waveform",
                  "path": wav("clipped", np.clip(audio * 20.0, -1.0, 1.0)),
                  "tone": clean["tone"]})
    cases.append({"name": "very_low_amplitude",
                  "path": wav("quiet", (audio * 1e-4).astype(np.float32),
                              subtype="FLOAT"),
                  "tone": clean["tone"]})
    cases.append({"name": "very_high_amplitude",
                  "path": wav("loud", (audio * 5.0).astype(np.float32), subtype="FLOAT"),
                  "tone": clean["tone"]})
    # Genuine resampling: the SAME speech carried at another rate, which is what
    # a browser or phone actually delivers. Relabelling the header alone would
    # not test anything, because the chain never reads the header.
    for rate in (8000, 44100, 48000):
        n = int(len(audio) * rate / SAMPLE_RATE)
        resampled = np.interp(np.linspace(0, len(audio) - 1, n),
                              np.arange(len(audio)), audio).astype(np.float32)
        cases.append({"name": f"sample_rate_{rate}",
                      "path": wav(f"sr{rate}", resampled, rate=rate),
                      "tone": clean["tone"]})
    cases.append({"name": "white_noise_unvoiced",
                  "path": wav("noise", (np.random.default_rng(0).normal(
                      0, 0.05, int(0.4 * SAMPLE_RATE))).astype(np.float32)),
                  "tone": "2"})
    cases.append({"name": "dc_offset_constant",
                  "path": wav("dc", np.full(int(0.3 * SAMPLE_RATE), 0.4, dtype=np.float32),
                              subtype="FLOAT"),
                  "tone": "2"})

    corrupted = SCRATCH / "TVROB_corrupted.wav"
    corrupted.write_bytes(b"RIFF" + np.random.default_rng(1).bytes(2048))
    cases.append({"name": "corrupted_file", "path": corrupted, "tone": "2"})

    unsupported = SCRATCH / "TVROB_unsupported.txt"
    unsupported.write_text("this is not audio", encoding="utf-8")
    cases.append({"name": "unsupported_file", "path": unsupported, "tone": "2"})

    cases.append({"name": "missing_file", "path": SCRATCH / "TVROB_does_not_exist.wav",
                  "tone": "2"})

    nan_path = SCRATCH / "TVROB_nan.wav"
    sf.write(nan_path, np.full(int(0.3 * SAMPLE_RATE), np.nan, dtype=np.float32),
             SAMPLE_RATE, subtype="FLOAT")
    cases.append({"name": "nan_samples", "path": nan_path, "tone": "2"})

    inf_path = SCRATCH / "TVROB_inf.wav"
    sf.write(inf_path, np.full(int(0.3 * SAMPLE_RATE), np.inf, dtype=np.float32),
             SAMPLE_RATE, subtype="FLOAT")
    cases.append({"name": "inf_samples", "path": inf_path, "tone": "2"})

    return cases


def section_robustness(system, reference, t_pass, enabled) -> list[dict]:
    print("\n9. AUDIO INPUT ROBUSTNESS MATRIX")
    import soundfile as sf

    rows = []
    for case in build_robustness_cases(reference):
        entry = {"case": case["name"], "expected_tone": case["tone"],
                 "accepted_by_input_layer": "NO", "trajectory_available": "NO",
                 "processing_completed": "NO", "decision": "RETRY",
                 "failure_code": "", "exception": ""}
        try:
            audio, file_rate = sf.read(str(case["path"]), dtype="float32")
            entry["accepted_by_input_layer"] = "YES"
            entry["file_sample_rate"] = int(file_rate)
        except Exception as error:  # noqa: BLE001
            entry["exception"] = f"{type(error).__name__}"
            entry["failure_code"] = "unreadable_input"
            entry["decision_reason"] = "input_rejected"
            rows.append(entry)
            continue

        out = system.infer(audio, case["tone"], t_pass, enabled)
        entry.update(
            trajectory_available="YES" if out["trajectory_available"] else "NO",
            processing_completed="YES" if not out["exception"] else "NO",
            decision=out["decision"], failure_code=out["failure_code"],
            exception=out["exception"],
            decision_reason=out["decision_reason"],
            raw_score="" if not math.isfinite(out["raw_score"]) else f"{out['raw_score']:.6f}")
        rows.append(entry)

    unsafe = [r for r in rows
              if r["decision"] == "PASS"
              and (r["trajectory_available"] == "NO" or r["exception"])]
    record("audio robustness", "no malformed or unprocessable input ever yields PASS",
           "0 unsafe PASS", f"{len(unsafe)} unsafe PASS "
           f"({[r['case'] for r in unsafe]})", not unsafe, SEVERITY_BLOCKING)

    crashed = [r for r in rows if r["exception"] and r["decision"] != "RETRY"]
    record("audio robustness", "every exception path still resolves to a decision",
           "0 unresolved", f"{len(crashed)} unresolved", not crashed, SEVERITY_BLOCKING)

    for name in ("digital_silence", "empty_audio", "very_short_10ms",
                 "corrupted_file", "unsupported_file", "missing_file",
                 "nan_samples", "inf_samples", "white_noise_unvoiced"):
        row = next(r for r in rows if r["case"] == name)
        record("audio robustness", f"{name} resolves to RETRY",
               "RETRY", f"{row['decision']} ({row['failure_code'] or row.get('decision_reason','')})",
               row["decision"] == "RETRY", SEVERITY_BLOCKING)

    stereo = next(r for r in rows if r["case"] == "stereo_input")
    record("audio robustness", "stereo input is refused rather than mis-parsed",
           "RETRY, not PASS", f"{stereo['decision']} ({stereo['failure_code']})",
           stereo["decision"] == "RETRY", SEVERITY_HIGH)

    # Sample-rate handling: the chain reads the file and discards the declared
    # rate, then tells Praat the audio is 16 kHz whatever it really is.
    rate_rows = [r for r in rows if r["case"].startswith("sample_rate")]
    baseline = next(r for r in rows if r["case"] == "mono_16k")
    drifted = [r for r in rate_rows
               if r.get("raw_score", "") != baseline.get("raw_score", "")]
    record("input validation",
           "non-16 kHz input is rejected or resampled before pitch extraction",
           "the same speech at 8/44.1/48 kHz is refused or scored identically",
           f"{len(drifted)}/{len(rate_rows)} rates silently produce a different "
           f"score (16 kHz baseline {baseline.get('raw_score','')}; "
           + ", ".join(f"{r['case'][12:]}Hz={r.get('raw_score','') or 'RETRY'}"
                       for r in rate_rows) + ")",
           not drifted, SEVERITY_HIGH,
           "trajectory_from_segment hardcodes SAMPLE_RATE=16000 and every call "
           "site discards the rate returned by sf.read, so the declared rate is "
           "never checked against the frozen 16 kHz assumption")

    with (OUT_DIR / "audio_robustness_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        fields = ["case", "expected_tone", "file_sample_rate", "accepted_by_input_layer",
                  "trajectory_available", "processing_completed", "raw_score",
                  "decision", "decision_reason", "failure_code", "exception"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 12. Metamorphic robustness
# ===========================================================================

def voiced_span(audio) -> dict:
    """The voiced window the trajectory is time-normalised over."""
    import parselmouth

    try:
        pitch = parselmouth.Sound(
            np.asarray(audio, dtype=np.float64), SAMPLE_RATE).to_pitch(
            time_step=PITCH_STEP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
    except Exception:  # noqa: BLE001
        return {"n_voiced": 0, "span_ms": 0.0, "first_f0": None, "last_f0": None}
    frequencies = pitch.selected_array["frequency"]
    times = np.asarray(pitch.xs(), dtype=float)
    voiced = np.isfinite(frequencies) & (frequencies > 0)
    if int(voiced.sum()) < MIN_VOICED_FRAMES:
        return {"n_voiced": int(voiced.sum()), "span_ms": 0.0,
                "first_f0": None, "last_f0": None}
    voiced_times, voiced_values = times[voiced], frequencies[voiced]
    return {"n_voiced": int(voiced.sum()),
            "span_ms": float((voiced_times[-1] - voiced_times[0]) * 1000.0),
            "first_f0": float(voiced_values[0]), "last_f0": float(voiced_values[-1])}


def section_metamorphic(system, reference, t_pass, enabled) -> list[dict]:
    print("\n10. METAMORPHIC ROBUSTNESS (tolerances pre-registered above)")
    import soundfile as sf

    SCRATCH.mkdir(parents=True, exist_ok=True)
    rows = []
    subjects = [r for r in reference if r["centred"] is not None][:6]
    pad = np.zeros(int(0.1 * SAMPLE_RATE), dtype=np.float32)

    for item in subjects:
        base = system.infer(item["audio"], item["tone"], t_pass, enabled)
        base_span = voiced_span(item["audio"])
        variants = {
            "amplitude_x0.8": item["audio"] * 0.8,
            "amplitude_x1.2": item["audio"] * 1.2,
            "leading_silence_100ms": np.concatenate([pad, item["audio"]]),
            "trailing_silence_100ms": np.concatenate([item["audio"], pad]),
        }
        rewrite = SCRATCH / f"TVMETA_{item['token_id']}.wav"
        sf.write(rewrite, item["audio"], SAMPLE_RATE, subtype="PCM_16")
        variants["lossless_wav_rewrite"] = sf.read(str(rewrite), dtype="float32")[0]

        for name, samples in variants.items():
            out = system.infer(np.asarray(samples, dtype=np.float32), item["tone"],
                               t_pass, enabled)
            traj_delta = (float(np.max(np.abs(base["trajectory"] - out["trajectory"])))
                          if out["trajectory"] is not None else float("inf"))
            score_delta = (abs(base["raw_score"] - out["raw_score"])
                           if math.isfinite(out["raw_score"]) else float("inf"))
            span = voiced_span(samples)
            rows.append({
                "ref_id": item["ref_id"], "transformation": name,
                "trajectory_max_delta_st": traj_delta,
                "trajectory_tolerance_st": METAMORPHIC_TOLERANCE[name]["trajectory_st"],
                "score_delta": score_delta,
                "score_tolerance": METAMORPHIC_TOLERANCE[name]["score"],
                "baseline_decision": base["decision"], "variant_decision": out["decision"],
                "within_tolerance": (traj_delta <= METAMORPHIC_TOLERANCE[name]["trajectory_st"]
                                     and score_delta <= METAMORPHIC_TOLERANCE[name]["score"]),
                "decision_preserved": base["decision"] == out["decision"],
                # Mechanism instrumentation: the contour is time-normalised over
                # the voiced span, so any change to that span rescales it.
                "baseline_voiced_frames": base_span["n_voiced"],
                "variant_voiced_frames": span["n_voiced"],
                "baseline_span_ms": round(base_span["span_ms"], 1),
                "variant_span_ms": round(span["span_ms"], 1),
                "span_changed": abs(span["span_ms"] - base_span["span_ms"]) > 1e-9,
                "baseline_first_f0": base_span["first_f0"],
                "variant_first_f0": span["first_f0"],
            })

    for name in METAMORPHIC_TOLERANCE:
        subset = [r for r in rows if r["transformation"] == name]
        worst_traj = max(r["trajectory_max_delta_st"] for r in subset)
        worst_score = max(r["score_delta"] for r in subset)
        record("metamorphic", f"{name}: contour within pre-registered tolerance",
               f"<= {METAMORPHIC_TOLERANCE[name]['trajectory_st']} ST",
               f"worst {worst_traj:.6f} ST", all(r["within_tolerance"] for r in subset),
               SEVERITY_HIGH, f"worst score delta {worst_score:.6f} "
               f"(tolerance {METAMORPHIC_TOLERANCE[name]['score']})")
        record("metamorphic", f"{name}: PASS/RETRY decision preserved",
               "identical decisions", f"{sum(1 for r in subset if r['decision_preserved'])}"
               f"/{len(subset)} preserved",
               all(r["decision_preserved"] for r in subset) or not METAMORPHIC_DECISION_MUST_HOLD,
               SEVERITY_HIGH)

    # --- mechanism isolation ------------------------------------------------
    # Section 12 asks for large UNEXPLAINED sensitivity. The padding results are
    # explained: the contour is time-normalised over the voiced span, so the
    # sensitivity should appear if and only if the pitch tracker changes that
    # span. These two checks test exactly that claim.
    padding = [r for r in rows if "silence" in r["transformation"]]
    stable_span = [r for r in padding if not r["span_changed"]]
    moved_span = [r for r in padding if r["span_changed"]]

    worst_stable = max((r["trajectory_max_delta_st"] for r in stable_span), default=0.0)
    record("metamorphic", "padding with an unchanged voiced span leaves the contour intact",
           "<= 0.05 ST when the span does not move",
           f"{len(stable_span)}/{len(padding)} cases kept their span; "
           f"worst delta {worst_stable:.6f} ST",
           worst_stable <= 0.05, SEVERITY_HIGH,
           "isolates the mechanism: padding itself is harmless")

    worst_moved = max((r["trajectory_max_delta_st"] for r in moved_span), default=0.0)
    record("metamorphic", "every large padding deviation is accompanied by a span change",
           "no large deviation with a stable span",
           f"{len(moved_span)}/{len(padding)} cases changed span "
           f"(worst delta {worst_moved:.3f} ST); largest stable-span delta "
           f"{worst_stable:.6f} ST",
           worst_stable <= 0.05, SEVERITY_HIGH,
           "the sensitivity is fully attributable to voiced-span redetection, "
           "not to an arithmetic error in the trajectory code")

    grew = [r for r in moved_span if r["variant_voiced_frames"] > r["baseline_voiced_frames"]]
    record("metamorphic", "silence padding makes the pitch tracker report extra voiced frames",
           "documented mechanism",
           f"{len(grew)}/{len(moved_span)} span changes came from added voiced "
           f"frames (e.g. {grew[0]['baseline_voiced_frames']}->"
           f"{grew[0]['variant_voiced_frames']} frames, first F0 "
           f"{grew[0]['baseline_first_f0']:.0f}->{grew[0]['variant_first_f0']:.0f} Hz)"
           if grew else "no span growth observed",
           bool(grew), SEVERITY_INFO, diagnostic_only=True)

    with (OUT_DIR / "metamorphic_results.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 13. Synthetic tone shapes -- DIAGNOSTIC ONLY
# ===========================================================================

def synthesise(contour_hz, seconds=0.4) -> np.ndarray:
    """A simple voiced buzz whose F0 follows contour_hz(t), t in [0, 1]."""
    n = int(seconds * SAMPLE_RATE)
    t = np.linspace(0.0, 1.0, n)
    f0 = contour_hz(t)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    wave = sum((1.0 / k) * np.sin(k * phase) for k in (1, 2, 3, 4))
    envelope = np.minimum(1.0, np.minimum(t, 1.0 - t) * 20.0)
    return (0.3 * wave * envelope).astype(np.float32)


def section_synthetic(system, t_pass, enabled) -> list[dict]:
    print("\n11. SYNTHETIC CONTOURS (DIAGNOSTIC ONLY -- not pronunciation evidence)")
    shapes = {
        "level":   lambda t: np.full_like(t, 200.0),
        "rising":  lambda t: 150.0 * (2.0 ** (t * 0.6)),
        "dipping": lambda t: 180.0 * (2.0 ** (-0.5 * np.sin(np.pi * t) + 0.25 * t)),
        "falling": lambda t: 260.0 * (2.0 ** (-t * 0.9)),
    }
    rows = []
    for name, contour in shapes.items():
        audio = synthesise(contour)
        out = system.infer(audio, "2", t_pass, enabled)
        traj = out["trajectory"]
        rows.append({
            "shape": name,
            "trajectory_available": out["trajectory_available"],
            "n_points": None if traj is None else len(traj),
            "start_st": None if traj is None else float(traj[0]),
            "end_st": None if traj is None else float(traj[-1]),
            "net_change_st": None if traj is None else float(traj[-1] - traj[0]),
            "all_finite": None if traj is None else bool(np.all(np.isfinite(traj))),
        })
        record("trajectory", f"synthetic {name} contour: pipeline numerically stable",
               "20 finite points", f"{rows[-1]['n_points']} points, "
               f"net {rows[-1]['net_change_st']:.2f} ST"
               if traj is not None else "trajectory unavailable",
               traj is not None and len(traj) == N_POINTS and np.all(np.isfinite(traj)),
               SEVERITY_MEDIUM, "diagnostic: synthetic buzz is not a human production")

    monotone_ok = (rows[1]["net_change_st"] > 1.0 and rows[3]["net_change_st"] < -1.0
                   and abs(rows[0]["net_change_st"]) < 1.0)
    record("trajectory", "synthetic rising/level/falling map to the expected contour sign",
           "rising > 0, level ~ 0, falling < 0",
           ", ".join(f"{r['shape']}={r['net_change_st']:+.2f}" for r in rows),
           monotone_ok, SEVERITY_MEDIUM,
           "transformation sanity only; says nothing about learner accuracy")

    with (OUT_DIR / "synthetic_contours.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 14. Fail-safe behaviour
# ===========================================================================

def section_failsafe(system, reference, t_pass, enabled) -> None:
    print("\n12. FAIL-SAFE BEHAVIOUR")
    clean = next(r for r in reference if r["centred"] is not None)

    # Praat failure and insufficient voiced frames are exercised through the
    # real extractor rather than simulated.
    too_short = trajectory_from_segment(np.zeros(int(0.01 * SAMPLE_RATE), dtype=np.float32))
    record("fail-safe", "sub-30 ms audio is refused with a named reason",
           "(None, too_short_for_pitch)", f"({too_short[0]}, {too_short[1]})",
           too_short == (None, "too_short_for_pitch"), SEVERITY_HIGH)

    silence = trajectory_from_segment(np.zeros(int(0.3 * SAMPLE_RATE), dtype=np.float32))
    record("fail-safe", "insufficient voiced frames is refused with a named reason",
           "(None, insufficient_voiced_frames)", f"({silence[0]}, {silence[1]})",
           silence[0] is None and silence[1] == "insufficient_voiced_frames",
           SEVERITY_HIGH)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        nan_audio = trajectory_from_segment(
            np.full(int(0.3 * SAMPLE_RATE), np.nan, dtype=np.float32))
        inf_audio = trajectory_from_segment(
            np.full(int(0.3 * SAMPLE_RATE), np.inf, dtype=np.float32))
    record("fail-safe", "NaN-filled audio never yields a usable trajectory",
           "None", str(nan_audio[1]), nan_audio[0] is None, SEVERITY_BLOCKING)
    record("fail-safe", "Inf-filled audio never yields a usable trajectory",
           "None", str(inf_audio[1]), inf_audio[0] is None, SEVERITY_BLOCKING)

    for bad in (None, "", "5", "0", "T2", 2, 2.0, "  2  "):
        decision = decide(0.0, bad, True, t_pass, enabled)[0]
        record("fail-safe", f"invalid expected tone {bad!r} cannot PASS",
               "RETRY", decision, decision == "RETRY", SEVERITY_BLOCKING)

    missing = decide(0.0, None, False, t_pass, enabled)
    record("fail-safe", "missing expected tone with no trajectory is RETRY",
           "RETRY/trajectory_unavailable", f"{missing[0]}/{missing[1]}",
           missing == ("RETRY", "trajectory_unavailable"), SEVERITY_BLOCKING)

    # Model-artefact tamper detection: mutate a copy of the frozen file in
    # memory and confirm the integrity check would refuse it.
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    tampered = dict(frozen)
    tampered["decision_policy"] = dict(frozen["decision_policy"])
    tampered["decision_policy"]["t_pass"] = 0.9
    detected = sha256_json_without(tampered, "sha256") != tampered["sha256"]
    record("fail-safe", "a tampered threshold breaks the frozen self-hash",
           "hash mismatch detected", "detected" if detected else "NOT DETECTED",
           detected, SEVERITY_BLOCKING,
           "in-memory tamper only; the file on disk is untouched")

    record("fail-safe", "the frozen file on disk is still byte-identical after tamper test",
           json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"][:16],
           frozen["sha256"][:16],
           json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"] == frozen["sha256"],
           SEVERITY_BLOCKING)

    # A corrupted feature cache must stop the run, not score against garbage.
    bad_base = np.full((1, N_POINTS), np.nan)
    try:
        score = system.score_one(bad_base[0], "2")
        outcome = ("RETRY" if not math.isfinite(score)
                   else decide(score, "2", True, t_pass, enabled)[0])
        detail = f"score={score:.6f} -> {outcome}"
        safe = outcome == "RETRY" or not math.isfinite(score)
    except Exception as error:  # noqa: BLE001
        outcome, detail, safe = "EXCEPTION", f"{type(error).__name__}", True
    record("fail-safe", "an all-NaN trajectory reaching the scorer cannot PASS",
           "RETRY or hard failure", detail, safe, SEVERITY_BLOCKING,
           "the median imputer replaces NaN, so the guard must live upstream -- "
           "infer() rejects non-finite contours before scoring")


# ===========================================================================
# 15-16. Logging integrity and learner-output privacy
# ===========================================================================

REQUIRED_LOG_FIELDS = (
    "system_version", "system_sha256", "timestamp", "item_id", "expected_tone",
    "trajectory_available", "raw_score", "decision", "failure_reason",
    "processing_latency_ms",
)

LEARNER_FORBIDDEN = (
    "wrong", "incorrect", "instead of", "%", "score", "percent", "probability",
    "confidence", "tone 1", "tone 2", "tone 3", "tone 4", "t1", "t2", "t3", "t4",
    "error", "exception", "traceback",
)


def section_logging_privacy(system, reference, frozen, t_pass, enabled) -> list[dict]:
    print("\n13. LOGGING INTEGRITY AND LEARNER-OUTPUT PRIVACY")
    log_rows = []
    for item in reference[:6]:
        out = system.infer(item["audio"], item["tone"], t_pass, enabled)
        log_rows.append({
            "system_version": frozen["system_version"],
            "system_sha256": frozen["sha256"],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "item_id": item["ref_id"],
            "expected_tone": item["tone"],
            "trajectory_available": "YES" if out["trajectory_available"] else "NO",
            "raw_score": "" if not math.isfinite(out["raw_score"]) else f"{out['raw_score']:.6f}",
            "decision": out["decision"],
            "failure_reason": out["failure_code"],
            "processing_latency_ms": f"{out['latency_ms']:.1f}",
            "learner_message": PASS_MESSAGE if out["decision"] == "PASS" else RETRY_MESSAGE,
        })

    missing = [f for f in REQUIRED_LOG_FIELDS if f not in log_rows[0]]
    record("logging", "every required research-log field is present",
           f"{len(REQUIRED_LOG_FIELDS)} fields", f"missing: {missing or 'none'}",
           not missing, SEVERITY_HIGH)

    record("logging", "internal raw score is retained in the research log",
           "present for scored trials",
           f"{sum(1 for r in log_rows if r['raw_score'])}/{len(log_rows)} rows carry a score",
           any(r["raw_score"] for r in log_rows), SEVERITY_MEDIUM)

    identifying = ("participant", "name", "email", "student", "speaker_id")
    leaked = [f for f in log_rows[0] for token in identifying if token in f.lower()]
    record("privacy", "technical inference requires no participant-identifying field",
           "no identifying field in the log schema", str(leaked or "none"),
           not leaked, SEVERITY_HIGH)

    messages = {r["learner_message"] for r in log_rows}
    record("privacy", "learner-facing output is one of exactly two frozen messages",
           "{PASS_MESSAGE, RETRY_MESSAGE}", f"{len(messages)} distinct message(s)",
           messages <= {PASS_MESSAGE, RETRY_MESSAGE}, SEVERITY_BLOCKING)

    violations = sorted({term for message in messages for term in LEARNER_FORBIDDEN
                         if term in message.lower()})
    record("privacy", "no forbidden term appears in a learner-facing message",
           "no forbidden term", str(violations or "clean"), not violations,
           SEVERITY_BLOCKING)

    record("privacy", "no digit reaches a learner-facing message",
           "no digits", str([m for m in messages if any(c.isdigit() for c in m)] or "clean"),
           not any(any(c.isdigit() for c in m) for m in messages), SEVERITY_BLOCKING)

    forbidden_outputs = [w.lower() for w in frozen["decision_policy"]["forbidden_outputs"]]
    emitted = {r["decision"] for r in log_rows}
    record("privacy", "no forbidden verdict label is emitted",
           str(frozen["decision_policy"]["outputs"]), str(sorted(emitted)),
           emitted <= set(frozen["decision_policy"]["outputs"])
           and not any(f in " ".join(emitted).lower() for f in forbidden_outputs),
           SEVERITY_BLOCKING)

    # Static scan: is there any other learner-facing surface for this system?
    consumers = sorted(
        p.name for p in HERE.glob("*.py")
        if "PASS_MESSAGE" in p.read_text(encoding="utf-8")
        or "learner_message" in p.read_text(encoding="utf-8"))
    record("privacy", "learner-facing message surfaces are enumerated",
           "every producer of a learner message is known", ", ".join(consumers),
           bool(consumers), SEVERITY_INFO,
           "OMPAL_R2_PASS_v1 has no HTTP route and no UI binding yet; the only "
           "learner-facing strings are these two constants")

    with (OUT_DIR / "logging_sample.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(log_rows[0].keys()))
        writer.writeheader()
        writer.writerows(log_rows)
    return log_rows


# ===========================================================================
# 17-18. Runtime smoke test and stress test
# ===========================================================================

def section_runtime(system, reference, t_pass, enabled, cold_seconds, stress_calls) -> dict:
    print("\n14. RUNTIME SMOKE TEST")
    latencies, successes, safe_retry, hard_failures = [], 0, 0, 0
    first_call = None
    for index, item in enumerate(reference):
        out = system.infer(item["audio"], item["tone"], t_pass, enabled)
        if index == 0:
            first_call = out["latency_ms"]
        latencies.append(out["latency_ms"])
        if out["exception"]:
            hard_failures += 1
        elif out["trajectory_available"]:
            successes += 1
        else:
            safe_retry += 1

    values = np.asarray(latencies)
    runtime = {
        "n_files": len(reference), "processing_successes": successes,
        "safe_retry": safe_retry, "hard_failures": hard_failures,
        "model_cold_start_seconds": cold_seconds,
        "first_inference_ms": first_call,
        "warm_median_ms": float(np.median(values[1:])) if len(values) > 1 else None,
        "median_ms": float(np.median(values)),
        "iqr_ms": [float(np.percentile(values, 25)), float(np.percentile(values, 75))],
        "p95_ms": float(np.percentile(values, 95)),
        "latency_scope": ("pre-extracted single-token audio already on disk; this "
                          "is NOT an end-user latency estimate -- it excludes "
                          "capture, upload, forced alignment and token segmentation"),
    }
    record("runtime", "technical reference batch completes without hard failure",
           "0 hard failures", f"{hard_failures} hard failures, {successes} scored, "
           f"{safe_retry} safe RETRY", hard_failures == 0, SEVERITY_HIGH)
    record("runtime", "latency is reported, not used as a pass criterion",
           "reported", f"median {runtime['median_ms']:.1f} ms, p95 "
           f"{runtime['p95_ms']:.1f} ms, cold start {cold_seconds:.1f} s",
           True, SEVERITY_INFO, runtime["latency_scope"])

    print(f"\n15. STRESS TEST ({stress_calls} inference calls)")
    tracemalloc.start()
    gc.collect()
    start_snapshot = tracemalloc.take_snapshot()
    baseline_hash = system.coefficient_hash()
    baseline_decisions = [system.infer(i["audio"], i["tone"], t_pass, enabled)["decision"]
                          for i in reference]

    crashes, instability, resource_errors = 0, 0, 0
    started = time.perf_counter()
    for call in range(stress_calls):
        item = reference[call % len(reference)]
        try:
            out = system.infer(item["audio"], item["tone"], t_pass, enabled)
            if out["decision"] != baseline_decisions[call % len(reference)]:
                instability += 1
            if out["exception"]:
                crashes += 1
        except OSError:
            resource_errors += 1
        except Exception:  # noqa: BLE001
            crashes += 1
    elapsed = time.perf_counter() - started
    end_snapshot = tracemalloc.take_snapshot()
    growth = sum(s.size_diff for s in end_snapshot.compare_to(start_snapshot, "filename"))
    tracemalloc.stop()

    record("stress", f"{stress_calls} calls complete without a crash",
           "0 crashes", f"{crashes} crashes", crashes == 0, SEVERITY_BLOCKING)
    record("stress", "no decision instability under repeated load",
           "0 changed decisions", f"{instability} changed", instability == 0,
           SEVERITY_BLOCKING)
    record("stress", "no file-handle or resource error",
           "0 resource errors", f"{resource_errors}", resource_errors == 0,
           SEVERITY_HIGH)
    record("stress", "model is not silently reloaded during the run",
           baseline_hash[:16], system.coefficient_hash()[:16],
           system.coefficient_hash() == baseline_hash, SEVERITY_BLOCKING)
    record("stress", "frozen system hash is unchanged after the stress run",
           EXPECTED_SYSTEM_HASH_PREFIX,
           json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"][:16],
           json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"].startswith(
               EXPECTED_SYSTEM_HASH_PREFIX), SEVERITY_BLOCKING)
    record("stress", "python heap growth over the stress run is bounded",
           "< 32 MB", f"{growth / 1e6:.2f} MB", abs(growth) < 32e6, SEVERITY_MEDIUM)

    runtime.update({
        "stress_calls": stress_calls, "stress_seconds": elapsed,
        "stress_crashes": crashes, "stress_decision_instability": instability,
        "stress_resource_errors": resource_errors,
        "stress_heap_growth_bytes": int(growth),
        "stress_calls_per_second": stress_calls / elapsed if elapsed else None,
    })
    return runtime


# ===========================================================================
# 24. OMPAL Test seal
# ===========================================================================

def section_test_seal() -> dict:
    print("\n16. OMPAL TEST SEAL")
    result = subprocess.run(
        [sys.executable, "-m", "pronunciation.wav2vec_tone.verify_ompal_test_seal"],
        cwd=str(HERE.parents[1]), capture_output=True, text=True, timeout=600)
    output = result.stdout + result.stderr
    sealed = result.returncode == 0
    record("artifact integrity", "independent OMPAL Test seal verifier reports SEALED",
           "exit 0", f"exit {result.returncode}", sealed, SEVERITY_BLOCKING,
           "authority: verify_ompal_test_seal.py")

    cache = dict(np.load(CACHE, allow_pickle=True))
    test_in_cache = int((np.asarray(cache["split"]) == "test").sum())
    record("artifact integrity", "no Test-split row is present in the feature cache",
           "0 rows", f"{test_in_cache} rows", test_in_cache == 0, SEVERITY_BLOCKING)

    reference_ids = {r["ref_id"] for r in []}  # placeholder, filled by caller
    manifest = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    test_tokens = {r["token_id"] for r in manifest if r["split"] == "test"}
    record("artifact integrity", "Test split still exists in the manifest (sealed, not deleted)",
           "322 test rows defined", f"{len(test_tokens)} test rows",
           len(test_tokens) == 322, SEVERITY_HIGH)

    return {"sealed": sealed, "test_rows_in_cache": test_in_cache,
            "test_rows_in_manifest": len(test_tokens),
            "verifier_exit_code": result.returncode,
            "verifier_tail": output.strip().splitlines()[-3:] if output.strip() else []}


def assert_reference_excludes_test(reference) -> None:
    manifest = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    test_tokens = {r["token_id"] for r in manifest if r["split"] == "test"}
    overlap = {r["token_id"] for r in reference} & test_tokens
    record("artifact integrity", "technical reference set contains no Test token",
           "0 overlap", f"{len(overlap)} overlapping tokens", not overlap,
           SEVERITY_BLOCKING,
           "reference set is drawn from native_reference only")


# ===========================================================================
# 19. Golden-reference regression file
# ===========================================================================

def write_golden_reference(system, reference, frozen, integrity, t_pass,
                           enabled, operator) -> dict:
    entries = []
    for item in reference:
        out = system.infer(item["audio"], item["tone"], t_pass, enabled)
        entries.append({
            "audio_reference_id": item["ref_id"],
            "token_id": item["token_id"],
            "audio_path": str(item["path"].relative_to(DATA_DIR)).replace("\\", "/"),
            "split": "native_reference",
            "expected_tone": item["tone"],
            "expected_trajectory_sha256": (
                None if out["trajectory"] is None
                else sha256_array(np.round(out["trajectory"], 9))),
            "expected_trajectory_tolerance_st": 1e-9,
            "expected_raw_score": (None if not math.isfinite(out["raw_score"])
                                   else round(out["raw_score"], 12)),
            "expected_raw_score_tolerance": 1e-9,
            "expected_decision": out["decision"],
            "expected_failure_status": out["failure_code"] or None,
        })

    golden = {
        "_note": ("Technical regression fixture for OMPAL_R2_PASS_v1. Non-Test, "
                  "non-validation material only (OMPAL native_reference tokens). "
                  "Expected values describe what the FROZEN implementation does "
                  "today; they are not correctness labels for pronunciation."),
        "system_version": frozen["system_version"],
        "system_sha256": frozen["sha256"],
        "t_pass": t_pass,
        "pass_comparison_operator": f"score {operator} t_pass",
        "score_semantics": "P(incorrect); LOW scores PASS",
        "enabled_pass_tones": sorted(enabled),
        "design_columns": EXPECTED_DESIGN_COLUMNS,
        "design_column_names": DESIGN_COLUMN_NAMES,
        "model_coefficient_sha256": system.coefficient_hash(),
        "training_input_hashes": integrity["training_hashes"],
        "config_model_hash": integrity["config_model_hash"],
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "contains_ompal_test_material": False,
        "entries": entries,
    }
    (OUT_DIR / "golden_reference.json").write_text(
        json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf-8")

    record("artifact integrity", "golden regression fixture written and self-consistent",
           f"{len(entries)} entries, no Test material",
           f"{len(entries)} entries, {sum(1 for e in entries if e['expected_decision'] == 'PASS')} PASS",
           len(entries) == len(reference) and not golden["contains_ompal_test_material"],
           SEVERITY_MEDIUM)
    return golden


# ===========================================================================
# Reports
# ===========================================================================

def write_matrix() -> None:
    with (OUT_DIR / "verification_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "test_id", "category", "input", "expected_behaviour",
            "observed_behaviour", "result", "severity", "notes"])
        writer.writeheader()
        writer.writerows(matrix)


def acceptance(summary: dict) -> tuple[list[dict], list[dict]]:
    """The ten acceptance criteria of the Phase TV brief, evaluated one by one.

    Metamorphic sensitivity and input-validation gaps are deliberately NOT
    folded in here: the brief lists the criteria explicitly and neither appears
    among them. They are reported separately as findings that must be disclosed
    rather than silently absorbed into a green verdict.
    """
    failures = [r for r in matrix if r["result"] == "FAIL"]

    def clean(*categories) -> bool:
        return not [r for r in failures if r["category"] in categories]

    criteria = [
        ("frozen hashes match", clean("artifact integrity")),
        ("0 policy violations", clean("policy", "threshold")),
        ("0 unsafe PASS from malformed or unprocessable input",
         summary["unsafe_pass_count"] == 0 and clean("audio robustness")),
        ("0 decision nondeterminism on identical inputs",
         summary["determinism"]["decision_changes"] == 0 and clean("determinism")),
        ("feature ordering exactly matches the frozen definition",
         clean("dimensionality")),
        ("expected-tone routing verified", clean("tone routing")),
        ("trajectory implementation verified", clean("trajectory")),
        ("no learner-facing raw-score leak", clean("privacy")),
        ("technical reference batch completes without unexplained failures",
         summary["runtime"]["hard_failures"] == 0),
        ("stress test shows no decision instability",
         summary["runtime"]["stress_decision_instability"] == 0 and clean("stress")),
    ]
    evaluated = [{"criterion": name, "met": bool(ok)} for name, ok in criteria]
    disclosed = [{"test_id": r["test_id"], "category": r["category"],
                  "severity": r["severity"], "finding": r["input"],
                  "observed": r["observed_behaviour"]}
                 for r in failures
                 if r["category"] in ("metamorphic", "input validation")]
    return evaluated, disclosed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true",
                        help="fewer repetitions and stress calls (smoke run)")
    parser.add_argument("--child-scores", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child_scores:
        child_scores_mode()
        return

    repetitions = 3 if args.quick else DETERMINISM_REPETITIONS
    stress_calls = 40 if args.quick else STRESS_CALLS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    print("=" * 78)
    print("PHASE TV -- FROZEN-SYSTEM TECHNICAL VERIFICATION")
    print("OMPAL_R2_PASS_v1 -- implementation only; NOT a validity study")
    print("=" * 78)

    integrity = section_artifact_integrity()
    frozen = integrity["frozen"]
    t_pass = frozen["decision_policy"]["t_pass"]
    enabled = {t.replace("T", "") for t in frozen["decision_policy"]["enabled_pass_tones"]}
    print(f"  system {frozen['system_version']}  t_pass={t_pass}  "
          f"enabled={sorted(enabled)}")

    cold_started = time.perf_counter()
    system = DeployedSystem()
    cold_seconds = time.perf_counter() - cold_started
    print(f"  deployed model fitted in {cold_seconds:.1f} s "
          f"({system.n_columns} design columns)")

    reference = build_reference_set(system)
    print(f"  technical reference set: {len(reference)} native-reference tokens")
    assert_reference_excludes_test(reference)

    section_deployment_equivalence(system, reference)
    section_policy(t_pass, enabled)
    operator = section_threshold(t_pass, enabled)
    determinism = section_determinism(system, reference, t_pass, enabled, repetitions)
    section_restart(determinism["baseline"], system)
    section_trajectory(system, reference)
    section_tone_routing(system, reference, t_pass, enabled)
    robustness = section_robustness(system, reference, t_pass, enabled)
    metamorphic = section_metamorphic(system, reference, t_pass, enabled)
    synthetic = section_synthetic(system, t_pass, enabled)
    section_failsafe(system, reference, t_pass, enabled)
    logging_rows = section_logging_privacy(system, reference, frozen, t_pass, enabled)
    runtime = section_runtime(system, reference, t_pass, enabled, cold_seconds,
                              stress_calls)
    seal = section_test_seal()
    golden = write_golden_reference(system, reference, frozen, integrity, t_pass,
                                    enabled, operator)

    write_matrix()

    total = len(matrix)
    failed = sum(1 for r in matrix if r["result"] == "FAIL")
    diagnostic = sum(1 for r in matrix if r["result"] == "DIAGNOSTIC")
    summary = {
        "phase": "TV",
        "title": "frozen-system technical verification",
        "system_version": frozen["system_version"],
        "system_sha256": frozen["sha256"],
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scope_statement": (
            "Technical verification of the frozen implementation only. A PASS "
            "here supports 'the frozen implementation behaves as specified'. It "
            "does NOT establish pronunciation-assessment validity for real "
            "learners; human criterion validation remains required."),
        "human_validation_status": "POSTPONED BY THE RESEARCHER; no recruitment performed",
        "t_pass": t_pass,
        "pass_comparison_operator": f"score {operator} t_pass",
        "enabled_pass_tones": sorted(enabled),
        "determinism_repetitions": repetitions,
        "reference_set": [r["ref_id"] for r in reference],
        "counts": {"total": total, "passed": total - failed - diagnostic,
                   "failed": failed, "diagnostic": diagnostic},
        "determinism": {k: v for k, v in determinism.items() if k != "baseline"},
        "runtime": runtime,
        "metamorphic_tolerances_preregistered": METAMORPHIC_TOLERANCE,
        "metamorphic_worst": {
            name: max(r["trajectory_max_delta_st"] for r in metamorphic
                      if r["transformation"] == name)
            for name in METAMORPHIC_TOLERANCE},
        "robustness_cases": len(robustness),
        "unsafe_pass_count": sum(
            1 for r in robustness if r["decision"] == "PASS"
            and (r["trajectory_available"] == "NO" or r["exception"])),
        "synthetic_contours": synthetic,
        "logging_fields_present": list(logging_rows[0].keys()),
        "ompal_test": {
            "predictions": False, "scores": False, "metrics": False,
            "cache_contamination": seal["test_rows_in_cache"] > 0,
            "seal_verified_by": "verify_ompal_test_seal.py",
            "seal_exit_code": seal["verifier_exit_code"],
        },
        "golden_reference_entries": len(golden["entries"]),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    criteria, disclosed = acceptance(summary)
    unmet = [c["criterion"] for c in criteria if not c["met"]]
    summary["acceptance_criteria"] = criteria
    summary["acceptance_criteria_unmet"] = unmet
    summary["findings_requiring_disclosure"] = disclosed
    summary["technical_verification_result"] = (
        "FROZEN SYSTEM TECHNICALLY VERIFIED" if not unmet
        else "TECHNICAL VERIFICATION FAILED")

    (OUT_DIR / "technical_verification_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"checks: {total - failed - diagnostic}/{total - diagnostic} passed "
          f"({diagnostic} diagnostic)")
    if failed:
        print("\nFAILED CHECKS")
        for row in matrix:
            if row["result"] == "FAIL":
                print(f"  {row['test_id']} [{row['severity']}] {row['input']}")
                print(f"      expected {row['expected_behaviour']} | "
                      f"observed {row['observed_behaviour']}")
    print("\nACCEPTANCE CRITERIA")
    for entry in criteria:
        print(f"  [{'MET ' if entry['met'] else 'UNMET'}] {entry['criterion']}")

    if disclosed:
        print("\nFINDINGS REQUIRING DISCLOSURE "
              "(outside the acceptance criteria, not waived)")
        for entry in disclosed:
            print(f"  {entry['test_id']} [{entry['severity']}] {entry['finding']}")
            print(f"      {entry['observed']}")

    print(f"\nresult: {summary['technical_verification_result']}")
    if unmet:
        print("unmet acceptance criteria: " + "; ".join(unmet))
    print(f"artefacts: {OUT_DIR}")
    print("\nThis does NOT establish pronunciation-assessment validity for real")
    print("learners. Human criterion validation remains required.")


if __name__ == "__main__":
    main()
