"""Prompt construction and output post-processing.

The core primitive is ``compose(style, diff)`` -> a finished verse string.
Today this produces *verse* mode (the versified message). A "dual" mode — a
clean Conventional-Commit subject line plus the verse — and a plain mode are
planned; the seams are left here so they slot in without churn.
"""

from __future__ import annotations

import re

from . import provider
from .styles import Style

# Persona + a hard output contract: no preamble, no fences, just the message.
SYSTEM_PROMPT = (
    "You are the Git Commit Bard, a poet laureate of version control. You read "
    "a unified diff and distill what changed into a memorable commit message. "
    "You are clever and concise, and you never sacrifice the truth of the diff "
    "for a rhyme. Output ONLY the commit message text — no preamble, no "
    "explanation, no code fences, no surrounding quotes."
)

_SUBJECT_NUDGE = "Keep the first line under ~72 characters."
_SUBJECT_NUDGE_RELAXED = (
    "A longer, flowing first line is fine for this form."
)


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


# Matches a ```lang\n ... ``` fence wrapping the whole reply. The newline
# before the closing fence is optional: smaller models (often via ollama) emit
# the closing ``` on the same line as the last content char.
_FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)
# Collapses 3+ consecutive newlines down to a single blank line.
_EXTRA_BLANKS = re.compile(r"\n{3,}")


def postprocess(text: str) -> str:
    """Clean up a model reply: strip fences/quotes/whitespace.

    Models sometimes wrap output in code fences or quotes despite instructions;
    we strip those, trim trailing whitespace per line, and normalize blank runs.
    """
    cleaned = text.strip()

    fence_match = _FENCE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Strip a single pair of matching wrapping quotes (straight or curly).
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    elif cleaned[:1] == "“" and cleaned[-1:] == "”":
        cleaned = cleaned[1:-1].strip()

    # Trim trailing whitespace on each line; collapse oversized blank runs.
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = _EXTRA_BLANKS.sub("\n\n", cleaned)
    return cleaned.strip()


def compose(
    style: Style,
    diff: str,
    *,
    temperature: float = 0.95,
    max_tokens: int = 300,
    timeout_s: int = 12,
    config: "provider.ProviderConfig | None" = None,
) -> str:
    """Generate a versified commit message for ``style`` from ``diff``.

    Raises ``provider.ProviderError`` if a real backend fails; the mock backend
    never raises. Callers decide how to degrade on failure.
    """
    user_prompt = build_user_prompt(style, diff)
    raw = provider.chat(
        SYSTEM_PROMPT,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
        config=config,
    )
    return postprocess(raw)
