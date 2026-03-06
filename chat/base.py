"""Abstract base class for LLM chat completion APIs."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChatClient(ABC):
    """Interface for LLM chat completion providers.

    Implementations must handle their own authentication and client setup.
    Errors should propagate — callers decide how to handle failures.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Send a chat completion request and return the assistant's text response.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant message content as a string.
        """
        ...

    def check_connection(self) -> None:
        """Verify that the API key and model are valid by making a minimal request.

        Raises on auth errors, quota issues, or connectivity problems.
        Default implementation sends a tiny chat request.
        """
        self.chat(
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
            max_tokens=1,
        )
