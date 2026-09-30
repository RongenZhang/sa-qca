"""Anthropic adapter. The API key is held in memory only and never logged or persisted."""

from __future__ import annotations

from typing import Any

import anthropic

from app.llm.base import LLMProvider, LLMResponse, ProviderError, RateLimitError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, client: Any | None = None, workspace_id: str | None = None) -> None:
        # Keys that are not scoped to a workspace must name one on every request.
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self._client = client or anthropic.Anthropic(api_key=api_key, max_retries=0, default_headers=headers)

    def __repr__(self) -> str:  # never expose the key
        return "AnthropicProvider(api_key=<redacted>)"

    def complete(self, prompt: str, *, model: str, sampling: dict[str, Any]) -> LLMResponse:
        kwargs: dict[str, Any] = {"max_tokens": sampling.get("max_tokens", 4096)}
        # Some recent models reject sampling parameters; send only what the caller set.
        for k in ("temperature", "top_p"):
            if sampling.get(k) is not None:
                kwargs[k] = sampling[k]
        try:
            msg = self._client.messages.create(
                model=model, messages=[{"role": "user", "content": prompt}], **kwargs
            )
        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e)) from e
        except anthropic.APIError as e:
            raise ProviderError(type(e).__name__ + ": " + str(e)) from e
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return LLMResponse(
            text=text,
            model_id=msg.model,
            tokens_in=msg.usage.input_tokens,
            tokens_out=msg.usage.output_tokens,
            raw={"id": msg.id, "stop_reason": msg.stop_reason},
        )
