"""The ``prepare-commit-msg`` hook: install, uninstall, and runtime.

Iron rule: **the hook never blocks a commit.** Every runtime path returns 0,
all errors are swallowed, git calls are timeout-bounded, the shim wraps
generation in a wall-clock ``timeout`` when available, and the message file is
written atomically so a crash mid-write can't corrupt it. Installation backs up
any existing hook and is aware of ``core.hooksPath`` (Husky/pre-commit).
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from . import compose, config, git_io, provider, styles

HOOK_NAME = "prepare-commit-msg"
_BACKUP_SUFFIX = ".bard.bak"
# Identifies a shim we wrote, so reinstall/uninstall never clobbers a user hook.
_MARKER = "Git Commit Bard prepare-commit-msg hook"
_PYTHON_TOKEN = "__BARD_PYTHON__"
_SKIP_ENV_TOKEN = "__BARD_SKIP_ENV__"
_DEFAULT_SKIP_ENV = "BARD_SKIP"
_HOOK_WALL_CLOCK_S = 20
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The installed shim. Tokens are substituted at install time:
#   __BARD_SKIP_ENV__ -> the configured skip-env var name (validated identifier)
#   __BARD_PYTHON__   -> the active interpreter, SINGLE-QUOTED (no shell expansion)
# The skip-check is inline so skipping never even spawns Python. A wall-clock
# `timeout`/`gtimeout` (when present) bounds the whole generation; `|| true`
# bounds the exit code. Either way the hook exits 0.
SHIM_TEMPLATE = """#!/usr/bin/env bash
# Git Commit Bard prepare-commit-msg hook. Never blocks a commit: always exits 0.

# Escape hatch: set this env var to skip versifying a commit.
if [ -n "${__BARD_SKIP_ENV__:-}" ]; then
  exit 0
fi

MSG_FILE="$1"
SOURCE="$2"

# Leave merges, squashes, amends, and -m/-F/-c messages alone.
case "$SOURCE" in
  merge|squash|commit|message)
    exit 0
    ;;
esac

# Bound the whole generation with a wall-clock timeout when one is available.
_bard_to="$(command -v timeout || command -v gtimeout || true)"
_bard_run() {
  if [ -n "$_bard_to" ]; then
    "$_bard_to" 20s "$@" || true
  else
    "$@" || true
  fi
}

if command -v commit-bard >/dev/null 2>&1; then
  _bard_run commit-bard --hook "$MSG_FILE"
else
  _bard_run __BARD_PYTHON__ -m commit_bard.cli --hook "$MSG_FILE"
fi
exit 0
"""


class HookError(RuntimeError):
    """A problem managing the hook (e.g. not in a repo). Install/uninstall only."""


def _safe_env_name(name: str) -> str:
    """Return ``name`` if it's a valid shell identifier, else the default.

    Prevents a stray (or hostile) ``[hook] skip_env`` value from injecting shell
    syntax into the generated shim at install time.
    """
    return name if name and _ENV_NAME_RE.match(name) else _DEFAULT_SKIP_ENV


def _shim_text(skip_env: str) -> str:
    # Single-quote the interpreter path so $VAR/`cmd`/$() in it cannot expand;
    # embedded single-quotes are escaped the POSIX way ('\'').
    safe_python = "'" + sys.executable.replace("'", "'\\''") + "'"
    return SHIM_TEMPLATE.replace(_PYTHON_TOKEN, safe_python).replace(
        _SKIP_ENV_TOKEN, _safe_env_name(skip_env)
    )


def _hooks_dir() -> Tuple[Path, bool]:
    """Return ``(hooks_dir, is_custom)`` honoring ``core.hooksPath``."""
    custom = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if custom.returncode == 0 and custom.stdout.strip():
        return Path(custom.stdout.strip()).expanduser(), True

    path = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if path.returncode == 0 and path.stdout.strip():
        return Path(path.stdout.strip()), False

    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    base = Path(git_dir.stdout.strip()) if git_dir.returncode == 0 else Path(".git")
    return base / "hooks", False


def install_hook() -> Tuple[Path, List[str]]:
    """Install the shim, backing up any pre-existing hook. Returns (path, notes)."""
    if not git_io.in_git_repo():
        raise HookError("Not inside a git repository.")

    hooks_dir, is_custom = _hooks_dir()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / HOOK_NAME
    notes: List[str] = []

    if is_custom:
        notes.append(
            f"core.hooksPath is set ({hooks_dir}); another hook manager may own "
            "it — verify the Bard's hook actually runs."
        )

    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if _MARKER not in existing:
            backup = hooks_dir / (HOOK_NAME + _BACKUP_SUFFIX)
            target.replace(backup)
            notes.append(f"Backed up existing {HOOK_NAME} -> {backup.name}")

    skip_env = config.load().hook_skip_env
    target.write_text(_shim_text(skip_env), encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o111)  # +x for all
    return target, notes


def uninstall_hook() -> Tuple[Path, List[str]]:
    """Remove the shim and restore any backup. Returns (path, notes)."""
    if not git_io.in_git_repo():
        raise HookError("Not inside a git repository.")

    hooks_dir, _ = _hooks_dir()
    target = hooks_dir / HOOK_NAME
    backup = hooks_dir / (HOOK_NAME + _BACKUP_SUFFIX)
    notes: List[str] = []

    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if _MARKER not in existing:
            notes.append(f"{HOOK_NAME} is not the Bard's hook; left it untouched.")
            return target, notes
        target.unlink()
        notes.append(f"Removed {HOOK_NAME}.")
    else:
        notes.append(f"No {HOOK_NAME} hook to remove.")

    if backup.exists():
        backup.replace(target)
        notes.append(f"Restored your previous hook from {backup.name}.")
    return target, notes


def _prepend_to_msg_file(path: Path, message: str) -> None:
    """Atomically write ``message`` above the existing template/comments.

    Writes a sibling temp file then ``os.replace``s it over the target, so a
    crash mid-write leaves the original message file intact.
    """
    try:
        existing = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        existing = ""
    new = message.rstrip() + "\n"
    if existing.strip():
        new = new + "\n" + existing

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".bard")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new)
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise  # caught by run_hook's outer except -> original file untouched


def _select_style(cfg: config.Config) -> styles.Style:
    if cfg.random_style:
        return styles.get_style(random.choice(styles.style_names()))
    return styles.STYLES.get(cfg.style) or styles.get_style(styles.DEFAULT_STYLE)


def run_hook(msg_file: str) -> int:
    """Generate a message into ``msg_file``. Never raises; always returns 0."""
    try:
        cfg = config.load()
        diff = git_io.staged_diff()
        if not diff.strip():
            return 0  # nothing staged (e.g. --allow-empty); leave message alone

        prov_cfg = provider.resolve(
            provider=cfg.provider or None,
            model=cfg.model or None,
            base_url=cfg.base_url or None,
        )
        try:
            message = compose.compose(
                _select_style(cfg),
                diff,
                mode=cfg.mode,
                max_diff_chars=cfg.max_diff_chars,
                timeout_s=cfg.hook_timeout_s,
                config=prov_cfg,
            )
        except Exception:
            if cfg.hook_on_error == "skip":
                return 0
            message = compose.fallback_plain(diff)  # on_error == "plain"

        if message and message.strip():
            _prepend_to_msg_file(Path(msg_file), message)
    except Exception:
        # Absolutely never block a commit, whatever goes wrong.
        return 0
    return 0
