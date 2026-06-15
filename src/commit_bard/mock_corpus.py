"""The curated offline verse corpus — the no-key demo asset.

With no provider or API key configured, ``chat()`` returns a hand-written,
on-theme verse from this corpus. The bar is high on purpose: ``commit-bard
--sample --style shanty`` with no key should *still* make someone smile. This is
a marketing asset, not a placeholder.

The first entry in each style nods at the bundled sample diff (a tokenizer that
now skips comment lines), so ``--sample`` reads as apt; the rest are general
hymns to shipping and fixing code. Selection is seedable for tests yet lively in
normal use.
"""

from __future__ import annotations

import random
import re

from .styles import DEFAULT_STYLE

# style name -> list of verses. Every built-in style MUST appear here.
CORPUS: "dict[str, list[str]]" = {
    "haiku": [
        "Comments fall like leaves—\n"
        "the parser walks a clean path,\n"
        "green tests rise at dawn.",
        "One null check, quiet—\n"
        "the crash that haunted midnight\n"
        "never comes again.",
        "Refactor at dusk:\n"
        "old functions fall, brown and spent;\n"
        "new green in the diff.",
    ],
    "shanty": [
        "Oh the comments clogged the scanner and the parser ran aground,\n"
        "  (heave away!)\n"
        "We struck 'em from the token-stream and turned the whole thing 'round,\n"
        "  (heave away, me hearties!)\n"
        "So haul upon the green test, boys, and sing her up the sound—\n"
        "  heave away, the build is bound!",
        "We sailed into a merge at noon with conflicts ten feet high,\n"
        "  (heave away!)\n"
        "We picked 'em clean and one by one we watched the markers die,\n"
        "  (heave away, me hearties!)\n"
        "So pull the branch to harbour, lads, beneath a passing CI—\n"
        "  heave away, the tests don't lie!",
    ],
    "limerick": [
        "A tokenizer, prone to complain,\n"
        "choked on each comment again and again.\n"
        "  We taught it to skip\n"
        "  with a one-line clip—\n"
        "now the parser is right as the rain.",
        "There once was a null we ignored,\n"
        "till it crashed every demo on board.\n"
        "  We added a check\n"
        "  (it took half a sec),\n"
        "and the stack traces finally snored.",
        "A merge that we thought would be neat\n"
        "left conflicts from our head to our feet.\n"
        "  We squashed every one,\n"
        "  re-ran till it spun\n"
        "all green—and we called it complete.",
    ],
    "epic": [
        "Sing, O Muse, of the hand that strode into the lexer's gloom,\n"
        "where comments lay like fallen kings athwart the parser's road.\n"
        "With one bold loop the hero swept the dead glyphs from the stream,\n"
        "and lo—the green tests rose as dawn upon the hills of code.",
        "Sing of the bug that lurked nine commits deep within the dark,\n"
        "a hydra of the midnight log, regrowing every head.\n"
        "The hero raised a single check, no larger than a spark,\n"
        "and where the crash had reigned for years, a quiet green was spread.",
    ],
    "ballad": [
        "The comments crowded every line,\n"
        "they choked the parser slow;\n"
        "we struck them out at half past nine\n"
        "and let the clean tests go.",
        "A null slipped quiet through the code\n"
        "and slept for many a day,\n"
        "one morning when the server slowed\n"
        "we coaxed the ghost away.",
    ],
    "pirate": [
        "Arr! The comments be stowaways, lurkin' in the hold o' the parser. "
        "So we keelhauled the lot, swabbed the token-deck spotless, and now the "
        "green tests be flyin' proud from the mast. Yo ho!",
        "Avast! A scurvy null been hidin' below decks, nine commits deep, "
        "sinkin' every demo we set to sail. One swing o' the cutlass and the "
        "blighter walked the plank. Dead men file no bug reports.",
    ],
    "corporate": [
        "Per our tokenization workstream, we proactively deprecated low-value "
        "comment artifacts upstream of the parser to unlock parse-time "
        "efficiencies. Net-net, coverage is trending green. Circling back "
        "Friday with learnings.",
        "Going forward, we've actioned a robust null-handling deliverable to "
        "de-risk the customer journey and right-size our exception surface. A "
        "true paradigm shift in stability. Let's socialize the win.",
    ],
    "noir": [
        "The comments came in like trouble always does—quiet, wearing a hash "
        "mark for a hat. They'd been gumming up the parser for weeks. I dropped "
        "them at the door of the token stream and didn't look back. The tests "
        "came up green. They always do, once you find the body.",
        "It was a null. It's always a null. Slipped into the codebase nine "
        "commits ago and waited, patient as a loan shark. I put one check "
        "between it and the door. The crash stopped calling. The city slept.",
    ],
}

# Pattern emitted by compose.py: "(style: haiku)". Primary detection signal.
_STYLE_TAG = re.compile(r"style:\s*([a-z0-9_-]+)", re.IGNORECASE)


def detect_style(user_prompt: str) -> str:
    """Infer the requested style from the composed user prompt.

    ``chat()`` only receives ``(system, user)`` text, so the mock recovers the
    style from the prompt. Prefers the explicit ``style: NAME`` tag, then any
    known style name appearing as a word, else the default.
    """
    match = _STYLE_TAG.search(user_prompt)
    if match:
        name = match.group(1).lower()
        if name in CORPUS:
            return name
    lowered = user_prompt.lower()
    for name in CORPUS:
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return name
    return DEFAULT_STYLE


def pick(style_name: str, *, rng: "random.Random | None" = None) -> str:
    """Return one verse for ``style_name`` (falling back to the default)."""
    verses = CORPUS.get(style_name) or CORPUS[DEFAULT_STYLE]
    chooser = rng or random
    return chooser.choice(verses)


def reply(system: str, user: str, *, seed: "int | None" = None) -> str:
    """Mock ``chat()``: detect the style and return a curated verse.

    Pass ``seed`` for deterministic selection in tests; omit it for lively
    variety in real use. Never touches the network and never raises.
    """
    style_name = detect_style(user)
    rng = random.Random(seed) if seed is not None else None
    return pick(style_name, rng=rng)
