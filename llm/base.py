"""Abstract LLM client interface.

All LLM provider implementations must inherit from LLMClient and implement
the two abstract methods. The rest of the codebase (bot, MCP server) only
imports this base class — swapping providers requires no changes outside llm/.
"""

from abc import ABC, abstractmethod
from typing import Any


class Message(dict):
    """A single conversation message.

    Thin dict subclass so callers can use attribute-style hints while
    still passing the object directly to provider SDKs that expect dicts.

    Keys:
        role: ``"user"``, ``"assistant"``, or ``"tool"``.
        content: Message text or list of content blocks (provider-specific).
    """


class ToolDefinition(dict):
    """Tool schema passed to the LLM so it knows what it can call.

    Keys:
        name: Unique tool identifier, e.g. ``"query_entity"``.
        description: Human/LLM-readable explanation of what the tool does.
        parameters: JSON Schema object describing the tool's input parameters.
    """


class LLMResponse:
    """Normalised response from any LLM provider.

    Attributes:
        content: Final text response from the model (``None`` if the model
            only returned tool calls without a text message).
        tool_calls: List of tool call dicts the model wants to execute.
            Each dict has keys ``id``, ``name``, ``arguments`` (parsed dict).
        raw: The original provider response object, for debugging.
        stop_reason: Why the model stopped — ``"end_turn"``, ``"tool_use"``,
            ``"max_tokens"``, etc. (normalised across providers).
    """

    def __init__(
        self,
        content: str | None,
        tool_calls: list[dict[str, Any]],
        raw: Any,
        stop_reason: str,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.raw = raw
        self.stop_reason = stop_reason

    @property
    def has_tool_calls(self) -> bool:
        """True if the model returned one or more tool calls."""
        return bool(self.tool_calls)


class LLMClient(ABC):
    """Abstract base class for LLM provider clients.

    To add a new provider:
    1. Create ``llm/<provider>_client.py``
    2. Subclass ``LLMClient`` and implement ``chat`` and ``chat_with_tools``
    3. Register the new class in ``llm/factory.py``
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> LLMResponse:
        """Send a conversation to the LLM and get a text response.

        Args:
            messages: Full conversation history in chronological order.
            system: Optional system prompt. If ``None``, no system prompt
                is sent (provider default applies).

        Returns:
            LLMResponse with ``content`` set and empty ``tool_calls``.
        """

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> LLMResponse:
        """Send a conversation with tool definitions to the LLM.

        The model may respond with text, tool calls, or both. The caller
        is responsible for executing tool calls and continuing the loop.

        Args:
            messages: Full conversation history including any previous
                tool results (as ``role="tool"`` messages).
            tools: List of tool definitions the model may call.
            system: Optional system prompt.

        Returns:
            LLMResponse with ``tool_calls`` populated if the model wants
            to call tools, or ``content`` set for a final text answer.
        """
