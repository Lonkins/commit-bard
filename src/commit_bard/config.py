"""Configuration loading and the defaults -> env resolution order.

Resolution order (later overrides earlier):
    built-in defaults
    -> user config   (~/.config/commit-bard/config.toml)
    -> repo config   (.commit-bard.toml at the repo root)
    -> environment variables
    -> CLI flags      (applied by the caller via ``dataclasses.replace``)

Secrets (API keys) are NEVER read from a config file — only from the
environment (see ``provider.py``). Storing keys in dotfiles that may be
committed is a security footgun we refuse on purpose.

TOML file support is wired here but is only *active* on Python 3.11+ (which has
``tomllib`` in the stdlib). On 3.9/3.10 the file layers are skipped gracefully;
a small vendored TOML subset parser could add it there later. Until then,
defaults + environment fully drive behaviour, which covers current needs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional

from .styles import DEFAULT_STYLE

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised on <3.11 only
    tomllib = None  # type: ignore


# Truthy string values for env-var booleans.
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # [bard]
    style: str = DEFAULT_STYLE
    mode: str = "dual"  # "dual" | "verse" | "plain"
    random_style: bool = False
    max_diff_chars: int = 6000
    # [provider] (non-secret prefs only; keys live in the environment)
    provider: str = ""  # "" -> auto-detect in provider.resolve()
    model: str = ""
    base_url: str = ""
    # [hook]
    hook_skip_env: str = "BARD_SKIP"
    hook_timeout_s: int = 12
    hook_on_error: str = "plain"  # "plain" | "skip" — never block the commit


def _user_config_path() -> Path:
    """~/.config/commit-bard/config.toml (honoring XDG_CONFIG_HOME)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "commit-bard" / "config.toml"


def _repo_config_path() -> Optional[Path]:
    """.commit-bard.toml at the git repo root, if we're in a repo."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    top = result.stdout.strip()
    return Path(top) / ".commit-bard.toml" if top else None


# Flat field name -> (toml table, toml key) for file-based overrides.
_TOML_MAP = {
    "style": ("bard", "style"),
    "mode": ("bard", "mode"),
    "random_style": ("bard", "random_style"),
    "max_diff_chars": ("bard", "max_diff_chars"),
    "provider": ("provider", "provider"),
    "model": ("provider", "model"),
    "base_url": ("provider", "base_url"),
    "hook_skip_env": ("hook", "skip_env"),
    "hook_timeout_s": ("hook", "timeout_s"),
    "hook_on_error": ("hook", "on_error"),
}


def _load_toml(path: Optional[Path]) -> Dict[str, Any]:
    """Read a config TOML into a flat overrides dict (best-effort)."""
    if path is None or tomllib is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError):
        # A malformed config file should never crash the Bard.
        return {}
    overrides: Dict[str, Any] = {}
    for field_name, (table, key) in _TOML_MAP.items():
        section = data.get(table)
        if isinstance(section, dict) and key in section:
            overrides[field_name] = section[key]
    return overrides


def _env_overrides() -> Dict[str, Any]:
    """Environment overrides for the non-secret config knobs."""
    overrides: Dict[str, Any] = {}
    env = os.environ
    if "COMMIT_BARD_STYLE" in env:
        overrides["style"] = env["COMMIT_BARD_STYLE"]
    if "COMMIT_BARD_MODE" in env:
        overrides["mode"] = env["COMMIT_BARD_MODE"]
    if "COMMIT_BARD_RANDOM_STYLE" in env:
        overrides["random_style"] = env["COMMIT_BARD_RANDOM_STYLE"].lower() in _TRUTHY
    if "COMMIT_BARD_MAX_DIFF_CHARS" in env:
        try:
            overrides["max_diff_chars"] = int(env["COMMIT_BARD_MAX_DIFF_CHARS"])
        except ValueError:
            pass
    if "COMMIT_BARD_PROVIDER" in env:
        overrides["provider"] = env["COMMIT_BARD_PROVIDER"]
    if "COMMIT_BARD_MODEL" in env:
        overrides["model"] = env["COMMIT_BARD_MODEL"]
    if "COMMIT_BARD_BASE_URL" in env:
        overrides["base_url"] = env["COMMIT_BARD_BASE_URL"]
    return overrides


def _coerce(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Drop keys that aren't real Config fields (defensive against typos)."""
    valid = {f.name for f in fields(Config)}
    return {k: v for k, v in overrides.items() if k in valid}


def load() -> Config:
    """Build the effective Config from defaults -> user -> repo -> env.

    CLI flags are layered on top by the caller via ``replace(cfg, **flags)``.
    """
    merged: Dict[str, Any] = {}
    merged.update(_load_toml(_user_config_path()))
    merged.update(_load_toml(_repo_config_path()))
    merged.update(_env_overrides())
    return Config(**_coerce(merged))
