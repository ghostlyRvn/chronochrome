"""macOS launchd user agent (StartInterval).

We deliberately use a periodic ``StartInterval`` rather than an internal sleep
loop: launchd handles boot, crash recovery, and running the job after the
machine wakes from sleep.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

LABEL = "com.chronochrome.apply"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _program_arguments(executable: str) -> list[str]:
    # If we fell back to a bare interpreter, invoke the module form.
    if Path(executable).name.startswith("python"):
        return [executable, "-m", "chronochrome.cli", "apply"]
    return [executable, "apply"]


def render_unit(executable: str, interval_minutes: int) -> str:
    """Render the .plist contents. Kept pure for testing."""
    args = _program_arguments(executable)
    arg_xml = "\n".join(f"      <string>{escape(a)}</string>" for a in args)
    interval_seconds = max(1, interval_minutes) * 60
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(LABEL)}</string>
    <key>ProgramArguments</key>
    <array>
{arg_xml}
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""


def is_installed() -> bool:
    return _plist_path().exists()


def install(executable: str, interval_minutes: int) -> Path:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_unit(executable, interval_minutes), encoding="utf-8")
    # Reload so changes take effect. Unload first (ignore failure), then load.
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True, check=False)
    subprocess.run(["launchctl", "load", str(path)], capture_output=True, check=False)
    return path


def uninstall() -> bool:
    path = _plist_path()
    if not path.exists():
        return False
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True, check=False)
    path.unlink()
    return True
