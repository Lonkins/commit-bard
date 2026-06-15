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
from dataclasses import dataclass
from typing import List, Optional

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


@dataclass(frozen=True)
class Commit:
    """One commit's metadata + message, for the 'wrapped' digest."""

    hash: str
    date: str  # ISO-8601 author date
    author: str
    subject: str
    body: str


# Field-separated, record-separated log so multiline bodies parse cleanly.
_LOG_FORMAT = "%H%x1f%aI%x1f%an%x1f%s%x1f%b%x1e"


def _parse_log(output: str) -> List[Commit]:
    commits: List[Commit] = []
    for record in output.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        # maxsplit=4: a body containing a stray \x1f must land intact in parts[4].
        parts = record.split("\x1f", 4)
        if len(parts) < 5:
            continue
        commits.append(
            Commit(
                hash=parts[0].strip(),
                date=parts[1].strip(),
                author=parts[2].strip(),
                subject=parts[3].strip(),
                body=parts[4].strip("\n"),
            )
        )
    return commits


def git_log(rev_range: Optional[str] = None, max_count: int = 2000) -> List[Commit]:
    """Return recent commits (newest first), bounded by ``max_count``.

    ``rev_range`` is an optional revision range like ``v1.0..HEAD``. Returns an
    empty list if git fails (never raises).
    """
    args = ["log", "--no-color", f"--format={_LOG_FORMAT}"]
    if max_count:
        args.append(f"--max-count={max_count}")
    if rev_range:
        args.append(rev_range)
    result = _run_git(args)
    if result.returncode != 0:
        return []
    return _parse_log(result.stdout)
