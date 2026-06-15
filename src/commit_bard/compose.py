"""Prompt construction, message composition, and post-processing.

Three output modes:

* ``verse``  — the versified message only.
* ``dual``   — a clean Conventional-Commit subject line plus the verse in the
               body (the default; useful *and* fun).
* ``plain``  — a conventional message only (no verse), handy as a fallback.

The conventional subject is solid, not state-of-the-art (the incumbents own
that). With a real provider, dual mode asks the model for both parts in one
call; offline (mock) or on any parse failure we synthesize the subject from the
diff's shape so a usable message is always produced.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from . import provider, truncate
from .styles import Style

# Persona + a hard output contract: no preamble, no fences, just the message.
SYSTEM_PROMPT = (
    "You are the Git Commit Bard, a poet laureate of version control. You read "
    "a unified diff and distill what changed into a memorable commit message. "
    "You are clever and concise, and you never sacrifice the truth of the diff "
    "for a rhyme. Output ONLY the commit message text — no preamble, no "
    "explanation, no code fences, no surrounding quotes."
)

PLAIN_SYSTEM = (
    "You are a precise commit-message writer. Read the unified diff and write a "
    "single Conventional-Commit subject line: type(scope): summary, in the "
    "imperative mood, under 72 characters. Output ONLY that one line — no body, "
    "no quotes, no code fences."
)

_SUBJECT_NUDGE = "Keep the first line under ~72 characters."
_SUBJECT_NUDGE_RELAXED = "A longer, flowing first line is fine for this form."

#: Sentinel separating the two parts of a dual-mode reply.
DUAL_SEPARATOR = "---"
_SUBJECT_LIMIT = 72


def build_user_prompt(style: Style, diff: str) -> str:
    """Build the user-turn prompt for verse mode."""
    nudge = _SUBJECT_NUDGE_RELAXED if style.allow_long_subject else _SUBJECT_NUDGE
    return (
        f"Write the commit message as {style.instruction} (style: {style.name}).\n"
        "It must still gesture at what actually changed in the diff below — be "
        "specific to this change, not generic.\n"
        f"{nudge}\n\n"
        "DIFF:\n"
        f"{diff}"
    )


def build_dual_prompt(style: Style, diff: str) -> str:
    """Build the user-turn prompt for dual mode (subject + verse)."""
    return (
        f"Write a commit message for the diff below as {style.instruction} "
        f"(style: {style.name}). It must reflect what actually changed.\n\n"
        f'Return EXACTLY two parts separated by a line containing only "{DUAL_SEPARATOR}":\n'
        "1) one Conventional-Commit subject line: type(scope): summary, "
        "imperative, under 72 characters\n"
        f"2) the {style.name} verse\n\n"
        "DIFF:\n"
        f"{diff}"
    )


def build_plain_prompt(diff: str) -> str:
    """Build the user-turn prompt for plain (conventional-only) mode."""
    return f"Write the Conventional-Commit subject line for this diff.\n\nDIFF:\n{diff}"


# Matches a ```lang\n ... ``` fence wrapping the whole reply. The newline
# before the closing fence is optional: smaller models (often via ollama) emit
# the closing ``` on the same line as the last content char.
_FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)
_EXTRA_BLANKS = re.compile(r"\n{3,}")


def postprocess(text: str) -> str:
    """Clean up a model reply: strip fences/quotes/whitespace."""
    cleaned = text.strip()

    fence_match = _FENCE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    elif cleaned[:1] == "“" and cleaned[-1:] == "”":
        cleaned = cleaned[1:-1].strip()

    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = _EXTRA_BLANKS.sub("\n\n", cleaned)
    return cleaned.strip()


# --- conventional subject synthesis (offline / fallback) -------------------

_DIFF_GIT = re.compile(r"^diff --git a/.+? b/(.+)$", re.MULTILINE)


def _changed_paths(diff: str) -> List[str]:
    return [p.strip() for p in _DIFF_GIT.findall(diff)]


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or "/tests/" in path or name.startswith("test_")


def _is_docs(path: str) -> bool:
    return path.endswith(".md") or path.startswith("docs/")


def _guess_type(diff: str, paths: List[str]) -> str:
    if paths and all(_is_test(p) for p in paths):
        return "test"
    if paths and all(_is_docs(p) for p in paths):
        return "docs"
    # New source files present -> lean "feat"; otherwise stay neutral.
    if "new file mode" in diff and any(not _is_test(p) and not _is_docs(p) for p in paths):
        return "feat"
    return "chore"


def _guess_scope(paths: List[str]) -> str:
    dirs = {p.rsplit("/", 1)[0] for p in paths if "/" in p}
    if len(dirs) == 1:
        only = next(iter(dirs))
        return only.rsplit("/", 1)[-1]
    return ""


def synthesize_subject(diff: str) -> str:
    """Build a solid Conventional-Commit subject from the diff's shape.

    Deterministic and offline — the mock-mode subject and the universal
    fallback when a real model is unavailable or its reply can't be parsed.
    """
    paths = _changed_paths(diff)
    if not paths:
        return "chore: update repository"
    ctype = _guess_type(diff, paths)
    scope = _guess_scope(paths)
    if len(paths) == 1:
        summary = f"update {Path(paths[0]).name}"
    else:
        summary = f"update {len(paths)} files"
    prefix = f"{ctype}({scope}): " if scope else f"{ctype}: "
    return _enforce_subject_len(prefix + summary)


def _enforce_subject_len(subject: str, limit: int = _SUBJECT_LIMIT) -> str:
    subject = subject.strip()
    if subject:
        subject = subject.splitlines()[0].strip()
    if len(subject) <= limit:
        return subject
    cut = subject[:limit].rsplit(" ", 1)[0]
    return (cut or subject[:limit]).rstrip()


def _parse_dual(text: str) -> Tuple[Optional[str], str]:
    """Split a dual reply on the ``---`` sentinel -> (subject, verse).

    Returns ``(None, text)`` if the sentinel is absent so the caller can
    synthesize a subject and treat the whole reply as the verse.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == DUAL_SEPARATOR:
            head = "\n".join(lines[:index]).strip()
            verse = "\n".join(lines[index + 1 :]).strip()
            subject = head.splitlines()[0].strip() if head else ""
            return (subject or None), verse
    return None, text


def _assemble_dual(subject: str, verse: str) -> str:
    """Subject, blank line, then the verse indented two spaces as a block."""
    indented = "\n".join(("  " + ln if ln.strip() else "") for ln in verse.splitlines())
    return f"{subject}\n\n{indented}".rstrip()


# --- composition -----------------------------------------------------------


def _chat_verse(
    style: Style,
    diff: str,
    cfg: "provider.ProviderConfig",
    temperature: float,
    max_tokens: int,
    timeout_s: int,
) -> str:
    raw = provider.chat(
        SYSTEM_PROMPT,
        build_user_prompt(style, diff),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        config=cfg,
    )
    return postprocess(raw)


def compose(
    style: Style,
    diff: str,
    *,
    mode: str = "dual",
    max_diff_chars: int = 6000,
    temperature: float = 0.95,
    max_tokens: int = 300,
    timeout_s: int = 12,
    config: "provider.ProviderConfig | None" = None,
) -> str:
    """Generate a commit message for ``style``/``mode`` from ``diff``.

    Raises ``provider.ProviderError`` if a real backend fails; the mock backend
    never raises. Callers (CLI/hook) handle graceful fallback via
    :func:`fallback_plain` so a commit is never blocked.
    """
    # Model prompts get the truncated diff (bounded cost); subject synthesis
    # gets the FULL diff so its file list/count stay accurate on big changes.
    truncated = truncate.truncate_diff(diff, max_diff_chars)
    cfg = config or provider.resolve()

    if mode == "verse":
        return _chat_verse(style, truncated, cfg, temperature, max_tokens, timeout_s)

    if mode == "plain":
        if cfg.provider == "mock":
            return synthesize_subject(diff)
        raw = provider.chat(
            PLAIN_SYSTEM,
            build_plain_prompt(truncated),
            temperature=0.4,
            max_tokens=80,
            timeout_s=timeout_s,
            config=cfg,
        )
        return _enforce_subject_len(postprocess(raw))

    # dual (default)
    if cfg.provider == "mock":
        subject = synthesize_subject(diff)
        verse = _chat_verse(style, truncated, cfg, temperature, max_tokens, timeout_s)
        return _assemble_dual(subject, verse)

    raw = postprocess(
        provider.chat(
            SYSTEM_PROMPT,
            build_dual_prompt(style, truncated),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            config=cfg,
        )
    )
    subject, verse = _parse_dual(raw)
    if subject is None:
        subject = synthesize_subject(diff)
    if not verse.strip():
        # Sentinel present but empty body (or whole reply was the subject):
        # take a second pass for the verse so dual never collapses to plain.
        verse = _chat_verse(style, truncated, cfg, temperature, max_tokens, timeout_s)
    return _assemble_dual(_enforce_subject_len(subject), verse)


def fallback_plain(diff: str) -> str:
    """A guaranteed, offline plain message — the never-block-a-commit safety net."""
    return synthesize_subject(diff)
