import asyncio
import html
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from telegram import Bot
from telegram.error import BadRequest, NetworkError

from pythia.schemas import ProcessedReel
from pythia.services.ranking import COMMENT_WEIGHT, Ranking

T = TypeVar("T")
TELEGRAM_RETRY_DELAYS = (1.0, 2.0, 4.0)


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def render_reel_details(reel: ProcessedReel, position: int) -> str:
    metadata = reel.metadata
    analysis = reel.analysis
    metrics = " · ".join(
        f"{label}: {value if value is not None else '—'}"
        for label, value in (("Лайки", metadata.likes_count), ("Комментарии", metadata.comments_count))
    )
    sections = [
        f"<b>Reel {position}</b> <a href=\"{html.escape(metadata.url, quote=True)}\">открыть в Instagram</a>",
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
    return _short("\n\n".join(sections), 4000)


def _count(value: int | None) -> str:
    return "—" if value is None else str(value)


def _reel_list(positions: list[int]) -> str:
    return " и ".join(f"Reel {position}" for position in positions)


def render_ranking(ranking: Ranking, failures: dict[int, str]) -> str:
    lines = ["<b>Итог: вовлечённость</b>"]
    for entry in ranking.entries:
        mark = "🏆 " if entry.position in ranking.winners else ""
        age = f" · {entry.age_days} дн." if entry.age_days is not None else ""
        score = f"score {entry.score}" if entry.score is not None else "нет данных о лайках/комментариях"
        lines.append(
            f"{mark}<a href=\"{html.escape(entry.url, quote=True)}\">Reel {entry.position}</a> — "
            f"❤️ {_count(entry.likes)} · 💬 {_count(entry.comments)} · {score}{age}"
        )
    for position, reason in sorted(failures.items()):
        lines.append(f"Reel {position} — не обработан: {html.escape(reason)}")
    lines.append("")
    if len(ranking.winners) == 1:
        lines.append(f"<b>Лучшая вовлечённость: Reel {ranking.winners[0]}</b>")
    elif ranking.winners:
        lines.append(f"<b>Лидеры с равным результатом: {_reel_list(ranking.winners)}</b>")
    else:
        lines.append("Победителя определить нельзя: метрики есть меньше чем у двух роликов.")
    lines.append(
        f"<i>score = лайки + {COMMENT_WEIGHT} × комментарии. Просмотры недоступны; "
        "учитывайте разный возраст публикаций и размер аудитории авторов.</i>"
    )
    return "\n".join(lines)


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

    async def send_reel(self, chat_id: int, reel: ProcessedReel, position: int) -> None:
        caption = _short(f"Reel {position}: {reel.analysis.summary}", 900)
        with Path(reel.key_frame_path).open("rb") as photo:
            async def send_photo() -> object:
                photo.seek(0)
                return await self._bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)

            await self._send_with_retry(send_photo)
        await self._send_with_retry(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=render_reel_details(reel, position),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        )

    async def send_ranking(self, chat_id: int, ranking: Ranking, failures: dict[int, str]) -> None:
        await self._send_with_retry(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=render_ranking(ranking, failures),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        )
