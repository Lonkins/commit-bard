"""Thin wrappers around git for reading the staged diff.

Everything here is read-only this phase. The only writes the Bard ever makes
are to the commit message file (the git hook), never to your tree or history.
"""

from __future__ import annotations

import subprocess


def _run_git(args: "list[str]") -> "subprocess.CompletedProcess[str]":
    """Run ``git <args>`` capturing text output.

    Decodes with ``errors="replace"`` so a diff containing non-UTF-8 bytes can
    never crash us — we'd rather versify a mojibake hunk than blow up.
    """
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )


def in_git_repo() -> bool:
    """True if the current directory is inside a git work tree."""
    try:
        result = _run_git(["rev-parse", "--is-inside-work-tree"])
    except FileNotFoundError:
        # git not on PATH at all.
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def staged_diff() -> str:
    """Return ``git diff --staged --no-color`` output (may be empty)."""
    result = _run_git(["diff", "--staged", "--no-color"])
    if result.returncode != 0:
        # Surface git's own complaint; the CLI decides how to present it.
        raise RuntimeError(result.stderr.strip() or "git diff --staged failed")
    return result.stdout


def staged_stat() -> str:
    """Return ``git diff --staged --stat`` (the shape of the change).

    Used for big-diff truncation; cheap and handy for showing the *shape* of a
    change even when the raw diff is trimmed.
    """
    result = _run_git(["diff", "--staged", "--stat", "--no-color"])
    if result.returncode != 0:
        return ""
    return result.stdout
