"""Provider abstraction. Adapters must return the model's text untouched."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class RateLimitError(Exception):
    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    """Non-retryable provider failure (auth, bad request, etc.)."""


@dataclass
class LLMResponse:
    text: str
    model_id: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def complete(self, prompt: str, *, model: str, sampling: dict[str, Any]) -> LLMResponse:
        """Single request. Raise RateLimitError on 429-type failures, ProviderError otherwise."""
