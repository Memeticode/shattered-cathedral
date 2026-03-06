"""OpenAI chat completion implementation."""
from __future__ import annotations

from chat.base import ChatClient


class OpenAIChatClient(ChatClient):
    """Chat client backed by the OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
