"""Add BKT evidence provenance and an immutable calibration-model registry."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


_ORIGINS = "evidence_origin IN ('real', 'synthetic', 'legacy_unknown')"


def _immutable_trigger(table_name: str, trigger_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER {trigger_name} BEFORE UPDATE OR DELETE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION bkt_reject_immutable_mutation()"
    )


def upgrade() -> None:
    # Legacy rows predate the route resolver. Preserve that uncertainty rather
    # than implying their client-derived facts are real learner evidence.
    op.add_column(
        "vocab_quiz_responses",
        sa.Column("evidence_origin", sa.Text, nullable=False, server_default="legacy_unknown"),
    )
    op.add_column("vocab_quiz_responses", sa.Column("resolver_version", sa.Text, nullable=True))
    op.add_column("vocab_quiz_responses", sa.Column("occurred_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "vocab_quiz_responses",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_check_constraint("ck_vocab_quiz_responses_evidence_origin", "vocab_quiz_responses", _ORIGINS)
    op.execute("UPDATE vocab_quiz_responses SET evidence_origin = 'legacy_unknown'")
    op.create_index(
        "ix_vocab_quiz_responses_calibration_snapshot",
        "vocab_quiz_responses",
        ["evidence_origin", "bkt_eligible", "resolver_version", "id", "occurred_at_utc"],
    )

    op.create_table(
        "bkt_model_fit_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("evidence_origin", sa.Text, nullable=False),
        sa.Column("resolver_version", sa.Text, nullable=True),
        sa.Column("source_digest", sa.Text, nullable=False),
        sa.Column("high_water_response_id", sa.BigInteger, nullable=True),
        sa.Column("response_count", sa.Integer, nullable=False),
        sa.Column("student_count", sa.Integer, nullable=False),
        sa.Column("concept_count", sa.Integer, nullable=False),
        sa.Column("split_spec", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("promotion_gates", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("diagnostics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.Text, nullable=False, server_default="completed"),
        sa.Column("promotable", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(_ORIGINS, name="ck_bkt_model_fit_runs_evidence_origin"),
        sa.CheckConstraint("response_count >= 0 AND student_count >= 0 AND concept_count >= 0", name="ck_bkt_model_fit_runs_counts"),
        sa.CheckConstraint("status IN ('completed', 'rejected', 'failed')", name="ck_bkt_model_fit_runs_status"),
        sa.CheckConstraint("NOT promotable OR evidence_origin = 'real'", name="ck_bkt_model_fit_runs_real_promotable"),
        sa.UniqueConstraint("id", "evidence_origin", name="uq_bkt_model_fit_runs_id_origin"),
    )
    op.create_table(
        "bkt_model_student_folds",
        sa.Column("fit_run_id", sa.Text, nullable=False),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("fold_index", sa.Integer, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("fit_run_id", "student_id", name="pk_bkt_model_student_folds"),
        sa.ForeignKeyConstraint(["fit_run_id"], ["bkt_model_fit_runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("fold_index >= 0", name="ck_bkt_model_student_folds_nonnegative"),
    )
    op.create_table(
        "bkt_model_versions",
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("fit_run_id", sa.Text, nullable=False),
        sa.Column("evidence_origin", sa.Text, nullable=False),
        sa.Column("initial_mastery", sa.Numeric(8, 6), nullable=False),
        sa.Column("learn_rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("guess_rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("slip_rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("parameter_fingerprint", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["fit_run_id", "evidence_origin"], ["bkt_model_fit_runs.id", "bkt_model_fit_runs.evidence_origin"], ondelete="RESTRICT"),
        sa.CheckConstraint(_ORIGINS, name="ck_bkt_model_versions_evidence_origin"),
        sa.CheckConstraint("initial_mastery >= 0 AND initial_mastery <= 1", name="ck_bkt_model_versions_l0"),
        sa.CheckConstraint("learn_rate >= 0 AND learn_rate <= 1", name="ck_bkt_model_versions_t"),
        sa.CheckConstraint("guess_rate >= 0 AND guess_rate <= 1", name="ck_bkt_model_versions_g"),
        sa.CheckConstraint("slip_rate >= 0 AND slip_rate <= 1", name="ck_bkt_model_versions_s"),
    )
    op.create_table(
        "bkt_model_active_deployment",
        sa.Column("singleton", sa.Boolean, primary_key=True, server_default=sa.true()),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["model_version"], ["bkt_model_versions.version"], ondelete="RESTRICT"),
        sa.CheckConstraint("singleton", name="ck_bkt_model_active_deployment_singleton"),
    )
    op.create_table(
        "bkt_model_deployment_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("previous_model_version", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["model_version"], ["bkt_model_versions.version"], ondelete="RESTRICT"),
    )
    op.create_table(
        "bkt_model_refit_requests",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("evidence_origin", sa.Text, nullable=False),
        sa.Column("requested_by", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="requested"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fit_run_id", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["fit_run_id"], ["bkt_model_fit_runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(_ORIGINS, name="ck_bkt_model_refit_requests_evidence_origin"),
        sa.CheckConstraint("status IN ('requested', 'running', 'completed', 'rejected')", name="ck_bkt_model_refit_requests_status"),
    )

    op.execute(
        """
        CREATE FUNCTION bkt_reject_immutable_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    _immutable_trigger("bkt_model_fit_runs", "trg_bkt_model_fit_runs_immutable")
    _immutable_trigger("bkt_model_student_folds", "trg_bkt_model_student_folds_immutable")
    _immutable_trigger("bkt_model_versions", "trg_bkt_model_versions_immutable")
    _immutable_trigger("bkt_model_deployment_events", "trg_bkt_model_deployment_events_immutable")
    op.execute(
        """
        CREATE FUNCTION bkt_reject_nonreal_deployment() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM bkt_model_versions AS model
                WHERE model.version = NEW.model_version
                  AND model.evidence_origin = 'real'
                  AND EXISTS (
                    SELECT 1 FROM bkt_model_fit_runs AS fit
                    WHERE fit.id = model.fit_run_id
                      AND fit.evidence_origin = 'real'
                      AND fit.promotable = TRUE
                  )
            ) THEN
                RAISE EXCEPTION 'Only real-evidence BKT model versions may be deployed';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_bkt_model_active_deployment_real BEFORE INSERT OR UPDATE "
        "ON bkt_model_active_deployment FOR EACH ROW EXECUTE FUNCTION bkt_reject_nonreal_deployment()"
    )
    op.execute(
        "CREATE TRIGGER trg_bkt_model_deployment_event_real BEFORE INSERT ON bkt_model_deployment_events "
        "FOR EACH ROW EXECUTE FUNCTION bkt_reject_nonreal_deployment()"
    )

    # This records the existing engineering defaults without changing serving.
    op.execute(
        """
        INSERT INTO bkt_model_fit_runs
            (id, evidence_origin, source_digest, response_count, student_count, concept_count, parameters, metrics)
        VALUES ('bootstrap-standard-bkt-v1', 'legacy_unknown', 'engineering-defaults-no-fit', 0, 0, 0,
                '{"source":"existing engineering defaults"}'::jsonb, '{}'::jsonb)
        """
    )
    op.execute(
        """
        INSERT INTO bkt_model_versions
            (version, fit_run_id, evidence_origin, initial_mastery, learn_rate, guess_rate, slip_rate, parameter_fingerprint)
        VALUES
            ('standard-bkt-v1', 'bootstrap-standard-bkt-v1', 'legacy_unknown', .2, .15, .2, .1,
             'bootstrap-engineering-defaults-l0-0.2-t-0.15-g-0.2-s-0.1')
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_bkt_model_deployment_event_real ON bkt_model_deployment_events")
    op.execute("DROP TRIGGER trg_bkt_model_active_deployment_real ON bkt_model_active_deployment")
    op.execute("DROP FUNCTION bkt_reject_nonreal_deployment()")
    for table_name, trigger_name in (
        ("bkt_model_deployment_events", "trg_bkt_model_deployment_events_immutable"),
        ("bkt_model_versions", "trg_bkt_model_versions_immutable"),
        ("bkt_model_student_folds", "trg_bkt_model_student_folds_immutable"),
        ("bkt_model_fit_runs", "trg_bkt_model_fit_runs_immutable"),
    ):
        op.execute(f"DROP TRIGGER {trigger_name} ON {table_name}")
    op.execute("DROP FUNCTION bkt_reject_immutable_mutation()")
    op.drop_table("bkt_model_refit_requests")
    op.drop_table("bkt_model_deployment_events")
    op.drop_table("bkt_model_active_deployment")
    op.drop_table("bkt_model_versions")
    op.drop_table("bkt_model_student_folds")
    op.drop_table("bkt_model_fit_runs")
    op.drop_index("ix_vocab_quiz_responses_calibration_snapshot", table_name="vocab_quiz_responses")
    op.drop_constraint("ck_vocab_quiz_responses_evidence_origin", "vocab_quiz_responses", type_="check")
    op.drop_column("vocab_quiz_responses", "ingested_at")
    op.drop_column("vocab_quiz_responses", "occurred_at_utc")
    op.drop_column("vocab_quiz_responses", "resolver_version")
    op.drop_column("vocab_quiz_responses", "evidence_origin")
