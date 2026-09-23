"""Use-case orchestration for the Epic 4 equal-budget BKT practice feature.

Builds one practice session's word list: resolves the student's frozen
condition assignment (Epic 2), splits their study's configured practice
budget evenly across the conditions actually represented in that assignment
(Task 4.5), and selects each condition's words with the rule that matches
its bkt_policy - lowest treatment p(learned) first when bkt_personalized
(Task 4.6), blind rotation by prior exposure count when mastery_blind (Task
4.7). A mastery-blind condition never has treatment BKT state fetched for
its words at all - not filtered out after the fact, simply never computed -
so it cannot leak through a future refactor.
"""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.bkt import BKT_CONFIG, BKT_MODEL_VERSION, BktConfig, bkt_parameter_fingerprint
from analytics.bkt_mastery import get_treatment_vocabulary_mastery
from application.vocabulary_research import get_research_context
from domain.vocabulary.research_assignment import BktPolicy, CONDITION_POLICIES, RetentionPolicy, condition_for_policies
from domain.vocabulary.research_practice import allocate_slots, select_bkt_ranked, select_mastery_blind
from repositories import vocabulary_research as repo


# The plan's own worked example (Task 4.5: "2 slots per condition out of 8").
# Used only when a study's config_json omits practiceBudget entirely.
DEFAULT_PRACTICE_BUDGET = 8


class ResearchPracticeUnavailableError(Exception):
    """The student is not an active research participant right now. The
    router turns this into a 409, never a session with zero words silently
    standing in for "not eligible"."""


def build_practice_session(db, student_id: str, params: BktConfig = BKT_CONFIG) -> dict:
    context = get_research_context(db, student_id)
    if not context.active or not context.study_id:
        raise ResearchPracticeUnavailableError("Student is not an active research participant.")
    study_id = context.study_id

    assignments = repo.find_assignments_for_student(db, study_id, student_id)
    if not assignments:
        return {"studyId": study_id, "wordIds": []}

    words_by_condition: dict = {}
    for row in assignments:
        condition = condition_for_policies(BktPolicy(row["bkt_policy"]), RetentionPolicy(row["retention_policy"]))
        words_by_condition.setdefault(condition, []).append(row["word_id"])

    budget = context.practice_budget or DEFAULT_PRACTICE_BUDGET
    slots_by_condition = allocate_slots(budget, list(words_by_condition))

    now = datetime.now(timezone.utc).isoformat()
    selected: list[str] = []
    for condition, word_ids in words_by_condition.items():
        slot_count = slots_by_condition.get(condition, 0)
        if slot_count <= 0:
            continue
        bkt_policy, _retention_policy = CONDITION_POLICIES[condition]
        if bkt_policy == BktPolicy.BKT_PERSONALIZED:
            mastery = get_treatment_vocabulary_mastery(db, student_id, study_id, word_ids, params)
            repo.upsert_research_bkt_state(
                db, student_id=student_id, study_id=study_id, now=now,
                states=[
                    {
                        **state,
                        "model_version": BKT_MODEL_VERSION,
                        "parameter_fingerprint": bkt_parameter_fingerprint(params),
                    }
                    for state in mastery.values()
                ],
            )
            candidates = [(word_id, state["p_learned"]) for word_id, state in mastery.items()]
            selected.extend(select_bkt_ranked(candidates, slot_count))
        else:
            # Mastery-blind: the only signal fetched is a raw exposure count.
            # p(learned)/correctness/response-time are never queried for
            # these words in this branch.
            exposure_counts = repo.count_research_practice_exposures(db, study_id, student_id, word_ids)
            candidates = [(word_id, exposure_counts.get(word_id, 0)) for word_id in word_ids]
            selected.extend(select_mastery_blind(candidates, slot_count))

    return {"studyId": study_id, "wordIds": selected}
