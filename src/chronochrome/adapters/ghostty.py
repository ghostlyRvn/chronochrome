"""Ghostty terminal adapter — the first non-editor, non-JSONC adapter.

Ghostty differs from Zed in three ways the ``EditorAdapter`` contract had to
grow to accommodate:

1. **Format.** The config is a flat ``key = value`` list with ``#`` comments —
   not JSONC — so it patches via ``_kv_patch`` instead of ``_jsonc_patch``. The
   theme value is written **bare** (unquoted) and may contain spaces:
   ``theme = Rose Pine``.

2. **No live reload.** Ghostty does not watch its config file. After writing,
   the adapter's :meth:`reload` best-effort signals every running ``ghostty``
   process with ``SIGUSR2`` so a change takes effect immediately; if none is
   running the theme simply loads on next launch.

3. **macOS dual config path.** On macOS Ghostty reads *both*
   ``~/Library/Application Support/com.mitchellh.ghostty/config`` and
   ``~/.config/ghostty/config``, and the Application Support file wins. We must
   patch the file Ghostty actually loads, so we resolve to the Application
   Support path when it exists and fall back to ``~/.config``. On Linux there is
   only ``$XDG_CONFIG_HOME/ghostty/config`` (default ``~/.config``).

Ghostty also accepts a split form for desktop light/dark switching —
``theme = light:Name,dark:Name`` — which is its analogue of Zed's object-form
``"theme"``. Like Zed's, it conflicts with per-block control, so we refuse to
overwrite it unless ``force=True``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from . import _kv_patch as kv
from .base import AdapterError

THEME_KEY = "theme"

_MACOS_APP_SUPPORT = (
    Path("Library") / "Application Support" / "com.mitchellh.ghostty" / "config"
)


def _default_candidates(platform: str) -> list[Path]:
    """The config files Ghostty may load, in the order it prefers them.

    macOS lists the Application Support file first (it wins on conflict), then
    the XDG path it also reads. Linux has only the XDG path.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    xdg_base = Path(xdg) if xdg else Path.home() / ".config"
    xdg_path = xdg_base / "ghostty" / "config"
    if platform == "darwin":
        return [Path.home() / _MACOS_APP_SUPPORT, xdg_path]
    return [xdg_path]


class GhosttyAdapter:
    name = "ghostty"

    def __init__(
        self,
        settings_path: Path | str | None = None,
        *,
        candidates: list[Path] | None = None,
        platform: str | None = None,
    ) -> None:
        """
        ``settings_path`` pins a single config file (used in tests and for an
        explicit override). ``candidates`` injects the ordered preference list
        directly (used to exercise macOS dual-path resolution in tests). At most
        one of the two may be given. With neither, the list is derived from the
        platform and ``XDG_CONFIG_HOME``.
        """
        if settings_path is not None and candidates is not None:
            raise ValueError("pass settings_path or candidates, not both")
        self._explicit = Path(settings_path) if settings_path is not None else None
        self._explicit_candidates = (
            [Path(p) for p in candidates] if candidates is not None else None
        )
        self._platform = platform or sys.platform

    # -- path resolution ---------------------------------------------------- #
    def _candidates(self) -> list[Path]:
        if self._explicit is not None:
            return [self._explicit]
        if self._explicit_candidates is not None:
            return list(self._explicit_candidates)
        return _default_candidates(self._platform)

    def settings_path(self) -> Path:
        """The file Ghostty actually loads: the first candidate that exists,
        else the most-preferred candidate (the one we'd create)."""
        candidates = self._candidates()
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def detect(self) -> bool:
        """Ghostty is considered present if any candidate config file — or its
        parent config directory — exists."""
        for path in self._candidates():
            if path.exists() or path.parent.exists():
                return True
        return False

    # -- theme read/write --------------------------------------------------- #
    def get_current_theme(self) -> str | None:
        path = self.settings_path()
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        value = kv.get_value(text, THEME_KEY)
        if value is None or _is_split_form(value):
            # Absent, or split light/dark form — no single theme to report.
            return None
        return value

    def set_theme(self, theme_name: str, *, force: bool = False) -> None:
        if "\n" in theme_name or "\r" in theme_name:
            raise AdapterError("theme name must not contain a newline")

        path = self.settings_path()

        if not path.exists():
            # Nothing to preserve — create a minimal config.
            self._write_atomic(path, kv.insert_key("", THEME_KEY, theme_name))
            return

        text = path.read_text(encoding="utf-8")
        value = kv.get_value(text, THEME_KEY)

        if value is None:
            new_text = kv.insert_key(text, THEME_KEY, theme_name)
        else:
            if _is_split_form(value) and not force:
                raise AdapterError(
                    f"{path} uses the split form of \"theme\" "
                    f"(theme = {value}) for desktop light/dark switching, which "
                    "conflicts with per-block control. Re-run with --force to "
                    "overwrite it with a single theme."
                )
            new_text = kv.replace_value(text, THEME_KEY, theme_name)

        if new_text != text:
            self._write_atomic(path, new_text)

    # -- reload hook -------------------------------------------------------- #
    def reload(self) -> str | None:
        """Ghostty does not watch its config, so nudge every running instance
        with ``SIGUSR2``. Best-effort: returns ``None`` if none is running or we
        cannot signal it (the theme then loads on next launch)."""
        pids = self._running_pids()
        signaled = 0
        for pid in pids:
            try:
                os.kill(pid, signal.SIGUSR2)
            except OSError:
                continue
            signaled += 1
        if signaled == 0:
            return None
        noun = "process" if signaled == 1 else "processes"
        return f"signaled {signaled} running Ghostty {noun} to reload (SIGUSR2)"

    def _running_pids(self) -> list[int]:
        """PIDs of running ``ghostty`` processes, via ``pgrep`` (present on both
        macOS and Linux). Best-effort — any failure yields an empty list."""
        try:
            proc = subprocess.run(
                ["pgrep", "-x", "ghostty"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []
        pids: list[int] = []
        for token in proc.stdout.split():
            try:
                pids.append(int(token))
            except ValueError:
                continue
        return pids

    # -- io ----------------------------------------------------------------- #
    def _write_atomic(self, path: Path, text: str) -> None:
        """Temp file + atomic rename, matching the Zed adapter. Even though
        Ghostty doesn't watch the file, an atomic write avoids leaving a
        half-written config behind if the process dies mid-write."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".chronochrome-", suffix=".tmp")
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


def _is_split_form(value: str) -> bool:
    """True if ``value`` is Ghostty's ``light:Name,dark:Name`` split form rather
    than a single theme name."""
    for segment in value.split(","):
        head = segment.split(":", 1)[0].strip().lower()
        if head in ("light", "dark"):
            return True
    return False
