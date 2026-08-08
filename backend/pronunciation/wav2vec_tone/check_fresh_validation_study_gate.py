"""Phase D2 — read-only study-start gate check.

Reports whether real data collection may begin. It reads the external sign-off
record, the teacher review sheet, the frozen artefacts and the study files, and
prints a status line per gate.

**It never writes anything and never resolves a gate.** A gate becomes PASS
because a human supplied a decision and someone recorded it in
`data/fresh_validation_external_signoff.json`, never because this script
inferred it. A failed requirement is not waivable here.

    python -m pronunciation.wav2vec_tone.check_fresh_validation_study_gate
    python -m pronunciation.wav2vec_tone.check_fresh_validation_study_gate --teacher-review
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import verify_ompal_test_seal

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
REPORTS = HERE.parents[1] / "reports"

SIGNOFF = DATA / "fresh_validation_external_signoff.json"
FROZEN = DATA / "fresh_validation_system_FROZEN.json"
ITEMS = DATA / "fresh_validation_items.csv"
FROZEN_ITEMS = DATA / "fresh_validation_items_FROZEN.csv"
TEACHER_SHEET = DATA / "fresh_validation_item_teacher_review_TEMPLATE.csv"
ORDERS = DATA / "fresh_validation_item_orders.csv"
TRACKER = DATA / "fresh_validation_collection_tracker_TEMPLATE.csv"
ANALYSIS = HERE / "analyze_fresh_human_validation.py"

VALID_DECISIONS = {"APPROVE", "REPLACE"}
TICK_FIELDS = ("appropriate_for_CFL", "expected_reading_unambiguous_in_this_prompt",
               "natural_as_isolated_word", "difficulty_reasonable")
YES = {"YES", "Y", "TRUE", "OK", "✓", "X"}

PASS, PENDING, FAIL = "PASS", "PENDING", "FAIL"


# --------------------------------------------------------------------------
# teacher-review ingestion
# --------------------------------------------------------------------------
def read_teacher_review() -> dict:
    """Validate a completed teacher sheet without acting on it.

    Returns a verdict dict. A REPLACE anywhere is a STOP: this function reports
    which item needs revision and never proposes a substitute, because choosing
    a replacement character is a teaching judgement, not a parsing task.
    """
    result = {"status": PENDING, "problems": [], "replace": [], "approved": 0,
              "reviewer": None, "date": None, "tone_changes": []}

    if not TEACHER_SHEET.exists():
        result["problems"].append("teacher review sheet is missing")
        result["status"] = FAIL
        return result

    rows = list(csv.DictReader(TEACHER_SHEET.open(encoding="utf-8-sig")))
    # Counted as a set: a duplicated row must not push the tally past 16.
    approved_items: set[str] = set()
    expected = {r["item_id"]: r for r in
                csv.DictReader(ITEMS.open(encoding="utf-8-sig"))}

    filled = [r for r in rows if (r.get("teacher_decision") or "").strip()]
    if not filled:
        result["status"] = PENDING
        result["problems"].append("sheet has not been returned (no decisions recorded)")
        return result

    # all 16 present, none duplicated
    seen = [r["item_id"].strip() for r in rows]
    missing = sorted(set(expected) - set(seen))
    duplicated = sorted({i for i in seen if seen.count(i) > 1})
    if missing:
        result["problems"].append(f"missing item(s): {', '.join(missing)}")
    if duplicated:
        result["problems"].append(f"duplicated item(s): {', '.join(duplicated)}")
    if len(rows) != 16:
        result["problems"].append(f"expected 16 rows, found {len(rows)}")

    for row in rows:
        item = row["item_id"].strip()
        decision = (row.get("teacher_decision") or "").strip().upper()

        if decision not in VALID_DECISIONS:
            result["problems"].append(
                f"{item}: teacher_decision {decision or '(blank)'!r} is not APPROVE or REPLACE")
            continue

        if decision == "REPLACE":
            result["replace"].append(
                f"{item} {row.get('character', '')} — {(row.get('teacher_comments') or '').strip() or 'no comment given'}")
            continue

        blanks = [f for f in TICK_FIELDS if not (row.get(f) or "").strip()]
        if blanks:
            result["problems"].append(f"{item}: unanswered — {', '.join(blanks)}")
        if not (row.get("teacher_initials_or_rater_id") or "").strip():
            result["problems"].append(f"{item}: reviewer id missing")
        if not (row.get("review_date") or "").strip():
            result["problems"].append(f"{item}: review date missing")

        # The expected tone is what is being validated. If it moved, that is a
        # different item, and it needs an explicit written justification.
        if item in expected:
            was, now = expected[item]["expected_tone"].strip(), (row.get("expected_tone") or "").strip()
            if was != now:
                note = (row.get("teacher_comments") or "").strip()
                result["tone_changes"].append(f"{item}: T{was} -> T{now or '?'}")
                if not note:
                    result["problems"].append(
                        f"{item}: expected tone changed T{was}->T{now} with no documented reason")
        if not blanks and decision == "APPROVE":
            approved_items.add(item)

    result["approved"] = len(approved_items)
    reviewers = {(r.get("teacher_initials_or_rater_id") or "").strip() for r in rows}
    dates = {(r.get("review_date") or "").strip() for r in rows}
    result["reviewer"] = ", ".join(sorted(x for x in reviewers if x)) or None
    result["date"] = ", ".join(sorted(x for x in dates if x)) or None

    if result["replace"]:
        result["status"] = FAIL          # STOP — a human must revise the item
    elif result["problems"]:
        result["status"] = FAIL
    elif result["approved"] == len(expected):
        result["status"] = PASS
    else:
        result["status"] = PENDING
    return result


def print_teacher_review(verdict: dict) -> None:
    print("teacher item review\n")
    print(f"  status          : {verdict['status']}")
    print(f"  items approved  : {verdict['approved']}/16")
    print(f"  reviewer        : {verdict['reviewer'] or '(none recorded)'}")
    print(f"  review date     : {verdict['date'] or '(none recorded)'}")
    for change in verdict["tone_changes"]:
        print(f"  tone change     : {change}")
    if verdict["replace"]:
        print("\n  STOP — item(s) marked REPLACE. A replacement is a teaching")
        print("  judgement and is not chosen automatically. These need teacher")
        print("  or researcher revision, then MoE re-verification:")
        for entry in verdict["replace"]:
            print(f"    - {entry}")
    for problem in verdict["problems"]:
        print(f"  problem         : {problem}")
    print()


# --------------------------------------------------------------------------
# gates
# --------------------------------------------------------------------------
def status_of(value: str) -> str:
    """Map a recorded sign-off value onto a gate status."""
    value = (value or "").strip().upper()
    if value in {"CONFIRMED", "NOT_REQUIRED", "APPROVED", "COMPLETE", "AMENDED",
                 "YES", "ISOLATED_CHARACTER", "CONTEXT_APPROVED"}:
        return PASS
    if value in {"REJECTED", "REPLACE_REQUESTED", "NO", "RETURNED_INCOMPLETE"}:
        return FAIL
    return PENDING


def frozen_hash_gate() -> tuple[str, str]:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    recorded = frozen.pop("sha256")
    recomputed = hashlib.sha256(
        json.dumps(frozen, sort_keys=True, default=str).encode()).hexdigest()
    if recomputed != recorded:
        return FAIL, "artefact has changed — STOP, this is not OMPAL_R2_PASS_v1"
    return PASS, f"{recorded[:16]} OMPAL_R2_PASS_v1"


def item_manifest_gate(signoff: dict) -> tuple[str, str]:
    """The frozen study manifest may only exist after teacher sign-off."""
    if not FROZEN_ITEMS.exists():
        return PENDING, "not created — correct while teacher review is pending"
    digest = hashlib.sha256(FROZEN_ITEMS.read_bytes()).hexdigest()
    recorded = (signoff.get("frozen_item_manifest") or {}).get("sha256")
    if recorded and recorded != digest:
        return FAIL, f"hash mismatch: file {digest[:16]} vs recorded {recorded[:16]}"
    return (PASS, digest[:16]) if recorded else (
        FAIL, f"exists but no hash recorded ({digest[:16]})")


def analysis_frozen_gate() -> tuple[str, str]:
    source = ANALYSIS.read_text(encoding="utf-8")
    if ".fit(" in source or "import joblib" in source:
        return FAIL, "analysis script contains a model fit"
    if "PASS_PRECISION_TARGET = 0.90" not in source:
        return FAIL, "0.90 target missing or parameterised"
    return PASS, "no model fit; 0.90 target hard-coded"


def item_orders_gate() -> tuple[str, str]:
    if not ORDERS.exists():
        return FAIL, "item order file missing"
    rows = list(csv.DictReader(ORDERS.open(encoding="utf-8-sig")))
    per_order: dict[str, list] = {}
    for row in rows:
        per_order.setdefault(row["order_id"], []).append(row)
    problems = []
    adjacent = 0
    for order_id, seq in per_order.items():
        if len(seq) != 16 or len({r["item_id"] for r in seq}) != 16:
            problems.append(f"{order_id} is not 16 distinct items")
        tones = [r["expected_tone"] for r in seq]
        if sorted(set(tones)) != ["1", "2", "3", "4"] or any(
                tones.count(t) != 4 for t in set(tones)):
            problems.append(f"{order_id} tone imbalance")
        adjacent += sum(1 for a, b in zip(seq, seq[1:])
                        if a["expected_tone"] == b["expected_tone"])
    if problems:
        return FAIL, "; ".join(problems[:2])
    return PASS, f"{len(per_order)} orders, {adjacent} adjacent same-tone"


def data_paths_gate(signoff: dict) -> tuple[str, str]:
    """Paths exist here, but 'tested' means the pilot wrote real files."""
    missing = [p.name for p in (ITEMS, ORDERS, TRACKER, ANALYSIS) if not p.exists()]
    if missing:
        return FAIL, f"missing: {', '.join(missing)}"
    if status_of(signoff.get("pilot_status")) != PASS:
        return PENDING, "files present; end-to-end write confirmed by the pilot"
    return PASS, "files present; pilot confirmed writes"


def all_pending(mapping: dict, keys) -> str:
    values = [status_of(mapping.get(k)) for k in keys]
    if FAIL in values:
        return FAIL
    return PASS if all(v == PASS for v in values) else PENDING


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-review", action="store_true",
                        help="validate the completed teacher sheet in detail")
    args = parser.parse_args()

    signoff = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    teacher = read_teacher_review()

    if args.teacher_review:
        print_teacher_review(teacher)

    seal = verify_ompal_test_seal.run(write=False, quiet=True)
    ethics = signoff.get("ethics_and_consent", {})
    raters = signoff.get("raters", {})
    context = signoff.get("lexical_context_decisions", {})

    # A recorded APPROVED status is necessary but not sufficient for items: the
    # sheet itself must also validate.
    recorded_items = status_of(signoff.get("teacher_item_review_status"))
    item_gate = PASS if (recorded_items == PASS and teacher["status"] == PASS) else (
        FAIL if FAIL in (recorded_items, teacher["status"]) else PENDING)

    gates = [
        ("SYSTEM HASH", *frozen_hash_gate()),
        ("ITEM APPROVAL", item_gate,
         f"{teacher['approved']}/16 approved"
         + (f", {len(teacher['replace'])} REPLACE — STOP" if teacher["replace"] else "")
         + (f", tone changed: {'; '.join(teacher['tone_changes'])}"
            if teacher["tone_changes"] else "")),
        ("話 / 電 CONTEXT", all_pending(
            {"h": (context.get("hua") or {}).get("status"),
             "d": (context.get("dian") or {}).get("status")}, ("h", "d")),
         f"話 {(context.get('hua') or {}).get('status', 'PENDING')} / "
         f"電 {(context.get('dian') or {}).get('status', 'PENDING')}"),
        ("T3 RULE", status_of(signoff.get("t3_rule_status")),
         "rating cannot begin while PENDING"),
        ("ETHICS / CONSENT", all_pending(ethics, [
            "ethics_determination", "consent_form_approved",
            "audio_recording_consent_confirmed", "data_storage_confirmed",
            "retention_policy_confirmed", "withdrawal_policy_confirmed",
            "recruitment_wording_confirmed", "participant_compensation_confirmed",
            "researcher_contact_confirmed"]),
         "9 external items; no approval is claimed"),
        ("RATERS", all_pending(raters, [
            "rater_1_confirmed", "rater_2_confirmed", "rater_training_complete",
            "rater_blinding_verified", "t3_rule_acknowledged",
            "rating_interface_tested"]),
         f">= {raters.get('minimum_required', 2)} independent raters"),
        ("PILOT", status_of(signoff.get("pilot_status")),
         "PILOT_ONLY, never in the analysis"),
        ("PARTICIPANT INSTR.", PASS if (
            REPORTS / "fresh_validation_participant_instructions.md").exists() else FAIL,
         "drafted; final wording follows the ethics text"),
        ("ITEM MANIFEST HASH", *item_manifest_gate(signoff)),
        ("ITEM ORDER FILE", *item_orders_gate()),
        ("COLLECTION TRACKER", PASS if TRACKER.exists() else FAIL,
         "template ready, no participant names"),
        ("DATA PATHS", *data_paths_gate(signoff)),
        ("ANALYSIS SCRIPT", *analysis_frozen_gate()),
        ("OMPAL TEST SEAL", PASS if seal["sealed"] else FAIL,
         f"{len(seal['checks']) - seal['n_failed']}/{len(seal['checks'])} seal checks"),
    ]

    print("fresh validation — study start gate\n")
    for name, state, detail in gates:
        print(f"  {name:<20} {state:<8} {detail}")

    blocked = [name for name, state, _ in gates if state != PASS]
    ready = not blocked
    print(f"\nSTUDY_START_READY = {'YES' if ready else 'NO'}")
    if blocked:
        print(f"blocked by: {', '.join(blocked)}")
        print("\nNo requirement may be waived. Each blocked gate needs a human "
              "decision recorded in\n"
              "data/fresh_validation_external_signoff.json before it clears.")
    else:
        print("\nAll gates clear. The next action is to COLLECT REAL PARTICIPANT "
              "DATA.\nThere is no model-tuning step before collection.")

    # Read-only by contract: nothing above writes, and neither does this exit.
    sys.exit(0)


if __name__ == "__main__":
    main()
