"""A tiny TOML-subset parser for Python 3.9/3.10 (which lack ``tomllib``).

This is intentionally minimal — just enough for the Bard's config files:
``[section]`` tables, ``key = value`` pairs where values are quoted strings,
integers, floats, or booleans, plus ``#`` comments and blank lines. It is NOT a
full TOML implementation (no arrays, datetimes, multiline strings, or inline
tables). On Python 3.11+ the real ``tomllib`` is used instead; this keeps the
no-dependency promise on older interpreters.

Mirrors the bits of the ``tomllib`` API we use: ``load(binary_file)`` and
``loads(text)``.
"""

from __future__ import annotations

from typing import Any, Dict


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ``# comment`` not inside a quoted string."""
    if value and value[0] in "\"'":
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[: end + 1]
        return value
    hash_pos = value.find("#")
    if hash_pos != -1:
        value = value[:hash_pos]
    return value.strip()


def _parse_value(value: str) -> Any:
    if not value:
        return ""
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1]
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value  # bare word -> treat as string


def loads(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current = data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = data
            for part in line[1:-1].split("."):
                key = part.strip()
                node = current.setdefault(key, {})
                if not isinstance(node, dict):  # collision -> reset to table
                    node = {}
                    current[key] = node
                current = node
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = _parse_value(_strip_inline_comment(value.strip()))
    return data


def load(fp) -> Dict[str, Any]:
    """Parse from a binary file object (matches ``tomllib.load``)."""
    raw = fp.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return loads(raw)
