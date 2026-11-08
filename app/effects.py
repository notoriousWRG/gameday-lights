"""Effect config + team colors -> bulb Pattern."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.bulbs.base import (
    MAX_CHANGES_PER_S,
    Capabilities,
    Color,
    Pattern,
    SegmentFrame,
    SegmentPattern,
    Step,
)

if TYPE_CHECKING:
    from app.config import Config, TeamConfig

FRAME_HZ = 10.0


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


@dataclass(frozen=True)
class EffectSpec:
    kind: str = "pulse"
    params: Mapping[str, Any] = field(default_factory=dict)


# Parameters each effect kind takes (colors are not parameters: they come from the resolver).
KIND_PARAMS: dict[str, frozenset[str]] = {
    "pulse": frozenset({"pulses", "duration_s", "brightness"}),
    "chase": frozenset({"chunk", "speed", "duration_s", "brightness"}),
}
CHASE_DEFAULTS = {"chunk": 4, "speed": 4.0, "duration_s": 6.0, "brightness": 255}


def chase_frame(n: int, offset: int, chunk: int, colors: tuple[Color, Color]) -> list[Color]:
    """n segments: chunks of `chunk` alternating the two colors, shifted by `offset` (wraps)."""
    return [colors[((i - offset) // chunk) % 2] for i in range(n)]


def _build_chase(
    params: Mapping[str, Any], primary: Color, alternate: Color, caps: Capabilities
) -> SegmentPattern:
    p = {**CHASE_DEFAULTS, **params}
    chunk, speed, duration = int(p["chunk"]), float(p["speed"]), float(p["duration_s"])
    if chunk < 1:
        raise ValueError("chunk must be >= 1")
    if speed <= 0 or duration <= 0:
        raise ValueError("speed and duration_s must be > 0")
    if speed / chunk > MAX_CHANGES_PER_S + 1e-9:
        raise ValueError(
            f"chase changes each segment {speed / chunk:g} times/sec, over the "
            f"{MAX_CHANGES_PER_S:g}/sec cap; lower speed or raise chunk"
        )
    frames = tuple(
        SegmentFrame(
            tuple(chase_frame(caps.segments, int(i * speed / FRAME_HZ + 1e-9), chunk,
                              (primary, alternate))),
            1.0 / FRAME_HZ,
        )
        for i in range(max(1, round(duration * FRAME_HZ)))
    )
    return SegmentPattern(frames, int(p["brightness"]))


def build_effect(
    spec: EffectSpec, primary: Color, alternate: Color, caps: Capabilities, fixture: str = "fixture"
) -> Pattern | SegmentPattern:
    """The pattern an effect plays on a fixture with these capabilities.

    Raises ValueError for an unknown kind, a kind the fixture does not support, or a parameter
    the kind does not take; PatternError (a ValueError) if the flash cap is exceeded.
    """
    if spec.kind not in KIND_PARAMS:
        raise ValueError(f"unknown effect kind {spec.kind!r}")
    if spec.kind not in caps.kinds:
        raise ValueError(f"{fixture} does not support {spec.kind!r} effects")
    extra = sorted(set(spec.params) - KIND_PARAMS[spec.kind])
    if extra:
        raise ValueError(f"{spec.kind} effect has no parameter {extra[0]!r}")
    if spec.kind == "chase":
        return _build_chase(spec.params, primary, alternate, caps)
    effect = EffectConfig(**{k: v for k, v in spec.params.items()})
    return build_pattern(effect, primary, alternate)


@dataclass(frozen=True)
class EffectLayer:
    """One level of overrides; unset fields fall through to the level above."""

    kind: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    color: Color | None = None
    alt_color: Color | None = None


@dataclass(frozen=True)
class ResolvedEffect:
    spec: EffectSpec
    primary: Color
    alternate: Color


def global_layer(effect: EffectConfig) -> EffectLayer:
    return EffectLayer(
        "pulse",
        {"pulses": effect.pulses, "duration_s": effect.duration_s, "brightness": effect.brightness},
        effect.color, effect.alt_color,
    )


def effect_layers(
    config: Config, team: TeamConfig, bulb_name: str
) -> list[tuple[str, EffectLayer | None]]:
    """The layers that decide what `team` plays on `bulb_name`, lowest first, with their names."""
    team_layer = EffectLayer(
        team.effect.kind if team.effect else None,
        team.effect.params if team.effect else {},
        team.color, team.alt_color,
    )
    return [
        ("default", global_layer(config.score_effect)),
        ("fixture", config.fixture_effects.get(bulb_name)),
        ("team", team_layer),
        ("team x fixture", team.fixture_effects.get(bulb_name)),
    ]


def resolve_effect(
    config: Config, team: TeamConfig, bulb_name: str, espn_colors: tuple[Color, Color]
) -> ResolvedEffect:
    """What `team` plays on fixture `bulb_name`: layers global, fixture, team, team x fixture.

    A later layer overrides an earlier one field by field. ESPN's colors are the last fallback
    for colors only. A parameter the final kind does not take is dropped, so a layer can switch
    a fixture to another kind without tripping over the global layer's parameters.
    """
    kind, params, color, alt = "pulse", {}, None, None
    for _, layer in effect_layers(config, team, bulb_name):
        if layer is None:
            continue
        kind = layer.kind or kind
        params = {**params, **layer.params}
        color = layer.color or color
        alt = layer.alt_color or alt
    allowed = KIND_PARAMS.get(kind, frozenset())
    params = {k: v for k, v in params.items() if k in allowed}
    return ResolvedEffect(EffectSpec(kind, params), color or espn_colors[0], alt or espn_colors[1])
