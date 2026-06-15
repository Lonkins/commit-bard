#!/usr/bin/env bash
# Git Commit Bard prepare-commit-msg hook (reference copy).
#
# `commit-bard install-hook` writes a copy of this into your repo's hooks dir
# (with the active Python interpreter baked in as a fallback, and your
# configured skip-env name). This standalone version is for wiring the hook
# manually or with a hook manager. It never blocks a commit: it always exits 0.

# Escape hatch: set BARD_SKIP to skip versifying this commit.
if [ -n "${BARD_SKIP:-}" ]; then
  exit 0
fi

MSG_FILE="$1"
SOURCE="$2"

# Leave merges, squashes, amends, and -m/-F/-c messages alone.
case "$SOURCE" in
  merge|squash|commit|message)
    exit 0
    ;;
esac

# Bound the whole generation with a wall-clock timeout when one is available.
_bard_to="$(command -v timeout || command -v gtimeout || true)"
if command -v commit-bard >/dev/null 2>&1; then
  if [ -n "$_bard_to" ]; then
    "$_bard_to" 20s commit-bard --hook "$MSG_FILE" || true
  else
    commit-bard --hook "$MSG_FILE" || true
  fi
fi
exit 0
