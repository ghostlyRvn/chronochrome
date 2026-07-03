"""OS scheduler integration.

Chronochrome is a stateless CLI invoked periodically by the OS's native
scheduler — launchd on macOS, a systemd --user timer on Linux — never a
long-running daemon. These modules generate and (un)install those units.

:func:`get_service` returns the right backend for the current platform.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import launchd, systemd


class UnsupportedPlatformError(Exception):
    pass


def chronochrome_executable() -> str:
    """Best-effort absolute path to the installed ``chronochrome`` command, for
    embedding in the generated unit. Falls back to ``python -m`` invocation."""
    found = shutil.which("chronochrome")
    if found:
        return found
    # Fall back to the interpreter running us, invoking the module.
    return sys.executable


def get_service():
    """Return the platform-appropriate service backend module."""
    if sys.platform == "darwin":
        return launchd
    if sys.platform.startswith("linux"):
        return systemd
    raise UnsupportedPlatformError(
        f"no scheduler backend for platform {sys.platform!r} (macOS and Linux only)"
    )


__all__ = [
    "UnsupportedPlatformError",
    "chronochrome_executable",
    "get_service",
    "launchd",
    "systemd",
]
