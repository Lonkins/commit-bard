"""Command-line entry point.

UX contract:
    stdout = the artifact (the commit message) — pipe-clean.
    stderr = chatter (the mock-mode notice, warnings, errors).

Exit codes:
    0  success (and ALWAYS for the internal --hook path)
    1  runtime problem (no staged changes, hook-management error)
    2  usage problem (unknown style/mode)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, compose, config, git_io, hook, provider, styles, wrapped

_PROG = "commit-bard"
_MODES = ("dual", "verse", "plain")

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
    parser.add_argument("--style", metavar="NAME", help="verse style (see --list-styles)")
    parser.add_argument(
        "--mode",
        choices=_MODES,
        help="dual (subject + verse, default), verse (verse only), or plain",
    )
    parser.add_argument(
        "--dual", action="store_true", help="shortcut for --mode dual"
    )
    parser.add_argument(
        "--sample",
        metavar="N",
        nargs="?",
        type=int,
        const=1,
        default=None,
        help="use a bundled diff (no repo/key needed); optional N prints N styles",
    )
    parser.add_argument(
        "--list-styles", action="store_true", help="list the built-in styles and exit"
    )
    parser.add_argument(
        "--random-style", action="store_true", help="surprise me — pick a random style"
    )
    parser.add_argument("--provider", metavar="P", help="one-off provider override")
    parser.add_argument("--model", metavar="M", help="one-off model override")
    parser.add_argument(
        "--diff-file",
        metavar="PATH",
        help="read the diff from a file (or - for stdin) instead of git (handy in CI)",
    )
    # Internal: invoked by the installed git hook. Hidden from --help.
    parser.add_argument("--hook", metavar="MSGFILE", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"{_PROG} {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("install-hook", help="install the prepare-commit-msg hook")
    subparsers.add_parser("uninstall-hook", help="remove the prepare-commit-msg hook")

    wrapped_p = subparsers.add_parser(
        "wrapped", help="collect the best commit poems from history into a digest"
    )
    wrapped_p.add_argument("--since", metavar="REF", help="only commits after this ref")
    wrapped_p.add_argument("--top", type=int, default=10, help="how many poems (default 10)")
    wrapped_p.add_argument(
        "--format", choices=("md", "html"), default="md", help="output format"
    )
    return parser


def _print_styles() -> int:
    width = max(len(name) for name in styles.style_names())
    for name in styles.style_names():
        print(f"  {name.ljust(width)}  {styles.STYLES[name].blurb}")
    return 0


def _resolve_mode(args: argparse.Namespace, cfg: config.Config) -> str:
    if args.dual:
        return "dual"
    return args.mode or cfg.mode


def _resolve_style_name(args: argparse.Namespace, cfg: config.Config) -> str:
    if args.random_style:
        import random

        return random.choice(styles.style_names())
    return args.style or cfg.style


def _get_diff(args: argparse.Namespace) -> Optional[str]:
    """Return the diff to versify, or None if the caller should stop (msg on stderr)."""
    if args.sample is not None:
        return styles.SAMPLE_DIFF
    if args.diff_file:
        if args.diff_file == "-":
            return sys.stdin.read()
        try:
            return Path(args.diff_file).read_text(errors="replace")
        except OSError as exc:
            print(f"Could not read diff file: {exc}", file=sys.stderr)
            return None
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


def _emit_mock_notice(prov_cfg: provider.ProviderConfig) -> None:
    if prov_cfg.provider == "mock":
        print(_MOCK_NOTICE, file=sys.stderr)


def _compose_or_fallback(
    style: styles.Style,
    diff: str,
    mode: str,
    cfg: config.Config,
    prov_cfg: provider.ProviderConfig,
) -> str:
    """Compose a message, gracefully degrading to a plain line on provider failure."""
    try:
        return compose.compose(
            style, diff, mode=mode, max_diff_chars=cfg.max_diff_chars, config=prov_cfg
        )
    except provider.ProviderError as exc:
        print(
            f"# (provider error: {exc}; falling back to a plain message)",
            file=sys.stderr,
        )
        return compose.fallback_plain(diff)


def _run_single(
    style_name: str,
    diff: str,
    mode: str,
    cfg: config.Config,
    prov_cfg: provider.ProviderConfig,
) -> int:
    style = styles.get_style(style_name)
    message = _compose_or_fallback(style, diff, mode, cfg, prov_cfg)
    _emit_mock_notice(prov_cfg)
    print(message)
    return 0


def _run_sample_palette(
    count: int, diff: str, mode: str, cfg: config.Config, prov_cfg: provider.ProviderConfig
) -> int:
    names = styles.style_names()[: max(1, count)]
    _emit_mock_notice(prov_cfg)
    for index, name in enumerate(names):
        style = styles.get_style(name)
        message = _compose_or_fallback(style, diff, mode, cfg, prov_cfg)
        if index:
            print()
        print(f"── {name} ──")
        print(message)
    return 0


def _cmd_install_hook() -> int:
    try:
        target, notes = hook.install_hook()
    except hook.HookError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    cfg = config.load()
    print(f"Installed {hook.HOOK_NAME} hook -> {target}")
    for note in notes:
        print(f"  - {note}")
    print(f"Active style/mode: {cfg.style} / {cfg.mode}")
    print(
        "Escape hatch: set BARD_SKIP=1 to skip a commit, "
        "or run `commit-bard uninstall-hook` to remove."
    )
    return 0


def _cmd_uninstall_hook() -> int:
    try:
        _, notes = hook.uninstall_hook()
    except hook.HookError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for note in notes:
        print(f"  - {note}")
    return 0


def _cmd_wrapped(args: argparse.Namespace) -> int:
    if not git_io.in_git_repo():
        print("Not inside a git repository — `wrapped` reads commit history.", file=sys.stderr)
        return 1
    rev_range = f"{args.since}..HEAD" if args.since else None
    print(wrapped.wrapped(rev_range=rev_range, top=args.top, fmt=args.format))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Subcommands.
    if args.command == "install-hook":
        return _cmd_install_hook()
    if args.command == "uninstall-hook":
        return _cmd_uninstall_hook()
    if args.command == "wrapped":
        return _cmd_wrapped(args)

    # Internal hook entry — always exits 0, never blocks a commit.
    if args.hook:
        return hook.run_hook(args.hook)

    if args.list_styles:
        return _print_styles()

    cfg = config.load()
    mode = _resolve_mode(args, cfg)
    if mode not in _MODES:
        print(f"Unknown mode {mode!r}. Valid modes: {', '.join(_MODES)}.", file=sys.stderr)
        return 2

    style_name = _resolve_style_name(args, cfg)
    if style_name not in styles.STYLES:
        print(f"Unknown style {style_name!r}. Valid styles:", file=sys.stderr)
        for name in styles.style_names():
            print(f"  {name}", file=sys.stderr)
        return 2

    diff = _get_diff(args)
    if diff is None:
        return 1

    prov_cfg = provider.resolve(provider=args.provider, model=args.model)

    if args.sample is not None and args.sample > 1:
        return _run_sample_palette(args.sample, diff, mode, cfg, prov_cfg)
    return _run_single(style_name, diff, mode, cfg, prov_cfg)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
