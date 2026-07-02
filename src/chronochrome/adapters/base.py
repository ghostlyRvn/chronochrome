"""The one interface all editor-specific knowledge lives behind.

``scheduler.py``, ``config.py``, and ``state.py`` know nothing about any
concrete editor — they only reason about time blocks and logical theme names.
An editor is supported by implementing this protocol in a self-contained module
under ``adapters/`` and registering it (see ``adapters/__init__.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class AdapterError(Exception):
    """Raised by an adapter when it cannot safely apply a theme.

    The canonical example is Zed's object-form ``"theme"`` (system light/dark
    switching), which Chronochrome refuses to overwrite unless forced.
    """


@runtime_checkable
class EditorAdapter(Protocol):
    name: str  # "zed", "vscode", "helix", ...

    def detect(self) -> bool:
        """Is this editor installed / its config file present on this machine?"""
        ...

    def settings_path(self) -> Path:
        """Absolute path to the editor's settings file."""
        ...

    def get_current_theme(self) -> str | None:
        """The theme currently set in the editor's config, or ``None`` if unset
        (or set in a form Chronochrome does not read as a single theme)."""
        ...

    def set_theme(self, theme_name: str, *, force: bool = False) -> None:
        """Format-safe patch: set the editor's theme, preserving everything else
        in the file. Raise :class:`AdapterError` rather than clobbering a config
        the tool doesn't own (unless ``force``)."""
        ...
