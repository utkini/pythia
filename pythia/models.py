import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID


metadata = MetaData()


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


competitors = Table(
    "competitors",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("username", String(64), nullable=False, unique=True, index=True),
    Column("profile_url", String(512), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

analysis_runs = Table(
    "analysis_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("competitor_id", UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False, index=True),
    Column("requested_by", Integer, nullable=False),
    Column("status", String(32), nullable=False, default=RunStatus.QUEUED, index=True),
    Column("source_url", String(512), nullable=False),
    Column("error_code", String(64)),
    Column("error_message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

reels = Table(
    "reels",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("run_id", UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False, index=True),
    Column("competitor_id", UUID(as_uuid=True), ForeignKey("competitors.id"), nullable=False, index=True),
    Column("shortcode", String(32), nullable=False),
    Column("url", String(512), nullable=False),
    Column("caption", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("likes_count", Integer),
    Column("views_count", Integer),
    Column("comments_count", Integer),
    Column("duration_seconds", Integer),
    Column("collected_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("shortcode", name="uq_reels_shortcode"),
)

reel_analyses = Table(
    "reel_analyses",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("reel_id", UUID(as_uuid=True), ForeignKey("reels.id"), nullable=False, unique=True),
    Column("transcript", Text, nullable=False),
    Column("screen_text", Text),
    Column("summary", Text, nullable=False),
    Column("analysis_json", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    id: uuid.UUID
    competitor_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Reel:
    id: uuid.UUID
