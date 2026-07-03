"""Config loading + validation (editor-agnostic).

This module knows about "time blocks" and "logical theme names" only. It has
no knowledge of any specific editor beyond treating adapter names as opaque
keys in each block's theme mapping.

Chronochrome's own config is TOML, read with stdlib ``tomllib`` (read-only,
which is all we need). This is entirely separate from ``tomlkit``, which would
only ever be pulled in for a TOML *target-editor* adapter (e.g. Helix).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "chronochrome" / "config.toml"

MINUTES_PER_DAY = 24 * 60


class ConfigError(Exception):
    """Raised when a config file cannot be loaded or is structurally invalid."""


@dataclass(frozen=True)
class TimeBlock:
    """A named window of the day mapped to a theme per editor.

    ``start`` and ``end`` are minutes-since-midnight (0..1439). A block whose
    ``end`` is less than or equal to ``start`` wraps past midnight.
    """

    name: str
    start: int
    end: int
    themes: dict[str, str] = field(default_factory=dict)

    @property
    def wraps_midnight(self) -> bool:
        return self.end <= self.start

    def theme_for(self, adapter_name: str) -> str | None:
        return self.themes.get(adapter_name)


@dataclass(frozen=True)
class Config:
    check_interval_minutes: int
    blocks: list[TimeBlock]


def parse_hhmm(value: str) -> int:
    """Parse ``"HH:MM"`` (24-hour) into minutes since midnight.

    Raises ``ConfigError`` on anything that is not a valid 24-hour time.
    """
    if not isinstance(value, str):
        raise ConfigError(f"time must be a string, got {value!r}")
    parts = value.split(":")
    if len(parts) != 2:
        raise ConfigError(f"time must be in HH:MM format, got {value!r}")
    hh_str, mm_str = parts
    if not (hh_str.isdigit() and mm_str.isdigit()):
        raise ConfigError(f"time must be in HH:MM format, got {value!r}")
    if len(hh_str) != 2 or len(mm_str) != 2:
        raise ConfigError(f"time must be zero-padded HH:MM, got {value!r}")
    hh, mm = int(hh_str), int(mm_str)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ConfigError(f"time out of range (00:00–23:59), got {value!r}")
    return hh * 60 + mm


def format_minutes(minutes: int) -> str:
    """Inverse of :func:`parse_hhmm` — minutes-since-midnight to ``HH:MM``."""
    minutes %= MINUTES_PER_DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _coerce_block(raw: object, index: int) -> TimeBlock:
    if not isinstance(raw, dict):
        raise ConfigError(f"blocks[{index}] must be a table")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"blocks[{index}] is missing a non-empty 'name'")
    if "start" not in raw or "end" not in raw:
        raise ConfigError(f"block {name!r} must define both 'start' and 'end'")
    start = parse_hhmm(raw["start"])
    end = parse_hhmm(raw["end"])
    themes_raw = raw.get("themes", {})
    if not isinstance(themes_raw, dict):
        raise ConfigError(f"block {name!r} 'themes' must be a table")
    themes: dict[str, str] = {}
    for adapter, theme in themes_raw.items():
        if not isinstance(theme, str):
            raise ConfigError(
                f"block {name!r} theme for {adapter!r} must be a string"
            )
        themes[adapter] = theme
    return TimeBlock(name=name, start=start, end=end, themes=themes)


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Load and structurally validate a config file.

    Raises ``ConfigError`` (with a human-readable message) on any structural or
    format problem. Deeper linting — overlaps, gaps, coverage — is reported
    non-fatally by :func:`validate_config`, not here.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    interval = raw.get("check_interval_minutes", 5)
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ConfigError("check_interval_minutes must be a positive integer")

    blocks_raw = raw.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        raise ConfigError("config must define at least one [[blocks]] entry")

    blocks = [_coerce_block(b, i) for i, b in enumerate(blocks_raw)]
    return Config(check_interval_minutes=interval, blocks=blocks)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _intervals(block: TimeBlock) -> list[tuple[int, int]]:
    """Expand a block into one or two non-wrapping [start, end) half-open
    intervals on the 0..1440 line, so overlap/gap math is simple."""
    if block.start == block.end:
        # Degenerate: treat as covering the entire day.
        return [(0, MINUTES_PER_DAY)]
    if block.wraps_midnight:
        return [(block.start, MINUTES_PER_DAY), (0, block.end)]
    return [(block.start, block.end)]


def validate_config(
    path: Path | str = DEFAULT_CONFIG_PATH,
    detected_adapters: list[str] | None = None,
) -> ValidationResult:
    """Lint a config: bad times, duplicate names, overlaps, gaps, and detected
    adapters with no theme mappings. Structural/format errors are surfaced as
    errors; coverage issues as warnings (per the spec)."""
    result = ValidationResult()
    try:
        config = load_config(path)
    except ConfigError as exc:
        result.errors.append(str(exc))
        return result

    # Duplicate block names.
    seen: set[str] = set()
    for block in config.blocks:
        if block.name in seen:
            result.errors.append(f"duplicate block name: {block.name!r}")
        seen.add(block.name)

    # Zero-length / full-day blocks are almost always a mistake.
    for block in config.blocks:
        if block.start == block.end:
            result.warnings.append(
                f"block {block.name!r} has start == end ({format_minutes(block.start)}); "
                "treating it as covering the entire day"
            )

    # Overlap + coverage via a per-minute occupancy sweep (1440 minutes is tiny).
    occupancy = [0] * MINUTES_PER_DAY
    for block in config.blocks:
        for lo, hi in _intervals(block):
            for minute in range(lo, hi):
                occupancy[minute] += 1

    overlap_minutes = sum(1 for c in occupancy if c > 1)
    if overlap_minutes:
        result.errors.append(
            f"blocks overlap for {overlap_minutes} minute(s) of the day; "
            "blocks must not overlap"
        )
    gap_minutes = sum(1 for c in occupancy if c == 0)
    if gap_minutes:
        result.warnings.append(
            f"blocks leave {gap_minutes} minute(s) of the day uncovered; "
            "Chronochrome leaves themes untouched during gaps"
        )

    # A detected adapter with no theme mapped anywhere is likely a forgotten
    # mapping rather than intentional.
    for adapter in detected_adapters or []:
        if not any(adapter in block.themes for block in config.blocks):
            result.warnings.append(
                f"adapter {adapter!r} is detected but has no theme mapped in any block"
            )

    return result
