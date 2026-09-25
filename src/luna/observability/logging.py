"""Structured (JSON) logging setup.

Why JSON logs from day one, before there's anything interesting to log:
plain-text logs are fine until you have more than one request in flight,
at which point interleaved lines from concurrent requests become
unreadable. JSON logs + a request-id field (see middleware.py) let you
filter to exactly one request's lines even under concurrency — and once
Loki exists (Phase 6), it's what makes "show me every log line for this
request-id" a real query instead of manual grep-and-hope.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Call once, at process startup, before anything else logs."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
