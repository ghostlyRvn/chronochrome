"""Which block is active right now — and when the next transition happens.

This module has NO knowledge of adapters or files. It only reasons about time
blocks. Midnight wraparound is handled here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import MINUTES_PER_DAY, TimeBlock


def now_minutes(when: datetime | None = None) -> int:
    """Local-time minutes since midnight for ``when`` (defaults to now)."""
    when = when or datetime.now()
    return when.hour * 60 + when.minute


def is_active(block: TimeBlock, minute: int) -> bool:
    """A block is active if ``start <= now < end``, except when it wraps past
    midnight (``end < start``), where active means ``now >= start or now < end``.
    A block with ``start == end`` covers the whole day."""
    if block.start == block.end:
        return True
    if block.wraps_midnight:
        return minute >= block.start or minute < block.end
    return block.start <= minute < block.end


def active_blocks(blocks: list[TimeBlock], minute: int) -> list[TimeBlock]:
    return [b for b in blocks if is_active(b, minute)]


@dataclass(frozen=True)
class Resolution:
    """Result of resolving the active block at a moment in time."""

    block: TimeBlock | None
    reason: str  # "ok", "no-match", or "multiple-match"

    @property
    def is_ok(self) -> bool:
        return self.block is not None and self.reason == "ok"


def resolve_active_block(blocks: list[TimeBlock], minute: int) -> Resolution:
    """Resolve the single active block.

    If zero or multiple blocks match (a config error), return a Resolution with
    no block and a reason; the caller logs and leaves themes untouched rather
    than guessing.
    """
    matches = active_blocks(blocks, minute)
    if len(matches) == 1:
        return Resolution(block=matches[0], reason="ok")
    if not matches:
        return Resolution(block=None, reason="no-match")
    return Resolution(block=None, reason="multiple-match")


def next_transition(blocks: list[TimeBlock], minute: int) -> int | None:
    """Minutes-since-midnight of the next block boundary strictly after
    ``minute`` (wrapping past midnight). Returns ``None`` if there are no
    boundaries at all. The boundary itself may open a gap or another block —
    this is purely "when does the schedule next change state."""
    boundaries: set[int] = set()
    for block in blocks:
        boundaries.add(block.start % MINUTES_PER_DAY)
        boundaries.add(block.end % MINUTES_PER_DAY)
    if not boundaries:
        return None
    ahead = sorted(b for b in boundaries if b > minute)
    if ahead:
        return ahead[0]
    # All boundaries are at or before now → the next one is tomorrow's earliest.
    return min(boundaries)


def minutes_until(target: int, minute: int) -> int:
    """How many minutes forward from ``minute`` to reach ``target`` (wrapping)."""
    return (target - minute) % MINUTES_PER_DAY
