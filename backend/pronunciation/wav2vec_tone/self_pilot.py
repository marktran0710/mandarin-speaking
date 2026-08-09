"""Researcher self-pilot -- workflow rehearsal, NOT validation.

The self-pilot exists to answer operational questions only:

  * does the whole study workflow run?
  * does the researcher hit technical failures or confusing behaviour?
  * are the PASS/RETRY messages understandable?
  * do deliberate challenge recordings produce technically plausible reactions?
  * is the path deterministic through the real frontend and API?

It does NOT ask whether the system is right about Mandarin pronunciation. The
researcher is not an independent criterion, so nothing here may be turned into
accuracy, PASS precision, sensitivity, specificity, agreement or kappa. That
prohibition is enforced in code (see `forbid_validity_metrics`), not just in
prose.

Every artefact is written under data/self_pilot/ and every row carries
PILOT_ONLY=YES and RESEARCHER_SELF_TEST=YES so it can never be confused with
fresh-validation data.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
SELF_PILOT_DIR = DATA_DIR / "self_pilot"
AUDIO_DIR = SELF_PILOT_DIR / "audio"
TRIALS_CSV = SELF_PILOT_DIR / "self_pilot_trials.csv"
SUMMARY_JSON = SELF_PILOT_DIR / "self_pilot_summary.json"
ITEMS_CSV = DATA_DIR / "fresh_validation_items.csv"

# Datasets the self-pilot must never touch.
PROTECTED_ARTEFACTS = (
    "fresh_validation_trials.csv",
    "fresh_validation_participants_TEMPLATE.csv",
    "fresh_validation_collection_tracker_TEMPLATE.csv",
    "fresh_validation_external_signoff.json",
    "fresh_validation_items_FROZEN.csv",
)

RUN_A = "A_natural"
RUN_B = "B_repeat"
RUN_C = "C_challenge"
RUN_TECHNICAL = "T_technical"
VALID_RUNS = (RUN_A, RUN_B, RUN_C, RUN_TECHNICAL)

# Run C manipulations, fixed in advance so the researcher does not improvise.
# These are DIAGNOSTIC probes. They are NOT verified Mandarin tone errors and
# must never be treated as labelled incorrect productions.
CHALLENGE_PLAN = (
    {"item_id": "I05", "expected_tone": "2", "challenge_type": "flatten",
     "intended_manipulation": "say ren with a level contour instead of rising"},
    {"item_id": "I07", "expected_tone": "2", "challenge_type": "invert_to_falling",
     "intended_manipulation": "say cha with a falling contour instead of rising"},
    {"item_id": "I09", "expected_tone": "3", "challenge_type": "invert_to_rising",
     "intended_manipulation": "say gou with a rising contour instead of dipping"},
    {"item_id": "I11", "expected_tone": "3", "challenge_type": "flatten",
     "intended_manipulation": "say ma with a level contour instead of dipping"},
    {"item_id": "I13", "expected_tone": "4", "challenge_type": "flatten",
     "intended_manipulation": "say fan with a level contour instead of falling"},
    {"item_id": "I16", "expected_tone": "4", "challenge_type": "invert_to_rising",
     "intended_manipulation": "say dian with a rising contour instead of falling"},
)

TRIAL_FIELDS = (
    "trial_uid", "recorded_at_utc", "run", "repetition", "item_id",
    "traditional_character", "expected_pinyin", "expected_tone", "audio_path",
    "capture_sample_rate", "pcm_spec_version", "source_sample_rate",
    "token_duration_ms", "trajectory_available", "raw_score_internal",
    "system_decision", "decision_reason", "failure_code", "latency_ms",
    "frontend_message", "technical_retry", "challenge_type",
    "intended_manipulation", "researcher_notes",
    "scientific_version", "deployment_version", "audio_contract_version",
    "fitted_model_sha256",
    "PILOT_ONLY", "RESEARCHER_SELF_TEST",
)

# Anything in this family is a validity claim the self-pilot may not make.
FORBIDDEN_METRICS = (
    "accuracy", "pass_precision", "precision", "recall", "sensitivity",
    "specificity", "agreement", "kappa", "auc", "f1", "correctness_rate",
    "error_rate", "hit_rate", "false_positive", "false_negative",
)


class ValidityMetricRefused(RuntimeError):
    """Raised when self-pilot data is asked to produce a validity statistic."""


def forbid_validity_metrics(payload: dict) -> None:
    """Fail loudly if a summary tries to smuggle in a validity statistic.

    The researcher is not the independent criterion. A number computed against
    their own productions would look like evidence and would not be. Making
    this an exception rather than a comment means a future edit cannot quietly
    reintroduce it.
    """
    def walk(node, trail=""):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                for banned in FORBIDDEN_METRICS:
                    if banned in lowered:
                        raise ValidityMetricRefused(
                            f"self-pilot summary may not contain {trail}{key!r}: "
                            f"the researcher is not an independent validation "
                            f"criterion")
                walk(value, f"{trail}{key}.")
        elif isinstance(node, list):
            for value in node:
                walk(value, trail)

    walk(payload)


@dataclass
class SelfPilotItem:
    item_id: str
    traditional_character: str
    expected_pinyin: str
    expected_tone: str
    english_gloss: str
    prompt_type: str
    teacher_approved: bool = False


def load_items() -> list[SelfPilotItem]:
    """The 16 proposed items, used here as TECHNICAL PROMPTS ONLY.

    These are still awaiting teacher review for the formal study. Running the
    self-pilot on them is not item approval and does not advance the D2 gate.
    """
    rows = list(csv.DictReader(ITEMS_CSV.open(encoding="utf-8-sig")))
    return [SelfPilotItem(
        item_id=row["item_id"],
        traditional_character=row["traditional_character"],
        expected_pinyin=row["expected_pinyin"],
        expected_tone=row["expected_tone"],
        english_gloss=row["english_gloss"],
        prompt_type=row["prompt_type"],
        teacher_approved=False,
    ) for row in rows]


def ensure_directories() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def next_trial_uid() -> str:
    existing = read_trials()
    return f"SP{len(existing) + 1:04d}"


def read_trials() -> list[dict]:
    if not TRIALS_CSV.exists():
        return []
    with TRIALS_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def append_trial(row: dict) -> dict:
    """Append one trial. Never overwrites: the file is opened in append mode
    and the audio filename carries the trial uid, so a repeat of the same item
    in Run B cannot clobber Run A."""
    ensure_directories()
    complete = {field: "" for field in TRIAL_FIELDS}
    complete.update({k: v for k, v in row.items() if k in TRIAL_FIELDS})
    complete["PILOT_ONLY"] = "YES"
    complete["RESEARCHER_SELF_TEST"] = "YES"
    if not complete.get("recorded_at_utc"):
        complete["recorded_at_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")

    is_new = not TRIALS_CSV.exists()
    with TRIALS_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TRIAL_FIELDS))
        if is_new:
            writer.writeheader()
        writer.writerow(complete)
    return complete


def audio_filename(trial_uid: str, run: str, item_id: str, repetition: int) -> str:
    """Unique per trial, so no run can overwrite another's audio."""
    return f"PILOT_ONLY_{trial_uid}_{run}_{item_id}_r{repetition}.wav"


def protected_artefact_digests() -> dict:
    """Fingerprint the fresh-validation files so a self-pilot run can prove it
    did not touch them."""
    import hashlib

    digests = {}
    for name in PROTECTED_ARTEFACTS:
        path = DATA_DIR / name
        digests[name] = (hashlib.sha256(path.read_bytes()).hexdigest()
                         if path.exists() else "ABSENT")
    return digests
