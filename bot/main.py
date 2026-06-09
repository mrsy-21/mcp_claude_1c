"""Telegram bot entry point."""

import asyncio
import os

import structlog
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from log_config.config import setup_logging
from bot.claude_client import init_tools, FASTAPI_URL
from bot.handlers import router

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
log = structlog.get_logger(__name__)


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    log.info("bot_starting", fastapi_url=FASTAPI_URL)

    await init_tools()

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    log.info("bot_polling_started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
