"""The real-provider HTTP path — request shapes, parsing, and error mapping.

All offline: ``urllib.request.urlopen`` is monkeypatched with a fake context
manager. The spec calls this abstraction "the part most worth getting right"
(architecture §4), and the Phase-1 DoD includes the real-key diff-aware verse,
so it gets first-class test coverage despite needing no network.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from commit_bard import provider


class _FakeResponse:
    """Minimal stand-in for the object urlopen returns as a context manager."""

    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, *, body=None, capture=None, raise_exc=None):
    def fake_urlopen(request, timeout=None):
        if capture is not None:
            capture.append(request)
        if raise_exc is not None:
            raise raise_exc
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _headers_lower(request):
    return {k.lower(): v for k, v in request.headers.items()}


# --- happy paths -----------------------------------------------------------


def test_anthropic_request_shape_and_response_parsing(clean_env, monkeypatch):
    captured = []
    body = json.dumps(
        {"content": [{"type": "text", "text": "a "}, {"type": "text", "text": "verse"}]}
    )
    _patch_urlopen(monkeypatch, body=body, capture=captured)
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "k")

    out = provider.chat("SYS", "USR", config=cfg)

    assert out == "a verse"  # text blocks concatenated
    request = captured[0]
    assert request.full_url.endswith("/v1/messages")
    headers = _headers_lower(request)
    assert headers["x-api-key"] == "k"
    assert "anthropic-version" in headers
    payload = json.loads(request.data)
    assert payload["system"] == "SYS"  # top-level system field
    assert payload["messages"] == [{"role": "user", "content": "USR"}]
    assert payload["model"] == "m"


def test_openai_compatible_request_shape_and_response_parsing(clean_env, monkeypatch):
    captured = []
    body = json.dumps({"choices": [{"message": {"content": "a verse"}}]})
    _patch_urlopen(monkeypatch, body=body, capture=captured)
    cfg = provider.ProviderConfig("openai-compatible", "m", "https://x/v1", "k")

    out = provider.chat("SYS", "USR", config=cfg)

    assert out == "a verse"
    request = captured[0]
    assert request.full_url.endswith("/chat/completions")
    headers = _headers_lower(request)
    assert headers["authorization"] == "Bearer k"
    payload = json.loads(request.data)
    assert payload["messages"][0] == {"role": "system", "content": "SYS"}
    assert payload["messages"][1] == {"role": "user", "content": "USR"}


def test_ollama_uses_openai_shape_without_auth_header(clean_env, monkeypatch):
    captured = []
    body = json.dumps({"choices": [{"message": {"content": "verse"}}]})
    _patch_urlopen(monkeypatch, body=body, capture=captured)
    # ollama dispatches through the openai-compatible path; empty key -> no auth.
    cfg = provider.ProviderConfig("ollama", "llama", "http://localhost:11434/v1", "")

    out = provider.chat("SYS", "USR", config=cfg)

    assert out == "verse"
    request = captured[0]
    assert request.full_url.endswith("/chat/completions")
    assert "authorization" not in _headers_lower(request)


# --- error mapping ---------------------------------------------------------


def test_anthropic_empty_key_raises_without_network(clean_env, monkeypatch):
    calls = []
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: calls.append(1)
    )
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)
    assert not calls, "must not hit the network when the key is missing"


def test_http_error_maps_to_provider_error(clean_env, monkeypatch):
    err = urllib.error.HTTPError(
        "https://x/v1/messages", 401, "Unauthorized", {}, io.BytesIO(b"bad key")
    )
    _patch_urlopen(monkeypatch, raise_exc=err)
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "k")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)


def test_url_error_maps_to_provider_error(clean_env, monkeypatch):
    _patch_urlopen(monkeypatch, raise_exc=urllib.error.URLError("timed out"))
    cfg = provider.ProviderConfig("openai-compatible", "m", "https://x/v1", "k")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)


def test_non_json_body_maps_to_provider_error(clean_env, monkeypatch):
    _patch_urlopen(monkeypatch, body="this is not json")
    cfg = provider.ProviderConfig("openai-compatible", "m", "https://x/v1", "k")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)


def test_empty_anthropic_content_maps_to_provider_error(clean_env, monkeypatch):
    _patch_urlopen(monkeypatch, body=json.dumps({"content": []}))
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "k")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)


def test_unexpected_openai_shape_maps_to_provider_error(clean_env, monkeypatch):
    _patch_urlopen(monkeypatch, body=json.dumps({"nope": True}))
    cfg = provider.ProviderConfig("openai-compatible", "m", "https://x/v1", "k")
    with pytest.raises(provider.ProviderError):
        provider.chat("s", "u", config=cfg)
