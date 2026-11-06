"""Effect config + team colors -> bulb Pattern."""

from __future__ import annotations

from dataclasses import dataclass

from app.bulbs.base import Color, Pattern, Step


def parse_color(s: str) -> Color:
    """Accepts "#RRGGBB", "RRGGBB" or "R,G,B"."""
    text = s.strip()
    try:
        if "," in text:
            parts = tuple(int(p) for p in text.split(","))
        else:
            h = text.removeprefix("#")
            if len(h) != 6:
                raise ValueError
            parts = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        if len(parts) != 3 or not all(0 <= p <= 255 for p in parts):
            raise ValueError
    except ValueError:
        raise ValueError(f"bad color {s!r}; use #RRGGBB or R,G,B") from None
    return parts  # type: ignore[return-value]


@dataclass(frozen=True)
class EffectConfig:
    pulses: int = 5
    duration_s: float = 6.0
    color: Color | None = None
    alt_color: Color | None = None
    brightness: int = 255


def build_pattern(effect: EffectConfig, team_primary: Color, team_alternate: Color) -> Pattern:
    """Slow pulse alternating two colors. Config colors override the team's.

    Pattern validation enforces the flash cap, so too many pulses for the
    duration raises PatternError.
    """
    if effect.pulses < 1:
        raise ValueError("pulses must be >= 1")
    a = effect.color or team_primary
    b = effect.alt_color or team_alternate
    hold = effect.duration_s / (effect.pulses * 2)
    steps = tuple(
        Step(a if i % 2 == 0 else b, hold, effect.brightness) for i in range(effect.pulses * 2)
    )
    return Pattern(steps)
