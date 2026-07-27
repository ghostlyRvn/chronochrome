"""Zed editor adapter — v1's only concrete adapter.

Path (macOS and Linux): ``~/.config/zed/settings.json``
Format: JSONC. Patched as text via ``_jsonc_patch`` — never json.load/dump'd.

Zed accepts two forms for ``"theme"``:
  * a plain string:  ``"theme": "One Dark"``
  * an object for system light/dark switching:
    ``"theme": { "mode": "system", "light": "...", "dark": "..." }``

Chronochrome only ever *writes* the plain string form. If it finds the object
form, the user has opted into system-appearance switching (which conflicts with
per-block control) — we refuse to overwrite unless ``force=True``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import _jsonc_patch as jsonc
from .base import AdapterError

THEME_KEY = "theme"
DEFAULT_SETTINGS_PATH = Path.home() / ".config" / "zed" / "settings.json"


class ZedAdapter:
    name = "zed"

    def __init__(self, settings_path: Path | None = None) -> None:
        self._settings_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH

    def settings_path(self) -> Path:
        return self._settings_path

    def detect(self) -> bool:
        """Zed is considered present if its settings file (or its parent config
        directory) exists."""
        path = self._settings_path
        return path.exists() or path.parent.exists()

    def get_current_theme(self) -> str | None:
        if not self._settings_path.exists():
            return None
        text = self._settings_path.read_text(encoding="utf-8")
        found = jsonc.get_top_level_value(text, THEME_KEY)
        if found is None:
            return None
        kind, raw = found
        if kind != "string":
            # Object/other form — no single theme string to report.
            return None
        return _decode_json_string(raw)

    def set_theme(self, theme_name: str, *, force: bool = False) -> None:
        path = self._settings_path

        if not path.exists():
            # Nothing to preserve — create a minimal settings file.
            new_text = jsonc.insert_top_level_key("{\n}\n", THEME_KEY, theme_name)
            self._write_atomic(new_text)
            return

        text = path.read_text(encoding="utf-8")
        found = jsonc.get_top_level_value(text, THEME_KEY)

        if found is None:
            new_text = jsonc.insert_top_level_key(text, THEME_KEY, theme_name)
        else:
            kind, _raw = found
            if kind == "object" and not force:
                raise AdapterError(
                    f"{path} uses the object form of \"theme\" (system light/dark "
                    "switching), which conflicts with per-block control. "
                    "Re-run with --force to overwrite it with a single theme."
                )
            if kind not in ("string", "object", "primitive"):
                # array or something unexpected — refuse unless forced.
                if not force:
                    raise AdapterError(
                        f"{path} has an unexpected \"theme\" value; "
                        "re-run with --force to overwrite."
                    )
            new_text = jsonc.replace_top_level_value(text, THEME_KEY, theme_name)

        if new_text != text:
            self._write_atomic(new_text)

    def reload(self) -> str | None:
        """No-op: Zed watches ``settings.json`` and reloads it live on change,
        so writing the file is all that's needed."""
        return None

    def _write_atomic(self, text: str) -> None:
        """Temp file + atomic rename. Zed reloads this file live on change, so a
        half-written file must never be visible."""
        path = self._settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".chronochrome-", suffix=".json")
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


def _decode_json_string(raw: str) -> str:
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip().strip('"')
