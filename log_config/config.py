"""structlog configuration for JSON-formatted logs compatible with Grafana Loki."""

import logging
import os
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON output.

    Call once at application startup before any logging occurs.

    In development the output is human-readable (ConsoleRenderer).
    In production (when LOG_FORMAT=json is set) it emits JSON lines
    suitable for ingestion by Grafana Loki.

    Args:
        log_level: Standard Python log level name, e.g. ``"INFO"``,
            ``"DEBUG"``, ``"WARNING"``.
    """
    use_json = os.getenv("LOG_FORMAT", "console").lower() == "json"

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if use_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
