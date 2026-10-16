import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from pythia.models import RunStatus
from pythia.schemas import ContentAnalysis, ProcessedReel, ReelMetadata
from pythia.services.instagram import InstagramError
from pythia.services.media import MediaError
from pythia.services.orchestrator import AnalysisService, JobManager

URLS = [f"https://www.instagram.com/reel/code{i}/" for i in range(1, 4)]


async def test_job_manager_allows_only_one_active_task() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def operation() -> None:
        started.set()
        await release.wait()

    manager = JobManager()
    assert await manager.submit(operation)
    await started.wait()
    assert not await manager.submit(operation)
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert await manager.submit(operation)
    release.set()


def processed(url: str, likes: int, comments: int) -> ProcessedReel:
    return ProcessedReel(
        metadata=ReelMetadata(shortcode=url.rsplit("/", 2)[1], url=url, likes_count=likes, comments_count=comments),
        transcript="", analysis=ContentAnalysis(summary="s"), key_frame_path=Path("key.jpg"),
    )


def build(tmp_path, outcomes):
    repository = SimpleNamespace(
        create_run=AsyncMock(return_value=SimpleNamespace(id="run")),
        set_run_status=AsyncMock(), save_ranking=AsyncMock(),
    )
    reporter = SimpleNamespace(info=AsyncMock(), error=AsyncMock(), send_reel=AsyncMock(), send_ranking=AsyncMock())
    service = AnalysisService(repository, Mock(), Mock(), Mock(), reporter, tmp_path)

    async def process(run, url, reel_dir):
        reel_dir.mkdir(parents=True)
        outcome = outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    service._process_reel = AsyncMock(side_effect=process)
    return service, repository, reporter


async def test_single_reel_gets_report_without_ranking(tmp_path):
    service, repository, reporter = build(tmp_path, {URLS[0]: processed(URLS[0], 1, 1)})
    await service.execute(URLS[:1], 7)
    repository.create_run.assert_awaited_once_with(7, URLS[:1])
    reporter.send_reel.assert_awaited_once()
    assert reporter.send_reel.call_args.args[2] == 1
    reporter.send_ranking.assert_not_called()
    repository.save_ranking.assert_not_called()
    repository.set_run_status.assert_awaited_with("run", RunStatus.COMPLETED)
    assert not list(tmp_path.iterdir())


async def test_three_reels_are_ranked_by_likes_and_weighted_comments(tmp_path):
    outcomes = {URLS[0]: processed(URLS[0], 100, 0), URLS[1]: processed(URLS[1], 50, 20), URLS[2]: processed(URLS[2], 10, 1)}
    service, repository, reporter = build(tmp_path, outcomes)
    await service.execute(URLS, 7)
    assert [call.args[2] for call in reporter.send_reel.call_args_list] == [1, 2, 3]
    ranking, failures = reporter.send_ranking.call_args.args[1:]
    assert ranking.winners == [2]
    assert failures == {}
    saved = repository.save_ranking.call_args.args[1]
    assert saved["winners"] == [2]
    repository.set_run_status.assert_awaited_with("run", RunStatus.COMPLETED)
    reporter.error.assert_not_called()


@pytest.mark.parametrize("error", [InstagramError("blocked"), MediaError("ffmpeg")])
async def test_one_failed_reel_does_not_stop_the_batch(tmp_path, error):
    outcomes = {URLS[0]: processed(URLS[0], 1, 1), URLS[1]: error, URLS[2]: processed(URLS[2], 5, 5)}
    service, repository, reporter = build(tmp_path, outcomes)
    await service.execute(URLS, 7)
    assert reporter.send_reel.await_count == 2
    ranking, failures = reporter.send_ranking.call_args.args[1:]
    assert ranking.winners == [3]
    assert list(failures) == [2]
    assert "Reel 2" in reporter.error.call_args.args[1]
    assert repository.set_run_status.call_args.args == ("run", RunStatus.PARTIAL)
    assert not list(tmp_path.iterdir())


async def test_all_failed_marks_run_failed(tmp_path):
    service, repository, reporter = build(tmp_path, {url: InstagramError("x") for url in URLS[:2]})
    await service.execute(URLS[:2], 7)
    reporter.send_ranking.assert_not_called()
    assert repository.set_run_status.call_args.args == ("run", RunStatus.FAILED)
    assert reporter.error.await_count == 3


async def test_database_failure_is_a_technical_error(tmp_path):
    service, repository, reporter = build(tmp_path, {URLS[0]: processed(URLS[0], 1, 1), URLS[1]: processed(URLS[1], 2, 2)})
    repository.save_ranking.side_effect = RuntimeError("db down")
    await service.execute(URLS[:2], 7)
    assert repository.set_run_status.call_args.kwargs["error_code"] == "internal_error"
    assert "технической ошибкой" in reporter.error.call_args.args[1]
    assert not list(tmp_path.iterdir())


async def test_process_reel_stores_each_author_separately(tmp_path):
    from pythia.schemas import DownloadedReel
    item = DownloadedReel(metadata=ReelMetadata(shortcode="abc", url=URLS[0]), video_path=tmp_path / "v.mp4", creator_username="nike")
    repository = SimpleNamespace(
        get_or_create_competitor=AsyncMock(return_value="author"),
        save_reel=AsyncMock(return_value=SimpleNamespace(id="reel")), save_analysis=AsyncMock(),
    )
    collector = SimpleNamespace(download_reel=Mock(return_value=item))
    media = SimpleNamespace(duration=AsyncMock(return_value=12.4), extract_audio=AsyncMock(return_value="a.mp3"),
                            extract_frames=AsyncMock(return_value=["f0.jpg", "f1.jpg"]))
    analyzer = SimpleNamespace(transcribe=AsyncMock(return_value="hi"),
                               analyse=AsyncMock(return_value=ContentAnalysis(summary="s", key_frame_index=1)))
    service = AnalysisService(repository, collector, media, analyzer, Mock(), tmp_path)
    result = await service._process_reel(SimpleNamespace(id="run"), URLS[0], tmp_path / "1")
    repository.get_or_create_competitor.assert_awaited_once_with("nike")
    repository.save_reel.assert_awaited_once_with("run", "author", item.metadata, 12)
    assert result.key_frame_path == Path("f1.jpg")

    item.creator_username = None
    repository.get_or_create_competitor.reset_mock()
    await service._process_reel(SimpleNamespace(id="run"), URLS[0], tmp_path / "1")
    repository.get_or_create_competitor.assert_not_called()
    assert repository.save_reel.call_args.args[1] is None
