"""Shared test fixtures."""

import pytest

# Every env var that can steer provider/style resolution. Cleared per-test so
# the suite is hermetic regardless of the developer's real environment.
_STEERING_VARS = (
    "COMMIT_BARD_PROVIDER",
    "COMMIT_BARD_API_KEY",
    "COMMIT_BARD_MODEL",
    "COMMIT_BARD_BASE_URL",
    "COMMIT_BARD_STYLE",
    "COMMIT_BARD_MODE",
    "COMMIT_BARD_RANDOM_STYLE",
    "COMMIT_BARD_MAX_DIFF_CHARS",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all provider/style steering env vars -> mock mode, defaults."""
    for var in _STEERING_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture(autouse=True)
def hermetic_config(monkeypatch, tmp_path):
    """Never read a real user/repo config file during tests.

    On Python 3.9/3.10 ``tomllib`` is absent so file config is already inert,
    but on 3.11+ a stray ``.commit-bard.toml`` at the repo root or a user
    ``~/.config/commit-bard/config.toml`` could non-hermetically steer results.
    Point XDG at an empty tmp dir and stub the repo-config lookup so the suite
    is hermetic on every interpreter.
    """
    from commit_bard import config

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(config, "_repo_config_path", lambda: None)
