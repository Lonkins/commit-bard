"""Repo "wrapped": collect the best commit poems from history into a digest.

It reads ``git log`` and pulls the verse out of dual-mode commits (the verse is
the two-space-indented block in the body), scores them with a small offline
heuristic, and renders a shareable digest as Markdown or a standalone HTML
"gallery" page. No history file required — it reconstructs straight from git, so
it works on any repo that has used the Bard.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from typing import List, Optional

from . import git_io

# Lines that mark a bullet/numbered list item (so we don't mistake a markdown
# list's hanging-indented continuation lines for a verse).
_BULLET_RE = re.compile(r"^\s*([-*+]\s|\d+[.)]\s)")


@dataclass(frozen=True)
class Poem:
    subject: str
    verse: str
    short_hash: str
    date: str
    author: str
    score: float


def _is_verse_line(line: str) -> bool:
    """A line that may belong to a verse: blank, or indented and not a bullet."""
    return not line.strip() or (line.startswith("  ") and not _BULLET_RE.match(line))


def _extract_verse(body: str) -> Optional[str]:
    """Pull the verse out of a dual-mode commit body.

    Dual mode appends the verse last, as an indented block preceded by a blank
    line. We take the trailing run of blank/indented lines — keeping internal
    blank lines so multi-stanza verses survive — but only if it's separated from
    any preceding prose by a blank line (or sits at the start of the body), so a
    markdown list's hanging-indented continuation lines aren't mistaken for a
    poem.
    """
    lines = body.splitlines()
    boundary = len(lines) - 1
    while boundary >= 0 and _is_verse_line(lines[boundary]):
        boundary -= 1
    region = lines[boundary + 1 :]

    # Need a real (non-blank, indented) verse line.
    if not any(ln.startswith("  ") and ln.strip() for ln in region):
        return None
    # Must be separated from preceding prose: at the body start, or led by a
    # blank line. Otherwise it's a continuation of the line above (e.g. a bullet).
    if boundary >= 0 and region and region[0].strip():
        return None

    dedented = [ln[2:] if ln.startswith("  ") else ln for ln in region]
    return "\n".join(dedented).strip() or None


def _score(verse: str) -> float:
    """A small, deterministic 'how poem-y is this' heuristic (offline).

    Rewards multi-line structure and lexical variety, lightly rewards length.
    Not the model's taste — just enough to float the good ones to the top.
    """
    lines = [ln for ln in verse.splitlines() if ln.strip()]
    words = verse.split()
    if not words:
        return 0.0
    distinct = len({w.lower().strip(".,;:!?—-'\"") for w in words})
    variety = distinct / len(words)
    return round(len(lines) + variety * 5 + min(len(words), 40) * 0.1, 2)


def collect(commits: List[git_io.Commit]) -> List[Poem]:
    """Extract and score every commit poem, best first."""
    poems = []
    for commit in commits:
        verse = _extract_verse(commit.body)
        if not verse:
            continue
        poems.append(
            Poem(
                subject=commit.subject,
                verse=verse,
                short_hash=commit.hash[:9],
                date=commit.date[:10],
                author=commit.author,
                score=_score(verse),
            )
        )
    poems.sort(key=lambda p: p.score, reverse=True)
    return poems


def render_markdown(poems: List[Poem]) -> str:
    if not poems:
        return (
            "# Your Repo, in Verse\n\n"
            "No commit poems found yet. Install the hook "
            "(`commit-bard install-hook`) and make a few commits!\n"
        )
    out = ["# 🎵 Your Repo, in Verse", "", f"*{len(poems)} commit poem(s), best first.*", ""]
    for index, poem in enumerate(poems, 1):
        # Escape commit-derived text: it's untrusted and the digest may be
        # viewed in a Markdown renderer that passes raw HTML through.
        out.append(f"## {index}. {_html.escape(poem.subject)}")
        out.append("")
        for line in poem.verse.splitlines():
            out.append(f"> {_html.escape(line)}" if line.strip() else ">")
        out.append("")
        out.append(
            f"`{poem.short_hash}` · {poem.date} · {_html.escape(poem.author)} · score {poem.score}"
        )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your Repo, in Verse</title>
<style>
  :root { --ink: #1d1a17; --paper: #f6f1e7; --accent: #b4532a; --muted: #8a7f70; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink);
         font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
         line-height: 1.5; padding: 3rem 1.25rem; }
  .wrap { max-width: 46rem; margin: 0 auto; }
  header h1 { font-size: clamp(2rem, 1rem + 5vw, 3.5rem); margin: 0 0 .25rem;
              letter-spacing: -0.02em; }
  header p { color: var(--muted); margin: 0 0 2.5rem; }
  .poem { position: relative; background: #fffdf8; border: 1px solid #e7ddca;
          border-radius: 14px; padding: 1.5rem 1.5rem 1.1rem; margin: 0 0 1.5rem;
          box-shadow: 0 1px 0 #fff inset, 0 8px 24px -18px rgba(0,0,0,.5); }
  .poem .rank { position: absolute; top: -0.9rem; left: 1.25rem; background: var(--accent);
                color: #fff; font-weight: 700; font-size: .8rem; width: 1.8rem; height: 1.8rem;
                display: grid; place-items: center; border-radius: 50%; }
  .poem h2 { font-size: 1.05rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
             color: var(--accent); margin: .4rem 0 1rem; font-weight: 600; }
  .verse { font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size: 1.2rem;
           white-space: pre-wrap; margin: 0; }
  footer.meta { color: var(--muted); font-size: .8rem; font-family: ui-monospace, Menlo, monospace;
                margin-top: 1rem; }
  .empty { color: var(--muted); font-size: 1.1rem; }
  .foot { color: var(--muted); font-size: .8rem; text-align: center; margin-top: 2rem; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Your Repo, in Verse</h1>
  <p>__COUNT__ commit poem(s), best first — by Git Commit Bard.</p>
</header>
__BODY__
<p class="foot">Generated by Git Commit Bard.</p>
</div>
</body>
</html>
"""


def render_html(poems: List[Poem]) -> str:
    if not poems:
        body = '<p class="empty">No commit poems yet. Install the hook and make a few commits!</p>'
    else:
        cards = []
        for index, poem in enumerate(poems, 1):
            cards.append(
                '<article class="poem">\n'
                f'  <div class="rank">{index}</div>\n'
                f"  <h2>{_html.escape(poem.subject)}</h2>\n"
                f'  <pre class="verse">{_html.escape(poem.verse)}</pre>\n'
                f'  <footer class="meta">{poem.short_hash} · {poem.date} · '
                f"{_html.escape(poem.author)} · score {poem.score}</footer>\n"
                "</article>"
            )
        body = "\n".join(cards)
    return _PAGE.replace("__COUNT__", str(len(poems))).replace("__BODY__", body)


def wrapped(rev_range: Optional[str] = None, top: int = 10, fmt: str = "md") -> str:
    """Build the digest: scan history, collect poems, render md/html."""
    poems = collect(git_io.git_log(rev_range))[: max(0, top)]
    return render_html(poems) if fmt == "html" else render_markdown(poems)
