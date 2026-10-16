import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from pythia.models import AnalysisRun, RunStatus
from pythia.reporting import TelegramReporter
from pythia.repositories import AnalysisRepository
from pythia.schemas import ProcessedReel, ReelMetadata
from pythia.services.instagram import InstagramCollector, InstagramError
from pythia.services.media import MediaError, MediaProcessor
from pythia.services.openai_analyzer import AnalysisError, OpenAIAnalyzer
from pythia.services.ranking import rank_reels

logger = structlog.get_logger(__name__)


class AnalysisService:
    def __init__(
        self,
        repository: AnalysisRepository,
        collector: InstagramCollector,
        media: MediaProcessor,
        analyzer: OpenAIAnalyzer,
        reporter: TelegramReporter,
        work_dir: Path,
    ) -> None:
        self._repository = repository
        self._collector = collector
        self._media = media
        self._analyzer = analyzer
        self._reporter = reporter
        self._work_dir = work_dir

    async def execute(self, urls: list[str], chat_id: int) -> None:
        run: AnalysisRun | None = None
        job_dir: Path | None = None
        try:
            run = await self._repository.create_run(chat_id, urls)
            log = logger.bind(run_id=str(run.id))
            job_dir = self._work_dir / f"run-{run.id}"
            await self._repository.set_run_status(run.id, RunStatus.PROCESSING)

            processed: dict[int, ReelMetadata] = {}
            failures: dict[int, str] = {}
            for position, url in enumerate(urls, start=1):
                await self._reporter.info(chat_id, f"Reel {position}/{len(urls)}: скачиваю и анализирую…")
                try:
                    reel = await self._process_reel(run, url, job_dir / str(position))
                except (InstagramError, MediaError, AnalysisError, OSError) as error:
                    log.warning("reel_processing_failed", position=position, error_type=type(error).__name__, error=str(error))
                    failures[position] = self._user_error(error)
                    await self._reporter.error(chat_id, f"Reel {position}: {failures[position]}")
                    continue
                processed[position] = reel.metadata
                await self._reporter.send_reel(chat_id, reel, position)

            if not processed:
                await self._repository.set_run_status(
                    run.id, RunStatus.FAILED, error_code="no_reels_processed", error_message="No Reel was analysed successfully.",
                )
                await self._reporter.error(chat_id, "Не удалось обработать ни один Reel.")
                return

            if len(urls) > 1:
                ranking = rank_reels(processed)
                await self._repository.save_ranking(run.id, {**ranking.as_dict(), "failures": failures})
                await self._reporter.send_ranking(chat_id, ranking, failures)

            if failures:
                await self._repository.set_run_status(run.id, RunStatus.PARTIAL, error_code="some_reels_failed")
                await self._reporter.info(chat_id, "Анализ завершён частично: часть Reels обработать не удалось.")
            else:
                await self._repository.set_run_status(run.id, RunStatus.COMPLETED)
                await self._reporter.info(chat_id, "Анализ завершён.")
        except Exception:
            logger.bind(run_id=str(run.id) if run else None).exception("run_failed")
            if run is not None:
                await self._repository.set_run_status(run.id, RunStatus.FAILED, error_code="internal_error", error_message="Unexpected processing error")
            await self._reporter.error(chat_id, "Анализ завершился технической ошибкой. Попробуйте ещё раз позже.")
        finally:
            if job_dir is not None:
                await asyncio.to_thread(shutil.rmtree, job_dir, ignore_errors=True)

    async def _process_reel(self, run: AnalysisRun, url: str, reel_dir: Path) -> ProcessedReel:
        item = await asyncio.to_thread(self._collector.download_reel, url, reel_dir)
        work_dir = reel_dir / item.metadata.shortcode
        duration = await self._media.duration(item.video_path)
        audio_path = await self._media.extract_audio(item.video_path, work_dir)
        frames = await self._media.extract_frames(item.video_path, duration, work_dir)
        transcript = await self._analyzer.transcribe(audio_path)
        analysis = await self._analyzer.analyse(item.metadata, transcript, frames)
        competitor_id = (
            await self._repository.get_or_create_competitor(item.creator_username) if item.creator_username else None
        )
        reel = await self._repository.save_reel(run.id, competitor_id, item.metadata, round(duration))
        await self._repository.save_analysis(reel.id, transcript, analysis)
        return ProcessedReel(
            metadata=item.metadata,
            transcript=transcript,
            analysis=analysis,
            key_frame_path=frames[analysis.key_frame_index],
            duration_seconds=round(duration),
        )

    @staticmethod
    def _user_error(error: Exception) -> str:
        if isinstance(error, InstagramError):
            return "не удалось скачать ролик (закрыт, удалён или Instagram ограничил доступ)."
        if isinstance(error, MediaError):
            return "не удалось обработать видео."
        if isinstance(error, AnalysisError):
            return "не удалось выполнить AI-анализ."
        return "техническая ошибка при обработке."


class JobManager:
    """A one-slot task manager: one analysis at a time on the Raspberry Pi."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: asyncio.Task[None] | None = None

    async def submit(self, operation: Callable[[], Awaitable[None]]) -> bool:
        async with self._lock:
            if self._active is not None and not self._active.done():
                return False
            self._active = asyncio.create_task(operation(), name="instagram-analysis")
            self._active.add_done_callback(self._log_unhandled_error)
            return True

    @staticmethod
    def _log_unhandled_error(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.exception("unhandled_analysis_task_error", exc_info=error)
