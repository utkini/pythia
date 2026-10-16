import structlog
from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from pythia.config import settings
from pythia.database import check_database, create_engine, create_session_factory
from pythia.reporting import TelegramReporter
from pythia.repositories import AnalysisRepository
from pythia.services.instagram import MAX_REELS, InvalidReelUrl, InstagramCollector, parse_reel_urls
from pythia.services.media import MediaProcessor
from pythia.services.openai_analyzer import OpenAIAnalyzer
from pythia.services.orchestrator import AnalysisService, JobManager

logger = structlog.get_logger(__name__)


def telegram_request() -> HTTPXRequest:
    return HTTPXRequest(
        connect_timeout=20,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=20,
        media_write_timeout=settings.external_timeout_seconds,
    )


async def is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user is None or update.effective_user.id != settings.owner_telegram_id:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Доступ запрещён.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_owner(update, context):
        return
    await update.effective_message.reply_text(
        f"Пришлите от 1 до {MAX_REELS} ссылок на публичные Reels одним сообщением, либо используйте /analyze <ссылки>."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_owner(update, context):
        return
    await update.effective_message.reply_text(
        f"Я анализирую от 1 до {MAX_REELS} публичных Reels: лайки, комментарии, речь, текст на экране и смысл ролика.\n"
        "Если ссылок несколько, в конце покажу, у какого ролика лучшая вовлечённость "
        "(лайки + 3 × комментарии). Просмотры недоступны, профили не принимаются.\n"
        "Пример: /analyze https://www.instagram.com/reel/AAA/ https://www.instagram.com/reel/BBB/"
    )


async def analyse_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not await is_owner(update, context):
        return
    try:
        request = parse_reel_urls(text)
    except InvalidReelUrl as error:
        await update.effective_message.reply_text(str(error))
        return

    manager: JobManager = context.application.bot_data["jobs"]
    service: AnalysisService = context.application.bot_data["service"]
    chat_id = update.effective_chat.id
    accepted = await manager.submit(lambda: service.execute(request.urls, chat_id))
    if not accepted:
        await update.effective_message.reply_text("Сейчас уже выполняется анализ. Дождитесь его завершения и повторите запрос.")
        return
    duplicates = f" Повторные ссылки пропущены: {request.duplicates}." if request.duplicates else ""
    await update.effective_message.reply_text(
        f"Принято Reels: {len(request.urls)}.{duplicates} Начинаю анализ, это может занять несколько минут."
    )


async def analyse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_owner(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("Использование: /analyze https://www.instagram.com/reel/<код>/ [ещё ссылки]")
        return
    await analyse_text(update, context, " ".join(context.args))


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is not None:
        await analyse_text(update, context, update.effective_message.text)


async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep transient Telegram transport failures from producing unhandled traces."""
    if isinstance(context.error, NetworkError):
        logger.warning("telegram_network_error", error=str(context.error))
        return
    logger.error("telegram_handler_error", error=repr(context.error), exc_info=context.error)


async def mark_interrupted_runs(app: Application) -> None:
    """A run cannot survive a restart; record that instead of leaving it 'processing'."""
    await app.bot_data["repository"].mark_interrupted_runs()


def build_application() -> Application:
    engine = create_engine(settings.database_url)
    repository = AnalysisRepository(create_session_factory(engine))
    analyzer = OpenAIAnalyzer()
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token.get_secret_value())
        .request(telegram_request())
        .get_updates_request(telegram_request())
        .concurrent_updates(8)
        .post_init(mark_interrupted_runs)
        .build()
    )
    app.bot_data.update(
        {
            "repository": repository,
            "analyzer": analyzer,
            "jobs": JobManager(),
            "service": AnalysisService(
                repository=repository,
                collector=InstagramCollector(),
                media=MediaProcessor(settings.frame_count),
                analyzer=analyzer,
                reporter=TelegramReporter(app.bot),
                work_dir=settings.work_dir,
            ),
        }
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("analyze", analyse_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    app.add_error_handler(telegram_error_handler)
    return app
