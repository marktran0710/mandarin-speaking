"""Store format-aware BKT candidates in the model registry.

Production scores multiple-choice and typed answers with separate guess/slip
pairs, but the model registry (0031) only had one pair, so no fitted version
could describe what serving actually uses. This adds the typed pair and the
model scope. The deployment guard from 0031 (only promotable real-evidence
versions may be deployed) is unchanged.
"""

from alembic import op
import sqlalchemy as sa


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows (the bootstrap defaults, legacy global fits)
    # describe a single-pair model and have no typed pair.
    op.add_column("bkt_model_versions", sa.Column("guess_rate_typed", sa.Numeric(8, 6), nullable=True))
    op.add_column("bkt_model_versions", sa.Column("slip_rate_typed", sa.Numeric(8, 6), nullable=True))
    op.add_column("bkt_model_versions", sa.Column("model_scope", sa.Text, nullable=True))
    op.create_check_constraint(
        "ck_bkt_model_versions_typed_pair",
        "bkt_model_versions",
        "(guess_rate_typed IS NULL AND slip_rate_typed IS NULL) OR "
        "(guess_rate_typed >= 0 AND guess_rate_typed <= 1 AND slip_rate_typed >= 0 AND slip_rate_typed <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bkt_model_versions_typed_pair", "bkt_model_versions", type_="check")
    op.drop_column("bkt_model_versions", "model_scope")
    op.drop_column("bkt_model_versions", "slip_rate_typed")
    op.drop_column("bkt_model_versions", "guess_rate_typed")
