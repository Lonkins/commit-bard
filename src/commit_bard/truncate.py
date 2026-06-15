"""Bound large diffs before sending them to a model.

Diffs can be enormous; we cap tokens, cost, and latency. When a diff exceeds the
budget we summarize *structurally* before truncating raw text: a compact
per-file ``+adds -dels`` shape (so the model still sees the change's silhouette),
then as many whole file hunks as fit, then a marker. Binary and lockfile-style
entries are collapsed to one line each rather than spending budget on noise.

A haiku about a 4000-file refactor is funny *because* it's reductive, so
aggressive truncation is fine — the verse only needs the gist.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_BINARY_RE = re.compile(r"^Binary files .* differ$", re.MULTILINE)
# Generated/lockfiles: spend a line, not the budget.
_LOCKFILE_HINTS = ("lock", ".min.js", ".min.css", ".map")
_FILE_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)
# Headroom kept aside for the "N of M files shown" marker line.
_MARKER_RESERVE = 80


def _split_sections(diff: str) -> List[str]:
    """Split a unified diff into per-file sections (each starts 'diff --git')."""
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    return [p for p in parts if p.strip()]


def _path_of(section: str) -> str:
    match = _FILE_HEADER_RE.search(section)
    return match.group(2).strip() if match else "?"


def _counts(section: str) -> Tuple[int, int]:
    adds = dels = 0
    for line in section.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            adds += 1
        elif line.startswith("-") and not line.startswith("---"):
            dels += 1
    return adds, dels


def _is_noise(path: str, section: str) -> bool:
    if _BINARY_RE.search(section):
        return True
    return any(hint in path for hint in _LOCKFILE_HINTS)


def truncate_diff(diff: str, max_chars: int = 6000) -> str:
    """Return ``diff`` unchanged if within budget, else a structural summary."""
    if len(diff) <= max_chars:
        return diff

    sections = _split_sections(diff)
    if not sections:  # couldn't parse structure; hard-trim as a last resort
        return diff[:max_chars] + "\n# … (diff truncated)\n"

    # 1) A compact shape of every file, always included. Noise (binary/lockfile)
    #    is tagged "(omitted)" and never contributes its content to the body.
    stat_lines: List[str] = []
    non_noise: List[str] = []
    for section in sections:
        path = _path_of(section)
        adds, dels = _counts(section)
        if _is_noise(path, section):
            stat_lines.append(f"#   {path}: +{adds} -{dels} (omitted)")
        else:
            stat_lines.append(f"#   {path}: +{adds} -{dels}")
            non_noise.append(section)
    stat_block = "# changed files:\n" + "\n".join(stat_lines) + "\n#\n"

    # 2) Pack whole non-noise hunks until the budget runs out. Reserve headroom
    #    for the marker so the total stays bounded.
    budget = max_chars - len(stat_block) - _MARKER_RESERVE
    kept = 0
    body: List[str] = []
    for section in non_noise:
        if len(section) <= budget:
            body.append(section)
            budget -= len(section)
            kept += 1

    # If no whole section fit but real content exists, hard-trim a non-noise
    # section (never the raw diff — that would re-leak omitted lockfile content).
    if kept == 0 and non_noise and budget > 120:
        snippet = non_noise[0][: budget - 30].rstrip()
        body.append(snippet + "\n# … (file truncated)\n")

    total = len(sections)
    marker = f"# ({kept} of {total} files shown in full; rest summarized above)\n"
    return stat_block + marker + "".join(body)
