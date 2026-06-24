"""Create Pythia analysis schema.

Revision ID: 20260623_0001
Revises:
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260623_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("profile_url", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_competitors_username", "competitors", ["username"])
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_analysis_runs_competitor_id", "analysis_runs", ["competitor_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])
    op.create_table(
        "reels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("shortcode", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("caption", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("likes_count", sa.Integer()),
        sa.Column("views_count", sa.Integer()),
        sa.Column("comments_count", sa.Integer()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("shortcode", name="uq_reels_shortcode"),
    )
    op.create_index("ix_reels_run_id", "reels", ["run_id"])
    op.create_index("ix_reels_competitor_id", "reels", ["competitor_id"])
    op.create_table(
        "reel_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reels.id"), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("screen_text", sa.Text()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("reel_id"),
    )


def downgrade() -> None:
    op.drop_table("reel_analyses")
    op.drop_index("ix_reels_competitor_id", table_name="reels")
    op.drop_index("ix_reels_run_id", table_name="reels")
    op.drop_table("reels")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_competitor_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_competitors_username", table_name="competitors")
    op.drop_table("competitors")
