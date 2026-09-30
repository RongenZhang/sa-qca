from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ProviderError, RateLimitError


class FakeMessages:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.kwargs = result, exc, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return self.result


def fake_client(**kw):
    return SimpleNamespace(messages=FakeMessages(**kw))


def msg(text):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], model="claude-x", id="m1", stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_text_returned_untouched_and_usage_recorded():
    c = fake_client(result=msg('  {"a": 1}\n'))
    r = AnthropicProvider("k", client=c).complete("hi", model="claude-x", sampling={})
    assert r.text == '  {"a": 1}\n' and (r.tokens_in, r.tokens_out, r.model_id) == (10, 5, "claude-x")


def test_sampling_params_only_sent_when_set():
    c = fake_client(result=msg("x"))
    AnthropicProvider("k", client=c).complete("hi", model="m", sampling={})
    assert "temperature" not in c.messages.kwargs
    AnthropicProvider("k", client=c).complete("hi", model="m", sampling={"temperature": 0.7})
    assert c.messages.kwargs["temperature"] == 0.7


def _err(cls):
    req = httpx.Request("POST", "https://x")
    resp = httpx.Response(429 if cls is anthropic.RateLimitError else 400, request=req)
    return cls("boom", response=resp, body=None)


def test_rate_limit_and_provider_errors_mapped():
    with pytest.raises(RateLimitError):
        AnthropicProvider("k", client=fake_client(exc=_err(anthropic.RateLimitError))).complete("p", model="m", sampling={})
    with pytest.raises(ProviderError):
        AnthropicProvider("k", client=fake_client(exc=_err(anthropic.BadRequestError))).complete("p", model="m", sampling={})


def test_key_never_in_repr():
    assert "sk-secret" not in repr(AnthropicProvider("sk-secret", client=fake_client()))


def test_workspace_id_is_sent_as_header_only_when_given(monkeypatch):
    seen = {}

    def fake_ctor(**kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    AnthropicProvider("k", workspace_id="wrkspc_123")
    assert seen["default_headers"] == {"anthropic-workspace-id": "wrkspc_123"}
    AnthropicProvider("k")
    assert seen["default_headers"] is None
