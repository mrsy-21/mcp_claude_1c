"""Manual integration test for LLM client factory and Groq/Claude providers.

Run with:
    uv run python -m tests.test_llm

Requires .env with LLM_PROVIDER and corresponding API key set.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Make sure project root is on path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.factory import create_llm_client
from llm.base import Message, ToolDefinition
from log_config.config import setup_logging

setup_logging("DEBUG")

import structlog
log = structlog.get_logger(__name__)


DUMMY_TOOL: ToolDefinition = ToolDefinition(
    name="get_current_time",
    description="Returns the current server time. Call this when the user asks what time it is.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name, e.g. 'Europe/Kyiv'. Default UTC.",
            }
        },
        "required": [],
    },
)


async def test_simple_chat() -> None:
    """Test plain chat without tools."""
    print("\n" + "=" * 60)
    print("TEST 1: simple chat (no tools)")
    print("=" * 60)

    client = create_llm_client()
    messages = [Message(role="user", content="Привіт! Відповідай коротко — хто ти?")]

    response = await client.chat(messages=messages, system="Ти корисний асистент.")

    print(f"stop_reason : {response.stop_reason}")
    print(f"has_tool_calls: {response.has_tool_calls}")
    print(f"content     : {response.content}")
    assert response.content, "Expected text content"
    assert not response.has_tool_calls, "Expected no tool calls"
    print("✓ PASSED")


async def test_chat_with_tools_no_call() -> None:
    """Test chat with tools available but model should NOT call them."""
    print("\n" + "=" * 60)
    print("TEST 2: chat with tools — model should answer without calling")
    print("=" * 60)

    client = create_llm_client()
    messages = [Message(role="user", content="Яка столиця України?")]

    response = await client.chat_with_tools(
        messages=messages,
        tools=[DUMMY_TOOL],
        system="Ти корисний асистент.",
    )

    print(f"stop_reason : {response.stop_reason}")
    print(f"has_tool_calls: {response.has_tool_calls}")
    print(f"content     : {response.content}")
    assert response.content, "Expected text content"
    print("✓ PASSED")


async def test_chat_with_tools_triggers_call() -> None:
    """Test that model calls a tool when it makes sense."""
    print("\n" + "=" * 60)
    print("TEST 3: chat with tools — model SHOULD call get_current_time")
    print("=" * 60)

    client = create_llm_client()
    messages = [Message(role="user", content="Котра зараз година?")]

    response = await client.chat_with_tools(
        messages=messages,
        tools=[DUMMY_TOOL],
        system="Ти корисний асистент. Для відповіді на питання про час використовуй get_current_time.",
    )

    print(f"stop_reason   : {response.stop_reason}")
    print(f"has_tool_calls: {response.has_tool_calls}")
    print(f"tool_calls    : {response.tool_calls}")
    print(f"content       : {response.content}")
    assert response.has_tool_calls, "Expected model to call get_current_time"
    assert response.tool_calls[0]["name"] == "get_current_time"
    print("✓ PASSED")


async def test_tool_result_loop() -> None:
    """Test a full one-iteration agentic loop: call → result → final answer."""
    print("\n" + "=" * 60)
    print("TEST 4: full tool loop (call → inject result → final answer)")
    print("=" * 60)

    client = create_llm_client()
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    # Step 1: user asks
    messages: list[Message] = [
        Message(role="user", content="Котра зараз година?")
    ]

    response = await client.chat_with_tools(
        messages=messages,
        tools=[DUMMY_TOOL],
        system="Ти корисний асистент.",
    )

    assert response.has_tool_calls, "Expected tool call in step 1"
    tc = response.tool_calls[0]
    print(f"Tool called: {tc['name']}({tc['arguments']})")

    # Step 2: inject tool result — format differs per provider
    if provider == "groq":
        # Groq/OpenAI: assistant message with tool_calls + tool result message
        messages.append(Message(
            role="assistant",
            content=response.content or "",
            tool_calls=[{
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": str(tc["arguments"]),
                },
            }],
        ))
        messages.append(Message(
            role="tool",
            tool_call_id=tc["id"],
            content="14:35 UTC+2 (Europe/Kyiv)",
        ))
    else:
        # Claude: assistant message with content blocks + user message with tool_result
        messages.append(Message(
            role="assistant",
            content=[
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]}
            ],
        ))
        messages.append(Message(
            role="user",
            content=[
                {"type": "tool_result", "tool_use_id": tc["id"], "content": "14:35 UTC+2 (Europe/Kyiv)"}
            ],
        ))

    # Step 3: get final answer
    final = await client.chat_with_tools(
        messages=messages,
        tools=[DUMMY_TOOL],
        system="Ти корисний асистент.",
    )

    print(f"Final stop_reason: {final.stop_reason}")
    print(f"Final content    : {final.content}")
    assert final.content, "Expected final text answer"
    assert not final.has_tool_calls, "Expected no more tool calls"
    print("✓ PASSED")


async def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "groq")
    print(f"\nRunning LLM tests with provider: {provider}")

    try:
        await test_simple_chat()
        await test_chat_with_tools_no_call()
        await test_chat_with_tools_triggers_call()
        await test_tool_result_loop()
        print("\n✓ ALL TESTS PASSED")
    except AssertionError as e:
        print(f"\n✗ FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
