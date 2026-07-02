"""Linux systemd --user timer.

A oneshot ``.service`` runs ``chronochrome apply``; a ``.timer`` fires it on an
interval (and shortly after boot). systemd handles boot, catch-up after
suspend (``Persistent=true``), and restart semantics — so Chronochrome stays a
stateless one-shot rather than a daemon.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SERVICE_NAME = "chronochrome.service"
TIMER_NAME = "chronochrome.timer"


def _unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _service_path() -> Path:
    return _unit_dir() / SERVICE_NAME


def _timer_path() -> Path:
    return _unit_dir() / TIMER_NAME


def _exec_start(executable: str) -> str:
    if Path(executable).name.startswith("python"):
        return f"{executable} -m chronochrome.cli apply"
    return f"{executable} apply"


def render_service(executable: str) -> str:
    return f"""[Unit]
Description=Chronochrome — apply the time-of-day editor theme

[Service]
Type=oneshot
ExecStart={_exec_start(executable)}
"""


def render_timer(interval_minutes: int) -> str:
    interval = max(1, interval_minutes)
    return f"""[Unit]
Description=Chronochrome periodic theme apply

[Timer]
OnBootSec=1min
OnUnitActiveSec={interval}min
Persistent=true

[Install]
WantedBy=timers.target
"""


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, check=False, text=True
    )


def is_installed() -> bool:
    return _timer_path().exists()


def install(executable: str, interval_minutes: int) -> Path:
    unit_dir = _unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    _service_path().write_text(render_service(executable), encoding="utf-8")
    _timer_path().write_text(render_timer(interval_minutes), encoding="utf-8")
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", TIMER_NAME)
    return _timer_path()


def uninstall() -> bool:
    existed = _timer_path().exists() or _service_path().exists()
    if not existed:
        return False
    _systemctl("disable", "--now", TIMER_NAME)
    for path in (_timer_path(), _service_path()):
        if path.exists():
            path.unlink()
    _systemctl("daemon-reload")
    return True
