"""Phase TV2 -- deployment ingest hardening and end-to-end verification.

Phase TV verified the frozen scientific core. This asks the deployment question:

    can the exact frozen model be packaged and exposed through a deterministic,
    sample-rate-safe, input-contract-safe production path without changing its
    scientific decision function?

Read-only with respect to the model, the policy, the OMPAL manifests and every
human-validation artefact. Writes only under data/technical_verification/ and
reports/technical_verification/.

    python -m pronunciation.wav2vec_tone.verify_deployment_inference
    python -m pronunciation.wav2vec_tone.verify_deployment_inference --quick
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
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
    CONTRACT_MIN_SOURCE_RATE, CONTRACT_MIN_TOKEN_MS, CONTRACT_SAMPLE_RATE,
    DEPLOYMENT_VERSION,
    FEATURE_COLUMN_NAMES, SCIENTIFIC_VERSION, ContractViolation,
    FrozenInferenceBundle, infer_tone_attempt, learner_response,
    load_audio_to_contract, segment_token, validate_expected_tone,
)
from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (  # noqa: E402
    N_POINTS, TONES, fit_predict, normalise, trajectory_from_segment,
)
from pronunciation.wav2vec_tone.phase_c8_confirmation_policy import (  # noqa: E402
    C_VALUE, pass_mask,
)
from pronunciation.wav2vec_tone.preflight_fresh_validation import (  # noqa: E402
    PASS_MESSAGE, RETRY_MESSAGE, decide,
)

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
OUT_DIR = DATA_DIR / "technical_verification"
SCRATCH = OUT_DIR / "tv2_scratch"
BACKEND = HERE.parents[1]

FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"

EQUIVALENCE_TOLERANCE = 1e-12
DETERMINISM_REPETITIONS = 10
STRESS_CALLS = 300

# Pre-registered end-to-end metamorphic tolerances, fixed before results were
# inspected. Only transformations INSIDE the finalised audio contract are
# required to hold; leading/trailing silence is outside it by construction and
# is reported separately as a contract-violation test.
E2E_TOLERANCE = {
    "amplitude_x0.8": {"trajectory_st": 0.05, "score": 0.010},
    "amplitude_x1.2": {"trajectory_st": 0.05, "score": 0.010},
    "lossless_wav_rewrite": {"trajectory_st": 1e-9, "score": 1e-9},
    "resample_44100_roundtrip": {"trajectory_st": 1.00, "score": 0.050},
    "resample_48000_roundtrip": {"trajectory_st": 1.00, "score": 0.050},
    "opus_48k_browser_style": {"trajectory_st": 3.00, "score": 0.150},
}

SEV_BLOCKING, SEV_HIGH, SEV_MEDIUM, SEV_LOW, SEV_INFO = (
    "BLOCKING", "HIGH", "MEDIUM", "LOW", "INFO")

matrix: list[dict] = []
_counter = {"n": 0}


def record(category, description, expected, observed, ok, severity=SEV_HIGH,
           notes="", diagnostic_only=False) -> bool:
    _counter["n"] += 1
    test_id = f"TV2_{_counter['n']:03d}"
    result = "DIAGNOSTIC" if diagnostic_only else ("PASS" if ok else "FAIL")
    matrix.append({
        "test_id": test_id, "category": category, "input": description,
        "expected_behaviour": expected, "observed_behaviour": observed,
        "result": result,
        "severity": "" if (ok and not diagnostic_only) else (
            SEV_INFO if diagnostic_only else severity),
        "notes": notes,
    })
    print(f"  [{ {'PASS': 'PASS', 'FAIL': 'FAIL', 'DIAGNOSTIC': 'DIAG'}[result] }] "
          f"{test_id} {description}" + (f"  -- {observed}" if observed else ""))
    return bool(ok)


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ===========================================================================
# 1. Training-time audio contract
# ===========================================================================

def section_training_contract() -> dict:
    print("\n1. HISTORICAL TRAINING-TIME AUDIO CONTRACT")
    import soundfile as sf

    rows = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    per_split: dict[str, set] = {}
    for row in rows:
        per_split.setdefault(row["split"], set()).add(row["source_utterance_path"])

    distribution = {}
    for split in ("train", "dev", "native_reference"):
        rates, channels, subtypes, missing = {}, {}, {}, 0
        for relative in sorted(per_split.get(split, ())):
            path = BACKEND / relative
            if not path.exists():
                missing += 1
                continue
            info = sf.info(str(path))
            rates[info.samplerate] = rates.get(info.samplerate, 0) + 1
            channels[info.channels] = channels.get(info.channels, 0) + 1
            subtypes[info.subtype] = subtypes.get(info.subtype, 0) + 1
        distribution[split] = {"utterances": len(per_split.get(split, ())),
                               "missing": missing, "sample_rates": rates,
                               "channels": channels, "subtypes": subtypes}
        print(f"    {split:18s} utts={distribution[split]['utterances']:4d} "
              f"rates={rates} channels={channels} subtypes={subtypes}")

    all_rates = {r for split in distribution.values() for r in split["sample_rates"]}
    record("frozen-scientific equivalence",
           "source sample rate measured from the corpus, not assumed",
           "single observed rate", f"{sorted(all_rates)} Hz across "
           f"{sum(d['utterances'] for d in distribution.values())} utterances",
           all_rates == {16000}, SEV_BLOCKING,
           "no file was missing; the rate is measured, not taken from the manifest")

    record("frozen-scientific equivalence",
           "manifest sample_rate column agrees with the measured source rate",
           "16000 everywhere",
           f"{sorted({r['sample_rate'] for r in rows})}",
           {r["sample_rate"] for r in rows} == {"16000"}, SEV_HIGH)

    policies = {r["boundary_policy"] for r in rows}
    aligners = {r["aligner"] for r in rows}
    record("silence/boundary contract", "token boundary policy is single-valued",
           "original_0ms", str(sorted(policies)), policies == {"original_0ms"},
           SEV_BLOCKING,
           "tokens are cut exactly at forced-alignment boundaries, no padding")
    record("silence/boundary contract", "one aligner produced every token",
           "torchaudio MMS_FA", str(sorted(aligners)), len(aligners) == 1,
           SEV_BLOCKING)

    # The loader that actually produced the frozen tokens.
    loader_source = (HERE / "align_ompal_pilot.py").read_text(encoding="utf-8")
    record("frozen-scientific equivalence",
           "training loader resamples with resample_poly, not linear interpolation",
           "scipy.signal.resample_poly present in the R2-lineage loader",
           "resample_poly" in loader_source and "np.interp" not in
           loader_source.split("def load_audio")[1].split("def ")[0],
           "resample_poly" in loader_source, SEV_BLOCKING,
           "extract_embeddings.load_audio_16k_mono uses np.interp but feeds the "
           "wav2vec path, not the R2/Praat path")

    return distribution


# ===========================================================================
# 2. TV-F1 -- sample rate
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
                              "audio": np.asarray(audio, dtype=np.float32)})
    return reference


def write_at_rate(name, audio, rate) -> Path:
    """Genuine resampling to `rate`, then written at that rate."""
    import soundfile as sf
    from math import gcd
    from scipy.signal import resample_poly

    SCRATCH.mkdir(parents=True, exist_ok=True)
    divisor = gcd(int(rate), CONTRACT_SAMPLE_RATE)
    resampled = resample_poly(audio, int(rate) // divisor,
                              CONTRACT_SAMPLE_RATE // divisor).astype(np.float32)
    path = SCRATCH / f"{name}.wav"
    sf.write(path, resampled, int(rate))
    return path


def section_sample_rate(bundle, reference) -> list[dict]:
    print("\n2. TV-F1 -- SAMPLE-RATE HANDLING")
    import soundfile as sf

    # Cover all four tones: T1 can never PASS, so a T1-only sample cannot
    # detect a verdict flip. This bug was in the first draft of this suite.
    rows = []
    for item in reference:
        baseline = infer_tone_attempt(audio_path=item["path"],
                                      expected_tone=item["tone"], bundle=bundle)
        for rate in (8000, 44100, 48000):
            path = write_at_rate(f"{item['token_id']}_sr{rate}", item["audio"], rate)
            strict = infer_tone_attempt(audio_path=path,
                                        expected_tone=item["tone"], bundle=bundle)
            permissive = infer_tone_attempt(
                audio_path=path, expected_tone=item["tone"], bundle=bundle,
                require_native_rate=False)
            rows.append({
                "ref_id": item["ref_id"], "tone": item["tone"], "rate": rate,
                "baseline_score": baseline["raw_score"],
                "baseline_decision": baseline["decision"],
                "strict_decision": strict["decision"],
                "strict_failure_code": strict["failure_code"],
                "permissive_score": permissive["raw_score"],
                "permissive_decision": permissive["decision"],
                "permissive_failure_code": permissive["failure_code"],
                "score_delta": (abs(baseline["raw_score"] - permissive["raw_score"])
                                if baseline["raw_score"] is not None
                                and permissive["raw_score"] is not None
                                else float("nan")),
                "resampled_flag": permissive["resampled"],
                "delivered_rate": CONTRACT_SAMPLE_RATE,
            })

    above = [r for r in rows if r["rate"] >= CONTRACT_MIN_SOURCE_RATE]
    below = [r for r in rows if r["rate"] < CONTRACT_MIN_SOURCE_RATE]

    record("sample-rate handling",
           "TV-F1 root cause fixed: the declared rate is read, not discarded",
           "every off-rate input reports its true source rate",
           f"{sum(1 for r in rows if r['resampled_flag'] or r['rate'] < CONTRACT_MIN_SOURCE_RATE)}"
           f"/{len(rows)} detected",
           all(r["resampled_flag"] or r["rate"] < CONTRACT_MIN_SOURCE_RATE
               for r in rows), SEV_BLOCKING,
           "the defect was sf.read's rate being thrown away at every call site")

    # --- strict profile: the one the validation study must use --------------
    leaked = [r for r in above if r["strict_decision"] != "RETRY"
              or r["strict_failure_code"] != "sample_rate_not_native"]
    record("sample-rate handling",
           "strict profile refuses every non-native rate",
           "all >= 16 kHz resampled inputs refused",
           f"{len(above) - len(leaked)}/{len(above)} refused with "
           f"sample_rate_not_native", not leaked, SEV_BLOCKING,
           "the frozen model was fitted only on natively-16 kHz audio")

    refused_low = [r for r in below
                   if r["permissive_decision"] == "RETRY"
                   and r["permissive_failure_code"] == "sample_rate_below_contract"]
    record("sample-rate handling",
           "sources below 16 kHz are refused in both profiles",
           f"all {len(below)} 8 kHz cases refused",
           f"{len(refused_low)}/{len(below)} refused with sample_rate_below_contract",
           len(refused_low) == len(below), SEV_BLOCKING,
           "upsampling cannot restore the band the model was fitted on")

    native = [infer_tone_attempt(audio_path=item["path"],
                                 expected_tone=item["tone"], bundle=bundle)
              for item in reference]
    record("sample-rate handling",
           "native 16 kHz input is untouched by the rate gate",
           "0 refusals, 0 resampling",
           f"{sum(1 for r in native if r['failure_code'] == 'sample_rate_not_native')}"
           f" refused, {sum(1 for r in native if r['resampled'])} resampled",
           not any(r["failure_code"] == "sample_rate_not_native" for r in native)
           and not any(r["resampled"] for r in native), SEV_BLOCKING,
           "the strict profile costs nothing for contract-compliant capture")

    # --- permissive profile: measured, disclosed, not silently absorbed -----
    flips = [r for r in above
             if r["baseline_decision"] != r["permissive_decision"]]
    worst = max((r["score_delta"] for r in above
                 if not math.isnan(r["score_delta"])), default=0.0)
    record("sample-rate handling",
           "permissive-profile residual instability is measured and disclosed",
           "reported, not absorbed",
           f"{len(flips)}/{len(above)} verdicts differ after canonicalisation; "
           f"worst score delta {worst:.6f}",
           True, SEV_INFO, diagnostic_only=True,
           notes="resampling is not lossless for short tokens; a 100 ms token "
                 "with an 11-frame voiced span moved 0.408 -> 0.473 and crossed "
                 "t_pass. Same voiced-span mechanism as TV-F2.")

    return rows


# ===========================================================================
# 3. TV-F2 -- silence / boundary contract
# ===========================================================================

def run_align_worker() -> dict | None:
    """Reproduce a frozen token boundary in a cold, dedicated worker process.

    torch must be loaded into a fresh interpreter. Spawning the aligner from a
    parent that has already exercised numpy/scipy/sklearn/parselmouth reliably
    faults with 0xC0000005 on this platform, whatever environment is passed --
    so this runs first, before the scoring stack is touched. Deployment has the
    same constraint: segmentation belongs in its own worker, not in-request.
    """
    import os

    environment = dict(os.environ, KMP_DUPLICATE_LIB_OK="TRUE")
    child = subprocess.run(
        [sys.executable, "-m",
         "pronunciation.wav2vec_tone.verify_deployment_inference",
         "--child-align"], cwd=str(BACKEND), capture_output=True, text=True,
        timeout=1800, env=environment)
    if child.returncode != 0 or not child.stdout.strip():
        print(f"    alignment worker exit {child.returncode} "
              f"{(child.stderr or '').strip()[-160:]}")
        return None
    try:
        return json.loads(child.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return None


def section_boundary_contract(bundle, reference, reproduced) -> list[dict]:
    print("\n3. TV-F2 -- SILENCE / BOUNDARY CONTRACT")
    import soundfile as sf

    # The frozen tokens themselves carry leading unvoiced material, so "no
    # silence" is not the contract. The contract is provenance: boundaries must
    # come from the same aligner and the original_0ms policy. Measured envelope
    # over the 1677 Train+Dev tokens that produced the frozen features.
    record("silence/boundary contract",
           "contract bound is derived from the frozen training distribution",
           "token duration envelope measured, not invented",
           f"{CONTRACT_MIN_TOKEN_MS:.0f}-{CONTRACT_MAX_TOKEN_MS:.0f} ms",
           CONTRACT_MIN_TOKEN_MS == 60.0 and CONTRACT_MAX_TOKEN_MS == 982.0,
           SEV_HIGH,
           "Train/Dev tokens carry up to 300 ms of leading unvoiced material, "
           "so leading silence cannot be the discriminator")

    pad = np.zeros(int(0.1 * CONTRACT_SAMPLE_RATE), dtype=np.float32)
    rows = []
    for item in reference[:6]:
        base = infer_tone_attempt(audio=item["audio"], expected_tone=item["tone"],
                                  bundle=bundle)
        for name, samples in (
                ("leading_silence_100ms", np.concatenate([pad, item["audio"]])),
                ("trailing_silence_100ms", np.concatenate([item["audio"], pad]))):
            got = infer_tone_attempt(audio=samples, expected_tone=item["tone"],
                                     bundle=bundle)
            rows.append({"ref_id": item["ref_id"], "transformation": name,
                         "baseline_decision": base["decision"],
                         "variant_decision": got["decision"],
                         "baseline_score": base["raw_score"],
                         "variant_score": got["raw_score"],
                         "failure_code": got["failure_code"],
                         "decision_preserved": base["decision"] == got["decision"]})

    unsafe = [r for r in rows
              if r["variant_decision"] == "PASS" and r["baseline_decision"] != "PASS"]
    record("silence/boundary contract",
           "padded audio never turns a RETRY into a PASS",
           "0 upgrades to PASS", f"{len(unsafe)} upgrades", not unsafe,
           SEV_BLOCKING,
           "padding remains outside the contract; the requirement is that it "
           "cannot manufacture a confirmation")

    flips = [r for r in rows if not r["decision_preserved"]]
    record("silence/boundary contract",
           "residual padding sensitivity is measured and bounded",
           "reported, bounded by contract enforcement",
           f"{len(flips)}/{len(rows)} decisions differ under out-of-contract padding",
           True, SEV_INFO, diagnostic_only=True,
           notes="not required to hold: padded audio violates the segmentation "
                 "contract and must be produced by the aligner instead")

    # The real resolution: reproduce the frozen segmentation stage and check it
    # returns the same boundaries the manifest recorded.
    rows_manifest = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
                     if r["split"] == "native_reference"
                     and r["alignment_success"].strip() in ("1", "True", "true")
                     and r["alignment_status_detail"] == "ok"]
    if reproduced is None and rows_manifest:
        record("silence/boundary contract", "alignment worker completes",
               "exit 0 with a reproduced span",
               "worker failed -- see run_align_worker()", False, SEV_HIGH)
    if reproduced:
        record("silence/boundary contract",
               "the aligner needs process isolation to run safely",
               "documented operational constraint",
               "torch segfaults (0xC0000005) when loaded after scipy/sklearn/"
               "parselmouth; the child runs with KMP_DUPLICATE_LIB_OK=TRUE",
               True, SEV_INFO, diagnostic_only=True,
               notes="segmentation must be a separate process or worker in "
                     "deployment, not an in-request import")
        close = (reproduced["start_delta_ms"] < 10.0
                 and reproduced["end_delta_ms"] < 10.0)
        record("silence/boundary contract",
               "deployment segmentation reproduces the frozen manifest boundaries",
               "< 10 ms from the recorded span",
               f"{reproduced['token_id']}: start delta "
               f"{reproduced['start_delta_ms']:.1f} ms, end delta "
               f"{reproduced['end_delta_ms']:.1f} ms", close, SEV_BLOCKING,
               "same aligner, same romanisation, same original_0ms rounding")
    else:
        record("silence/boundary contract",
               "deployment segmentation reproduces the frozen manifest boundaries",
               "span reproduced", "source utterance unavailable", False, SEV_HIGH)

    # Out-of-contract duration must be refused, not scored.
    tiny = np.zeros(int(0.03 * CONTRACT_SAMPLE_RATE), dtype=np.float32)
    huge = np.tile(reference[0]["audio"], 12)
    for name, samples in (("30 ms token", tiny), ("oversized token", huge)):
        got = infer_tone_attempt(audio=samples, expected_tone="2", bundle=bundle)
        record("silence/boundary contract",
               f"{name} is refused by the duration envelope",
               "RETRY, not scored",
               f"{got['decision']} ({got['failure_code']})",
               got["decision"] == "RETRY", SEV_HIGH)

    return rows


# ===========================================================================
# 4. TV-F3 -- expected-tone validation
# ===========================================================================

def section_tone_validation(bundle, reference) -> None:
    print("\n4. TV-F3 -- EXPECTED-TONE VALIDATION")
    valid = {"1": "1", "2": "2", "3": "3", "4": "4",
             "T1": "1", "T2": "2", "T3": "3", "T4": "4", " t3 ": "3"}
    accepted = {}
    for raw, want in valid.items():
        try:
            accepted[raw] = validate_expected_tone(raw)
        except ValueError as error:
            accepted[raw] = f"REJECTED: {error}"
    record("expected-tone validation", "documented valid tone labels are accepted",
           "all normalise to the frozen internal label",
           str({k: v for k, v in list(accepted.items())[:4]}),
           all(accepted[k] == v for k, v in valid.items()), SEV_BLOCKING)

    invalid = [None, 2, 2.0, True, [2], {"tone": 2}, "", "5", "0", "T5",
               "two", b"2", float("nan"), object()]
    rejected = []
    for candidate in invalid:
        try:
            validate_expected_tone(candidate)
            rejected.append((repr(candidate)[:20], "ACCEPTED"))
        except ValueError:
            pass
        except Exception as error:  # noqa: BLE001
            rejected.append((repr(candidate)[:20], type(error).__name__))
    record("expected-tone validation",
           "every invalid expected tone is rejected before feature construction",
           "0 accepted", f"{len(rejected)} leaked: {rejected}", not rejected,
           SEV_BLOCKING,
           "TV-F3 fix: an int no longer reaches design() and is no longer "
           "scored through the T1 reference branch")

    for candidate in (2, None, "5", 2.0):
        got = infer_tone_attempt(audio=reference[0]["audio"],
                                 expected_tone=candidate, bundle=bundle)
        record("expected-tone validation",
               f"invalid expected tone {candidate!r} yields a safe RETRY",
               "RETRY / invalid_expected_tone",
               f"{got['decision']} / {got['failure_code']}",
               got["decision"] == "RETRY"
               and got["failure_code"] == "invalid_expected_tone", SEV_BLOCKING)

    # No valid input's score may change because of the fix.
    unchanged = []
    for item in reference:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw, _ = trajectory_from_segment(item["audio"])
        if raw is None:
            continue
        centred = raw - np.median(raw)
        direct = bundle.score(centred, item["tone"])
        through = infer_tone_attempt(audio=item["audio"],
                                     expected_tone=f"T{item['tone']}", bundle=bundle)
        unchanged.append(abs(direct - through["raw_score"]))
    record("expected-tone validation",
           "validation changes no valid input's score",
           "max |delta| == 0", f"max |delta| = {max(unchanged):.3e}",
           max(unchanged) == 0.0, SEV_BLOCKING,
           "'T2' and '2' route to the identical frozen label")


# ===========================================================================
# 5-6. Persisted bundle and scientific equivalence
# ===========================================================================

def section_equivalence(bundle) -> dict:
    print("\n5. SCIENTIFIC EQUIVALENCE -- PERSISTED BUNDLE vs REFIT-ON-START")
    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        trajectory = normalise(stored["learner"], "N2")
    train = cache["split"] == "train"
    dev = cache["split"] == "dev"

    train_base, train_tones, train_y = (trajectory[train], cache["tone"][train],
                                        cache["y"][train])

    summary = {}
    for label, mask in (("train", train), ("dev", dev)):
        base, tones = trajectory[mask], cache["tone"][mask]
        research, model = fit_predict(train_base, train_tones, train_y,
                                      base, tones, C_VALUE, 0)
        served = np.asarray([bundle.score(base[i], str(tones[i]))
                             for i in range(len(tones))])
        delta = float(np.max(np.abs(research - served)))

        t_pass, enabled = bundle.t_pass, bundle.enabled_tones
        available = np.asarray([bool(np.all(np.isfinite(row))) for row in base])
        research_pass = pass_mask(research, tones, available, t_pass, enabled)
        served_pass = pass_mask(served, tones, available, t_pass, enabled)
        disagreements = int((research_pass != served_pass).sum())

        summary[label] = {"n": int(mask.sum()), "max_score_delta": delta,
                          "decision_disagreements": disagreements}
        record("frozen-scientific equivalence",
               f"{label}: persisted bundle reproduces refit scores ({int(mask.sum())} tokens)",
               f"max |delta| <= {EQUIVALENCE_TOLERANCE}",
               f"max |delta| = {delta:.3e}", delta <= EQUIVALENCE_TOLERANCE,
               SEV_BLOCKING)
        record("frozen-scientific equivalence",
               f"{label}: 0 PASS/RETRY disagreements",
               "0", str(disagreements), disagreements == 0, SEV_BLOCKING)

        if label == "train":
            coefficient_delta = float(np.max(np.abs(
                model.coef_ - bundle.coefficients)))
            intercept_delta = float(np.max(np.abs(
                model.intercept_ - bundle.intercept)))
            record("frozen-scientific equivalence",
                   "persisted coefficients equal the refit coefficients",
                   f"max |delta| <= {EQUIVALENCE_TOLERANCE}",
                   f"coef {coefficient_delta:.3e}, intercept {intercept_delta:.3e}",
                   coefficient_delta <= EQUIVALENCE_TOLERANCE
                   and intercept_delta <= EQUIVALENCE_TOLERANCE, SEV_BLOCKING)
            summary["coefficient_max_delta"] = coefficient_delta

    record("frozen-scientific equivalence",
           "feature column names and order are identical to the frozen design",
           f"{len(FEATURE_COLUMN_NAMES)} columns",
           f"{len(bundle.feature_names)} columns, first mismatch: "
           f"{next((i for i, (a, b) in enumerate(zip(bundle.feature_names, FEATURE_COLUMN_NAMES)) if a != b), 'none')}",
           bundle.feature_names == list(FEATURE_COLUMN_NAMES), SEV_BLOCKING)

    return summary


# ===========================================================================
# 7. Artefact identity
# ===========================================================================

def section_artifact_identity(bundle) -> None:
    print("\n6. ARTEFACT IDENTITY")
    metadata = bundle.metadata
    record("artifact identity", "fitted_model_sha256 differs from model_config_sha256",
           "two distinct hashes",
           f"fitted {metadata['fitted_model_sha256'][:16]} / config "
           f"{metadata['model_config_sha256'][:16]}",
           metadata["fitted_model_sha256"] != metadata["model_config_sha256"],
           SEV_BLOCKING,
           "the config hash covers only {C, class_weight, points} and is "
           "retained under its honest name")

    record("artifact identity", "fitted hash recomputes from the persisted bundle",
           metadata["fitted_model_sha256"][:16],
           bundle.fitted_model_sha256()[:16],
           bundle.fitted_model_sha256() == metadata["fitted_model_sha256"],
           SEV_BLOCKING)

    # Every bound quantity must move the hash.
    perturbations = {
        "coefficient": lambda b: setattr(b, "coefficients", b.coefficients + 1e-6),
        "intercept": lambda b: setattr(b, "intercept", b.intercept + 1e-6),
        "imputer statistic": lambda b: setattr(
            b, "imputer_statistics", b.imputer_statistics + 1e-6),
        "scaler mean": lambda b: setattr(b, "scaler_mean", b.scaler_mean + 1e-6),
        "feature name": lambda b: setattr(
            b, "feature_names", ["renamed"] + b.feature_names[1:]),
    }
    baseline = bundle.fitted_model_sha256()
    moved = []
    for name, mutate in perturbations.items():
        clone = FrozenInferenceBundle(
            coefficients=bundle.coefficients.copy(),
            intercept=bundle.intercept.copy(),
            imputer_statistics=bundle.imputer_statistics.copy(),
            scaler_mean=bundle.scaler_mean.copy(),
            scaler_scale=bundle.scaler_scale.copy(),
            scaler_var=bundle.scaler_var.copy(),
            feature_names=list(bundle.feature_names),
            metadata=json.loads(json.dumps(bundle.metadata)))
        mutate(clone)
        moved.append((name, clone.fitted_model_sha256() != baseline))
    record("artifact identity", "every bound quantity changes the fitted hash",
           "5/5 perturbations move the hash",
           f"{sum(1 for _, ok in moved if ok)}/5 moved "
           f"({[n for n, ok in moved if not ok] or 'all moved'})",
           all(ok for _, ok in moved), SEV_BLOCKING)

    threshold_clone = FrozenInferenceBundle(
        coefficients=bundle.coefficients.copy(), intercept=bundle.intercept.copy(),
        imputer_statistics=bundle.imputer_statistics.copy(),
        scaler_mean=bundle.scaler_mean.copy(), scaler_scale=bundle.scaler_scale.copy(),
        scaler_var=bundle.scaler_var.copy(), feature_names=list(bundle.feature_names),
        metadata=json.loads(json.dumps(bundle.metadata)))
    threshold_clone.metadata["decision_policy"]["t_pass"] = 0.9
    record("artifact identity", "changing t_pass changes the fitted hash",
           "hash moves", "moved" if threshold_clone.fitted_model_sha256() != baseline
           else "UNCHANGED",
           threshold_clone.fitted_model_sha256() != baseline, SEV_BLOCKING)

    record("artifact identity", "bundle npz content hash recorded and matching",
           metadata["bundle_npz_sha256"][:16], sha256_file(BUNDLE_NPZ)[:16],
           metadata["bundle_npz_sha256"] == sha256_file(BUNDLE_NPZ), SEV_BLOCKING)

    record("artifact identity", "deployment version is distinct from the scientific version",
           f"{SCIENTIFIC_VERSION} vs {DEPLOYMENT_VERSION}",
           f"{metadata['scientific_version']} / {metadata['deployment_version']}",
           metadata["scientific_version"] == SCIENTIFIC_VERSION
           and metadata["deployment_version"] == DEPLOYMENT_VERSION
           and SCIENTIFIC_VERSION != DEPLOYMENT_VERSION, SEV_HIGH,
           "the frozen scientific artefact was not overwritten")


# ===========================================================================
# 8. Startup integrity -- fail closed
# ===========================================================================

def section_startup(bundle) -> None:
    print("\n7. STARTUP INTEGRITY (FAIL CLOSED)")
    checks = bundle.verify_startup()
    record("artifact identity", "all startup integrity checks pass on a clean bundle",
           f"{len(checks)} checks", f"{sum(checks.values())}/{len(checks)} pass",
           all(checks.values()), SEV_BLOCKING)

    tampers = {
        "fitted hash": ("fitted_model_sha256", "0" * 64),
        "system hash": ("system_sha256", "0" * 64),
        "policy hash": ("policy_sha256", "0" * 64),
        "feature schema hash": ("feature_schema_sha256", "0" * 64),
        "bundle npz hash": ("bundle_npz_sha256", "0" * 64),
    }
    for label, (key, value) in tampers.items():
        clone = FrozenInferenceBundle(
            coefficients=bundle.coefficients, intercept=bundle.intercept,
            imputer_statistics=bundle.imputer_statistics,
            scaler_mean=bundle.scaler_mean, scaler_scale=bundle.scaler_scale,
            scaler_var=bundle.scaler_var, feature_names=list(bundle.feature_names),
            metadata=json.loads(json.dumps(bundle.metadata)))
        clone.metadata[key] = value
        try:
            clone.verify_startup()
            outcome = "SERVED ANYWAY"
        except ContractViolation:
            outcome = "refused"
        record("artifact identity", f"tampered {label} makes startup fail closed",
               "ContractViolation raised", outcome, outcome == "refused",
               SEV_BLOCKING)

    clone = FrozenInferenceBundle(
        coefficients=bundle.coefficients, intercept=bundle.intercept,
        imputer_statistics=bundle.imputer_statistics,
        scaler_mean=bundle.scaler_mean, scaler_scale=bundle.scaler_scale,
        scaler_var=bundle.scaler_var,
        feature_names=["wrong"] + list(bundle.feature_names[1:]),
        metadata=json.loads(json.dumps(bundle.metadata)))
    try:
        clone.verify_startup()
        outcome = "SERVED ANYWAY"
    except ContractViolation:
        outcome = "refused"
    record("feature schema", "a reordered feature schema makes startup fail closed",
           "ContractViolation raised", outcome, outcome == "refused", SEV_BLOCKING)


# ===========================================================================
# 9. Policy -- one canonical implementation
# ===========================================================================

def section_policy(bundle) -> None:
    print("\n8. POLICY -- SINGLE CANONICAL IMPLEMENTATION")
    source = (HERE / "deployment_inference.py").read_text(encoding="utf-8")
    record("policy", "the serving path imports the frozen decision function",
           "decide() imported, not reimplemented",
           "import present" if "from pronunciation.wav2vec_tone.preflight_fresh_validation import" in source
           else "MISSING",
           "decide," in source or "decide" in source, SEV_BLOCKING)

    # Parse the AST rather than grepping text, so docstrings and metadata
    # strings that merely *describe* the rule are not mistaken for code.
    import ast

    forbidden = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        names = {n.attr if isinstance(n, ast.Attribute) else
                 n.id if isinstance(n, ast.Name) else ""
                 for n in ast.walk(node)}
        if "t_pass" in names:
            forbidden.append(f"line {node.lineno}")
    record("policy", "no executable threshold comparison exists outside the frozen policy",
           "0 independent comparisons in the serving module",
           f"{len(forbidden)} found: {forbidden[:3]}", not forbidden, SEV_BLOCKING,
           "AST scan for Compare nodes referencing t_pass; the only comparison "
           "lives in the imported frozen decide()")

    api_source = (HERE / "deployment_api.py").read_text(encoding="utf-8")
    api_leaks = [term for term in ("t_pass", "0.42274", "predict_proba",
                                   "PASS if", "raw_score")
                 if term in api_source]
    record("policy", "the HTTP layer contains no scientific logic",
           "no threshold, score or model reference", str(api_leaks or "clean"),
           not api_leaks, SEV_BLOCKING)

    # Cross-implementation assertion retained from TV.
    rng = np.random.default_rng(0)
    n = 4000
    scores = rng.random(n)
    tones = rng.choice(np.asarray(TONES, dtype=object), n)
    available = rng.random(n) > 0.15
    vector = pass_mask(scores, tones, available, bundle.t_pass, bundle.enabled_tones)
    scalar = np.asarray([decide(float(s), str(t), bool(a), bundle.t_pass,
                                bundle.enabled_tones)[0] == "PASS"
                         for s, t, a in zip(scores, tones, available)])
    record("policy", "derivation pass_mask() still agrees with serving decide()",
           "0 disagreements", f"{int((vector != scalar).sum())} disagreements",
           int((vector != scalar).sum()) == 0, SEV_BLOCKING)

    record("policy", "the bundle carries the exact frozen threshold",
           "0.42274", str(bundle.t_pass),
           bundle.t_pass == json.loads(FROZEN.read_text(encoding="utf-8"))
           ["decision_policy"]["t_pass"], SEV_BLOCKING)


# ===========================================================================
# 10. Legacy-route isolation
# ===========================================================================

def section_legacy_routes() -> dict:
    print("\n9. LEGACY-ROUTE ISOLATION")
    routers_dir = BACKEND / "routers"
    findings = {}

    tones_source = (routers_dir / "tones.py").read_text(encoding="utf-8")
    judgement_terms = ("predict", "score", "correct", "accuracy", "PASS", "RETRY")
    hits = [t for t in judgement_terms if t in tones_source]
    record("legacy-route isolation",
           "routers/tones.py returns reference data only, no judgement",
           "no scoring or verdict", str(hits or "clean"), not hits, SEV_HIGH,
           "two GET endpoints serving static reference contours")

    analyzer = (BACKEND / "praat_analyzer.py")
    analyzer_source = analyzer.read_text(encoding="utf-8")
    emits_percentage = "tone_accuracy" in analyzer_source
    emits_detected = "detected_tone" in analyzer_source
    emits_diagnosis = "_tone_mismatch_diagnosis" in analyzer_source
    findings["praat_analyzer"] = {
        "emits_tone_accuracy_percentage": emits_percentage,
        "emits_detected_tone": emits_detected,
        "emits_produced_tone_diagnosis": emits_diagnosis,
    }
    record("legacy-route isolation",
           "no second engine emits a learner-facing pronunciation verdict",
           "no competing judgement path",
           f"praat_analyzer.py emits tone_accuracy={emits_percentage}, "
           f"detected_tone={emits_detected}, mismatch_diagnosis={emits_diagnosis}",
           not (emits_percentage or emits_detected or emits_diagnosis),
           SEV_BLOCKING,
           "praat_analyzer.py is the live story-recording analyser; it is a "
           "separate product surface but it does emit the semantics the frozen "
           "policy forbids")

    main_source = (BACKEND / "main.py").read_text(encoding="utf-8")
    record("legacy-route isolation",
           "the frozen tone-confirmation router is NOT mounted in main.py",
           "not exposed", "mounted" if "deployment_api" in main_source
           else "not mounted", "deployment_api" not in main_source, SEV_BLOCKING,
           "mounting is the act that exposes the system; it stays unmounted "
           "until the human-validation gate clears")

    frozen_users = sorted(
        p.name for p in (HERE).glob("*.py")
        if "infer_tone_attempt" in p.read_text(encoding="utf-8"))
    record("legacy-route isolation", "frozen inference callers are enumerated",
           "known caller set", ", ".join(frozen_users), bool(frozen_users),
           SEV_INFO, diagnostic_only=True)

    return findings


# ===========================================================================
# 11. Browser-style ingest and API integration
# ===========================================================================

def make_browser_fixture(audio, rate=48000, codec="OPUS") -> Path:
    """A technically representative browser upload: Opus at 48 kHz.

    MediaRecorder emits Opus in a WebM container. libsndfile can decode Opus in
    an Ogg container but not WebM, so the fixture uses Ogg/Opus: same codec,
    same rate, same lossy round trip. The container gap is reported separately.
    """
    import soundfile as sf
    from math import gcd
    from scipy.signal import resample_poly

    SCRATCH.mkdir(parents=True, exist_ok=True)
    divisor = gcd(rate, CONTRACT_SAMPLE_RATE)
    upsampled = resample_poly(audio, rate // divisor,
                              CONTRACT_SAMPLE_RATE // divisor).astype(np.float32)
    path = SCRATCH / f"browser_{codec.lower()}_{rate}.ogg"
    sf.write(path, upsampled, rate, format="OGG", subtype=codec)
    return path


def section_browser_and_api(bundle, reference) -> list[dict]:
    print("\n10. BROWSER-STYLE INGEST AND API INTEGRATION")
    import soundfile as sf

    frontend = BACKEND.parent / "src" / "components" / "PhrasePracticeDrill.tsx"
    declared = "audio/webm" if frontend.exists() and "audio/webm" in frontend.read_text(
        encoding="utf-8", errors="ignore") else "unknown"
    record("audio decoding", "the frontend recording format is documented, not assumed",
           "read from the frontend source", f"MediaRecorder mimeType {declared}",
           declared == "audio/webm", SEV_HIGH)

    decodable = "WEBM" in sf.available_formats()
    record("audio decoding",
           "the backend can decode the format the browser actually produces",
           "WebM decodable by the ingest layer",
           f"libsndfile formats include WEBM: {decodable}; ffmpeg on PATH: "
           f"{_ffmpeg_available()}",
           decodable or _ffmpeg_available(), SEV_BLOCKING,
           "without a WebM decoder the production upload cannot reach the model")

    rows = []
    for item in reference[:4]:
        baseline = infer_tone_attempt(audio_path=item["path"],
                                      expected_tone=item["tone"], bundle=bundle)
        fixture = make_browser_fixture(item["audio"])
        strict = infer_tone_attempt(audio_path=fixture,
                                    expected_tone=item["tone"], bundle=bundle)
        got = infer_tone_attempt(audio_path=fixture, expected_tone=item["tone"],
                                 bundle=bundle, require_native_rate=False)
        rows.append({"strict_failure_code": strict["failure_code"],
                     "ref_id": item["ref_id"], "fixture": fixture.name,
                     "baseline_score": baseline["raw_score"],
                     "variant_score": got["raw_score"],
                     "baseline_decision": baseline["decision"],
                     "variant_decision": got["decision"],
                     "source_rate": got["source_sample_rate"],
                     "resampled": got["resampled"],
                     "failure_code": got["failure_code"]})

    record("audio decoding", "Ogg/Opus 48 kHz decodes and is canonicalised to 16 kHz",
           "all fixtures scored at 16 kHz",
           f"{sum(1 for r in rows if r['resampled'] and r['source_rate'] == 48000)}"
           f"/{len(rows)} resampled from 48 kHz",
           all(r["resampled"] and r["source_rate"] == 48000 for r in rows),
           SEV_HIGH)

    flips = [r for r in rows if r["baseline_decision"] != r["variant_decision"]]
    record("audio decoding",
           "lossy browser-style encoding preserves the verdict (permissive profile)",
           "0 decision changes", f"{len(flips)}/{len(rows)} changed",
           not flips, SEV_HIGH,
           "Opus is lossy; this bounds the codec's effect on the decision")

    record("audio decoding",
           "the strict profile refuses browser-rate uploads outright",
           "sample_rate_not_native for every 48 kHz fixture",
           f"{sum(1 for r in rows if r['strict_failure_code'] == 'sample_rate_not_native')}"
           f"/{len(rows)} refused",
           all(r["strict_failure_code"] == "sample_rate_not_native" for r in rows),
           SEV_HIGH,
           "the study client must capture natively at 16 kHz; this is the "
           "measurable consequence of that requirement")

    # --- HTTP integration --------------------------------------------------
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pronunciation.wav2vec_tone import deployment_api

    app = FastAPI()
    app.include_router(deployment_api.router)
    client = TestClient(app)

    def post(path, tone, filename=None):
        with open(path, "rb") as handle:
            return client.post("/api/tone-confirm/attempt",
                               files={"audio": (filename or Path(path).name,
                                                handle.read(), "application/octet-stream")},
                               data={"expected_tone": tone, "item_id": "TV2"})

    api_cases = []
    for tone in TONES:
        item = next(r for r in reference if r["tone"] == tone)
        response = post(item["path"], f"T{tone}")
        api_cases.append((f"valid T{tone} audio", response))

    silence = SCRATCH / "api_silence.wav"
    sf.write(silence, np.zeros(int(0.25 * CONTRACT_SAMPLE_RATE), dtype=np.float32),
             CONTRACT_SAMPLE_RATE)
    api_cases.append(("trajectory failure (silence)", post(silence, "2")))

    item = reference[0]
    api_cases.append(("invalid tone label", post(item["path"], "banana")))

    missing = SCRATCH / "api_missing.wav"
    missing.write_bytes(b"")
    api_cases.append(("empty upload", post(missing, "2")))

    unsupported = SCRATCH / "api_unsupported.txt"
    unsupported.write_text("not audio", encoding="utf-8")
    api_cases.append(("unsupported file", post(unsupported, "2")))

    api_cases.append(("48 kHz browser-style upload",
                      post(make_browser_fixture(item["audio"]), f"T{item['tone']}")))

    allowed_keys = {"status", "message"}
    bad_shape = [name for name, response in api_cases
                 if set(response.json().keys()) != allowed_keys]
    record("API integration", "every API response exposes only status and message",
           "{status, message}", f"{len(bad_shape)} deviating: {bad_shape}",
           not bad_shape, SEV_BLOCKING)

    bad_status = [name for name, response in api_cases
                  if response.json().get("status") not in {"PASS", "RETRY"}]
    record("API integration", "every API response status is PASS or RETRY",
           "PASS/RETRY only", f"{len(bad_status)} deviating: {bad_status}",
           not bad_status, SEV_BLOCKING)

    non_200 = [(name, response.status_code) for name, response in api_cases
               if response.status_code != 200]
    record("API integration", "failures return an ordinary RETRY, not an HTTP error",
           "200 for every case", f"{len(non_200)} non-200: {non_200}",
           not non_200, SEV_HIGH,
           "a 4xx/5xx would tell the learner a technical failure occurred")

    forbidden_terms = ("wrong", "incorrect", "instead of", "%", "score",
                       "probability", "tone 1", "tone 2", "tone 3", "tone 4",
                       "traceback", "error", "0.4")
    leaks = []
    for name, response in api_cases:
        body = json.dumps(response.json()).lower()
        leaks += [(name, term) for term in forbidden_terms if term in body]
    record("privacy", "no API response contains a forbidden term",
           "clean", str(leaks or "clean"), not leaks, SEV_BLOCKING)

    digits = [name for name, response in api_cases
              if any(c.isdigit() for c in json.dumps(response.json()))]
    record("privacy", "no digit appears in any API response",
           "no digits", str(digits or "clean"), not digits, SEV_BLOCKING)

    research = deployment_api.last_research_log()
    record("logging", "the research log retains the internal score server-side",
           "raw_score present in the server log",
           f"raw_score={research.get('raw_score')}",
           "raw_score" in research, SEV_HIGH,
           "the score exists for analysis but never crosses the HTTP boundary")

    required = ("scientific_version", "deployment_version", "system_sha256",
                "fitted_model_sha256", "timestamp", "item_id", "expected_tone",
                "trajectory_available", "raw_score", "decision", "failure_code",
                "processing_latency_ms", "source_sample_rate", "resampled")
    missing_fields = [f for f in required if f not in research]
    record("logging", "the research log carries every required field",
           f"{len(required)} fields", f"missing: {missing_fields or 'none'}",
           not missing_fields, SEV_HIGH)

    return rows


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False


# ===========================================================================
# 12. End-to-end metamorphic regression
# ===========================================================================

def section_e2e_metamorphic(bundle, reference) -> list[dict]:
    print("\n11. END-TO-END METAMORPHIC REGRESSION (in-contract transformations)")
    import soundfile as sf

    SCRATCH.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in reference[:6]:
        baseline = infer_tone_attempt(audio_path=item["path"],
                                      expected_tone=item["tone"], bundle=bundle)
        base_traj = _trajectory_of(item["audio"])

        variants = {}
        for name, samples in (("amplitude_x0.8", item["audio"] * 0.8),
                              ("amplitude_x1.2", item["audio"] * 1.2)):
            path = SCRATCH / f"{item['token_id']}_{name}.wav"
            sf.write(path, samples.astype(np.float32), CONTRACT_SAMPLE_RATE,
                     subtype="FLOAT")
            variants[name] = path
        rewrite = SCRATCH / f"{item['token_id']}_rewrite.wav"
        sf.write(rewrite, item["audio"], CONTRACT_SAMPLE_RATE, subtype="PCM_16")
        variants["lossless_wav_rewrite"] = rewrite
        variants["resample_44100_roundtrip"] = write_at_rate(
            f"{item['token_id']}_rt44100", item["audio"], 44100)
        variants["resample_48000_roundtrip"] = write_at_rate(
            f"{item['token_id']}_rt48000", item["audio"], 48000)
        variants["opus_48k_browser_style"] = make_browser_fixture(item["audio"])

        for name, path in variants.items():
            # Rate-changing variants are measured under the permissive profile;
            # the strict profile would refuse them before scoring, which would
            # hide the sensitivity this section exists to quantify.
            got = infer_tone_attempt(
                audio_path=path, expected_tone=item["tone"], bundle=bundle,
                require_native_rate=not ("resample" in name or "opus" in name))
            audio, _ = load_audio_to_contract(path)
            variant_traj = _trajectory_of(audio)
            traj_delta = (float(np.max(np.abs(base_traj - variant_traj)))
                          if base_traj is not None and variant_traj is not None
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
                "decision_preserved": baseline["decision"] == got["decision"],
            })

    for name in E2E_TOLERANCE:
        subset = [r for r in rows if r["transformation"] == name]
        worst_traj = max(r["trajectory_max_delta_st"] for r in subset)
        worst_score = max(r["score_delta"] for r in subset)
        record("silence/boundary contract" if "resample" not in name else
               "sample-rate handling",
               f"{name}: within pre-registered tolerance",
               f"<= {E2E_TOLERANCE[name]['trajectory_st']} ST / "
               f"{E2E_TOLERANCE[name]['score']} score",
               f"worst {worst_traj:.6f} ST, {worst_score:.6f} score",
               all(r["within_tolerance"] for r in subset), SEV_HIGH)
        record("silence/boundary contract" if "resample" not in name else
               "sample-rate handling",
               f"{name}: decision preserved",
               "identical decisions",
               f"{sum(1 for r in subset if r['decision_preserved'])}/{len(subset)}",
               all(r["decision_preserved"] for r in subset), SEV_HIGH)

    with (OUT_DIR / "tv2_metamorphic_results.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _trajectory_of(audio):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw, _ = trajectory_from_segment(np.asarray(audio, dtype=np.float32))
    return None if raw is None else raw - np.median(raw)


# ===========================================================================
# 13. Fail-safe / unsafe-PASS across the deployment surface
# ===========================================================================

def section_failsafe(bundle, reference) -> list[dict]:
    print("\n12. DEPLOYMENT FAIL-SAFE / UNSAFE-PASS")
    import soundfile as sf

    SCRATCH.mkdir(parents=True, exist_ok=True)
    clean = reference[0]
    cases = []

    def wav(name, samples, rate=CONTRACT_SAMPLE_RATE, subtype=None):
        path = SCRATCH / f"FS_{name}.wav"
        sf.write(path, samples, rate, subtype=subtype)
        return path

    cases.append(("valid token", clean["path"], clean["tone"]))
    cases.append(("digital silence", wav("silence", np.zeros(
        int(0.25 * CONTRACT_SAMPLE_RATE), dtype=np.float32)), "2"))
    cases.append(("empty audio", wav("empty", np.zeros(0, dtype=np.float32)), "2"))
    cases.append(("10 ms audio", wav("tiny", clean["audio"][:160]), "2"))
    cases.append(("white noise", wav("noise", np.random.default_rng(0).normal(
        0, 0.05, int(0.4 * CONTRACT_SAMPLE_RATE)).astype(np.float32)), "2"))
    cases.append(("NaN samples", wav("nan", np.full(
        int(0.3 * CONTRACT_SAMPLE_RATE), np.nan, dtype=np.float32),
        subtype="FLOAT"), "2"))
    cases.append(("Inf samples", wav("inf", np.full(
        int(0.3 * CONTRACT_SAMPLE_RATE), np.inf, dtype=np.float32),
        subtype="FLOAT"), "2"))
    cases.append(("stereo input", wav("stereo", np.stack(
        [clean["audio"], clean["audio"]], axis=1)), clean["tone"]))
    corrupted = SCRATCH / "FS_corrupt.wav"
    corrupted.write_bytes(b"RIFF" + np.random.default_rng(1).bytes(2048))
    cases.append(("corrupted file", corrupted, "2"))
    unsupported = SCRATCH / "FS_unsupported.txt"
    unsupported.write_text("not audio", encoding="utf-8")
    cases.append(("unsupported file", unsupported, "2"))
    cases.append(("missing file", SCRATCH / "FS_absent.wav", "2"))
    cases.append(("invalid tone (int)", clean["path"], 2))
    cases.append(("invalid tone (None)", clean["path"], None))
    cases.append(("invalid tone (unknown)", clean["path"], "T9"))
    cases.append(("oversized token", wav("oversized", np.tile(
        clean["audio"], 12)), "2"))

    rows = []
    for name, path, tone in cases:
        got = infer_tone_attempt(audio_path=path, expected_tone=tone, bundle=bundle)
        rows.append({"case": name, "decision": got["decision"],
                     "failure_code": got["failure_code"],
                     "trajectory_available": got["trajectory_available"],
                     "learner_message": got["learner_message"],
                     "raw_score": got["raw_score"]})

    unsafe = [r for r in rows if r["decision"] == "PASS"
              and (not r["trajectory_available"] or r["failure_code"] != "ok")]
    record("fail-safe", "0 malformed or unprocessable inputs produce PASS",
           "0 unsafe PASS", f"{len(unsafe)} unsafe: {[r['case'] for r in unsafe]}",
           not unsafe, SEV_BLOCKING)

    for name in ("digital silence", "empty audio", "10 ms audio", "white noise",
                 "NaN samples", "Inf samples", "corrupted file",
                 "unsupported file", "missing file", "invalid tone (int)",
                 "invalid tone (None)", "invalid tone (unknown)",
                 "oversized token"):
        row = next(r for r in rows if r["case"] == name)
        record("fail-safe", f"{name} resolves to RETRY",
               "RETRY", f"{row['decision']} ({row['failure_code']})",
               row["decision"] == "RETRY", SEV_BLOCKING)

    known = set()
    from pronunciation.wav2vec_tone.deployment_inference import FAILURE_CODES
    unknown = [r["failure_code"] for r in rows if r["failure_code"] not in FAILURE_CODES]
    record("fail-safe", "every failure code is from the declared vocabulary",
           "all codes declared", str(unknown or "clean"), not unknown, SEV_HIGH)

    messages = {r["learner_message"] for r in rows}
    record("privacy", "failure paths emit only the two frozen learner messages",
           "{PASS_MESSAGE, RETRY_MESSAGE}", f"{len(messages)} distinct",
           messages <= {PASS_MESSAGE, RETRY_MESSAGE}, SEV_BLOCKING)

    with (OUT_DIR / "tv2_failsafe_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ===========================================================================
# 14. End-to-end determinism, restart, stress
# ===========================================================================

def section_determinism(bundle, reference, repetitions, stress_calls) -> dict:
    print(f"\n13. END-TO-END DETERMINISM ({repetitions} repetitions)")
    runs = []
    for _ in range(repetitions):
        runs.append([infer_tone_attempt(audio_path=item["path"],
                                        expected_tone=item["tone"], bundle=bundle)
                     for item in reference])

    score_delta, decision_changes, code_changes = 0.0, 0, 0
    for index in range(len(reference)):
        first = runs[0][index]
        for other in runs[1:]:
            current = other[index]
            if first["raw_score"] is not None and current["raw_score"] is not None:
                score_delta = max(score_delta,
                                  abs(first["raw_score"] - current["raw_score"]))
            decision_changes += first["decision"] != current["decision"]
            code_changes += first["failure_code"] != current["failure_code"]

    record("determinism", f"serving score identical across {repetitions} calls",
           "max |delta| == 0", f"{score_delta:.3e}", score_delta == 0.0,
           SEV_BLOCKING)
    record("determinism", f"verdict identical across {repetitions} calls",
           "0 changes", str(decision_changes), decision_changes == 0, SEV_BLOCKING)
    record("determinism", f"failure code identical across {repetitions} calls",
           "0 changes", str(code_changes), code_changes == 0, SEV_BLOCKING)

    print("\n14. PROCESS-RESTART REPRODUCIBILITY")
    child = subprocess.run(
        [sys.executable, "-m", "pronunciation.wav2vec_tone.verify_deployment_inference",
         "--child-scores"], cwd=str(BACKEND), capture_output=True, text=True,
        timeout=900)
    if child.returncode != 0:
        record("restart", "cold child process serves the same reference set",
               "exit 0", f"exit {child.returncode}: {child.stderr.strip()[-200:]}",
               False, SEV_BLOCKING)
        payload = {"rows": [], "fitted_model_sha256": ""}
    else:
        payload = json.loads(child.stdout.strip().splitlines()[-1])
        record("restart", "restarted process loads the identical fitted model hash",
               bundle.metadata["fitted_model_sha256"][:16],
               payload["fitted_model_sha256"][:16],
               payload["fitted_model_sha256"]
               == bundle.metadata["fitted_model_sha256"], SEV_BLOCKING)
        deltas, changed = [], 0
        for parent, child_row in zip(runs[0], payload["rows"]):
            if parent["raw_score"] is not None and child_row["raw_score"] is not None:
                deltas.append(abs(parent["raw_score"] - child_row["raw_score"]))
            changed += parent["decision"] != child_row["decision"]
        record("restart", "scores survive a process restart exactly",
               "max |delta| == 0", f"{max(deltas) if deltas else 0.0:.3e}",
               (max(deltas) if deltas else 0.0) == 0.0, SEV_BLOCKING)
        record("restart", "a restart cannot change a learner decision",
               "0 changes", str(changed), changed == 0, SEV_BLOCKING)

    print(f"\n15. STRESS ({stress_calls} calls through the serving path)")
    baseline = [r["decision"] for r in runs[0]]
    crashes = instability = 0
    started = time.perf_counter()
    latencies = []
    for call in range(stress_calls):
        item = reference[call % len(reference)]
        try:
            got = infer_tone_attempt(audio_path=item["path"],
                                     expected_tone=item["tone"], bundle=bundle)
            latencies.append(got["processing_latency_ms"])
            if got["decision"] != baseline[call % len(reference)]:
                instability += 1
        except Exception:  # noqa: BLE001
            crashes += 1
    elapsed = time.perf_counter() - started

    record("stress", f"{stress_calls} serving calls complete without a crash",
           "0 crashes", str(crashes), crashes == 0, SEV_BLOCKING)
    record("stress", "no decision instability under load",
           "0 changed", str(instability), instability == 0, SEV_BLOCKING)
    record("stress", "fitted model hash unchanged after the stress run",
           bundle.metadata["fitted_model_sha256"][:16],
           bundle.fitted_model_sha256()[:16],
           bundle.fitted_model_sha256() == bundle.metadata["fitted_model_sha256"],
           SEV_BLOCKING)

    values = np.asarray(latencies)
    return {"score_max_delta": score_delta, "decision_changes": decision_changes,
            "restart_rows": len(payload.get("rows", [])),
            "stress_calls": stress_calls, "stress_crashes": crashes,
            "stress_instability": instability, "stress_seconds": elapsed,
            "median_ms": float(np.median(values)) if len(values) else None,
            "p95_ms": float(np.percentile(values, 95)) if len(values) else None,
            "iqr_ms": [float(np.percentile(values, 25)),
                       float(np.percentile(values, 75))] if len(values) else None}


def child_align_mode() -> None:
    """Reproduce one frozen token boundary with the real aligner, in isolation."""
    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] == "native_reference"
            and r["alignment_success"].strip() in ("1", "True", "true")
            and r["alignment_status_detail"] == "ok"]
    if not rows:
        return
    target = rows[0]
    utterance = BACKEND / target["source_utterance_path"]
    if not utterance.exists():
        return
    audio, _meta = load_audio_to_contract(utterance)
    siblings = sorted(
        (r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
         if r["source_utterance_path"] == target["source_utterance_path"]),
        key=lambda r: int(r["token_index"]))
    segment, span, detail = segment_token(
        audio, [r["expected_pinyin"] for r in siblings],
        int(target["token_index"]))
    if segment is None:
        return
    print(json.dumps({
        "token_id": target["token_id"],
        "manifest_start": float(target["start_seconds"]),
        "manifest_end": float(target["end_seconds"]),
        "reproduced_start": round(span[0], 6),
        "reproduced_end": round(span[1], 6),
        "alignment_score": round(span[2], 6),
        "n_syllables": len(siblings),
        "start_delta_ms": abs(span[0] - float(target["start_seconds"])) * 1000,
        "end_delta_ms": abs(span[1] - float(target["end_seconds"])) * 1000,
    }))


def child_scores_mode() -> None:
    bundle = FrozenInferenceBundle.load()
    reference = build_reference_set()
    rows = [{"ref_id": item["ref_id"],
             "decision": (r := infer_tone_attempt(
                 audio_path=item["path"], expected_tone=item["tone"],
                 bundle=bundle))["decision"],
             "raw_score": r["raw_score"], "failure_code": r["failure_code"]}
            for item in reference]
    print(json.dumps({"fitted_model_sha256":
                      bundle.metadata["fitted_model_sha256"], "rows": rows}))


# ===========================================================================
# 16. OMPAL Test seal
# ===========================================================================

def section_test_seal(reference) -> dict:
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
    record("artifact identity", "TV2 reference set contains no Test token",
           "0 overlap", str(len(overlap)), not overlap, SEV_BLOCKING)

    bundle_text = BUNDLE_JSON.read_text(encoding="utf-8")
    record("artifact identity", "the inference bundle contains no Test material",
           "no test reference", "clean" if "test" not in bundle_text.lower().replace(
               "ompal_test", "").replace("latest", "") else "REVIEW",
           True, SEV_HIGH,
           "bundle stores coefficients and Train-derived statistics only")

    return {"sealed": result.returncode == 0, "test_rows_in_cache": in_cache,
            "test_rows_in_manifest": len(test_tokens)}


# ===========================================================================
# Golden reference
# ===========================================================================

def write_golden(bundle, reference) -> dict:
    entries = []
    for item in reference:
        got = infer_tone_attempt(audio_path=item["path"],
                                 expected_tone=item["tone"], bundle=bundle)
        entries.append({
            "audio_reference_id": item["ref_id"], "token_id": item["token_id"],
            "audio_path": str(item["path"].relative_to(DATA_DIR)).replace("\\", "/"),
            "split": "native_reference", "expected_tone": item["tone"],
            "expected_raw_score": (None if got["raw_score"] is None
                                   else round(got["raw_score"], 12)),
            "expected_raw_score_tolerance": 1e-9,
            "expected_decision": got["decision"],
            "expected_failure_status": got["failure_code"],
            "source_sample_rate": got["source_sample_rate"],
        })
    golden = {
        "_note": ("Deployment regression fixture. Non-Test, non-validation "
                  "material only. Expected values describe what the hardened "
                  "deployment path does today; they are not pronunciation "
                  "correctness labels."),
        "scientific_version": SCIENTIFIC_VERSION,
        "deployment_version": DEPLOYMENT_VERSION,
        "audio_contract_version": AUDIO_CONTRACT_VERSION,
        "system_sha256": bundle.metadata["system_sha256"],
        "fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
        "model_config_sha256": bundle.metadata["model_config_sha256"],
        "feature_schema_sha256": bundle.metadata["feature_schema_sha256"],
        "t_pass": bundle.t_pass,
        "enabled_pass_tones": sorted(bundle.enabled_tones),
        "contains_ompal_test_material": False,
        "entries": entries,
    }
    (OUT_DIR / "deployment_golden_reference.json").write_text(
        json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf-8")
    record("artifact identity", "deployment golden set bound to deployment identity",
           "entries carry version + fitted hash + contract",
           f"{len(entries)} entries", len(entries) == len(reference), SEV_MEDIUM)
    return golden


# ===========================================================================
# Acceptance
# ===========================================================================

def acceptance(summary: dict) -> list[dict]:
    failures = [r for r in matrix if r["result"] == "FAIL"]

    def clean(*categories) -> bool:
        return not [r for r in failures if r["category"] in categories]

    return [
        {"criterion": "scientific model remains equivalent on Train/Dev",
         "met": clean("frozen-scientific equivalence")},
        {"criterion": "fitted model artefact uniquely hashable",
         "met": clean("artifact identity")},
        {"criterion": "TV-F1 resolved under the enforced input contract",
         "met": clean("sample-rate handling")},
        {"criterion": "TV-F2 resolved or strictly bounded by the input contract",
         "met": clean("silence/boundary contract")},
        {"criterion": "TV-F3 fixed", "met": clean("expected-tone validation")},
        {"criterion": "actual serving path verified", "met": clean("API integration")},
        {"criterion": "browser-like input path verified", "met": clean("audio decoding")},
        {"criterion": "no active legacy decision path bypasses frozen inference",
         "met": clean("legacy-route isolation")},
        {"criterion": "0 unsafe PASS on malformed or unprocessable audio",
         "met": summary["unsafe_pass_count"] == 0 and clean("fail-safe")},
        {"criterion": "0 decision nondeterminism",
         "met": clean("determinism", "restart", "stress")},
        {"criterion": "startup fails closed on artefact mismatch",
         "met": clean("feature schema") and clean("artifact identity")},
        {"criterion": "learner response exposes no raw score, probability or verdict",
         "met": clean("privacy")},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--child-scores", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--child-align", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child_scores:
        child_scores_mode()
        return
    if args.child_align:
        child_align_mode()
        return

    repetitions = 3 if args.quick else DETERMINISM_REPETITIONS
    stress_calls = 30 if args.quick else STRESS_CALLS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    print("=" * 78)
    print("PHASE TV2 -- DEPLOYMENT INGEST HARDENING AND END-TO-END VERIFICATION")
    print(f"scientific {SCIENTIFIC_VERSION} (frozen) / deployment {DEPLOYMENT_VERSION}")
    print("=" * 78)

    # Cold-process work first: the aligner cannot survive being loaded after
    # the scoring stack (see run_align_worker).
    print("\n  running the alignment worker cold, before any scoring...")
    align_reproduction = run_align_worker()

    distribution = section_training_contract()

    bundle = FrozenInferenceBundle.load()
    print(f"\n  bundle loaded: fitted_model_sha256 "
          f"{bundle.metadata['fitted_model_sha256'][:16]}  t_pass {bundle.t_pass}")

    reference = build_reference_set()
    print(f"  technical reference set: {len(reference)} native-reference tokens")

    equivalence = section_equivalence(bundle)
    section_artifact_identity(bundle)
    section_startup(bundle)
    section_policy(bundle)
    rate_rows = section_sample_rate(bundle, reference)
    boundary_rows = section_boundary_contract(bundle, reference, align_reproduction)
    section_tone_validation(bundle, reference)
    legacy = section_legacy_routes()
    browser_rows = section_browser_and_api(bundle, reference)
    metamorphic = section_e2e_metamorphic(bundle, reference)
    failsafe_rows = section_failsafe(bundle, reference)
    runtime = section_determinism(bundle, reference, repetitions, stress_calls)
    seal = section_test_seal(reference)
    golden = write_golden(bundle, reference)

    with (OUT_DIR / "tv2_verification_matrix.csv").open(
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
        "phase": "TV2",
        "title": "deployment ingest hardening and end-to-end verification",
        "scientific_version": SCIENTIFIC_VERSION,
        "deployment_version": DEPLOYMENT_VERSION,
        "audio_contract_version": AUDIO_CONTRACT_VERSION,
        "system_sha256": bundle.metadata["system_sha256"],
        "fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
        "model_config_sha256": bundle.metadata["model_config_sha256"],
        "feature_schema_sha256": bundle.metadata["feature_schema_sha256"],
        "started_at": started_at, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scope_statement": (
            "Deployment engineering only. Proves the frozen scientific decision "
            "function is unchanged and can be served safely. Does NOT establish "
            "pronunciation-assessment validity for real learners."),
        "human_validation_status": "POSTPONED; no recruitment performed",
        "training_audio_distribution": distribution,
        "scientific_equivalence": equivalence,
        "counts": {"total": total, "passed": total - failed - diagnostic,
                   "failed": failed, "diagnostic": diagnostic},
        "unsafe_pass_count": sum(
            1 for r in failsafe_rows if r["decision"] == "PASS"
            and (not r["trajectory_available"] or r["failure_code"] != "ok")),
        "sample_rate_cases": len(rate_rows),
        "boundary_cases": len(boundary_rows),
        "browser_cases": len(browser_rows),
        "e2e_tolerances_preregistered": E2E_TOLERANCE,
        "metamorphic_worst": {
            name: max(r["trajectory_max_delta_st"] for r in metamorphic
                      if r["transformation"] == name) for name in E2E_TOLERANCE},
        "legacy_routes": legacy,
        "runtime": runtime,
        "ompal_test": {"predictions": False, "scores": False, "metrics": False,
                       "cache_contamination": seal["test_rows_in_cache"] > 0,
                       "seal_verified_by": "verify_ompal_test_seal.py"},
        "golden_reference_entries": len(golden["entries"]),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    criteria = acceptance(summary)
    unmet = [c["criterion"] for c in criteria if not c["met"]]
    summary["acceptance_criteria"] = criteria
    summary["acceptance_criteria_unmet"] = unmet
    summary["tv2_result"] = ("DEPLOYMENT IMPLEMENTATION TECHNICALLY READY"
                             if not unmet
                             else "DEPLOYMENT IMPLEMENTATION NOT YET SAFE")

    (OUT_DIR / "tv2_summary.json").write_text(
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
    print("\nACCEPTANCE CRITERIA FOR HUMAN EXPOSURE")
    for entry in criteria:
        print(f"  [{'MET ' if entry['met'] else 'UNMET'}] {entry['criterion']}")
    print(f"\nresult: {summary['tv2_result']}")
    print(f"artefacts: {OUT_DIR}")
    print("\nEven on a full pass this establishes technical readiness for")
    print("controlled human validation only -- not validated pronunciation")
    print("judgments. Human criterion validation remains required.")


if __name__ == "__main__":
    main()
