"""Per-adapter last-applied theme tracking.

Stored at ``~/.local/state/chronochrome/state.json``:

    { "zed": { "block": "night", "theme": "Ayu Dark" } }

Each invocation patches a given editor's file only if the resolved theme for
that editor differs from its last-applied theme. State is keyed per adapter so
one editor's state never influences another's write decision.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_PATH = (
    Path.home() / ".local" / "state" / "chronochrome" / "state.json"
)


@dataclass
class State:
    """In-memory view of state.json. ``entries`` maps adapter name → record."""

    entries: dict[str, dict[str, str]]
    path: Path

    def theme_for(self, adapter: str) -> str | None:
        entry = self.entries.get(adapter)
        return entry.get("theme") if entry else None

    def block_for(self, adapter: str) -> str | None:
        entry = self.entries.get(adapter)
        return entry.get("block") if entry else None

    def record(self, adapter: str, block: str, theme: str) -> None:
        self.entries[adapter] = {"block": block, "theme": theme}

    def save(self) -> None:
        save_state(self, self.path)


def load_state(path: Path | str = DEFAULT_STATE_PATH) -> State:
    """Load state.json, tolerating a missing or corrupt file by starting fresh."""
    path = Path(path)
    entries: dict[str, dict[str, str]] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            for adapter, record in data.items():
                if (
                    isinstance(record, dict)
                    and isinstance(record.get("block"), str)
                    and isinstance(record.get("theme"), str)
                ):
                    entries[adapter] = {
                        "block": record["block"],
                        "theme": record["theme"],
                    }
    return State(entries=entries, path=path)


def save_state(state: State, path: Path | str | None = None) -> None:
    """Persist state via temp file + atomic rename."""
    path = Path(path) if path is not None else state.path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.entries, indent=2, sort_keys=True) + "\n"
    _atomic_write(path, payload)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
