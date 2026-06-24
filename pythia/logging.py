from __future__ import annotations

import logging.config
from typing import Any

import structlog


def setup(log_level: str) -> None:
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.format_exc_info,
    ]
    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': True,
            'formatters': _get_formatters(pre_chain, 'plain_text'),
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'plain_text',
                },
            },
            'loggers': {
                '': {
                    'handlers': ['console'],
                    'level': log_level,
                },
                'uvicorn': {
                    'handlers': ['console'],
                    'level': logging.ERROR,
                },
            },
        },
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _get_formatters(pre_chain: Any, formatter: str) -> dict[str, Any]:  # pragma: no cover
    """Helper for choosing your fighter."""
    basic_formatter = {
        '()': structlog.stdlib.ProcessorFormatter,
        'foreign_pre_chain': pre_chain,
    }
    # we don't use mapping here, because ConsoleRenderer can require additional permission,
    # and we need lazy processor creation
    processor: Any
    if formatter == 'json':
        processor = structlog.processors.JSONRenderer()
    elif formatter == 'plain_text':
        processor = structlog.dev.ConsoleRenderer(colors=False)
    elif formatter == 'colored_text':
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        raise RuntimeError(f'Unknown formatter: {formatter}')

    basic_formatter['processor'] = processor
    return {formatter: basic_formatter}
