"""Allow an explicit local test transaction to deploy synthetic BKT."""

from alembic import op


revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normal deployments still require real evidence and passing promotion
    # gates. The transaction-local setting is only set by the explicit local
    # test command, never by ordinary serving code.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bkt_reject_nonreal_deployment() RETURNS trigger AS $$
        DECLARE
            origin TEXT;
        BEGIN
            SELECT evidence_origin INTO origin
            FROM bkt_model_versions
            WHERE version = NEW.model_version;

            IF origin = 'synthetic'
               AND current_setting('mandarin.allow_synthetic_bkt_deployment', true) = 'on' THEN
                RETURN NEW;
            END IF;

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


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bkt_reject_nonreal_deployment() RETURNS trigger AS $$
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
