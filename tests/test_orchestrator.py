import asyncio

from pythia.services.orchestrator import JobManager


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
