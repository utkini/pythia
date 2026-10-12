import asyncio
import shutil
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

from pythia.models import AnalysisRun, RunStatus
from pythia.reporting import TelegramReporter
from pythia.repositories import AnalysisRepository
from pythia.schemas import DownloadedReel, ProcessedReel
from pythia.services.instagram import InstagramCollector, InstagramError
from pythia.services.media import MediaError, MediaProcessor
from pythia.services.openai_analyzer import AnalysisError, OpenAIAnalyzer

logger = structlog.get_logger(__name__)


@dataclass
class StoredReel:
    reel: ProcessedReel


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

    async def execute(self, username: str | None, profile_url: str, chat_id: int) -> None:
        run: AnalysisRun | None = None
        job_dir: Path | None = None
        processed: list[StoredReel] = []
        try:
            if username is None:
                job_dir = self._work_dir / f"download-{uuid.uuid4()}"
                await self._reporter.info(chat_id, "Скачиваю Reel по ссылке…")
                item = await asyncio.to_thread(self._collector.download_reel, profile_url, job_dir)
                username = item.creator_username
                if username is None:
                    raise InstagramError("Unable to identify the Reel author.")
                downloaded = [item]
                run = await self._repository.create_run(
                    username, f"https://www.instagram.com/{username}/", chat_id, source_url=profile_url,
                )
                await self._repository.set_run_status(run.id, RunStatus.PROCESSING)
            else:
                run = await self._repository.create_run(username, profile_url, chat_id)
                job_dir = self._work_dir / f"run-{run.id}"
                await self._repository.set_run_status(run.id, RunStatus.PROCESSING)
                await self._reporter.info(chat_id, "Ищу до трёх свежих Reels профиля и скачиваю видео…")
                downloaded = await asyncio.to_thread(self._collector.collect, username, job_dir)
            log = logger.bind(run_id=str(run.id), username=username)
            await self._reporter.info(chat_id, f"Найдено {len(downloaded)} Reel(ов). Анализирую аудио и кадры…")
            for item in downloaded:
                try:
                    processed.append(await self._process_reel(run, item, job_dir))
                except (MediaError, AnalysisError, OSError) as error:
                    log.warning("reel_processing_failed", shortcode=item.metadata.shortcode, error=str(error))

            if not processed:
                raise AnalysisError("No Reel was analysed successfully.")

            for stored in processed:
                await self._reporter.send_reel(chat_id, stored.reel, "")
            status = RunStatus.COMPLETED if len(processed) == len(downloaded) else RunStatus.PARTIAL
            await self._repository.set_run_status(run.id, status)
            await self._reporter.info(chat_id, "Анализ завершён." if status is RunStatus.COMPLETED else "Анализ завершён частично: часть Reels обработать не удалось.")
        except InstagramError as error:
            logger.bind(run_id=str(run.id) if run else None, username=username).warning("instagram_failed", code=error.code)
            if run is not None:
                await self._repository.set_run_status(run.id, RunStatus.FAILED, error_code=error.code, error_message=str(error))
            await self._reporter.error(chat_id, self._user_error(error.code))
        except AnalysisError as error:
            logger.bind(run_id=str(run.id) if run else None, username=username).warning("analysis_failed", error=str(error))
            if run is not None:
                await self._repository.set_run_status(run.id, RunStatus.FAILED, error_code="ai_failed", error_message=str(error))
            await self._reporter.error(chat_id, "Не удалось завершить AI-анализ. Попробуйте ещё раз позже.")
        except Exception:
            logger.bind(run_id=str(run.id) if run else None, username=username).exception("run_failed")
            if run is not None:
                await self._repository.set_run_status(run.id, RunStatus.FAILED, error_code="internal_error", error_message="Unexpected processing error")
            await self._reporter.error(chat_id, "Анализ завершился технической ошибкой. Попробуйте ещё раз позже.")
        finally:
            if job_dir is not None:
                await asyncio.to_thread(shutil.rmtree, job_dir, ignore_errors=True)

    async def _process_reel(self, run: AnalysisRun, item: DownloadedReel, job_dir: Path) -> StoredReel:
        reel_dir = job_dir / item.metadata.shortcode
        duration = await self._media.duration(item.video_path)
        audio_path = await self._media.extract_audio(item.video_path, reel_dir)
        frames = await self._media.extract_frames(item.video_path, duration, reel_dir)
        transcript = await self._analyzer.transcribe(audio_path)
        analysis = await self._analyzer.analyse(item.metadata, transcript, frames)
        reel = await self._repository.save_reel(run.id, run.competitor_id, item.metadata, round(duration))
        await self._repository.save_analysis(reel.id, transcript, analysis)
        return StoredReel(
            reel=ProcessedReel(
                metadata=item.metadata,
                transcript=transcript,
                analysis=analysis,
                key_frame_path=frames[analysis.key_frame_index],
                duration_seconds=round(duration),
            )
        )

    @staticmethod
    def _user_error(code: str) -> str:
        return {
            "private_profile": "Профиль закрыт: можно анализировать только публичные аккаунты.",
            "no_reels": "У профиля нет доступных Reels.",
            "instagram_limited": "Instagram временно ограничил запросы. Попробуйте позднее.",
            "instagram_blocked": "Instagram остановил доступ к данным. Не повторяйте запрос сразу: откройте Instagram в браузере, проверьте уведомления и вход в аккаунт. Для поиска по профилю может понадобиться обновить session-файл. Можно прислать прямую ссылку на публичный Reel.",
            "invalid_url": "Нужна ссылка на публичный Instagram-профиль или Reel.",
        }.get(code, "Не удалось получить данные из Instagram. Для профиля попробуйте прямую ссылку на публичный Reel; для Reel проверьте доступность видео и попробуйте позднее.")


class JobManager:
    """A one-slot task manager that prevents parallel Instagram sessions."""

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
