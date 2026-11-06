"""Brand-neutral bulb interface, the flash pattern type and its rate cap."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

Color = tuple[int, int, int]
MAX_CHANGES_PER_S = 2.0
MIN_HOLD_S = 1.0 / MAX_CHANGES_PER_S


class PatternError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    color: Color
    hold_s: float
    brightness: int = 255


@dataclass(frozen=True)
class Pattern:
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise PatternError("pattern has no steps")
        for s in self.steps:
            if len(s.color) != 3 or not all(0 <= c <= 255 for c in s.color):
                raise PatternError(f"bad color {s.color}")
            if not 1 <= s.brightness <= 255:
                raise PatternError(f"bad brightness {s.brightness}")
            if s.hold_s < MIN_HOLD_S - 1e-9:
                raise PatternError(
                    f"hold {s.hold_s:g}s exceeds the {MAX_CHANGES_PER_S:g} changes/sec cap"
                )

    @property
    def duration_s(self) -> float:
        return sum(s.hold_s for s in self.steps)


Sleep = Callable[[float], Awaitable[None]]


class BulbAdapter(ABC):
    """One implementation per brand. The rest of the app only sees this."""

    def __init__(self, name: str, sleep: Sleep = asyncio.sleep) -> None:
        self.name = name
        self._sleep = sleep

    @abstractmethod
    async def set_color(self, color: Color, brightness: int = 255) -> None: ...

    @abstractmethod
    async def snapshot(self) -> Any:
        """Opaque state object accepted by restore()."""

    @abstractmethod
    async def restore(self, snapshot: Any) -> None: ...

    async def flash(self, pattern: Pattern) -> None:
        for step in pattern.steps:
            t0 = time.monotonic()
            await self.set_color(step.color, step.brightness)
            # Command time counts toward the hold so the pattern keeps its length.
            await self._sleep(max(0.0, step.hold_s - (time.monotonic() - t0)))


class DryRunBulb(BulbAdapter):
    """Logs what would happen; never touches hardware."""

    def __init__(self, name: str, sleep: Sleep = asyncio.sleep) -> None:
        super().__init__(name, sleep)
        self.calls: list[tuple] = []

    async def set_color(self, color: Color, brightness: int = 255) -> None:
        self.calls.append(("set_color", color, brightness))
        log.info("[dry-run %s] set_color %s brightness %d", self.name, color, brightness)

    async def snapshot(self) -> str:
        self.calls.append(("snapshot",))
        log.info("[dry-run %s] snapshot", self.name)
        return "dry-run-snapshot"

    async def restore(self, snapshot: Any) -> None:
        self.calls.append(("restore", snapshot))
        log.info("[dry-run %s] restore", self.name)
