"""Chat client package — pluggable LLM providers for config generation."""
from __future__ import annotations

import os

from chat.base import ChatClient
from chat.openai_client import OpenAIChatClient
from chat.anthropic_client import AnthropicChatClient
from chat.prompts import PromptTemplate, render

__all__ = [
    "ChatClient",
    "OpenAIChatClient",
    "AnthropicChatClient",
    "PromptTemplate",
    "create_client",
    "render",
]

_PROVIDERS = {
    "openai": "_create_openai",
    "anthropic": "_create_anthropic",
}


def create_client(provider: str, check: bool = True, **kwargs) -> ChatClient:
    """Create a ChatClient by provider name.

    Args:
        provider: Provider name (e.g. "openai", "anthropic").
        check: If True (default), verify connectivity with a minimal API call.
               This catches auth/quota errors at startup instead of mid-iteration.

    Raises ValueError if the provider is unknown or misconfigured.
    Raises on API errors if check=True and the connection fails.
    """
    factory = _PROVIDERS.get(provider)
    if factory is None:
        available = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown chat provider: {provider!r}. Available: {available}"
        )
    client = globals()[factory](**kwargs)
    if check:
        client.check_connection()
    return client


def _create_openai(**kwargs) -> OpenAIChatClient:
    api_key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI provider selected but no API key found. "
            "Set OPENAI_API_KEY environment variable or pass api_key=."
        )
    model = kwargs.get("model") or os.environ.get("MODEL_NAME", "gpt-4o-mini")
    return OpenAIChatClient(api_key=api_key, model=model)


def _create_anthropic(**kwargs) -> AnthropicChatClient:
    api_key = kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "Anthropic provider selected but no API key found. "
            "Set ANTHROPIC_API_KEY environment variable or pass api_key=."
        )
    model = kwargs.get("model") or os.environ.get("MODEL_NAME", "claude-sonnet-4-20250514")
    return AnthropicChatClient(api_key=api_key, model=model)
