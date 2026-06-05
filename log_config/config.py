"""structlog configuration for JSON-formatted logs compatible with Grafana Loki."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON output.

    In development (LOG_FORMAT=console) — human-readable ConsoleRenderer to stdout.
    In production (LOG_FORMAT=json) — JSON lines to stdout AND to logs/app.log.
    Promtail reads logs/app.log and pushes to Loki.
    """
    use_json = os.getenv("LOG_FORMAT", "console").lower() == "json"
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if use_json:
        renderer = structlog.processors.JSONRenderer()

        # File handler — Promtail reads this
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB per file
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(level)

        logging.basicConfig(
            level=level,
            handlers=[stdout_handler, file_handler],
            format="%(message)s",
        )

        # Заглушити httpx transport логи — вони не JSON і засмічують app.log
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        logging.basicConfig(
            level=level,
            stream=sys.stdout,
            format="%(message)s",
        )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout) if not use_json
        else structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
