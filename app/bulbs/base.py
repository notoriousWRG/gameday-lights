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


@dataclass(frozen=True)
class SegmentFrame:
    colors: tuple[Color, ...]
    hold_s: float


@dataclass(frozen=True)
class SegmentPattern:
    """Frames of one color per segment. The flash cap applies per segment: a segment may not
    change color more than MAX_CHANGES_PER_S times a second."""

    frames: tuple[SegmentFrame, ...]
    brightness: int = 255

    def __post_init__(self) -> None:
        if not self.frames:
            raise PatternError("pattern has no frames")
        n = len(self.frames[0].colors)
        if n < 1:
            raise PatternError("frame has no segments")
        if not 1 <= self.brightness <= 255:
            raise PatternError(f"bad brightness {self.brightness}")
        last_change: list[float | None] = [None] * n
        t = 0.0
        previous: tuple[Color, ...] | None = None
        for f in self.frames:
            if len(f.colors) != n:
                raise PatternError("frames have different segment counts")
            if f.hold_s <= 0:
                raise PatternError(f"bad frame hold {f.hold_s}")
            for c in f.colors:
                if len(c) != 3 or not all(0 <= v <= 255 for v in c):
                    raise PatternError(f"bad color {c}")
            if previous is not None:
                for i, (a, b) in enumerate(zip(previous, f.colors, strict=True)):
                    if a == b:
                        continue
                    seen = last_change[i]
                    if seen is not None and t - seen < MIN_HOLD_S - 1e-9:
                        raise PatternError(
                            f"segment {i} changes color faster than the "
                            f"{MAX_CHANGES_PER_S:g} changes/sec cap"
                        )
                    last_change[i] = t
            previous = f.colors
            t += f.hold_s

    @property
    def segments(self) -> int:
        return len(self.frames[0].colors)

    @property
    def duration_s(self) -> float:
        return sum(f.hold_s for f in self.frames)


@dataclass(frozen=True)
class Capabilities:
    """What a fixture can do. Effect kinds outside `kinds` are never offered to it."""

    kinds: frozenset[str] = frozenset({"pulse"})
    min_hold_s: float = MIN_HOLD_S
    segments: int = 1  # 1 = whole fixture
    restores_scenes: bool = False

    def __post_init__(self) -> None:
        if self.min_hold_s < MIN_HOLD_S - 1e-9:
            raise ValueError(f"min_hold_s cannot go below the {MAX_CHANGES_PER_S:g}/sec cap")
        if self.segments < 1:
            raise ValueError("segments must be >= 1")


def capabilities_for(kind: str, segments: int = 1) -> Capabilities:
    """The capabilities of a bulb kind with this many segments (config-side, no adapter needed)."""
    kinds = {"pulse"}
    if kind == "govee" and segments > 1:
        kinds.add("chase")
    return Capabilities(kinds=frozenset(kinds), segments=segments if kind == "govee" else 1)


Sleep = Callable[[float], Awaitable[None]]


class BulbAdapter(ABC):
    """One implementation per brand. The rest of the app only sees this."""

    capabilities: Capabilities = Capabilities()

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

    async def ping(self) -> float | None:
        """Round-trip seconds of a read-only state query, or None if unreachable."""
        t0 = time.monotonic()
        try:
            await self.snapshot()
        except Exception:
            return None
        return time.monotonic() - t0

    async def play(self, pattern: Pattern | SegmentPattern) -> None:
        """Play either kind of pattern; the dispatcher only calls this."""
        if isinstance(pattern, SegmentPattern):
            await self.play_segments(pattern)
        else:
            await self.flash(pattern)

    async def play_segments(self, pattern: SegmentPattern) -> None:
        raise PatternError(f"{self.name} cannot play per-segment patterns")

    async def flash(self, pattern: Pattern) -> None:
        for step in pattern.steps:
            t0 = time.monotonic()
            await self.set_color(step.color, step.brightness)
            # Command time counts toward the hold so the pattern keeps its length.
            await self._sleep(max(0.0, step.hold_s - (time.monotonic() - t0)))


class DryRunBulb(BulbAdapter):
    """Logs what would happen; never touches hardware."""

    def __init__(
        self, name: str, sleep: Sleep = asyncio.sleep, capabilities: Capabilities | None = None
    ) -> None:
        super().__init__(name, sleep)
        if capabilities is not None:
            self.capabilities = capabilities
        self.calls: list[tuple] = []

    async def play_segments(self, pattern: SegmentPattern) -> None:
        self.calls.append(("play_segments", len(pattern.frames), pattern.segments))
        log.info("[dry-run %s] %d segment frames", self.name, len(pattern.frames))

    async def set_color(self, color: Color, brightness: int = 255) -> None:
        self.calls.append(("set_color", color, brightness))
        log.info("[dry-run %s] set_color %s brightness %d", self.name, color, brightness)

    async def ping(self) -> float | None:
        return 0.0

    async def snapshot(self) -> str:
        self.calls.append(("snapshot",))
        log.info("[dry-run %s] snapshot", self.name)
        return "dry-run-snapshot"

    async def restore(self, snapshot: Any) -> None:
        self.calls.append(("restore", snapshot))
        log.info("[dry-run %s] restore", self.name)
