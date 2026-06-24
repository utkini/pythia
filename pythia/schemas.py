from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ReelMetadata(BaseModel):
    shortcode: str
    url: str
    caption: str | None = None
    published_at: datetime | None = None
    likes_count: int | None = None
    views_count: int | None = None
    comments_count: int | None = None


class DownloadedReel(BaseModel):
    metadata: ReelMetadata
    video_path: Path


class ContentAnalysis(BaseModel):
    summary: str = Field(description="A short Russian summary of the reel")
    topics: list[str] = Field(default_factory=list)
    screen_text: str = ""
    hook: str | None = None
    cta: str | None = None
    content_format: str | None = None
    sentiment: str | None = None
    language: str | None = None
    key_frame_index: int = 0

    @field_validator("key_frame_index")
    @classmethod
    def key_frame_is_non_negative(cls, value: int) -> int:
        return max(value, 0)


class ProcessedReel(BaseModel):
    metadata: ReelMetadata
    transcript: str
    analysis: ContentAnalysis
    key_frame_path: Path
    duration_seconds: int | None = None
