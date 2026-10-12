import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pythia.models import RunStatus
from pythia.services.instagram import InstagramBlocked
from pythia.services.orchestrator import AnalysisService, JobManager


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


async def test_instagram_block_marks_run_failed_and_explains_next_step(tmp_path) -> None:
    repository = SimpleNamespace(
        create_run=AsyncMock(return_value=SimpleNamespace(id="test-run")),
        set_run_status=AsyncMock(),
    )
    collector = SimpleNamespace(collect=Mock(side_effect=InstagramBlocked("blocked")))
    reporter = SimpleNamespace(info=AsyncMock(), error=AsyncMock())
    analyzer = Mock()
    service = AnalysisService(repository, collector, Mock(), analyzer, reporter, tmp_path)

    await service.execute("example", "https://www.instagram.com/example/", 1)

    assert repository.set_run_status.call_args.args == ("test-run", RunStatus.FAILED)
    assert repository.set_run_status.call_args.kwargs["error_code"] == "instagram_blocked"
    reporter.error.assert_awaited_once()
    assert "Не повторяйте запрос сразу" in reporter.error.call_args.args[1]
    analyzer.transcribe.assert_not_called()
    assert not (tmp_path / "run-test-run").exists()


async def test_direct_reel_saves_author_and_source_without_ranking(tmp_path):
    from pythia.schemas import DownloadedReel, ReelMetadata
    from pythia.services.orchestrator import StoredReel
    item = DownloadedReel(metadata=ReelMetadata(shortcode="abc", url="https://www.instagram.com/reel/abc/"),
                          video_path=tmp_path / "video.mp4", creator_username="nike")
    repository = SimpleNamespace(create_run=AsyncMock(return_value=SimpleNamespace(id="run", competitor_id="author")),
                                 set_run_status=AsyncMock())
    collector = SimpleNamespace(download_reel=Mock(return_value=item), collect=Mock())
    reporter = SimpleNamespace(info=AsyncMock(), error=AsyncMock(), send_reel=AsyncMock())
    service = AnalysisService(repository, collector, Mock(), Mock(), reporter, tmp_path)
    service._process_reel = AsyncMock(return_value=StoredReel(reel="processed"))
    await service.execute(None, item.metadata.url, 1)
    repository.create_run.assert_awaited_once_with(
        "nike", "https://www.instagram.com/nike/", 1, source_url=item.metadata.url,
    )
    collector.collect.assert_not_called()
    reporter.send_reel.assert_awaited_once_with(1, "processed", "")
    repository.set_run_status.assert_awaited_with("run", RunStatus.COMPLETED)
    reporter.error.assert_not_called()
    assert not list(tmp_path.glob("download-*"))


async def test_profile_still_discovers_and_processes_reels(tmp_path):
    from pythia.services.orchestrator import StoredReel
    repository = SimpleNamespace(create_run=AsyncMock(return_value=SimpleNamespace(id="run", competitor_id="author")),
                                 set_run_status=AsyncMock())
    collector = SimpleNamespace(collect=Mock(return_value=["one", "two", "three"]), download_reel=Mock())
    reporter = SimpleNamespace(info=AsyncMock(), error=AsyncMock(), send_reel=AsyncMock())
    service = AnalysisService(repository, collector, Mock(), Mock(), reporter, tmp_path)
    service._process_reel = AsyncMock(side_effect=[StoredReel(reel=value) for value in ["one", "two", "three"]])
    await service.execute("nike", "https://www.instagram.com/nike/", 1)
    collector.collect.assert_called_once_with("nike", tmp_path / "run-run")
    assert reporter.send_reel.await_count == 3
    assert all(call.args[2] == "" for call in reporter.send_reel.call_args_list)
    repository.set_run_status.assert_awaited_with("run", RunStatus.COMPLETED)
    reporter.error.assert_not_called()
