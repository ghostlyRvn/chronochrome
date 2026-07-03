"""Shared text-preserving patch helper for JSONC-format editor configs.

JSONC = JSON with ``//`` and ``/* */`` comments and trailing commas. We must
NOT ``json.load`` / ``json.dump`` these files: the round-trip strips comments
and reformats everything, destroying the user's file.

Instead we treat the file as text. This helper locates a *top-level* key and
lets a caller read or replace only its value, leaving comments, whitespace, and
key order untouched. Any future JSONC adapter (VSCode, Sublime) reuses this —
only the key name and file path differ.

The scanner tracks strings and comments so it never mistakes a key-like token
inside a string or comment for the real thing, and only matches keys at brace
depth 1 (direct members of the root object).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


class JsoncPatchError(Exception):
    """Raised when the file's structure is too malformed to patch safely."""


@dataclass(frozen=True)
class KeyLocation:
    """Where a top-level key and its value live in the source text."""

    key_start: int      # index of the opening quote of the key
    key_end: int        # index just past the closing quote of the key
    value_start: int    # index of the first char of the value
    value_end: int      # index just past the last char of the value
    kind: str           # "string" | "object" | "array" | "primitive"

    @property
    def raw_value(self) -> str:
        return ""  # placeholder; real slice filled in by find_top_level_key


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        break
    return i


def _string_end(text: str, start: int) -> int:
    """Given ``start`` at an opening quote, return index just past the closing
    quote, honoring backslash escapes."""
    n = len(text)
    i = start + 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    raise JsoncPatchError("unterminated string literal")


def _bracket_end(text: str, start: int) -> int:
    """Given ``start`` at ``{`` or ``[``, return index just past the matching
    close bracket, skipping nested strings and comments."""
    n = len(text)
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    i = start
    while i < n:
        c = text[i]
        if c == '"':
            i = _string_end(text, i)
            continue
        if c == "/" and i + 1 < n and text[i + 1] in "/*":
            i = _skip_ws_and_comments(text, i)
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise JsoncPatchError(f"unterminated {open_ch!r} ... {close_ch!r}")


def _value_span(text: str, value_start: int) -> tuple[int, str]:
    """Return (value_end, kind) for the value beginning at ``value_start``."""
    c = text[value_start]
    if c == '"':
        return _string_end(text, value_start), "string"
    if c == "{":
        return _bracket_end(text, value_start), "object"
    if c == "[":
        return _bracket_end(text, value_start), "array"
    # Primitive: number, true, false, null. Runs until a structural terminator.
    n = len(text)
    i = value_start
    while i < n and text[i] not in ",}]\n\r":
        # Stop at the start of a comment too.
        if text[i] == "/" and i + 1 < n and text[i + 1] in "/*":
            break
        i += 1
    # Trim trailing whitespace.
    while i > value_start and text[i - 1] in " \t":
        i -= 1
    return i, "primitive"


def find_top_level_key(text: str, key: str) -> KeyLocation | None:
    """Locate the first top-level (brace depth 1) occurrence of ``key``.

    Returns ``None`` if the key is absent. Raises :class:`JsoncPatchError` if the
    document is structurally unparseable.
    """
    n = len(text)
    i = 0
    depth = 0
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] in "/*":
            i = _skip_ws_and_comments(text, i)
            continue
        if c == '"':
            str_start = i
            str_end = _string_end(text, i)
            content = text[str_start + 1 : str_end - 1]
            if depth == 1:
                after = _skip_ws_and_comments(text, str_end)
                if after < n and text[after] == ":":
                    # This string is a key. Is it the one we want?
                    if _unescape(content) == key:
                        value_start = _skip_ws_and_comments(text, after + 1)
                        if value_start >= n:
                            raise JsoncPatchError(f"key {key!r} has no value")
                        value_end, kind = _value_span(text, value_start)
                        return KeyLocation(
                            key_start=str_start,
                            key_end=str_end,
                            value_start=value_start,
                            value_end=value_end,
                            kind=kind,
                        )
            i = str_end
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return None


def get_top_level_value(text: str, key: str) -> tuple[str, str] | None:
    """Return ``(kind, raw_slice)`` for a top-level key's value, or ``None``."""
    loc = find_top_level_key(text, key)
    if loc is None:
        return None
    return loc.kind, text[loc.value_start : loc.value_end]


def replace_top_level_value(text: str, key: str, new_string_value: str) -> str:
    """Replace an existing top-level key's value with a JSON string literal.

    The caller is responsible for deciding whether replacement is allowed (e.g.
    refusing to clobber an object-form value). This function only rewrites the
    value span; everything else in the file is byte-for-byte preserved.
    """
    loc = find_top_level_key(text, key)
    if loc is None:
        raise JsoncPatchError(f"key {key!r} not found")
    literal = json.dumps(new_string_value)
    return text[: loc.value_start] + literal + text[loc.value_end :]


def insert_top_level_key(text: str, key: str, new_string_value: str) -> str:
    """Insert ``"key": "value"`` near the top of the root object.

    Used when the key is absent. Matches the file's existing indentation style
    where it can infer one, defaulting to two spaces.
    """
    literal = json.dumps(new_string_value)
    open_brace = _find_root_open_brace(text)
    if open_brace is None:
        # No root object at all — create a minimal one.
        return "{\n  " + json.dumps(key) + ": " + literal + "\n}\n"

    indent = _infer_indent(text, open_brace)
    insert_at = open_brace + 1
    # Peek at what follows the brace to decide whether a trailing comma is needed.
    rest_idx = _skip_ws_and_comments(text, insert_at)
    empty_object = rest_idx < len(text) and text[rest_idx] == "}"
    new_member = f"\n{indent}{json.dumps(key)}: {literal}"
    if not empty_object:
        new_member += ","
    return text[:insert_at] + new_member + text[insert_at:]


def _find_root_open_brace(text: str) -> int | None:
    i = _skip_ws_and_comments(text, 0)
    if i < len(text) and text[i] == "{":
        return i
    return None


def _infer_indent(text: str, open_brace: int) -> str:
    """Infer the indentation of the first member after the root ``{``."""
    i = open_brace + 1
    n = len(text)
    # Move to the first newline, then measure leading whitespace of next line.
    nl = text.find("\n", i)
    if nl != -1:
        j = nl + 1
        indent_chars = []
        while j < n and text[j] in " \t":
            indent_chars.append(text[j])
            j += 1
        if j < n and text[j] not in "\r\n":
            return "".join(indent_chars) or "  "
    return "  "


def _unescape(raw: str) -> str:
    """Decode a JSON string's inner content (without surrounding quotes)."""
    try:
        return json.loads('"' + raw + '"')
    except json.JSONDecodeError:
        return raw
