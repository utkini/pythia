"""Support batches of 1-3 Reels from different authors with an engagement ranking.

Revision ID: 20261015_0002
Revises: 20260623_0001
Create Date: 2026-10-15

Downgrade is lossy once the same shortcode is stored in several runs or a run has
no author: it fails on the restored constraints instead of deleting history.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261015_0002"
down_revision = "20260623_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("analysis_runs", "competitor_id", nullable=True)
    op.alter_column("analysis_runs", "source_url", nullable=True)
    op.add_column("analysis_runs", sa.Column("source_urls", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("analysis_runs", sa.Column("ranking_json", postgresql.JSONB(astext_type=sa.Text())))
    op.alter_column("reels", "competitor_id", nullable=True)
    op.drop_constraint("uq_reels_shortcode", "reels", type_="unique")
    op.create_unique_constraint("uq_reels_run_shortcode", "reels", ["run_id", "shortcode"])


def downgrade() -> None:
    op.drop_constraint("uq_reels_run_shortcode", "reels", type_="unique")
    op.create_unique_constraint("uq_reels_shortcode", "reels", ["shortcode"])
    op.alter_column("reels", "competitor_id", nullable=False)
    op.drop_column("analysis_runs", "ranking_json")
    op.drop_column("analysis_runs", "source_urls")
    op.alter_column("analysis_runs", "source_url", nullable=False)
    op.alter_column("analysis_runs", "competitor_id", nullable=False)
