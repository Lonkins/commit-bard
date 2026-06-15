"""Command-line entry point.

UX contract:
    stdout = the artifact (the commit message) — pipe-clean.
    stderr = chatter (the mock-mode notice, warnings, errors).

Exit codes:
    0  success
    1  runtime problem (no staged changes, a real-provider failure)
    2  usage problem (unknown style)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import List, Optional

from . import __version__, compose, config, git_io, provider, styles

_PROG = "commit-bard"

_MOCK_NOTICE = (
    "# (mock mode — set a provider + API key for diff-aware verse; "
    "see `commit-bard --help`)"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Your staged diff, returned as verse.",
        epilog="No API key? It still runs, in a charming offline mock mode.",
    )
    parser.add_argument(
        "--style",
        metavar="NAME",
        help="verse style (default from config; see --list-styles)",
    )
    parser.add_argument(
        "--sample",
        metavar="N",
        nargs="?",
        type=int,
        const=1,
        default=None,
        help="use a bundled diff so it runs with no repo/key; "
        "optional N prints N styles side by side",
    )
    parser.add_argument(
        "--list-styles",
        action="store_true",
        help="list the built-in styles and exit",
    )
    parser.add_argument(
        "--random-style",
        action="store_true",
        help="surprise me — pick a random style",
    )
    parser.add_argument(
        "--provider",
        metavar="P",
        help="one-off provider override (anthropic|openai-compatible|ollama|mock)",
    )
    parser.add_argument(
        "--model",
        metavar="M",
        help="one-off model override",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{_PROG} {__version__}",
    )
    return parser


def _print_styles() -> int:
    width = max(len(name) for name in styles.style_names())
    for name in styles.style_names():
        print(f"  {name.ljust(width)}  {styles.STYLES[name].blurb}")
    return 0


def _resolve_style_name(args: argparse.Namespace, cfg: config.Config) -> str:
    if args.random_style:
        import random

        return random.choice(styles.style_names())
    return args.style or cfg.style


def _get_diff(args: argparse.Namespace) -> Optional[str]:
    """Return the diff to versify, or None if the caller should stop.

    On the stop path the user-facing message has already gone to stderr.
    """
    if args.sample is not None:
        return styles.SAMPLE_DIFF
    if not git_io.in_git_repo():
        print(
            "Not inside a git repository. Stage some changes in a repo, "
            "or try `commit-bard --sample`.",
            file=sys.stderr,
        )
        return None
    diff = git_io.staged_diff()
    if not diff.strip():
        print(
            "No staged changes found. Stage something with `git add`, "
            "or try `commit-bard --sample`.",
            file=sys.stderr,
        )
        return None
    return diff


def _emit_mock_notice(cfg: provider.ProviderConfig) -> None:
    if cfg.provider == "mock":
        print(_MOCK_NOTICE, file=sys.stderr)


def _run_single(style_name: str, diff: str, prov_cfg: provider.ProviderConfig) -> int:
    style = styles.get_style(style_name)
    try:
        message = compose.compose(style, diff, config=prov_cfg)
    except provider.ProviderError as exc:
        # On a real-provider failure, report cleanly rather than crashing.
        print(f"Provider error: {exc}", file=sys.stderr)
        return 1
    _emit_mock_notice(prov_cfg)
    print(message)
    return 0


def _run_sample_palette(count: int, diff: str, prov_cfg: provider.ProviderConfig) -> int:
    names = styles.style_names()[: max(1, count)]
    _emit_mock_notice(prov_cfg)
    for index, name in enumerate(names):
        style = styles.get_style(name)
        try:
            message = compose.compose(style, diff, config=prov_cfg)
        except provider.ProviderError as exc:
            print(f"Provider error: {exc}", file=sys.stderr)
            return 1
        if index:
            print()
        print(f"── {name} ──")
        print(message)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_styles:
        return _print_styles()

    cfg = config.load()
    style_name = _resolve_style_name(args, cfg)

    # Validate the chosen style early, before any model call.
    if style_name not in styles.STYLES:
        print(
            f"Unknown style {style_name!r}. Valid styles:",
            file=sys.stderr,
        )
        for name in styles.style_names():
            print(f"  {name}", file=sys.stderr)
        return 2

    diff = _get_diff(args)
    if diff is None:
        return 1

    prov_cfg = provider.resolve(provider=args.provider, model=args.model)

    # A multi-style palette (--sample N, N>1) is a demo/screenshot affordance.
    if args.sample is not None and args.sample > 1:
        return _run_sample_palette(args.sample, diff, prov_cfg)

    return _run_single(style_name, diff, prov_cfg)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
