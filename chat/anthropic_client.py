"""Anthropic (Claude) chat completion implementation."""
from __future__ import annotations

from chat.base import ChatClient


class AnthropicChatClient(ChatClient):
    """Chat client backed by the Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        # Anthropic uses a separate system parameter instead of a system message role
        system = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system

        resp = self._client.messages.create(**kwargs)
        return resp.content[0].text.strip()
