"""Use-case orchestration for the vocabulary Research Policy Layer.

Coordinates the research repository with the pure policy decision in
domain/vocabulary/research_policy.py. This is the one place production code
should call to find out "is this student in a research study, and if so
which progression policy applies" - routers must not query
vocab_research_participants/vocab_research_studies directly.
"""
from repositories import vocabulary_research as repo
from domain.vocabulary.research_policy import ResearchContext, build_research_context


def get_research_context(db, student_id: str) -> ResearchContext:
    row = repo.find_active_participation(db, student_id)
    if row is None:
        return build_research_context(
            study_id=None,
            study_status=None,
            policy_version=None,
            assignment_version=None,
            practice_budget=None,
            participant_active=False,
        )

    config = row.get("config_json") or {}
    return build_research_context(
        study_id=row["study_id"],
        study_status=row["study_status"],
        policy_version=row["policy_version"],
        assignment_version=row["assignment_version"],
        practice_budget=config.get("practiceBudget"),
        participant_active=bool(row["participant_active"]),
    )
