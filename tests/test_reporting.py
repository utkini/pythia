from datetime import UTC, datetime
from pathlib import Path

import pytest
from telegram.error import BadRequest, NetworkError

from pythia.reporting import TelegramReporter, render_reel_details
from pythia.schemas import ContentAnalysis, ProcessedReel, ReelMetadata


def test_report_escapes_model_output_and_includes_metrics() -> None:
    reel = ProcessedReel(
        metadata=ReelMetadata(
            shortcode="abc",
            url="https://www.instagram.com/reel/abc/",
            published_at=datetime.now(UTC),
            views_count=1000,
            likes_count=50,
            comments_count=10,
        ),
        transcript="<script>",
        analysis=ContentAnalysis(summary="<b>test</b>", topics=["AI"], key_frame_index=0),
        key_frame_path=Path("/tmp/key.jpg"),
    )
    text = render_reel_details(reel, "1-е место")
    assert "Просмотры" not in text
    assert "Лайки: 50" in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;test&lt;/b&gt;" in text
    assert "1-е место" in text


class FlakyBot:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def send_message(self, **kwargs: object) -> object:
        self.calls += 1
        if self.calls <= self.failures:
            raise NetworkError("temporary")
        return object()


async def test_reporter_retries_transient_telegram_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pythia.reporting.TELEGRAM_RETRY_DELAYS", (0.0,))
    bot = FlakyBot(failures=1)

    await TelegramReporter(bot).info(1, "hello")

    assert bot.calls == 2


async def test_reporter_raises_after_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pythia.reporting.TELEGRAM_RETRY_DELAYS", (0.0,))
    bot = FlakyBot(failures=2)

    with pytest.raises(NetworkError):
        await TelegramReporter(bot).info(1, "hello")

    assert bot.calls == 2


async def test_reporter_does_not_retry_bad_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pythia.reporting.TELEGRAM_RETRY_DELAYS", (0.0,))
    calls = 0

    async def invalid_request() -> None:
        nonlocal calls
        calls += 1
        raise BadRequest("invalid message")

    with pytest.raises(BadRequest):
        await TelegramReporter._send_with_retry(invalid_request)

    assert calls == 1


async def test_reporter_rewinds_photo_on_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pythia.reporting.TELEGRAM_RETRY_DELAYS", (0.0,))
    photo_path = tmp_path / "key.jpg"
    photo_path.write_bytes(b"photo content")

    class FlakyPhotoBot(FlakyBot):
        def __init__(self) -> None:
            super().__init__(failures=1)
            self.uploads: list[bytes] = []

        async def send_photo(self, **kwargs: object) -> object:
            self.uploads.append(kwargs["photo"].read())
            if len(self.uploads) == 1:
                raise NetworkError("upload interrupted")
            return object()

    bot = FlakyPhotoBot()
    reel = ProcessedReel(
        metadata=ReelMetadata(
            shortcode="abc",
            url="https://www.instagram.com/reel/abc/",
            published_at=datetime.now(UTC),
        ),
        transcript="hello",
        analysis=ContentAnalysis(summary="test", key_frame_index=0),
        key_frame_path=photo_path,
    )

    await TelegramReporter(bot).send_reel(1, reel, "1-е место")

    assert bot.uploads == [b"photo content", b"photo content"]
    assert bot.calls == 2
