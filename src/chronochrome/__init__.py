"""Chronochrome — time-of-day editor theme switching.

A small, stateless CLI (`chronochrome apply`) invoked periodically by the OS
scheduler (launchd / systemd --user timer). Each invocation resolves the
active time block and patches each detected editor's config file only if its
theme needs to change.
"""

__version__ = "0.1.0"
