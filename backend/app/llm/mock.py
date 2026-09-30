"""Scripted provider for tests and the demo. Items are response text or an Exception to raise."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.llm.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, script: list[str | Exception] | Callable[[str], str | Exception]) -> None:
        self._script = script
        self.prompts: list[str] = []
        self._i = 0

    def complete(self, prompt: str, *, model: str, sampling: dict[str, Any]) -> LLMResponse:
        self.prompts.append(prompt)
        item = self._script(prompt) if callable(self._script) else self._script[self._i]
        self._i += 1
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model_id=model, tokens_in=len(prompt) // 4, tokens_out=len(item) // 4)
