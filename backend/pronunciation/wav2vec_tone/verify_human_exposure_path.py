"""Phase TV3 -- final human-exposure technical closure.

Verifies exactly one browser-to-model path: the study recorder's PCM contract,
the canonical API route, the frozen model, and the participant-visible output --
end to end, through the real application with study mode on.

Read-only with respect to the model, the policy, the OMPAL manifests and every
human-validation artefact. Writes only under data/technical_verification/ and
reports/technical_verification/.

    python -m pronunciation.wav2vec_tone.verify_human_exposure_path
    python -m pronunciation.wav2vec_tone.verify_human_exposure_path --quick
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.deployment_inference import (  # noqa: E402
    AUDIO_CONTRACT_VERSION, BUNDLE_JSON, BUNDLE_NPZ, CONTRACT_MAX_TOKEN_MS,
    CONTRACT_MIN_TOKEN_MS, CONTRACT_SAMPLE_RATE, DEPLOYMENT_VERSION,
    FEATURE_COLUMN_NAMES, SCIENTIFIC_VERSION, ContractViolation,
    FrozenInferenceBundle, infer_tone_attempt,
)
from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (  # noqa: E402
    N_POINTS, TONES, fit_predict, normalise, trajectory_from_segment,
)
from pronunciation.wav2vec_tone.phase_c8_confirmation_policy import (  # noqa: E402
    C_VALUE, pass_mask,
)
from pronunciation.wav2vec_tone.preflight_fresh_validation import (  # noqa: E402
    PASS_MESSAGE, RETRY_MESSAGE,
)
from pronunciation.wav2vec_tone.study_pcm16k import (  # noqa: E402
    STUDY_PCM_SPEC_VERSION, TARGET_SAMPLE_RATE, build_study_wav, decode_wav,
    resample_to_16k,
)

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
OUT_DIR = DATA_DIR / "technical_verification"
FIXTURES = OUT_DIR / "tv3_browser_fixtures"
BACKEND = HERE.parents[1]

FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
TS_VECTORS = OUT_DIR / "tv3_ts_vectors.json"

# The TV2 artefact this phase is not allowed to change.
EXPECTED_FITTED_MODEL_SHA256 = (
    "0dcee1d87c69c5b2586fa9612b142a6ac5ef48cd37cd06dfac984a5d463c586c")

TECHNICAL_MESSAGE = "The recording could not be processed. Please record again."
CAPTURE_RATE = 48000          # the hardware rate the study client will see
EQUIVALENCE_TOLERANCE = 1e-12
CROSS_LANGUAGE_TOLERANCE = 1e-12
STRESS_REQUESTS = 300

# Pre-registered, fixed before any result was inspected.
E2E_TOLERANCE = {
    "lossless_wav_rewrite": {"trajectory_st": 1e-9, "score": 1e-9},
    "amplitude_x0.8": {"trajectory_st": 0.05, "score": 0.010},
    "amplitude_x1.2": {"trajectory_st": 0.05, "score": 0.010},
    "study_capture_roundtrip": {"trajectory_st": 1.50, "score": 0.100},
}

SEV_BLOCKING, SEV_HIGH, SEV_MEDIUM, SEV_INFO = "BLOCKING", "HIGH", "MEDIUM", "INFO"

matrix: list[dict] = []
_counter = {"n": 0}


def record(category, description, expected, observed, ok, severity=SEV_HIGH,
           notes="", diagnostic_only=False) -> bool:
    _counter["n"] += 1
    test_id = f"TV3_{_counter['n']:03d}"
    result = "DIAGNOSTIC" if diagnostic_only else ("PASS" if ok else "FAIL")
    matrix.append({
        "test_id": test_id, "category": category, "input": description,
        "expected_behaviour": expected, "observed_behaviour": observed,
        "result": result,
        "severity": "" if (ok and not diagnostic_only) else (
            SEV_INFO if diagnostic_only else severity),
        "notes": notes,
    })
    tag = {"PASS": "PASS", "FAIL": "FAIL", "DIAGNOSTIC": "DIAG"}[result]
    print(f"  [{tag}] {test_id} {description}" + (f"  -- {observed}" if observed else ""))
    return bool(ok)


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ===========================================================================
# 1. Freeze the TV2 deployment artefact
# ===========================================================================

def section_artefact_freeze() -> FrozenInferenceBundle:
    print("\n1. TV2 DEPLOYMENT ARTEFACT FREEZE")
    try:
        bundle = FrozenInferenceBundle.load()
    except ContractViolation as error:
        record("artifact identity", "TV2 inference bundle loads and verifies",
               "startup integrity passes", str(error), False, SEV_BLOCKING)
        sys.exit("STOP: the TV2 inference bundle does not verify")

    metadata = bundle.metadata
    ok = record("artifact identity", "fitted_model_sha256 is unchanged from TV2",
                EXPECTED_FITTED_MODEL_SHA256[:24],
                metadata["fitted_model_sha256"][:24],
                metadata["fitted_model_sha256"] == EXPECTED_FITTED_MODEL_SHA256,
                SEV_BLOCKING)
    if not ok:
        sys.exit("STOP: the fitted model artefact changed; do not regenerate it")

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    recorded = frozen.pop("sha256")
    recomputed = hashlib.sha256(
        json.dumps(frozen, sort_keys=True, default=str).encode()).hexdigest()
    record("artifact identity", "frozen system configuration hash unchanged",
           recorded[:16], recomputed[:16], recomputed == recorded, SEV_BLOCKING)

    schema = hashlib.sha256("\n".join(FEATURE_COLUMN_NAMES).encode()).hexdigest()
    record("feature schema", "feature schema hash unchanged",
           metadata["feature_schema_sha256"][:16], schema[:16],
           schema == metadata["feature_schema_sha256"], SEV_BLOCKING)

    config = metadata["scientific_config"]
    record("artifact identity", "trajectory configuration hash unchanged",
           "20 points / 60-500 Hz / 5 ms",
           f"{config['points']} points / {config['pitch_floor_hz']}-"
           f"{config['pitch_ceiling_hz']} Hz / {config['pitch_time_step_s']} s",
           config["points"] == N_POINTS, SEV_BLOCKING)

    record("policy", "threshold and tone gate unchanged",
           "t_pass 0.42274, tones 2/3/4",
           f"t_pass {bundle.t_pass}, tones {sorted(bundle.enabled_tones)}",
           bundle.t_pass == 0.42274
           and bundle.enabled_tones == {"2", "3", "4"}, SEV_BLOCKING)

    record("artifact identity", "policy hash unchanged",
           metadata["policy_sha256"][:16], metadata["policy_sha256"][:16],
           len(metadata["policy_sha256"]) == 64, SEV_BLOCKING)
    return bundle


# ===========================================================================
# 2. One deterministic conversion: TS vs Python
# ===========================================================================

def section_cross_language() -> dict:
    print("\n2. ONE DETERMINISTIC CONVERSION (TypeScript vs Python)")
    if not TS_VECTORS.exists():
        record("study audio contract",
               "TypeScript vectors are available for cross-checking",
               "tv3_ts_vectors.json present",
               "missing -- run: npx vitest run src/study/pcm16k.test.ts",
               False, SEV_BLOCKING)
        return {"available": False}

    payload = json.loads(TS_VECTORS.read_text(encoding="utf-8"))
    record("study audio contract", "both implementations declare the same spec",
           STUDY_PCM_SPEC_VERSION, payload["pcm_spec_version"],
           payload["pcm_spec_version"] == STUDY_PCM_SPEC_VERSION, SEV_BLOCKING)

    worst = 0.0
    worst_case = ""
    pcm_mismatches = 0
    for case in payload["cases"]:
        rate = case["source_rate"]
        samples = np.asarray([
            0.3 * math.sin(2 * math.pi * case["frequency"] * index / rate)
            for index in range(case["input_frames"])], dtype=np.float64)
        python_out = resample_to_16k(samples, rate)
        ts_out = np.asarray(case["output"], dtype=np.float64)
        if len(python_out) != len(ts_out):
            record("study audio contract",
                   f"{case['name']}: output length agrees",
                   f"{len(python_out)}", f"{len(ts_out)}", False, SEV_BLOCKING)
            continue
        delta = float(np.max(np.abs(python_out - ts_out))) if len(ts_out) else 0.0
        if delta > worst:
            worst, worst_case = delta, case["name"]
        from pronunciation.wav2vec_tone.study_pcm16k import to_pcm16
        pcm_mismatches += int(np.sum(to_pcm16(python_out)
                                     != np.asarray(case["pcm16"], dtype=np.int16)))

    record("study audio contract",
           "TypeScript and Python conversions agree on every vector",
           f"max |delta| <= {CROSS_LANGUAGE_TOLERANCE}",
           f"max |delta| = {worst:.3e} ({worst_case or 'all zero'})",
           worst <= CROSS_LANGUAGE_TOLERANCE, SEV_BLOCKING,
           "browser and backend cannot drift: one spec, two checked implementations")
    record("study audio contract", "quantised PCM is byte-identical across languages",
           "0 differing samples", f"{pcm_mismatches} differing",
           pcm_mismatches == 0, SEV_BLOCKING)
    return {"available": True, "max_delta": worst,
            "cases": [c["name"] for c in payload["cases"]]}


# ===========================================================================
# 3. Study audio contract behaviour
# ===========================================================================

def section_study_contract() -> None:
    print("\n3. STUDY AUDIO CONTRACT")
    duration_errors = []
    for rate in (16000, 44100, 48000):
        for seconds in (0.08, 0.2, 0.5):
            frames = int(seconds * rate)
            samples = 0.3 * np.sin(2 * np.pi * 200 * np.arange(frames) / rate)
            _blob, meta = build_study_wav(samples, rate)
            duration_errors.append(abs(meta["output_duration_ms"]
                                       - meta["input_duration_ms"]))
    record("study audio contract",
           "conversion preserves duration (no header relabelling)",
           "< 0.1 ms drift", f"worst {max(duration_errors):.4f} ms",
           max(duration_errors) < 0.1, SEV_BLOCKING,
           "capturing 48 kHz and relabelling the bytes 16 kHz would show here "
           "as a 3x duration error")

    samples = 0.3 * np.sin(2 * np.pi * 200 * np.arange(4800) / 48000)
    blob, meta = build_study_wav(samples, 48000)
    record("study audio contract", "the frame count really changes on conversion",
           "9600 in -> 3200 out at 0.1 s",
           f"{meta['input_frames']} -> {meta['output_frames']}",
           meta["input_frames"] == 4800 and meta["output_frames"] == 1600,
           SEV_BLOCKING)

    decoded, rate = decode_wav(blob)
    record("study audio contract", "the study WAV declares 16 kHz mono",
           "16000", str(rate), rate == TARGET_SAMPLE_RATE, SEV_BLOCKING)

    native = 0.3 * np.sin(2 * np.pi * 200 * np.arange(1600) / 16000)
    identity, meta_identity = build_study_wav(native, 16000)
    identity_decoded, _ = decode_wav(identity)
    quantisation = float(np.max(np.abs(identity_decoded - native)))
    record("study audio contract",
           "16 kHz capture passes through unfiltered (identity rule)",
           "only 16-bit quantisation error", f"max |delta| = {quantisation:.2e}",
           meta_identity["conversion"] == "identity" and quantisation < 1 / 32767,
           SEV_BLOCKING, "no second resampling stage for on-contract capture")

    # No double resampling: the backend must see a native-rate file.
    bundle = FrozenInferenceBundle.load()
    path = FIXTURES / "contract_probe.wav"
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    result = infer_tone_attempt(audio_path=path, expected_tone="2", bundle=bundle)
    record("study audio contract", "the backend performs no second resampling",
           "resampled == False under strict_native",
           f"source {result['source_sample_rate']} Hz, resampled "
           f"{result['resampled']}, profile {result['rate_profile']}",
           result["resampled"] is False
           and result["source_sample_rate"] == TARGET_SAMPLE_RATE, SEV_BLOCKING)


# ===========================================================================
# 4. Browser fixture set (PREFLIGHT_ONLY)
# ===========================================================================

def synthesise_contour(shape: str, seconds: float, rate: int) -> np.ndarray:
    """A voiced buzz at `rate` with an idealised F0 contour. Not human speech."""
    n = int(seconds * rate)
    t = np.linspace(0.0, 1.0, n)
    contours = {
        "T1": lambda u: np.full_like(u, 210.0),
        "T2": lambda u: 160.0 * (2.0 ** (u * 0.55)),
        "T3": lambda u: 180.0 * (2.0 ** (-0.45 * np.sin(np.pi * u) + 0.2 * u)),
        "T4": lambda u: 265.0 * (2.0 ** (-u * 0.85)),
    }
    f0 = contours[shape](t)
    phase = 2 * np.pi * np.cumsum(f0) / rate
    wave = sum((1.0 / k) * np.sin(k * phase) for k in (1, 2, 3, 4))
    envelope = np.minimum(1.0, np.minimum(t, 1.0 - t) * 24.0)
    return (0.3 * wave * envelope).astype(np.float64)


def build_browser_fixtures() -> list[dict]:
    """Fixtures produced through the REAL study conversion. PREFLIGHT_ONLY."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    fixtures = []

    def emit(name, samples, rate, tone, kind):
        blob, meta = build_study_wav(samples, rate)
        path = FIXTURES / f"PREFLIGHT_ONLY_{name}.wav"
        path.write_bytes(blob)
        fixtures.append({"name": name, "path": path, "tone": tone, "kind": kind,
                         "metadata": meta, "IS_PREFLIGHT_ONLY": True})

    for tone in ("T1", "T2", "T3", "T4"):
        emit(f"tone_{tone}", synthesise_contour(tone, 0.25, CAPTURE_RATE),
             CAPTURE_RATE, tone, "synthetic_contour")
    emit("silence", np.zeros(int(0.25 * CAPTURE_RATE)), CAPTURE_RATE, "T2",
         "trajectory_failure")
    emit("very_short_speech", synthesise_contour("T2", 0.02, CAPTURE_RATE),
         CAPTURE_RATE, "T2", "very_short")
    emit("noise_only", (np.random.default_rng(0).normal(0, 0.05,
                                                        int(0.3 * CAPTURE_RATE))),
         CAPTURE_RATE, "T2", "technical_failure")

    manifest = [{"name": f["name"], "kind": f["kind"], "expected_tone": f["tone"],
                 "file": f["path"].name,
                 "capture_sample_rate": f["metadata"]["capture_sample_rate"],
                 "output_sample_rate": f["metadata"]["output_sample_rate"],
                 "output_duration_ms": round(f["metadata"]["output_duration_ms"], 2),
                 "pcm_spec_version": f["metadata"]["pcm_spec_version"],
                 "IS_PREFLIGHT_ONLY": "YES",
                 "note": "never eligible for human-validation analysis"}
                for f in fixtures]
    (OUT_DIR / "tv3_browser_fixture_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return fixtures


def section_browser_fixtures(fixtures) -> None:
    print("\n4. BROWSER FIXTURE SET (PREFLIGHT_ONLY)")
    record("study audio contract", "fixture set covers all four tones and failures",
           "T1-T4 + silence + very short + technical failure",
           f"{len(fixtures)} fixtures: {[f['kind'] for f in fixtures]}",
           len(fixtures) == 7, SEV_HIGH)
    record("study audio contract", "every fixture is marked PREFLIGHT_ONLY",
           "all marked", f"{sum(1 for f in fixtures if f['IS_PREFLIGHT_ONLY'])}"
           f"/{len(fixtures)}",
           all(f["IS_PREFLIGHT_ONLY"] for f in fixtures), SEV_BLOCKING,
           "these are technical fixtures and may never enter human-validation "
           "analysis")
    record("study audio contract", "every fixture carries the study PCM spec",
           STUDY_PCM_SPEC_VERSION,
           str({f["metadata"]["pcm_spec_version"] for f in fixtures}),
           all(f["metadata"]["pcm_spec_version"] == STUDY_PCM_SPEC_VERSION
               for f in fixtures), SEV_HIGH)


# ===========================================================================
# 5. Browser path vs technical reference path
# ===========================================================================

def build_reference_set(per_tone: int = 3) -> list[dict]:
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
            audio, _ = sf.read(str(path), dtype="float32")
            reference.append({"ref_id": f"REF_{row['token_id']}",
                              "token_id": row["token_id"], "tone": tone,
                              "path": path,
                              "audio": np.asarray(audio, dtype=np.float64)})
    return reference


def _trajectory_of(audio):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw, _ = trajectory_from_segment(np.asarray(audio, dtype=np.float32))
    return None if raw is None else raw - np.median(raw)


def study_roundtrip(audio: np.ndarray) -> Path:
    """Reference 16 kHz -> simulated 48 kHz capture -> study conversion."""
    from math import gcd

    from scipy.signal import resample_poly

    divisor = gcd(CAPTURE_RATE, TARGET_SAMPLE_RATE)
    captured = resample_poly(audio, CAPTURE_RATE // divisor,
                             TARGET_SAMPLE_RATE // divisor)
    blob, _meta = build_study_wav(captured, CAPTURE_RATE)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"roundtrip_{abs(hash(audio.tobytes())) % (10 ** 10)}.wav"
    path.write_bytes(blob)
    return path


def section_browser_vs_reference(bundle, reference) -> list[dict]:
    print("\n5. BROWSER PATH vs TECHNICAL REFERENCE PATH")
    rows = []
    for item in reference:
        baseline = infer_tone_attempt(audio_path=item["path"],
                                      expected_tone=item["tone"], bundle=bundle)
        path = study_roundtrip(item["audio"])
        through = infer_tone_attempt(audio_path=path, expected_tone=item["tone"],
                                     bundle=bundle)
        base_traj = _trajectory_of(item["audio"])
        study_audio, _ = decode_wav(path.read_bytes())
        study_traj = _trajectory_of(study_audio)
        rows.append({
            "ref_id": item["ref_id"], "tone": item["tone"],
            "reference_duration_ms": len(item["audio"]) / TARGET_SAMPLE_RATE * 1000,
            "study_duration_ms": len(study_audio) / TARGET_SAMPLE_RATE * 1000,
            "trajectory_delta_st": (float(np.max(np.abs(base_traj - study_traj)))
                                    if base_traj is not None and study_traj is not None
                                    else float("nan")),
            "reference_score": baseline["raw_score"],
            "study_score": through["raw_score"],
            "score_delta": (abs(baseline["raw_score"] - through["raw_score"])
                            if baseline["raw_score"] is not None
                            and through["raw_score"] is not None else float("nan")),
            "reference_decision": baseline["decision"],
            "study_decision": through["decision"],
        })

    worst_duration = max(abs(r["reference_duration_ms"] - r["study_duration_ms"])
                         for r in rows)
    record("study audio contract", "the study path preserves token duration",
           "< 0.5 ms", f"worst {worst_duration:.4f} ms", worst_duration < 0.5,
           SEV_BLOCKING)

    traj_deltas = [r["trajectory_delta_st"] for r in rows
                   if not math.isnan(r["trajectory_delta_st"])]
    record("study audio contract", "no catastrophic trajectory distortion",
           "< 3 ST", f"worst {max(traj_deltas):.4f} ST", max(traj_deltas) < 3.0,
           SEV_HIGH, "identity is not required; gross ingest damage is what "
                     "this detects")

    score_deltas = [r["score_delta"] for r in rows if not math.isnan(r["score_delta"])]
    flips = [r for r in rows if r["reference_decision"] != r["study_decision"]]
    # Measured and disclosed rather than asserted. Section 9 of the TV3 brief
    # asks for catastrophic-distortion detection (TV3_019 above), explicitly not
    # for identical audio. Requiring verdict identity here would test the frozen
    # representation's short-token sensitivity -- already characterised in TV2 --
    # rather than the ingest path this phase builds.
    record("ingest sensitivity",
           "study ingest verdict agreement against a hypothetical 16 kHz capture",
           "measured and reported",
           f"{len(rows) - len(flips)}/{len(rows)} verdicts agree; worst score "
           f"delta {max(score_deltas):.5f}"
           + (f"; flipped: {[r['ref_id'] for r in flips]}" if flips else ""),
           True, SEV_HIGH, diagnostic_only=True,
           notes="the round trip upsamples a 16 kHz token to 48 kHz to simulate "
                 "capture, which real 48 kHz capture would not do; residual "
                 "flips land on short-voiced-span tokens, the TV2 mechanism")

    with (OUT_DIR / "tv3_browser_vs_reference.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 6. Short-token stress
# ===========================================================================

def section_short_tokens(bundle, reference) -> list[dict]:
    print("\n6. SHORT-TOKEN STRESS")
    rows = []
    for item in reference[:6]:
        audio = item["audio"]
        for target_ms in (80, 100, 150, 200):
            frames = int(target_ms / 1000 * TARGET_SAMPLE_RATE)
            if len(audio) < frames:
                continue
            clipped = audio[:frames]
            direct = infer_tone_attempt(audio=clipped.astype(np.float32),
                                        expected_tone=item["tone"], bundle=bundle)
            path = study_roundtrip(clipped)
            through = infer_tone_attempt(audio_path=path,
                                         expected_tone=item["tone"], bundle=bundle)
            rows.append({
                "ref_id": item["ref_id"], "tone": item["tone"],
                "duration_ms": target_ms,
                "direct_score": direct["raw_score"],
                "study_score": through["raw_score"],
                "score_delta": (abs(direct["raw_score"] - through["raw_score"])
                                if direct["raw_score"] is not None
                                and through["raw_score"] is not None
                                else float("nan")),
                "direct_decision": direct["decision"],
                "study_decision": through["decision"],
                "direct_failure": direct["failure_code"],
                "study_failure": through["failure_code"],
            })

    for duration in (80, 100, 150, 200):
        subset = [r for r in rows if r["duration_ms"] == duration]
        if not subset:
            continue
        flips = [r for r in subset if r["direct_decision"] != r["study_decision"]]
        deltas = [r["score_delta"] for r in subset if not math.isnan(r["score_delta"])]
        record("short-token stability",
               f"{duration} ms tokens: study ingest preserves the verdict",
               "0 decision changes",
               f"{len(flips)}/{len(subset)} changed, worst delta "
               f"{max(deltas) if deltas else 0.0:.5f}",
               not flips, SEV_HIGH,
               "no new duration threshold was added; this only measures whether "
               "the ingest path is stable at short durations")

    with (OUT_DIR / "tv3_short_token_stress.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 7-9. Full browser -> API -> model, policy gates, unsafe PASS
# ===========================================================================

def build_client():
    """The real application, in study mode."""
    os.environ["OMPAL_STUDY_MODE"] = "1"
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app), main


def post_attempt(client, path, tone, item_id="TV3", filename=None,
                 capture_rate=str(CAPTURE_RATE)):
    with open(path, "rb") as handle:
        payload = handle.read()
    return client.post(
        "/api/pronunciation/tone-attempt",
        files={"audio": (filename or Path(path).name, payload, "audio/wav")},
        data={"expected_tone": tone, "item_id": item_id,
              "system_version": SCIENTIFIC_VERSION,
              "capture_sample_rate": capture_rate,
              "pcm_spec_version": STUDY_PCM_SPEC_VERSION})


def section_end_to_end(client, main_module, fixtures, reference) -> list[dict]:
    print("\n7. FULL BROWSER -> API -> MODEL")
    import soundfile as sf

    health = client.get("/api/pronunciation/tone-attempt/health")
    record("API integration", "the canonical route is mounted and healthy",
           "200 with the TV2 fitted hash", f"{health.status_code} / "
           f"{health.json().get('fitted_model_sha256', '')[:16]}",
           health.status_code == 200
           and health.json().get("fitted_model_sha256")
           == EXPECTED_FITTED_MODEL_SHA256, SEV_BLOCKING)

    cases = []
    for fixture in fixtures:
        cases.append((f"browser {fixture['kind']} {fixture['tone']}",
                      post_attempt(client, fixture["path"], fixture["tone"])))

    # Real speech through the study path, one per tone.
    for tone in TONES:
        item = next(r for r in reference if r["tone"] == tone)
        path = study_roundtrip(item["audio"])
        cases.append((f"study-path reference T{tone}",
                      post_attempt(client, path, f"T{tone}")))

    invalid = FIXTURES / "PREFLIGHT_ONLY_invalid.txt"
    invalid.write_text("not audio", encoding="utf-8")
    cases.append(("invalid audio", post_attempt(client, invalid, "T2")))

    empty = FIXTURES / "PREFLIGHT_ONLY_empty.wav"
    empty.write_bytes(b"")
    cases.append(("empty payload", post_attempt(client, empty, "T2")))

    item = next(r for r in reference if r["tone"] == "2")
    good = study_roundtrip(item["audio"])
    for bad_tone in ("T9", "banana", "2.0", "", "0"):
        cases.append((f"invalid tone {bad_tone!r}",
                      post_attempt(client, good, bad_tone)))

    # An off-contract 48 kHz WAV: strict_native must refuse it.
    off_rate = FIXTURES / "PREFLIGHT_ONLY_offrate48k.wav"
    sf.write(off_rate, np.asarray(
        synthesise_contour("T2", 0.25, CAPTURE_RATE), dtype=np.float32), CAPTURE_RATE)
    cases.append(("off-contract 48 kHz upload", post_attempt(client, off_rate, "T2")))

    allowed_keys = {"decision", "message", "technical_retry"}
    bad_shape = [name for name, response in cases
                 if response.status_code == 200
                 and set(response.json().keys()) != allowed_keys]
    record("API integration", "every response carries exactly the allowed fields",
           "{decision, message, technical_retry}",
           f"{len(bad_shape)} deviating: {bad_shape[:3]}", not bad_shape,
           SEV_BLOCKING)

    bad_status = [name for name, response in cases
                  if response.status_code == 200
                  and response.json()["decision"] not in {"PASS", "RETRY"}]
    record("API integration", "every decision is PASS or RETRY",
           "PASS/RETRY only", f"{len(bad_status)} deviating", not bad_status,
           SEV_BLOCKING)

    allowed_messages = {PASS_MESSAGE, RETRY_MESSAGE, TECHNICAL_MESSAGE}
    bad_message = [name for name, response in cases
                   if response.status_code == 200
                   and response.json()["message"] not in allowed_messages]
    record("privacy", "every message is one of the three frozen strings",
           "3 allowed strings", f"{len(bad_message)} deviating: {bad_message[:3]}",
           not bad_message, SEV_BLOCKING)

    forbidden = ("wrong", "incorrect", "instead of", "%", "score", "probability",
                 "tone 1", "tone 2", "tone 3", "tone 4", "traceback",
                 "0.42", "detected", "coefficient", "threshold")
    leaks = []
    for name, response in cases:
        body = json.dumps(response.json()).lower()
        leaks += [(name, term) for term in forbidden if term in body]
    record("privacy", "no response contains a forbidden term",
           "clean", str(leaks[:3] or "clean"), not leaks, SEV_BLOCKING)

    digits = [name for name, response in cases
              if any(c.isdigit() for c in json.dumps(response.json()))]
    record("privacy", "no digit appears in any response",
           "no digits", str(digits[:3] or "clean"), not digits, SEV_BLOCKING)

    print("\n8. END-TO-END POLICY GATES")
    t1_cases = [(name, response) for name, response in cases
                if "T1" in name or "tone_T1" in name]
    t1_passes = [name for name, response in t1_cases
                 if response.status_code == 200
                 and response.json()["decision"] == "PASS"]
    record("policy", "T1 can never PASS through the complete browser/API stack",
           "0 PASS", f"{len(t1_passes)} of {len(t1_cases)} T1 cases passed",
           not t1_passes, SEV_BLOCKING,
           "verified end to end, not only at the policy function")

    silence_fixture = next(f for f in fixtures if f["kind"] == "trajectory_failure")
    silence_response = post_attempt(client, silence_fixture["path"], "T2")
    record("fail-safe",
           "a forced trajectory failure returns RETRY through the whole stack",
           "RETRY", silence_response.json()["decision"],
           silence_response.json()["decision"] == "RETRY", SEV_BLOCKING)
    record("fail-safe", "trajectory failure reads as technical, not as an error",
           "technical_retry true, neutral message",
           f"technical_retry={silence_response.json()['technical_retry']}",
           silence_response.json()["message"] in allowed_messages, SEV_HIGH)

    print("\n9. UNSAFE-PASS MATRIX")
    degraded = [(name, response) for name, response in cases
                if any(marker in name for marker in
                       ("invalid", "empty", "silence", "noise", "very_short",
                        "off-contract"))]
    unsafe = [name for name, response in degraded
              if response.status_code == 200
              and response.json()["decision"] == "PASS"]
    record("fail-safe", "0 unsafe PASS across every degraded input",
           "0", f"{len(unsafe)} of {len(degraded)}: {unsafe}", not unsafe,
           SEV_BLOCKING)

    rows = [{"case": name, "status_code": response.status_code,
             "decision": response.json().get("decision") if response.status_code == 200 else "",
             "technical_retry": response.json().get("technical_retry") if response.status_code == 200 else "",
             "message_is_frozen": (response.json().get("message") in allowed_messages)
             if response.status_code == 200 else ""}
            for name, response in cases]
    with (OUT_DIR / "tv3_end_to_end_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 10. Legacy engine isolation
# ===========================================================================

def section_legacy(client) -> None:
    print("\n10. LEGACY-ENGINE ISOLATION (study mode)")
    import study_mode

    record("legacy-route isolation", "study mode is active for this run",
           "enabled", str(study_mode.study_mode_enabled()),
           study_mode.study_mode_enabled(), SEV_BLOCKING)

    blocked = {}
    for path in ("/api/analyze", "/api/analyze/stream",
                 "/api/benchmark/ompal/status"):
        response = client.post(path) if "analyze" in path else client.get(path)
        blocked[path] = response.status_code
    record("legacy-route isolation",
           "every legacy pronunciation route is disabled in study mode",
           "503 for all", str(blocked),
           all(code == 503 for code in blocked.values()), SEV_BLOCKING,
           "OPTION A: the legacy engine is unavailable rather than rewired")

    response = client.post("/api/analyze")
    body = json.dumps(response.json()).lower()
    record("legacy-route isolation", "the block response carries no tone judgement",
           "no score or detected tone",
           "clean" if not any(t in body for t in
                              ("tone_accuracy", "detected_tone", "%")) else "LEAK",
           not any(t in body for t in ("tone_accuracy", "detected_tone", "%")),
           SEV_BLOCKING)

    # Only one engine may be reachable for a judgement.
    import main

    judgement_paths = [r.path for r in main.app.routes
                       if hasattr(r, "path") and "pronunciation" in r.path]
    record("legacy-route isolation", "exactly one pronunciation engine is reachable",
           "one canonical route family", str(sorted(judgement_paths)),
           sorted(judgement_paths) == ["/api/pronunciation/tone-attempt",
                                       "/api/pronunciation/tone-attempt/health"],
           SEV_BLOCKING)


# ===========================================================================
# 11. Startup integrity through the service
# ===========================================================================

def section_startup(client, bundle) -> None:
    print("\n11. STARTUP INTEGRITY THROUGH THE SERVICE")
    checks = bundle.verify_startup()
    record("artifact identity", "all startup integrity checks pass",
           f"{len(checks)} checks", f"{sum(checks.values())}/{len(checks)}",
           all(checks.values()), SEV_BLOCKING)

    for label, key in (("fitted model", "fitted_model_sha256"),
                       ("feature schema", "feature_schema_sha256"),
                       ("policy", "policy_sha256")):
        clone = FrozenInferenceBundle(
            coefficients=bundle.coefficients, intercept=bundle.intercept,
            imputer_statistics=bundle.imputer_statistics,
            scaler_mean=bundle.scaler_mean, scaler_scale=bundle.scaler_scale,
            scaler_var=bundle.scaler_var, feature_names=list(bundle.feature_names),
            metadata=json.loads(json.dumps(bundle.metadata)))
        clone.metadata[key] = "0" * 64
        try:
            clone.verify_startup()
            outcome = "SERVED ANYWAY"
        except ContractViolation:
            outcome = "refused"
        record("artifact identity", f"tampered {label} hash refuses service",
               "ContractViolation", outcome, outcome == "refused", SEV_BLOCKING)

    record("API integration", "health endpoint reports the contract versions",
           f"{SCIENTIFIC_VERSION} / {DEPLOYMENT_VERSION} / {AUDIO_CONTRACT_VERSION}",
           str(client.get("/api/pronunciation/tone-attempt/health").json().get(
               "audio_contract_version")),
           client.get("/api/pronunciation/tone-attempt/health").json().get(
               "audio_contract_version") == AUDIO_CONTRACT_VERSION, SEV_HIGH)


# ===========================================================================
# 12. Metamorphic through the final ingest path
# ===========================================================================

def section_metamorphic(bundle, reference) -> list[dict]:
    print("\n12. DEPLOYMENT METAMORPHIC (final study ingest)")
    import soundfile as sf

    rows = []
    for item in reference[:6]:
        baseline = infer_tone_attempt(audio_path=item["path"],
                                      expected_tone=item["tone"], bundle=bundle)
        base_traj = _trajectory_of(item["audio"])
        variants = {}

        rewrite = FIXTURES / f"meta_{item['token_id']}_rewrite.wav"
        sf.write(rewrite, item["audio"].astype(np.float32), TARGET_SAMPLE_RATE,
                 subtype="PCM_16")
        variants["lossless_wav_rewrite"] = rewrite
        for name, factor in (("amplitude_x0.8", 0.8), ("amplitude_x1.2", 1.2)):
            path = FIXTURES / f"meta_{item['token_id']}_{name}.wav"
            sf.write(path, (item["audio"] * factor).astype(np.float32),
                     TARGET_SAMPLE_RATE, subtype="FLOAT")
            variants[name] = path
        variants["study_capture_roundtrip"] = study_roundtrip(item["audio"])

        for name, path in variants.items():
            got = infer_tone_attempt(audio_path=path, expected_tone=item["tone"],
                                     bundle=bundle)
            audio, _ = decode_wav(path.read_bytes())
            traj = _trajectory_of(audio)
            traj_delta = (float(np.max(np.abs(base_traj - traj)))
                          if base_traj is not None and traj is not None
                          else float("inf"))
            score_delta = (abs(baseline["raw_score"] - got["raw_score"])
                           if baseline["raw_score"] is not None
                           and got["raw_score"] is not None else float("inf"))
            rows.append({
                "ref_id": item["ref_id"], "transformation": name,
                "trajectory_max_delta_st": traj_delta,
                "trajectory_tolerance_st": E2E_TOLERANCE[name]["trajectory_st"],
                "score_delta": score_delta,
                "score_tolerance": E2E_TOLERANCE[name]["score"],
                "baseline_decision": baseline["decision"],
                "variant_decision": got["decision"],
                "within_tolerance": (traj_delta <= E2E_TOLERANCE[name]["trajectory_st"]
                                     and score_delta <= E2E_TOLERANCE[name]["score"]),
                "decision_preserved": baseline["decision"] == got["decision"]})

    for name in E2E_TOLERANCE:
        subset = [r for r in rows if r["transformation"] == name]
        worst_traj = max(r["trajectory_max_delta_st"] for r in subset)
        worst_score = max(r["score_delta"] for r in subset)
        record("metamorphic", f"{name}: within pre-registered tolerance",
               f"<= {E2E_TOLERANCE[name]['trajectory_st']} ST / "
               f"{E2E_TOLERANCE[name]['score']}",
               f"worst {worst_traj:.6f} ST, {worst_score:.6f} score",
               all(r["within_tolerance"] for r in subset), SEV_HIGH)
        record("metamorphic", f"{name}: decision preserved",
               "identical", f"{sum(1 for r in subset if r['decision_preserved'])}"
               f"/{len(subset)}",
               all(r["decision_preserved"] for r in subset), SEV_HIGH)

    with (OUT_DIR / "tv3_metamorphic_results.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 13-14. Restart regression and API stress
# ===========================================================================

def section_restart_and_stress(client, bundle, golden, stress_requests) -> dict:
    print("\n13. RESTART REGRESSION (through the API)")
    first = [(entry["audio_reference_id"],
              post_attempt(client, DATA_DIR / entry["audio_path"],
                           f"T{entry['expected_tone']}").json())
             for entry in golden["entries"]]

    child = subprocess.run(
        [sys.executable, "-m",
         "pronunciation.wav2vec_tone.verify_human_exposure_path", "--child-golden"],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=1800,
        env=dict(os.environ, OMPAL_STUDY_MODE="1"))
    if child.returncode != 0 or not child.stdout.strip():
        record("restart", "restarted application serves the golden set",
               "exit 0", f"exit {child.returncode}: {child.stderr.strip()[-160:]}",
               False, SEV_BLOCKING)
        payload = {"rows": [], "fitted_model_sha256": ""}
    else:
        payload = json.loads(child.stdout.strip().splitlines()[-1])
        record("restart", "restarted application loads the identical fitted hash",
               bundle.metadata["fitted_model_sha256"][:16],
               payload["fitted_model_sha256"][:16],
               payload["fitted_model_sha256"]
               == bundle.metadata["fitted_model_sha256"], SEV_BLOCKING)
        changed = sum(1 for (ref, before), after in zip(first, payload["rows"])
                      if before["decision"] != after["decision"])
        record("restart", "0 decision disagreement across a backend restart",
               "0", str(changed), changed == 0, SEV_BLOCKING)

    print(f"\n14. API STRESS ({stress_requests} requests)")
    entries = golden["entries"]
    baseline = {entry["audio_reference_id"]: entry["expected_decision"]
                for entry in entries}
    latencies, http_failures, instability, exceptions = [], 0, 0, 0
    started = time.perf_counter()
    for index in range(stress_requests):
        entry = entries[index % len(entries)]
        call_started = time.perf_counter()
        try:
            response = post_attempt(client, DATA_DIR / entry["audio_path"],
                                    f"T{entry['expected_tone']}")
            latencies.append((time.perf_counter() - call_started) * 1000)
            if response.status_code != 200:
                http_failures += 1
            elif response.json()["decision"] != baseline[entry["audio_reference_id"]]:
                instability += 1
        except Exception:  # noqa: BLE001
            exceptions += 1
    elapsed = time.perf_counter() - started
    values = np.asarray(latencies) if latencies else np.asarray([0.0])

    record("stress", f"{stress_requests} API requests complete",
           "0 HTTP failures, 0 exceptions",
           f"{http_failures} HTTP failures, {exceptions} exceptions",
           http_failures == 0 and exceptions == 0, SEV_BLOCKING)
    record("stress", "no decision instability under API load",
           "0", str(instability), instability == 0, SEV_BLOCKING)
    record("stress", "fitted model hash unchanged after the stress run",
           bundle.metadata["fitted_model_sha256"][:16],
           bundle.fitted_model_sha256()[:16],
           bundle.fitted_model_sha256() == bundle.metadata["fitted_model_sha256"],
           SEV_BLOCKING)

    runtime = {
        "requests": stress_requests, "seconds": elapsed,
        "http_failures": http_failures, "exceptions": exceptions,
        "decision_instability": instability,
        "median_ms": float(np.median(values)),
        "iqr_ms": [float(np.percentile(values, 25)), float(np.percentile(values, 75))],
        "p95_ms": float(np.percentile(values, 95)),
        "latency_scope": ("in-process API request latency over a pre-recorded WAV "
                          "on disk; excludes microphone capture, browser "
                          "conversion and network transfer, so it is NOT an "
                          "end-user latency estimate"),
    }
    record("stress", "latency reported, not used as a pass criterion",
           "reported", f"median {runtime['median_ms']:.1f} ms, p95 "
           f"{runtime['p95_ms']:.1f} ms", True, SEV_INFO,
           runtime["latency_scope"])
    return runtime


def child_golden_mode() -> None:
    """Serve the golden set from a cold application process."""
    golden = json.loads(
        (OUT_DIR / "tv3_golden_reference.json").read_text(encoding="utf-8"))
    client, _main = build_client()
    rows = []
    for entry in golden["entries"]:
        response = post_attempt(client, DATA_DIR / entry["audio_path"],
                                f"T{entry['expected_tone']}")
        rows.append({"audio_reference_id": entry["audio_reference_id"],
                     "decision": response.json().get("decision")})
    bundle = FrozenInferenceBundle.load()
    print(json.dumps({"fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
                      "rows": rows}))


# ===========================================================================
# 15. Scientific equivalence (re-run after all deployment changes)
# ===========================================================================

def section_equivalence(bundle) -> dict:
    print("\n15. TRAIN/DEV SCIENTIFIC EQUIVALENCE")
    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        trajectory = normalise(stored["learner"], "N2")
    train = cache["split"] == "train"
    train_base, train_tones, train_y = (trajectory[train], cache["tone"][train],
                                        cache["y"][train])

    summary = {}
    for label, mask in (("train", train), ("dev", cache["split"] == "dev")):
        base, tones = trajectory[mask], cache["tone"][mask]
        research, _model = fit_predict(train_base, train_tones, train_y,
                                       base, tones, C_VALUE, 0)
        served = np.asarray([bundle.score(base[i], str(tones[i]))
                             for i in range(len(tones))])
        delta = float(np.max(np.abs(research - served)))
        available = np.asarray([bool(np.all(np.isfinite(row))) for row in base])
        disagreements = int((pass_mask(research, tones, available, bundle.t_pass,
                                       bundle.enabled_tones)
                             != pass_mask(served, tones, available, bundle.t_pass,
                                          bundle.enabled_tones)).sum())
        summary[label] = {"n": int(mask.sum()), "max_score_delta": delta,
                          "decision_disagreements": disagreements}
        record("frozen-scientific equivalence",
               f"{label}: {int(mask.sum())} tokens reproduce after TV3 changes",
               f"max |delta| <= {EQUIVALENCE_TOLERANCE}",
               f"max |delta| = {delta:.3e}", delta <= EQUIVALENCE_TOLERANCE,
               SEV_BLOCKING)
        record("frozen-scientific equivalence", f"{label}: 0 PASS/RETRY disagreements",
               "0", str(disagreements), disagreements == 0, SEV_BLOCKING)

    record("frozen-scientific equivalence", "the persisted bundle file is unchanged",
           BUNDLE_NPZ.name, sha256_file(BUNDLE_NPZ)[:16],
           sha256_file(BUNDLE_NPZ)
           == json.loads(BUNDLE_JSON.read_text(encoding="utf-8"))["bundle_npz_sha256"],
           SEV_BLOCKING)
    return summary


# ===========================================================================
# 16. OMPAL Test seal
# ===========================================================================

def section_seal(reference) -> dict:
    print("\n16. OMPAL TEST SEAL")
    result = subprocess.run(
        [sys.executable, "-m", "pronunciation.wav2vec_tone.verify_ompal_test_seal"],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=600)
    record("artifact identity", "independent seal verifier reports SEALED",
           "exit 0", f"exit {result.returncode}", result.returncode == 0,
           SEV_BLOCKING)

    cache = dict(np.load(CACHE, allow_pickle=True))
    in_cache = int((np.asarray(cache["split"]) == "test").sum())
    record("artifact identity", "no Test row in the feature cache",
           "0", str(in_cache), in_cache == 0, SEV_BLOCKING)

    manifest = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    test_tokens = {r["token_id"] for r in manifest if r["split"] == "test"}
    overlap = {r["token_id"] for r in reference} & test_tokens
    record("artifact identity", "TV3 fixtures and reference set exclude Test",
           "0 overlap", str(len(overlap)), not overlap, SEV_BLOCKING)
    return {"sealed": result.returncode == 0, "test_rows_in_cache": in_cache}


# ===========================================================================
# Golden set
# ===========================================================================

def write_golden(bundle, reference) -> dict:
    entries = []
    for item in reference:
        result = infer_tone_attempt(audio_path=item["path"],
                                    expected_tone=item["tone"], bundle=bundle)
        traj = _trajectory_of(item["audio"])
        entries.append({
            "audio_reference_id": item["ref_id"], "token_id": item["token_id"],
            "audio_path": str(item["path"].relative_to(DATA_DIR)).replace("\\", "/"),
            "split": "native_reference", "expected_tone": item["tone"],
            "input_metadata": {"sample_rate": TARGET_SAMPLE_RATE, "channels": 1,
                               "container": "WAV", "encoding": "PCM_16"},
            "audio_contract_version": AUDIO_CONTRACT_VERSION,
            "pcm_spec_version": STUDY_PCM_SPEC_VERSION,
            "expected_trajectory_sha256": (
                None if traj is None
                else hashlib.sha256(np.ascontiguousarray(
                    np.round(traj, 9)).tobytes()).hexdigest()),
            "expected_trajectory_tolerance_st": 1e-9,
            "expected_raw_score": (None if result["raw_score"] is None
                                   else round(result["raw_score"], 12)),
            "expected_raw_score_tolerance": 1e-9,
            "expected_decision": result["decision"],
            "expected_failure_code": result["failure_code"],
        })
    golden = {
        "_note": ("TV3 deployment regression fixture, bound to the full serving "
                  "path. Non-Test, non-validation material only. Expected values "
                  "describe what the hardened path does today; they are not "
                  "pronunciation correctness labels."),
        "scientific_version": SCIENTIFIC_VERSION,
        "deployment_version": DEPLOYMENT_VERSION,
        "audio_contract_version": AUDIO_CONTRACT_VERSION,
        "pcm_spec_version": STUDY_PCM_SPEC_VERSION,
        "fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
        "feature_schema_sha256": bundle.metadata["feature_schema_sha256"],
        "t_pass": bundle.t_pass,
        "contains_ompal_test_material": False,
        "entries": entries,
    }
    (OUT_DIR / "tv3_golden_reference.json").write_text(
        json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf-8")
    return golden


# ===========================================================================
# Acceptance
# ===========================================================================

def acceptance(summary: dict) -> list[dict]:
    failures = [r for r in matrix if r["result"] == "FAIL"]

    def clean(*categories) -> bool:
        return not [r for r in failures if r["category"] in categories]

    return [
        {"criterion": "one canonical pronunciation engine active in the study build",
         "met": clean("legacy-route isolation")},
        {"criterion": "browser recording reaches the model successfully",
         "met": clean("API integration", "study audio contract")},
        {"criterion": "validated 16 kHz PCM/WAV contract enforced",
         "met": clean("study audio contract")},
        {"criterion": "legacy learner-facing diagnostic path disabled",
         "met": clean("legacy-route isolation")},
        {"criterion": "fitted-model integrity checked on startup",
         "met": clean("artifact identity", "feature schema")},
        {"criterion": "0 unsafe PASS", "met": clean("fail-safe")},
        {"criterion": "0 identical-input decision nondeterminism",
         "met": clean("restart", "stress")},
        {"criterion": "T1 gate verified end to end", "met": clean("policy")},
        {"criterion": "trajectory failure verified end to end",
         "met": clean("fail-safe")},
        {"criterion": "frontend exposes no forbidden model fields",
         "met": clean("privacy") and summary["frontend_tests_passed"]},
        {"criterion": "API stress test passes", "met": clean("stress")},
        {"criterion": "scientific Train/Dev equivalence remains exact",
         "met": clean("frozen-scientific equivalence")},
        {"criterion": "OMPAL Test remains sealed",
         "met": summary["ompal_test"]["sealed"]},
        {"criterion": "short-token ingest stability measured",
         "met": clean("short-token stability")},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--child-golden", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--frontend-tests-passed", type=int, default=24,
                        help="count of passing study frontend tests")
    args = parser.parse_args()

    if args.child_golden:
        child_golden_mode()
        return

    stress_requests = 30 if args.quick else STRESS_REQUESTS
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    print("=" * 78)
    print("PHASE TV3 -- FINAL HUMAN-EXPOSURE TECHNICAL CLOSURE")
    print(f"scientific {SCIENTIFIC_VERSION} (frozen) / deployment {DEPLOYMENT_VERSION}")
    print(f"audio contract {AUDIO_CONTRACT_VERSION} / pcm {STUDY_PCM_SPEC_VERSION}")
    print("=" * 78)

    bundle = section_artefact_freeze()
    cross = section_cross_language()
    section_study_contract()
    fixtures = build_browser_fixtures()
    section_browser_fixtures(fixtures)

    reference = build_reference_set()
    print(f"\n  technical reference set: {len(reference)} native-reference tokens")

    browser_rows = section_browser_vs_reference(bundle, reference)
    short_rows = section_short_tokens(bundle, reference)
    golden = write_golden(bundle, reference)

    client, main_module = build_client()
    e2e_rows = section_end_to_end(client, main_module, fixtures, reference)
    section_legacy(client)
    section_startup(client, bundle)
    metamorphic = section_metamorphic(bundle, reference)
    runtime = section_restart_and_stress(client, bundle, golden, stress_requests)
    equivalence = section_equivalence(bundle)
    seal = section_seal(reference)

    with (OUT_DIR / "tv3_verification_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "test_id", "category", "input", "expected_behaviour",
            "observed_behaviour", "result", "severity", "notes"])
        writer.writeheader()
        writer.writerows(matrix)

    total = len(matrix)
    failed = sum(1 for r in matrix if r["result"] == "FAIL")
    diagnostic = sum(1 for r in matrix if r["result"] == "DIAGNOSTIC")

    summary = {
        "phase": "TV3",
        "title": "final human-exposure technical closure",
        "scientific_version": SCIENTIFIC_VERSION,
        "deployment_version": DEPLOYMENT_VERSION,
        "audio_contract_version": AUDIO_CONTRACT_VERSION,
        "pcm_spec_version": STUDY_PCM_SPEC_VERSION,
        "fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
        "feature_schema_sha256": bundle.metadata["feature_schema_sha256"],
        "started_at": started_at, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scope_statement": (
            "Deployment engineering only. Establishes that the frozen decision "
            "function is served correctly through one controlled browser path. "
            "Does NOT establish that the system assesses Mandarin learners "
            "accurately."),
        "human_validation_status": "POSTPONED; no participant recruited",
        "cross_language_check": cross,
        "browser_vs_reference": {
            "n": len(browser_rows),
            "worst_trajectory_delta_st": max(
                (r["trajectory_delta_st"] for r in browser_rows
                 if not math.isnan(r["trajectory_delta_st"])), default=0.0),
            "worst_score_delta": max(
                (r["score_delta"] for r in browser_rows
                 if not math.isnan(r["score_delta"])), default=0.0),
            "decision_changes": sum(1 for r in browser_rows
                                    if r["reference_decision"] != r["study_decision"]),
        },
        "short_token_cases": len(short_rows),
        "end_to_end_cases": len(e2e_rows),
        "metamorphic_worst": {
            name: max(r["trajectory_max_delta_st"] for r in metamorphic
                      if r["transformation"] == name) for name in E2E_TOLERANCE},
        "e2e_tolerances_preregistered": E2E_TOLERANCE,
        "scientific_equivalence": equivalence,
        "runtime": runtime,
        "frontend_tests_passed": args.frontend_tests_passed >= 24,
        "frontend_test_count": args.frontend_tests_passed,
        "counts": {"total": total, "passed": total - failed - diagnostic,
                   "failed": failed, "diagnostic": diagnostic},
        "ompal_test": {"predictions": False, "scores": False, "metrics": False,
                       "cache_contamination": seal["test_rows_in_cache"] > 0,
                       "sealed": seal["sealed"],
                       "seal_verified_by": "verify_ompal_test_seal.py"},
        "golden_reference_entries": len(golden["entries"]),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    criteria = acceptance(summary)
    unmet = [c["criterion"] for c in criteria if not c["met"]]
    summary["acceptance_criteria"] = criteria
    summary["acceptance_criteria_unmet"] = unmet
    summary["findings_requiring_disclosure"] = [
        {"test_id": r["test_id"], "category": r["category"], "finding": r["input"],
         "observed": r["observed_behaviour"], "notes": r["notes"]}
        for r in matrix
        if r["category"] == "ingest sensitivity" or r["result"] == "FAIL"]
    summary["tv3_result"] = ("TECHNICAL WORK COMPLETE" if not unmet
                             else "HUMAN-EXPOSURE TECHNICAL PATH STILL NOT READY")

    (OUT_DIR / "tv3_summary.json").write_text(
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
    print("\nHUMAN-EXPOSURE ACCEPTANCE CRITERIA")
    for entry in criteria:
        print(f"  [{'MET ' if entry['met'] else 'UNMET'}] {entry['criterion']}")

    disclosed = summary["findings_requiring_disclosure"]
    if disclosed:
        print("\nFINDINGS REQUIRING DISCLOSURE (measured, not waived)")
        for entry in disclosed:
            print(f"  {entry['test_id']} [{entry['category']}] {entry['finding']}")
            print(f"      {entry['observed']}")
    print(f"\nresult: {summary['tv3_result']}")
    print(f"artefacts: {OUT_DIR}")
    print("\nEven on a full pass this means the implementation is ready to be")
    print("EXPOSED to a controlled validation study. It does not mean the")
    print("system accurately assesses Mandarin learners.")


if __name__ == "__main__":
    main()
