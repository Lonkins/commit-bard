"""Provider-agnostic model client (stdlib HTTP only).

One primary entry point — ``chat(system, user)`` — dispatches to one of four
backends resolved from the environment:

* ``anthropic``          -> POST {base}/v1/messages          (x-api-key header)
* ``openai-compatible``  -> POST {base}/chat/completions     (Bearer auth)
* ``ollama``             -> the OpenAI-compatible shape at a local base_url
* ``mock``               -> a curated offline corpus, no network, never fails

Auto-detect: no key -> ``mock``; one key -> it just works. Keys are read from
the environment only, never from a config file.

We deliberately avoid vendor SDKs: each backend is one POST shape, ``urllib``
handles it, and ``pipx install`` stays instant and dependency-free.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import mock_corpus

# Model defaults are ILLUSTRATIVE and change constantly — always overridable via
# COMMIT_BARD_MODEL. Do not treat these as permanent or authoritative.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",  # illustrative; override via COMMIT_BARD_MODEL
    "openai-compatible": "gpt-4o-mini",  # illustrative; override via COMMIT_BARD_MODEL
    "ollama": "llama3.1",  # illustrative; override via COMMIT_BARD_MODEL
}

DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai-compatible": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
}

# Anthropic pins a dated API version via this header.
_ANTHROPIC_VERSION = "2023-06-01"

VALID_PROVIDERS = ("anthropic", "openai-compatible", "ollama", "mock")


class ProviderError(RuntimeError):
    """A real provider call failed (network, auth, bad response).

    The mock backend never raises this; callers use it to fall back gracefully.
    """


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key: str  # may be "" for mock / keyless ollama


def _detect_provider() -> str:
    """Pick a provider when COMMIT_BARD_PROVIDER is unset.

    anthropic key present -> anthropic; else openai key -> openai-compatible;
    else mock. So: no key -> mock; one key -> it just works.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai-compatible"
    return "mock"


def _resolve_api_key(provider: str) -> str:
    """Resolve the API key for ``provider`` from the environment only."""
    generic = os.environ.get("COMMIT_BARD_API_KEY")
    if generic:
        return generic
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY", "")
    if provider in ("openai-compatible", "ollama"):
        # Ollama usually ignores the key, but an OpenAI-compatible gateway may
        # require one; honor OPENAI_API_KEY for both.
        return os.environ.get("OPENAI_API_KEY", "")
    return ""


def resolve(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ProviderConfig:
    """Resolve the effective provider configuration.

    Precedence for each field: explicit argument (a one-off CLI override) ->
    environment variable -> per-provider default. ``provider`` falls back to
    ``COMMIT_BARD_PROVIDER`` then auto-detection.
    """
    chosen = (provider or os.environ.get("COMMIT_BARD_PROVIDER") or "").strip().lower()
    if not chosen:
        chosen = _detect_provider()
    if chosen not in VALID_PROVIDERS:
        raise ProviderError(
            f"Unknown provider {chosen!r}. "
            f"Valid values: {', '.join(VALID_PROVIDERS)}."
        )

    if chosen == "mock":
        return ProviderConfig(provider="mock", model="mock", base_url="", api_key="")

    chosen_model = model or os.environ.get("COMMIT_BARD_MODEL") or DEFAULT_MODELS[chosen]
    chosen_base = (
        base_url or os.environ.get("COMMIT_BARD_BASE_URL") or DEFAULT_BASE_URLS[chosen]
    )
    return ProviderConfig(
        provider=chosen,
        model=chosen_model,
        base_url=chosen_base.rstrip("/"),
        api_key=_resolve_api_key(chosen),
    )


def current_provider() -> str:
    """The provider that would be used right now (for UX messaging)."""
    return resolve().provider


def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.95,
    max_tokens: int = 300,
    timeout_s: int = 12,
    config: Optional[ProviderConfig] = None,
) -> str:
    """Send one chat turn and return the model's text.

    The mock backend returns a curated verse offline and never raises; real
    backends raise ``ProviderError`` on failure so callers can fall back.
    """
    cfg = config or resolve()
    if cfg.provider == "mock":
        return mock_corpus.reply(system, user)
    if cfg.provider == "anthropic":
        return _anthropic(cfg, system, user, temperature, max_tokens, timeout_s)
    # openai-compatible and ollama share one HTTP shape.
    return _openai_compatible(cfg, system, user, temperature, max_tokens, timeout_s)


def _post_json(url: str, payload: dict, headers: dict, timeout_s: int) -> dict:
    """POST JSON and return the parsed JSON response, mapping errors uniformly."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # 4xx/5xx
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise ProviderError(f"HTTP {exc.code} from {url}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:  # connection/timeout/DNS
        raise ProviderError(f"Could not reach {url}: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Non-JSON response from {url}: {body[:500]}") from exc


def _anthropic(
    cfg: ProviderConfig,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    timeout_s: int,
) -> str:
    if not cfg.api_key:
        raise ProviderError(
            "No API key for anthropic. Set ANTHROPIC_API_KEY (or "
            "COMMIT_BARD_API_KEY), or unset keys to use mock mode."
        )
    url = f"{cfg.base_url}/v1/messages"
    headers = {
        "content-type": "application/json",
        "x-api-key": cfg.api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
    }
    payload = {
        "model": cfg.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    result = _post_json(url, payload, headers, timeout_s)
    try:
        # content is a list of blocks; concatenate the text blocks.
        parts = [
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        ]
        text = "".join(parts).strip()
    except (AttributeError, TypeError) as exc:
        raise ProviderError(f"Unexpected anthropic response shape: {result}") from exc
    if not text:
        raise ProviderError(f"Empty anthropic response: {result}")
    return text


def _openai_compatible(
    cfg: ProviderConfig,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    timeout_s: int,
) -> str:
    url = f"{cfg.base_url}/chat/completions"
    headers = {"content-type": "application/json"}
    if cfg.api_key:
        headers["authorization"] = f"Bearer {cfg.api_key}"
    payload = {
        "model": cfg.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    result = _post_json(url, payload, headers, timeout_s)
    try:
        text = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError(f"Unexpected response shape: {result}") from exc
    if not text:
        raise ProviderError(f"Empty response from {url}: {result}")
    return text
