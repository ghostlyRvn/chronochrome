"""Text-preserving patch helper for ``key = value`` config files (Ghostty).

Ghostty's config is neither JSONC nor TOML: it is a flat list of ``key = value``
directives, one per line, with ``#`` starting a comment line. Values are bare —
``theme = Rose Pine`` — not quoted, and may contain spaces. So it cannot reuse
``_jsonc_patch.py``; this is its analogue for the ``key = value`` format.

Like the JSONC helper, we treat the file as text and touch only the one value we
own, leaving comments, blank lines, key order, and spacing intact. Operations
are line-based, which is the natural grain for this format.

Semantics worth knowing:
  * A line is a directive only if its first non-blank character is not ``#`` and
    it contains ``=``. The key is everything before the first ``=``, stripped;
    the value is everything after, stripped.
  * Ghostty applies the **last** occurrence of a repeated scalar key, so reads
    and replaces here operate on the last matching line — the one that is
    actually in effect — not the first.
  * ``#`` is only a comment at the start of a line. Ghostty does not support
    trailing inline comments, so we never strip a ``#`` out of a value.
"""

from __future__ import annotations

from dataclasses import dataclass


class KvPatchError(Exception):
    """Raised when the file cannot be patched safely."""


@dataclass(frozen=True)
class KeyLocation:
    """Where a directive lives, by line index, in the source text."""

    line_index: int  # index into text.splitlines(keepends=True)
    key: str
    value: str  # the directive's value, stripped of surrounding whitespace


def _parse_directive(line: str) -> tuple[str, str] | None:
    """Return ``(key, value)`` for a ``key = value`` line, else ``None``.

    Blank lines and comment lines (first non-blank char ``#``) are not
    directives. ``key`` and ``value`` are both stripped; ``value`` may be empty.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in line:
        return None
    raw_key, _, raw_value = line.partition("=")
    key = raw_key.strip()
    if not key:
        return None
    return key, raw_value.strip()


def find_key(text: str, key: str) -> KeyLocation | None:
    """Locate the effective (last) directive for ``key``, or ``None`` if absent."""
    found: KeyLocation | None = None
    for idx, line in enumerate(text.splitlines(keepends=True)):
        parsed = _parse_directive(line)
        if parsed is None:
            continue
        k, value = parsed
        if k == key:
            found = KeyLocation(line_index=idx, key=k, value=value)
    return found


def get_value(text: str, key: str) -> str | None:
    """Return the effective value for ``key`` (stripped), or ``None`` if absent."""
    loc = find_key(text, key)
    return loc.value if loc is not None else None


def replace_value(text: str, key: str, new_value: str) -> str:
    """Replace the value of the effective ``key`` directive, preserving the key,
    the spacing around ``=``, and the line ending. Raises if ``key`` is absent."""
    if "\n" in new_value or "\r" in new_value:
        raise KvPatchError("value must not contain a newline")
    loc = find_key(text, key)
    if loc is None:
        raise KvPatchError(f"key {key!r} not found")

    lines = text.splitlines(keepends=True)
    line = lines[loc.line_index]

    eq = line.index("=")
    prefix = line[: eq + 1]  # "theme =" up to and including the '='
    after = line[eq + 1 :]  # " Rose Pine\n"

    # Peel off the line ending so we can rebuild it verbatim.
    body = after.rstrip("\r\n")
    newline = after[len(body) :]
    # Preserve the leading whitespace between '=' and the value (usually one space).
    leading = body[: len(body) - len(body.lstrip())]

    lines[loc.line_index] = f"{prefix}{leading}{new_value}{newline}"
    return "".join(lines)


def insert_key(text: str, key: str, new_value: str) -> str:
    """Append a ``key = value`` directive. Used when the key is absent.

    Appending (rather than inserting at the top) keeps the operation predictable
    for a flat file and never disturbs a leading comment banner. A trailing
    newline is ensured before and after the new line.
    """
    if "\n" in new_value or "\r" in new_value:
        raise KvPatchError("value must not contain a newline")
    directive = f"{key} = {new_value}\n"
    if text == "":
        return directive
    if text.endswith("\n"):
        return text + directive
    return text + "\n" + directive
