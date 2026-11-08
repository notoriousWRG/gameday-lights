"""TOML config -> frozen dataclasses."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.bulbs.base import PatternError, capabilities_for
from app.effects import (
    KIND_PARAMS,
    EffectConfig,
    EffectLayer,
    build_effect,
    build_pattern,
    parse_color,
    resolve_effect,
)

MIN_POLL_S = 10.0


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GeneralConfig:
    dispatch_enabled: bool
    db_path: Path
    delay_s: float = 45.0
    schedule_sync_hours: float = 6.0
    watch_lead_min: float = 10.0
    poll_live_s: float = 15.0
    poll_break_s: float = 60.0


BULB_KINDS = ("wiz", "govee")
DEFAULT_PORTS = {"wiz": 38899, "govee": 4003}


@dataclass(frozen=True)
class BulbConfig:
    name: str
    ip: str
    mac: str | None = None
    port: int = 38899
    signing_key: str | None = None
    kind: str = "wiz"
    segments: int = 1  # individually addressable segments along the fixture; 1 = whole fixture


@dataclass(frozen=True)
class TeamConfig:
    league: str
    id: str
    abbr: str
    bulbs: tuple[str, ...]
    color: tuple[int, int, int] | None = None
    alt_color: tuple[int, int, int] | None = None
    effect: EffectLayer | None = None  # team layer: kind and parameters (colors are above)
    fixture_effects: Mapping[str, EffectLayer] = field(default_factory=dict)  # team x fixture


@dataclass(frozen=True)
class WebConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8787
    pulse_cooldown_s: float = 10.0
    final_hold_min: float = 30.0


@dataclass(frozen=True)
class Config:
    general: GeneralConfig
    bulbs: tuple[BulbConfig, ...]
    teams: tuple[TeamConfig, ...]
    score_effect: EffectConfig = field(default_factory=EffectConfig)
    web: WebConfig = field(default_factory=WebConfig)
    fixture_effects: Mapping[str, EffectLayer] = field(default_factory=dict)  # fixture layer


def _color(table: dict, key: str, where: str):
    if table.get(key) in (None, ""):
        return None
    try:
        return parse_color(str(table[key]))
    except ValueError as e:
        raise ConfigError(f"{where}.{key}: {e}") from None


def _num(table: dict, key: str, default: float, where: str, minimum: float) -> float:
    v = table.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{where}.{key}: must be a number")
    if v < minimum:
        raise ConfigError(f"{where}.{key}: must be >= {minimum:g} (got {v:g})")
    return float(v)


def _segments(table: dict, kind: str, where: str) -> int:
    n = int(_num(table, "segments", 1, where, 1))
    if kind != "govee" and n != 1:
        raise ConfigError(f"{where}.segments: a {kind} bulb has no segments")
    return n


def _str(table: dict, key: str, where: str, required: bool = True) -> str | None:
    v = table.get(key)
    if v is None:
        if required:
            raise ConfigError(f"{where}.{key}: required")
        return None
    return str(v)


_LAYER_KEYS = {"kind", "color", "alt_color"}
_PARAM_MINIMUMS = {"pulses": 1, "chunk": 1, "duration_s": 0.1, "speed": 0.1, "brightness": 1}
_INT_PARAMS = {"pulses", "chunk", "brightness"}


def _layer(table: Any, where: str, colors: bool = True) -> EffectLayer:
    """One override layer from its table: `kind`, any of the kind's parameters, and colors."""
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: must be a table")
    allowed = set(_PARAM_MINIMUMS) | (_LAYER_KEYS if colors else {"kind"})
    for key in table:
        if key not in allowed:
            raise ConfigError(f"{where}.{key}: unknown field")
    kind = _str(table, "kind", where, False)
    if kind is not None and kind not in KIND_PARAMS:
        raise ConfigError(f"{where}.kind: must be one of {', '.join(KIND_PARAMS)}")
    params: dict[str, float | int] = {}
    for key, minimum in _PARAM_MINIMUMS.items():
        if key not in table:
            continue
        if kind is not None and key not in KIND_PARAMS[kind]:
            raise ConfigError(f"{where}.{key}: not a {kind} parameter")
        v = _num(table, key, 0, where, minimum)
        if key == "brightness" and v > 255:
            raise ConfigError(f"{where}.brightness: must be <= 255 (got {v:g})")
        params[key] = int(v) if key in _INT_PARAMS else v
    return EffectLayer(
        kind, params,
        _color(table, "color", where) if colors else None,
        _color(table, "alt_color", where) if colors else None,
    )


def _layers(table: Any, where: str, bulb_names: tuple[str, ...]) -> dict[str, EffectLayer]:
    """A table of {bulb name: layer}; every name must be a known bulb."""
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: must be a table")
    out = {}
    for name, layer in table.items():
        if name not in bulb_names:
            raise ConfigError(f"{where}.{name}: unknown bulb")
        out[name] = _layer(layer, f"{where}.{name}")
    return out


def load_raw(path: str | Path) -> tuple[dict, Path]:
    """Parse a TOML file into a plain dict (and the directory relative paths resolve against)."""
    path = Path(path)
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None
    return raw, path.resolve().parent


def load_config(path: str | Path) -> Config:
    return parse_config(*load_raw(path))


def parse_config(raw: dict, base_dir: Path) -> Config:
    """Validate a config document (TOML-shaped dict) into a Config. The one validation path:
    the TOML file and the stored, UI-edited settings both go through it."""
    g = raw.get("general", {})
    if "dispatch_enabled" not in g or not isinstance(g["dispatch_enabled"], bool):
        raise ConfigError("general.dispatch_enabled: required true/false")
    db = Path(str(g.get("db_path", "gameday-lights.db")))
    if not db.is_absolute():
        db = base_dir / db
    general = GeneralConfig(
        dispatch_enabled=g["dispatch_enabled"],
        db_path=db,
        delay_s=_num(g, "delay_s", 45, "general", 0),
        schedule_sync_hours=_num(g, "schedule_sync_hours", 6, "general", 0.1),
        watch_lead_min=_num(g, "watch_lead_min", 10, "general", 0),
        poll_live_s=_num(g, "poll_live_s", 15, "general", MIN_POLL_S),
        poll_break_s=_num(g, "poll_break_s", 60, "general", MIN_POLL_S),
    )

    bulbs: list[BulbConfig] = []
    for i, b in enumerate(raw.get("bulbs", [])):
        where = f"bulbs[{i}]"
        name = (_str(b, "name", where) or "").strip()
        if not name:
            raise ConfigError(f"{where}.name: must not be empty")
        ip = (_str(b, "ip", where) or "").strip()
        if not ip:
            raise ConfigError(f"{where}.ip: must not be empty")
        if any(x.name == name for x in bulbs):
            raise ConfigError(f"{where}.name: duplicate bulb {name!r}")
        kind = _str(b, "kind", where, False) or "wiz"
        if kind not in BULB_KINDS:
            raise ConfigError(f"{where}.kind: must be one of {', '.join(BULB_KINDS)}")
        bulbs.append(BulbConfig(
            name=name, ip=ip, mac=_str(b, "mac", where, False),
            port=int(b.get("port", DEFAULT_PORTS[kind])),
            signing_key=_str(b, "signing_key", where, False), kind=kind,
            segments=_segments(b, kind, where),
        ))

    teams: list[TeamConfig] = []
    for i, t in enumerate(raw.get("teams", [])):
        where = f"teams[{i}]"
        names = t.get("bulbs", [])
        if not names or not isinstance(names, list):
            raise ConfigError(f"{where}.bulbs: list of bulb names required")
        for n in names:
            if not any(b.name == n for b in bulbs):
                raise ConfigError(f"{where}.bulbs: unknown bulb {n!r}")
        fixture_effects = _layers(t.get("fixture_effects", {}), f"{where}.fixture_effects",
                                  tuple(names))
        team = TeamConfig(
            league=_str(t, "league", where), id=_str(t, "id", where),
            abbr=_str(t, "abbr", where), bulbs=tuple(names),
            color=_color(t, "color", where), alt_color=_color(t, "alt_color", where),
            effect=_layer(t["effects"], f"{where}.effects", colors=False)
            if "effects" in t else None,
            fixture_effects=fixture_effects,
        )
        if any((x.league, x.id) == (team.league, team.id) for x in teams):
            raise ConfigError(f"{where}: duplicate team {team.league}/{team.id}")
        teams.append(team)

    e = raw.get("effects", {}).get("score", {})
    effect = EffectConfig(
        pulses=int(_num(e, "pulses", 5, "effects.score", 1)),
        duration_s=_num(e, "duration_s", 6.0, "effects.score", 0.1),
        color=_color(e, "color", "effects.score"),
        alt_color=_color(e, "alt_color", "effects.score"),
        brightness=int(_num(e, "brightness", 255, "effects.score", 1)),
    )
    try:
        build_pattern(effect, (0, 0, 0), (255, 255, 255))
    except (PatternError, ValueError) as err:
        raise ConfigError(f"effects.score: {err}") from None

    bulb_names = tuple(b.name for b in bulbs)
    fixture_effects = _layers(raw.get("effects", {}).get("fixtures", {}), "effects.fixtures",
                              bulb_names)

    w = raw.get("web", {})
    enabled = w.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("web.enabled: must be true or false")
    host = str(w.get("host", "127.0.0.1")).strip()
    if not host:
        raise ConfigError("web.host: must not be empty")
    port = w.get("port", 8787)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError("web.port: must be an integer 1-65535")

    cooldown = _num(w, "pulse_cooldown_s", 10, "web", 1)
    final_hold = _num(w, "final_hold_min", 30, "web", 0)

    config = Config(
        general, tuple(bulbs), tuple(teams), effect,
        WebConfig(enabled, host, port, cooldown, final_hold), fixture_effects,
    )
    _check_effects(config)
    return config


def _check_effects(config: Config) -> None:
    """Every team x fixture must resolve to an effect its fixture supports and the cap allows."""
    colors = ((0, 255, 0), (255, 255, 255))
    by_name = {b.name: b for b in config.bulbs}
    for i, team in enumerate(config.teams):
        for name in team.bulbs:
            bulb = by_name[name]
            resolved = resolve_effect(config, team, name, colors)
            try:
                build_effect(resolved.spec, resolved.primary, resolved.alternate,
                             capabilities_for(bulb.kind, bulb.segments), name)
            except (PatternError, ValueError) as err:
                raise ConfigError(f"teams[{i}].bulbs: effect on {name!r}: {err}") from None
