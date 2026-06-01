"""Groq LLM client implementation (Kimi K2 / llama models).

Groq uses the OpenAI-compatible API format, so tool_use works via the
standard ``tools`` + ``tool_choice`` parameters. Tool call results are
passed back as ``role="tool"`` messages with a ``tool_call_id``.
"""

import json
from typing import Any

import structlog
from groq import AsyncGroq
from llm.base import LLMClient, LLMResponse, Message, ToolDefinition

log = structlog.get_logger(__name__)


class GroqClient(LLMClient):
    """LLM client backed by Groq API (OpenAI-compatible format).

    Args:
        api_key: Groq API key.
        model: Model ID, e.g. ``"moonshotai/kimi-k2-instruct"``.
        max_tokens: Maximum tokens in the response (default 4096).
        temperature: Sampling temperature (default 0.1 for factual tasks).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> LLMResponse:
        """Send conversation without tools and return text response.

        Args:
            messages: Conversation history.
            system: Optional system prompt.

        Returns:
            LLMResponse with text content and empty tool_calls.
        """
        groq_messages = self._build_messages(messages, system)
        log.info("groq_chat", model=self._model, message_count=len(groq_messages))

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        return self._parse_response(response)

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> LLMResponse:
        """Send conversation with tool definitions.

        Args:
            messages: Conversation history including tool results.
            tools: Tools the model may call.
            system: Optional system prompt.

        Returns:
            LLMResponse with tool_calls if model wants to call a tool,
            or content for a final text answer.
        """
        groq_messages = self._build_messages(messages, system)
        groq_tools = [self._convert_tool(t) for t in tools]

        log.info(
            "groq_chat_with_tools",
            model=self._model,
            message_count=len(groq_messages),
            tool_count=len(groq_tools),
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        return self._parse_response(response)

    @staticmethod
    def _build_messages(
        messages: list[Message],
        system: str | None,
    ) -> list[dict[str, Any]]:
        """Prepend system message and return Groq-formatted message list."""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend(messages)
        return result

    @staticmethod
    def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
        """Convert our ToolDefinition to Groq/OpenAI tool format."""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }

    def _parse_response(self, response: Any) -> LLMResponse:
        """Normalise a Groq completion response into LLMResponse."""
        choice = response.choices[0]
        message = choice.message
        stop_reason = choice.finish_reason or "end_turn"

        content: str | None = message.content or None
        tool_calls: list[dict[str, Any]] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": arguments,
                    }
                )
            log.info("groq_tool_calls", tools=[t["name"] for t in tool_calls])

        if stop_reason == "tool_calls":
            stop_reason = "tool_use"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw=response,
            stop_reason=stop_reason,
        )
