import asyncio
import html
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from telegram import Bot
from telegram.error import BadRequest, NetworkError

from pythia.schemas import ProcessedReel

T = TypeVar("T")
TELEGRAM_RETRY_DELAYS = (1.0, 2.0, 4.0)


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def render_reel_details(reel: ProcessedReel, ranking: str) -> str:
    metadata = reel.metadata
    analysis = reel.analysis
    metrics = " · ".join(
        f"{label}: {value if value is not None else '—'}"
        for label, value in (("Лайки", metadata.likes_count), ("Комментарии", metadata.comments_count))
    )
    sections = [
        f"<b>Reel</b> <a href=\"{html.escape(metadata.url, quote=True)}\">открыть в Instagram</a>",
        html.escape(metrics),
        f"<b>О чём:</b> {html.escape(analysis.summary)}",
    ]
    if analysis.topics:
        sections.append(f"<b>Темы:</b> {html.escape(', '.join(analysis.topics))}")
    if analysis.hook:
        sections.append(f"<b>Hook:</b> {html.escape(analysis.hook)}")
    if analysis.cta:
        sections.append(f"<b>CTA:</b> {html.escape(analysis.cta)}")
    if analysis.screen_text:
        sections.append(f"<b>Текст на экране:</b> {html.escape(_short(analysis.screen_text, 1200))}")
    if reel.transcript:
        sections.append(f"<b>Речь:</b> {html.escape(_short(reel.transcript, 1800))}")
    if ranking:
        sections.append(f"<b>Сравнение:</b> {html.escape(ranking)}")
    return _short("\n\n".join(sections), 4000)


class TelegramReporter:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    @staticmethod
    async def _send_with_retry(operation: Callable[[], Awaitable[T]]) -> T:
        for delay in (*TELEGRAM_RETRY_DELAYS, None):
            try:
                return await operation()
            except BadRequest:
                raise
            except NetworkError:
                if delay is None:
                    raise
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def info(self, chat_id: int, message: str) -> None:
        await self._send_with_retry(lambda: self._bot.send_message(chat_id=chat_id, text=message))

    async def error(self, chat_id: int, message: str) -> None:
        await self._send_with_retry(lambda: self._bot.send_message(chat_id=chat_id, text=message))

    async def send_reel(self, chat_id: int, reel: ProcessedReel, ranking: str) -> None:
        caption = _short(f"Reel: {reel.analysis.summary}", 900)
        with Path(reel.key_frame_path).open("rb") as photo:
            async def send_photo() -> object:
                photo.seek(0)
                return await self._bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)

            await self._send_with_retry(send_photo)
        await self._send_with_retry(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=render_reel_details(reel, ranking),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        )
