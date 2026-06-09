"""Aiogram handlers for the BAS accounting bot."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.claude_client import ask
from bot.history import History

router = Router()
history = History()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привіт! Я бухгалтерський асистент з доступом до 1С/BAS.\n"
        "Задавай питання про документи, контрагентів, співробітників.\n\n"
        "Команди:\n"
        "/clear — очистити історію розмови"
    )


@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    history.clear(message.from_user.id)
    await message.answer("Історію розмови очищено.")


@router.message()
async def handle_text(message: Message) -> None:
    user_id = message.from_user.id
    question = message.text or ""

    if not question.strip():
        return

    # Show typing indicator while processing
    await message.bot.send_chat_action(message.chat.id, "typing")

    user_history = history.get(user_id)
    answer, input_tokens, output_tokens = await ask(question, user_history)

    # Save only clean text to history (no tool blocks)
    history.append(user_id, "user", question)
    history.append(user_id, "assistant", answer)

    token_line = f"\n\n_🔢 токени: in={input_tokens} out={output_tokens} total={input_tokens + output_tokens}_"
    await message.answer(answer + token_line, parse_mode="Markdown")
