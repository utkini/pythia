import structlog

import pythia.logging as log
from pythia.bot import build_application
from pythia.config import settings

logger = structlog.get_logger(__name__)


def main() -> None:
    log.setup('INFO')
    logger.info('Starting Pythia')
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    build_application().run_polling(drop_pending_updates=True, bootstrap_retries=-1, timeout=30)


if __name__ == "__main__":
    main()
