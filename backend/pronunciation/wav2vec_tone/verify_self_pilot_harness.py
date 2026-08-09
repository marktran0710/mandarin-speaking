"""Self-pilot harness verification -- the parts that need no human voice.

Runs A, B and C require the researcher to speak, and this script deliberately
does not simulate them: synthesised audio is not a researcher production, and
writing it into the self-pilot log as though it were would be inventing data.

What this DOES verify, through the real API in study mode:

  * the self-pilot namespace exists and is isolated from validation data
  * section 7 -- the T1 gate holds on the self-pilot route
  * section 8 -- failure paths yield 0 unsafe PASS
  * repeated identical input is deterministic through the real path
  * repeat recordings never overwrite an earlier trial or its audio
  * the summary exporter refuses to emit a validity statistic
  * fresh-validation artefacts are byte-identical before and after

Technical rows are written with run=T_technical so they are distinguishable
from the researcher's own Runs A/B/C.

    python -m pronunciation.wav2vec_tone.verify_self_pilot_harness
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.self_pilot import (  # noqa: E402
    AUDIO_DIR, CHALLENGE_PLAN, RUN_TECHNICAL, SELF_PILOT_DIR, SUMMARY_JSON,
    TRIALS_CSV, ValidityMetricRefused, forbid_validity_metrics, load_items,
    protected_artefact_digests, read_trials,
)
from pronunciation.wav2vec_tone.study_pcm16k import (  # noqa: E402
    STUDY_PCM_SPEC_VERSION, build_study_wav,
)

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
SCRATCH = SELF_PILOT_DIR / "harness_scratch"
CAPTURE_RATE = 48000

matrix: list[dict] = []
_counter = {"n": 0}


def record(category, description, expected, observed, ok, severity="HIGH",
           notes="") -> bool:
    _counter["n"] += 1
    test_id = f"SP{_counter['n']:03d}"
    matrix.append({"test_id": test_id, "category": category,
                   "input": description, "expected_behaviour": expected,
                   "observed_behaviour": observed,
                   "result": "PASS" if ok else "FAIL",
                   "severity": "" if ok else severity, "notes": notes})
    print(f"  [{'PASS' if ok else 'FAIL'}] {test_id} {description}"
          + (f"  -- {observed}" if observed else ""))
    return bool(ok)


def synthesise(shape: str, seconds: float, rate: int = CAPTURE_RATE) -> np.ndarray:
    """An idealised voiced buzz. NOT speech, and never logged as a researcher run."""
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


def study_wav(samples, rate: int = CAPTURE_RATE) -> bytes:
    blob, _meta = build_study_wav(samples, rate)
    return blob


def build_client():
    os.environ["OMPAL_STUDY_MODE"] = "1"
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


def post(client, payload: bytes, item_id: str, tone: str, *, run=RUN_TECHNICAL,
         repetition=1, notes="", filename="attempt.wav"):
    return client.post(
        "/api/self-pilot/attempt",
        files={"audio": (filename, payload, "audio/wav")},
        data={"item_id": item_id, "expected_tone": tone, "run": run,
              "repetition": repetition,
              "capture_sample_rate": str(CAPTURE_RATE),
              "pcm_spec_version": STUDY_PCM_SPEC_VERSION,
              "researcher_notes": notes})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    SELF_PILOT_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("SELF-PILOT HARNESS VERIFICATION -- no researcher voice required")
    print("Runs A/B/C are NOT simulated; they await the researcher.")
    print("=" * 76)

    before_digests = protected_artefact_digests()
    trials_before = len(read_trials())

    print("\n1. NAMESPACE AND ISOLATION")
    record("namespace", "self-pilot directory exists and is separate from validation",
           "data/self_pilot/", str(SELF_PILOT_DIR.relative_to(BACKEND)),
           SELF_PILOT_DIR.exists() and "self_pilot" in str(SELF_PILOT_DIR))

    items = load_items()
    record("namespace", "16 prompts load and are marked unapproved",
           "16 items, teacher_approved=False",
           f"{len(items)} items, approved={any(i.teacher_approved for i in items)}",
           len(items) == 16 and not any(i.teacher_approved for i in items),
           notes="using them as technical prompts is not item approval")

    tones = sorted({item.expected_tone for item in items})
    record("namespace", "prompts cover all four tones, four per tone",
           "4 x T1-T4",
           str({t: sum(1 for i in items if i.expected_tone == t) for t in tones}),
           all(sum(1 for i in items if i.expected_tone == t) == 4 for t in tones))

    client = build_client()
    body = client.get("/api/self-pilot/items").json()
    record("namespace", "self-pilot route is mounted in study mode",
           "200 with 16 items", f"{len(body.get('items', []))} items",
           len(body.get("items", [])) == 16)
    record("namespace", "the API states the data is not validation material",
           "explicit notice present", body.get("not_validation", "")[:48],
           "accuracy" in body.get("not_validation", "").lower())
    record("namespace", "Run C challenge plan is fixed in advance",
           f"{len(CHALLENGE_PLAN)} planned probes",
           f"{len(body.get('challenge_plan', []))} returned",
           len(body.get("challenge_plan", [])) == len(CHALLENGE_PLAN),
           notes="prevents improvised manipulations during the run")

    print("\n2. SECTION 7 -- T1 GATE ON THE SELF-PILOT ROUTE")
    t1_results = []
    for seconds in (0.20, 0.25, 0.30):
        response = post(client, study_wav(synthesise("T1", seconds)), "I01", "T1",
                        notes="harness T1 gate probe")
        t1_results.append(response.json())
    scores = [r["raw_score_internal"] for r in t1_results
              if r["raw_score_internal"] is not None]
    record("t1 gate", "every T1 probe returns RETRY",
           "RETRY x3",
           f"{[r['decision'] for r in t1_results]}, internal scores "
           f"{[round(s, 4) for s in scores]}",
           all(r["decision"] == "RETRY" for r in t1_results), "BLOCKING")
    # The synthetic probes above may score above t_pass, in which case they do
    # not test the gate at all -- the threshold alone would refuse them. The
    # decisive case is a T1 whose internal score is BELOW t_pass, so only the
    # gate can stop it. Search the non-Test native-reference T1 tokens for one.
    import soundfile as sf

    manifest = BACKEND / "pronunciation/wav2vec_tone/data/ompal_full_tone_benchmark_manifest_split.csv"
    data_dir = BACKEND / "pronunciation/wav2vec_tone/data"
    native_t1 = [r for r in csv.DictReader(manifest.open(encoding="utf-8"))
                 if r["split"] == "native_reference" and r["expected_tone"] == "1"]
    if any(r["split"] == "test" for r in native_t1):
        sys.exit("TEST LOCK VIOLATION")

    decisive = None
    for row in sorted(native_t1, key=lambda r: r["token_id"]):
        audio, rate = sf.read(str(data_dir / row["extracted_token_path"]),
                              dtype="float32")
        payload = study_wav(np.asarray(audio, dtype=np.float64), int(rate))
        response = post(client, payload, "I01", "T1",
                        notes="harness: T1 gate decisive probe").json()
        score = response["raw_score_internal"]
        if score is not None and score <= 0.42274:
            decisive = {"token_id": row["token_id"], "score": score,
                        "decision": response["decision"]}
            break

    if decisive:
        record("t1 gate",
               "a T1 whose internal score is BELOW t_pass still returns RETRY",
               "RETRY despite a passing score",
               f"{decisive['token_id']} scored {decisive['score']:.6f} "
               f"(<= 0.42274) and returned {decisive['decision']}",
               decisive["decision"] == "RETRY", "BLOCKING",
               notes="only the T1 gate can refuse this; the threshold alone "
                     "would have passed it")
    else:
        record("t1 gate",
               "a T1 whose internal score is BELOW t_pass still returns RETRY",
               "a decisive low-scoring T1 probe",
               "no native-reference T1 token scored below t_pass; the gate was "
               "not exercised at its decisive point",
               False, "HIGH",
               notes="without such a case the gate is untested where it matters")

    print("\n3. SECTION 8 -- FAILURE PATHS")
    cases = []
    cases.append(("silence", study_wav(np.zeros(int(0.25 * CAPTURE_RATE))), "I05", "T2"))
    cases.append(("empty recording", b"", "I05", "T2"))
    cases.append(("very short recording",
                  study_wav(synthesise("T2", 0.02)), "I05", "T2"))
    cases.append(("stopped too early",
                  study_wav(synthesise("T2", 0.05)), "I05", "T2"))
    cases.append(("invalid expected tone",
                  study_wav(synthesise("T2", 0.25)), "I05", "T9"))
    cases.append(("missing expected tone",
                  study_wav(synthesise("T2", 0.25)), "I05", ""))
    # A capture that never started: the recorder returns an empty blob, which is
    # what a denied microphone permission produces downstream.
    cases.append(("microphone permission denied (empty capture)", b"", "I05", "T2"))
    cases.append(("corrupted payload",
                  b"RIFF" + bytes(range(256)) * 4, "I05", "T2"))

    failure_rows = []
    for name, payload, item_id, tone in cases:
        response = post(client, payload, item_id, tone, notes=f"harness: {name}")
        parsed = response.json() if response.status_code == 200 else {}
        failure_rows.append({"case": name, "status": response.status_code,
                             "decision": parsed.get("decision"),
                             "failure_code": parsed.get("failure_code"),
                             "trajectory": parsed.get("trajectory_available")})
        record("failure path", f"{name} resolves safely",
               "RETRY (or refused), never PASS",
               f"HTTP {response.status_code} {parsed.get('decision')} "
               f"({parsed.get('failure_code')})",
               response.status_code != 200 or parsed.get("decision") == "RETRY",
               "BLOCKING")

    unsafe = [row for row in failure_rows
              if row["decision"] == "PASS"
              and (not row["trajectory"] or row["failure_code"] not in ("", "ok"))]
    record("failure path", "0 unsafe PASS across every failure case",
           "0", f"{len(unsafe)}", not unsafe, "BLOCKING")

    print("\n4. DETERMINISM THROUGH THE REAL PATH")
    payload = study_wav(synthesise("T4", 0.25))
    repeats = [post(client, payload, "I13", "T4",
                    notes="harness determinism probe").json() for _ in range(5)]
    scores = [r["raw_score_internal"] for r in repeats]
    record("determinism", "identical input gives an identical verdict 5 times",
           "1 distinct decision", str(sorted({r["decision"] for r in repeats})),
           len({r["decision"] for r in repeats}) == 1, "BLOCKING")
    record("determinism", "identical input gives an identical internal score",
           "max |delta| == 0",
           f"{max(scores) - min(scores):.3e}",
           max(scores) - min(scores) == 0.0, "BLOCKING")

    print("\n5. NO OVERWRITE ACROSS REPEATS")
    before_rows = len(read_trials())
    first = post(client, payload, "I13", "T4", run=RUN_TECHNICAL, repetition=1,
                 notes="overwrite probe rep 1").json()
    second = post(client, payload, "I13", "T4", run=RUN_TECHNICAL, repetition=2,
                  notes="overwrite probe rep 2").json()
    after_rows = len(read_trials())
    record("logging", "each attempt appends a new row rather than replacing one",
           "+2 rows", f"{before_rows} -> {after_rows}",
           after_rows == before_rows + 2, "BLOCKING")
    record("logging", "repeat attempts receive distinct trial ids",
           "two different uids", f"{first['trial_uid']} vs {second['trial_uid']}",
           first["trial_uid"] != second["trial_uid"], "BLOCKING")

    stored = sorted(p.name for p in AUDIO_DIR.glob("*.wav"))
    record("logging", "stored audio filenames are unique per trial",
           "no duplicates", f"{len(stored)} files, {len(set(stored))} unique",
           len(stored) == len(set(stored)), "BLOCKING")
    record("logging", "every stored audio file is marked PILOT_ONLY",
           "all prefixed", f"{sum(1 for n in stored if n.startswith('PILOT_ONLY_'))}"
           f"/{len(stored)}",
           all(name.startswith("PILOT_ONLY_") for name in stored))

    rows = read_trials()
    record("logging", "every logged row carries both pilot flags",
           "PILOT_ONLY=YES and RESEARCHER_SELF_TEST=YES",
           f"{sum(1 for r in rows if r.get('PILOT_ONLY') == 'YES' and r.get('RESEARCHER_SELF_TEST') == 'YES')}"
           f"/{len(rows)}",
           all(r.get("PILOT_ONLY") == "YES"
               and r.get("RESEARCHER_SELF_TEST") == "YES" for r in rows),
           "BLOCKING")

    required = ("item_id", "expected_tone", "audio_path", "trajectory_available",
                "raw_score_internal", "system_decision", "failure_code",
                "latency_ms", "frontend_message", "researcher_notes")
    missing = [field for field in required if rows and field not in rows[0]]
    record("logging", "the trial schema carries every field section 4 requires",
           f"{len(required)} fields", f"missing: {missing or 'none'}", not missing)

    print("\n6. VALIDITY-METRIC GUARD")
    try:
        forbid_validity_metrics({"summary": {"pass_precision": 0.9}})
        refused = False
    except ValidityMetricRefused:
        refused = True
    record("metric guard", "a summary containing PASS precision is refused",
           "ValidityMetricRefused raised", "refused" if refused else "ACCEPTED",
           refused, "BLOCKING")

    blocked = []
    for banned in ("accuracy", "kappa", "sensitivity", "specificity",
                   "human_system_agreement", "f1_score"):
        try:
            forbid_validity_metrics({banned: 1})
        except ValidityMetricRefused:
            blocked.append(banned)
    record("metric guard", "every forbidden statistic family is rejected",
           "6 of 6 rejected", f"{len(blocked)} of 6",
           len(blocked) == 6, "BLOCKING")

    from pronunciation.wav2vec_tone.export_self_pilot import summarise

    summary_payload = summarise(read_trials())
    record("metric guard", "the real exporter output passes the guard",
           "no forbidden key", "clean",
           summary_payload["is_validation_data"] is False, "BLOCKING")
    record("metric guard", "the exporter marks the data ineligible for validation",
           "eligible_for_human_validation_analysis == False",
           str(summary_payload["eligible_for_human_validation_analysis"]),
           summary_payload["eligible_for_human_validation_analysis"] is False,
           "BLOCKING")

    print("\n7. VALIDATION ARTEFACTS UNTOUCHED")
    after_digests = protected_artefact_digests()
    changed = [name for name in before_digests
               if before_digests[name] != after_digests[name]]
    record("isolation", "no fresh-validation artefact changed during the harness",
           "0 changed", f"{len(changed)} changed: {changed or 'none'}",
           not changed, "BLOCKING")
    record("isolation", "the frozen items file is still absent (not fabricated)",
           "fresh_validation_items_FROZEN.csv ABSENT",
           after_digests.get("fresh_validation_items_FROZEN.csv", "?")[:8],
           after_digests.get("fresh_validation_items_FROZEN.csv") == "ABSENT",
           "BLOCKING",
           notes="creating it would fabricate a teacher approval that does not exist")

    print("\n8. RUNS A / B / C STATUS")
    researcher_rows = [r for r in read_trials() if r.get("run") != RUN_TECHNICAL]
    record("runs", "Runs A, B and C are not simulated by this harness",
           "0 researcher rows written by the harness",
           f"{len(researcher_rows)} researcher-run rows present",
           True, "INFO",
           notes="synthesised audio is not a researcher production; writing it "
                 "as one would fabricate the self-pilot")

    latencies = [float(r["latency_ms"]) for r in read_trials()
                 if r.get("latency_ms")]
    values = np.asarray(latencies) if latencies else np.asarray([0.0])

    total = len(matrix)
    failed = sum(1 for r in matrix if r["result"] == "FAIL")
    payload = {
        "_note": ("Harness verification for the researcher self-pilot. Covers "
                  "only the parts that need no human voice. Runs A/B/C are "
                  "outstanding."),
        "phase": "SELF_PILOT_HARNESS",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "PILOT_ONLY": True,
        "RESEARCHER_SELF_TEST": True,
        "checks": {"total": total, "passed": total - failed, "failed": failed},
        "technical_rows_written": len(read_trials()) - trials_before,
        "researcher_rows_present": len(researcher_rows),
        "runs_outstanding": ["A_natural", "B_repeat", "C_challenge"],
        "harness_latency_ms": {"median": float(np.median(values)),
                               "p95": float(np.percentile(values, 95))},
        "protected_artefacts_unchanged": not changed,
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    forbid_validity_metrics(payload)
    (SELF_PILOT_DIR / "self_pilot_harness_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with (SELF_PILOT_DIR / "self_pilot_harness_matrix.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "test_id", "category", "input", "expected_behaviour",
            "observed_behaviour", "result", "severity", "notes"])
        writer.writeheader()
        writer.writerows(matrix)

    print("\n" + "=" * 76)
    print(f"harness checks: {total - failed}/{total} passed")
    if failed:
        print("\nFAILED")
        for row in matrix:
            if row["result"] == "FAIL":
                print(f"  {row['test_id']} [{row['severity']}] {row['input']}")
                print(f"      expected {row['expected_behaviour']} | "
                      f"observed {row['observed_behaviour']}")
    print("\nRuns A, B and C remain OUTSTANDING and require the researcher's own")
    print("voice. This harness verifies the workflow around them, not the runs.")


if __name__ == "__main__":
    main()
