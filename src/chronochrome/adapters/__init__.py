"""Adapter registry.

v1 ships exactly one adapter: Zed. The registry is the single place the CLI
looks to enumerate "registered" adapters; ``apply`` further filters to those
that ``detect()`` as present. Adding an editor later means writing a module here
and appending its factory to :data:`REGISTRY` — no changes to scheduling,
config parsing, or state tracking.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import AdapterError, EditorAdapter
from .zed import ZedAdapter

# Factories, so callers get fresh instances (and tests can register their own).
REGISTRY: list[Callable[[], EditorAdapter]] = [
    ZedAdapter,
]


def all_adapters() -> list[EditorAdapter]:
    """Instantiate every registered adapter."""
    return [factory() for factory in REGISTRY]


def detected_adapters() -> list[EditorAdapter]:
    """Registered adapters whose editor is present on this machine."""
    return [a for a in all_adapters() if a.detect()]


__all__ = [
    "AdapterError",
    "EditorAdapter",
    "ZedAdapter",
    "REGISTRY",
    "all_adapters",
    "detected_adapters",
]
