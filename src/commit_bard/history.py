"""Optional local poem history (off by default).

When enabled (``[bard] history = true`` / ``COMMIT_BARD_HISTORY=1``), each
generated message is appended as one JSON line to
``.git/commit-bard/history.jsonl``. It lives *inside* ``.git`` so it's local and
never committed, and it gives ``wrapped`` a precise record of poems — including
ones for commits you amended or never made.

Everything here is best-effort: recording never raises and never disrupts a
commit, and reading degrades to an empty list.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import git_io

_REL_PATH = ("commit-bard", "history.jsonl")


def _history_path() -> Optional[Path]:
    """``<git-dir>/commit-bard/history.jsonl`` if we're in a repo, else None."""
    result = git_io._run_git(["rev-parse", "--git-dir"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).joinpath(*_REL_PATH)


def record(entry: Dict[str, Any], *, enabled: bool) -> None:
    """Append ``entry`` (stamped with a UTC timestamp) to the history log.

    No-op when disabled; swallows every error so it can never block a commit.
    """
    if not enabled:
        return
    try:
        path = _history_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), **entry}, ensure_ascii=False
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass  # history is a nicety, never a failure point


def load() -> List[Dict[str, Any]]:
    """Return all recorded entries (newest last), or [] if none/unreadable."""
    path = _history_path()
    if path is None or not path.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
