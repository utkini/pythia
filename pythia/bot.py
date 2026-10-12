import structlog
from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from pythia.config import settings
from pythia.database import check_database, create_engine, create_session_factory
from pythia.reporting import TelegramReporter
from pythia.repositories import AnalysisRepository
from pythia.services.instagram import InvalidProfileUrl, InstagramCollector, normalize_instagram_url
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
    await update.effective_message.reply_text("Пришлите ссылку на публичный Instagram-профиль или Reel, либо используйте /analyze <ссылка>.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_owner(update, context):
        return
    await update.effective_message.reply_text(
        "Я анализирую до трёх свежих Reels публичного профиля: лайки, комментарии, речь, текст на экране и смысл ролика.\n"
        "Также принимаю прямую ссылку на Reel. Просмотры пока не учитываются.\n"
        "Пример: /analyze https://www.instagram.com/instagram/"
    )


async def analyse_url(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_url: str) -> None:
    if not await is_owner(update, context):
        return
    try:
        username, profile_url = normalize_instagram_url(raw_url)
    except InvalidProfileUrl as error:
        await update.effective_message.reply_text(str(error))
        return

    manager: JobManager = context.application.bot_data["jobs"]
    service: AnalysisService = context.application.bot_data["service"]
    chat_id = update.effective_chat.id
    accepted = await manager.submit(lambda: service.execute(username, profile_url, chat_id))
    if not accepted:
        await update.effective_message.reply_text("Сейчас уже выполняется анализ. Дождитесь его завершения и повторите запрос.")
        return
    await update.effective_message.reply_text(f"Принято: {profile_url}. Начинаю анализ, это может занять несколько минут.")


async def analyse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_owner(update, context):
        return
    if not context.args:
        await update.effective_message.reply_text("Использование: /analyze https://www.instagram.com/<username>/")
        return
    await analyse_url(update, context, " ".join(context.args))


async def text_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is not None:
        await analyse_url(update, context, update.effective_message.text)


async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep transient Telegram transport failures from producing unhandled traces."""
    if isinstance(context.error, NetworkError):
        logger.warning("telegram_network_error", error=str(context.error))
        return
    logger.error("telegram_handler_error", error=repr(context.error), exc_info=context.error)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_url))
    app.add_error_handler(telegram_error_handler)
    return app
