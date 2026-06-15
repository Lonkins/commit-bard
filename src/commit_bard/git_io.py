"""Thin wrappers around git for reading the staged diff.

Everything here is read-only. The only writes the Bard ever makes are to the
commit message file (the git hook), never to your tree or history.

Every git call is bounded by a timeout: inside the prepare-commit-msg hook a
stalled git (hung credential helper, ``index.lock`` contention, slow/NFS work
tree) must never hang the commit. A timeout degrades to a synthetic failure that
callers handle gracefully (skip versifying), upholding the never-block rule.
"""

from __future__ import annotations

import subprocess

# Bound on any single git invocation. Generous for big repos, but finite.
_GIT_TIMEOUT_S = 10


def _run_git(
    args: "list[str]", timeout: float = _GIT_TIMEOUT_S
) -> "subprocess.CompletedProcess[str]":
    """Run ``git <args>`` capturing text output; never hang, never raise.

    Decodes with ``errors="replace"`` so non-UTF-8 diffs can't crash us, and
    maps a missing or stalled git to a synthetic non-zero result instead of an
    exception so callers degrade gracefully.
    """
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, returncode=124, stdout="", stderr=str(exc))


def in_git_repo() -> bool:
    """True if the current directory is inside a git work tree."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def staged_diff() -> str:
    """Return ``git diff --staged --no-color`` output (may be empty)."""
    result = _run_git(["diff", "--staged", "--no-color"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff --staged failed")
    return result.stdout


def staged_stat() -> str:
    """Return ``git diff --staged --stat`` (the shape of the change)."""
    result = _run_git(["diff", "--staged", "--stat", "--no-color"])
    if result.returncode != 0:
        return ""
    return result.stdout
