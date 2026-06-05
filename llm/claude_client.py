"""Anthropic Claude LLM client implementation.

Claude uses a different tool_use format from OpenAI/Groq:
- Tools are passed as ``tools`` list with ``input_schema`` (not ``parameters``)
- Tool calls come back as content blocks with ``type="tool_use"``
- Tool results are passed as ``role="user"`` messages with ``type="tool_result"``

This client normalises all of that into the shared LLMResponse format.
"""

import json
from typing import Any

import structlog
from llm.base import LLMClient, LLMResponse, Message, ToolDefinition

log = structlog.get_logger(__name__)


class ClaudeClient(LLMClient):
    """LLM client backed by Anthropic Claude API.

    Args:
        api_key: Anthropic API key.
        model: Model ID, e.g. ``"claude-sonnet-4-20250514"``.
        max_tokens: Maximum tokens in the response (default 4096).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
    ) -> None:
        # Import here so missing anthropic package doesn't break Groq-only usage
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

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
        log.info("claude_chat", model=self._model, message_count=len(messages))

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": list(messages),
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
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
        claude_tools = [self._convert_tool(t) for t in tools]

        log.info(
            "claude_chat_with_tools",
            model=self._model,
            message_count=len(messages),
            tool_count=len(claude_tools),
        )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": list(messages),
            "tools": claude_tools,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return self._parse_response(response)

    @staticmethod
    def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
        """Convert our ToolDefinition to Anthropic tool format.

        Anthropic uses ``input_schema`` instead of ``parameters``.
        """
        return {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }

    def _parse_response(self, response: Any) -> LLMResponse:
        """Normalise an Anthropic messages response into LLMResponse."""
        stop_reason = response.stop_reason or "end_turn"
        content_text: str | None = None
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)

        log.info(
            "claude_response",
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tools=[t["name"] for t in tool_calls] if tool_calls else [],
        )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            raw=response,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
