"""LLM client factory.

Reads LLM_PROVIDER from environment and returns the appropriate LLMClient
implementation. Adding a new provider requires only:
  1. Creating llm/<provider>_client.py with a LLMClient subclass
  2. Adding an entry to _PROVIDERS below
  3. Setting LLM_PROVIDER=<provider> in .env
"""

import os

from llm.base import LLMClient

_PROVIDERS: dict[str, tuple[str, str, list[str]]] = {
    "groq": (
        "llm.groq_client",
        "GroqClient",
        ["GROQ_API_KEY", "GROQ_MODEL"],
    ),
    "claude": (
        "llm.claude_client",
        "ClaudeClient",
        ["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"],
    ),
}


def create_llm_client() -> LLMClient:
    """Instantiate and return the configured LLM client.

    Reads ``LLM_PROVIDER`` from environment (default: ``"groq"``).
    Provider-specific credentials are also read from environment.

    Returns:
        Configured LLMClient instance ready for use.

    Raises:
        ValueError: If LLM_PROVIDER is unknown or required env vars are missing.

    Example:
        Set ``LLM_PROVIDER=groq`` in .env to use Groq (default).
        Set ``LLM_PROVIDER=claude`` to switch to Anthropic Claude.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider not in _PROVIDERS:
        available = ", ".join(_PROVIDERS.keys())
        raise ValueError(f"Unknown LLM_PROVIDER='{provider}'. Available: {available}")

    module_path, class_name, required_vars = _PROVIDERS[provider]

    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise ValueError(
            f"LLM_PROVIDER='{provider}' requires env vars: {', '.join(missing)}"
        )

    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    if provider == "groq":
        return cls(
            api_key=os.environ["GROQ_API_KEY"],
            model=os.environ["GROQ_MODEL"],
        )

    if provider == "claude":
        return cls(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ["ANTHROPIC_MODEL"],
        )

    raise ValueError(f"Provider '{provider}' registered but not instantiated.")
