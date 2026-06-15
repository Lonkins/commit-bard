"""Built-in styles and the bundled sample diff.

Styles are *data, not code* so they're easy to add and (later) share as
community packs. Each style is a small instruction handed to the model plus a
one-line blurb for ``--list-styles``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    """A single verse style.

    Attributes:
        name: short identifier used on the CLI (e.g. ``"haiku"``).
        instruction: the per-style direction handed to the model.
        blurb: one-liner shown by ``--list-styles``.
        allow_long_subject: narrative forms (epic, ballad, shanty) read poorly
            when squeezed under ~72 chars; when True the length nudge is relaxed.
    """

    name: str
    instruction: str
    blurb: str
    allow_long_subject: bool = False


# The built-in set. Eight styles is a deliberate balance: rich enough to feel
# like a real palette, few enough that each one stays excellent (taste is the
# moat).
_BUILTIN = [
    Style(
        name="haiku",
        instruction=(
            "a strict 5-7-5 haiku across exactly three lines, leaning on a "
            "single concrete image; let the change feel like a small turning "
            "of the season"
        ),
        blurb="A 5-7-5 distillation of what you just did.",
    ),
    Style(
        name="shanty",
        instruction=(
            "a rollicking sea-shanty stanza with a stomping rhythm and a "
            "call-and-response refrain (a 'heave away!' the crew would shout "
            "back)"
        ),
        blurb="A stomping sea-shanty about the merge you survived.",
        allow_long_subject=True,
    ),
    Style(
        name="limerick",
        instruction=(
            "a single AABBA limerick with a bouncy meter and a punchy, "
            "slightly smug final line"
        ),
        blurb="Five bouncy lines with a smug little punchline.",
    ),
    Style(
        name="epic",
        instruction=(
            "grand Homeric epic verse: invoke the muse, treat the diff as the "
            "deed of a hero, and render a trivial change as world-shaking legend"
        ),
        blurb="Homeric grandeur for your one-line null check.",
        allow_long_subject=True,
    ),
    Style(
        name="ballad",
        instruction=(
            "a wistful folk-ballad quatrain rhyming ABAB, telling the change "
            "as a small, slightly melancholy story"
        ),
        blurb="A wistful little folk ballad of the change.",
        allow_long_subject=True,
    ),
    Style(
        name="pirate",
        instruction=(
            "salty pirate-speak — arr, all swagger and sea-dog bravado, the "
            "codebase a ship and the bug a scurvy stowaway"
        ),
        blurb="Arr. The bug be walkin' the plank.",
    ),
    Style(
        name="corporate",
        instruction=(
            "soulless corporate-buzzword synergy-speak: leverage paradigm "
            "shifts, circle back on key learnings, and action the deliverable "
            "going forward — utterly hollow, gloriously so"
        ),
        blurb="Leveraging synergies to action your deliverable.",
    ),
    Style(
        name="noir",
        instruction=(
            "hard-boiled 1940s detective-noir narration: rain on the window, a "
            "cheap cigarette, and a bug that was guilty all along"
        ),
        blurb="The bug walked in. It looked guilty.",
    ),
]

#: Mapping of style name -> Style, the canonical lookup used everywhere.
STYLES = {style.name: style for style in _BUILTIN}

#: The default style when none is configured or requested.
DEFAULT_STYLE = "haiku"


def get_style(name: str) -> Style:
    """Return the Style for ``name``.

    Raises:
        KeyError: if no such style exists. Callers (the CLI) catch this and
            print the list of valid names.
    """
    return STYLES[name]


def style_names() -> "list[str]":
    """Style names in their declared (curated) order."""
    return [s.name for s in _BUILTIN]


# A small, believable staged diff bundled so the tool runs with no repo and no
# key: ``commit-bard --sample`` is the instant, shareable demo. It mirrors the
# README taste example — a tokenizer fix that now skips comment tokens, plus a
# test for it.
SAMPLE_DIFF = '''diff --git a/src/lexer/tokenizer.py b/src/lexer/tokenizer.py
index 3f9a1c2..b7e4d05 100644
--- a/src/lexer/tokenizer.py
+++ b/src/lexer/tokenizer.py
@@ -42,9 +42,13 @@ class Tokenizer:
     def _scan(self, source):
         tokens = []
         for line in source.splitlines():
+            # Skip comment lines so they never reach the parser.
+            if line.lstrip().startswith("#"):
+                continue
             for tok in self._split(line):
-                tokens.append(tok)
+                if tok:
+                    tokens.append(tok)
         return tokens
diff --git a/tests/test_tokenizer.py b/tests/test_tokenizer.py
index 1a2b3c4..9d8e7f6 100644
--- a/tests/test_tokenizer.py
+++ b/tests/test_tokenizer.py
@@ -10,3 +10,8 @@ def test_splits_simple_line():
     assert Tokenizer().scan("a b c") == ["a", "b", "c"]
+
+
+def test_skips_comment_lines():
+    src = "# a comment\\nx = 1"
+    assert Tokenizer().scan(src) == ["x", "=", "1"]
'''
