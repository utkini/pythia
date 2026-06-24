import uuid
from datetime import UTC, datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pythia.models import AnalysisRun, Reel, RunStatus, analysis_runs, competitors, reel_analyses, reels
from pythia.schemas import ContentAnalysis, ReelMetadata


class AnalysisRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_run(self, username: str, profile_url: str, requested_by: int) -> AnalysisRun:
        async with self._sessions() as session:
            competitor_id = await session.scalar(select(competitors.c.id).where(competitors.c.username == username))
            if competitor_id is None:
                competitor_id = await session.scalar(
                    insert(competitors).values(username=username, profile_url=profile_url).returning(competitors.c.id)
                )
            run_id = await session.scalar(
                insert(analysis_runs)
                .values(competitor_id=competitor_id, requested_by=requested_by, source_url=profile_url)
                .returning(analysis_runs.c.id)
            )
            await session.commit()
            return AnalysisRun(id=run_id, competitor_id=competitor_id)

    async def set_run_status(
        self,
        run_id: uuid.UUID,
        status: RunStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status, "error_code": error_code, "error_message": error_message}
        now = datetime.now(UTC)
        if status is RunStatus.PROCESSING:
            values["started_at"] = now
        if status in {RunStatus.COMPLETED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.INTERRUPTED}:
            values["finished_at"] = now
        async with self._sessions() as session:
            await session.execute(update(analysis_runs).where(analysis_runs.c.id == run_id).values(**values))
            await session.commit()

    async def mark_interrupted_runs(self) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(analysis_runs)
                .where(analysis_runs.c.status.in_([RunStatus.QUEUED, RunStatus.PROCESSING]))
                .values(status=RunStatus.INTERRUPTED, finished_at=datetime.now(UTC), error_code="restart")
            )
            await session.commit()

    async def save_reel(self, run_id: uuid.UUID, competitor_id: uuid.UUID, metadata: ReelMetadata, duration_seconds: int | None) -> Reel:
        async with self._sessions() as session:
            reel_id = await session.scalar(select(reels.c.id).where(reels.c.shortcode == metadata.shortcode))
            values = {
                "run_id": run_id,
                "competitor_id": competitor_id,
                "url": metadata.url,
                "caption": metadata.caption,
                "published_at": metadata.published_at,
                "likes_count": metadata.likes_count,
                "views_count": metadata.views_count,
                "comments_count": metadata.comments_count,
                "duration_seconds": duration_seconds,
            }
            if reel_id is None:
                reel_id = await session.scalar(
                    insert(reels).values(shortcode=metadata.shortcode, **values).returning(reels.c.id)
                )
            else:
                await session.execute(update(reels).where(reels.c.id == reel_id).values(**values))
            await session.commit()
            return Reel(id=reel_id)

    async def save_analysis(self, reel_id: uuid.UUID, transcript: str, analysis: ContentAnalysis) -> None:
        async with self._sessions() as session:
            analysis_id = await session.scalar(select(reel_analyses.c.id).where(reel_analyses.c.reel_id == reel_id))
            values = {
                "transcript": transcript,
                "screen_text": analysis.screen_text,
                "summary": analysis.summary,
                "analysis_json": analysis.model_dump(),
            }
            if analysis_id is None:
                await session.execute(insert(reel_analyses).values(reel_id=reel_id, **values))
            else:
                await session.execute(update(reel_analyses).where(reel_analyses.c.id == analysis_id).values(**values))
            await session.commit()
