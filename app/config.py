"""TOML config -> frozen dataclasses."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.bulbs.base import PatternError
from app.effects import EffectConfig, build_pattern, parse_color

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


@dataclass(frozen=True)
class BulbConfig:
    name: str
    ip: str
    mac: str | None = None
    port: int = 38899
    signing_key: str | None = None


@dataclass(frozen=True)
class TeamConfig:
    league: str
    id: str
    abbr: str
    bulbs: tuple[str, ...]
    color: tuple[int, int, int] | None = None
    alt_color: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class Config:
    general: GeneralConfig
    bulbs: tuple[BulbConfig, ...]
    teams: tuple[TeamConfig, ...]
    score_effect: EffectConfig = field(default_factory=EffectConfig)


def _color(table: dict, key: str, where: str):
    if key not in table:
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


def _str(table: dict, key: str, where: str, required: bool = True) -> str | None:
    v = table.get(key)
    if v is None:
        if required:
            raise ConfigError(f"{where}.{key}: required")
        return None
    return str(v)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None

    g = raw.get("general", {})
    if "dispatch_enabled" not in g or not isinstance(g["dispatch_enabled"], bool):
        raise ConfigError("general.dispatch_enabled: required true/false")
    db = Path(str(g.get("db_path", "game-lights.db")))
    if not db.is_absolute():
        db = path.resolve().parent / db
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
        name = _str(b, "name", where)
        if any(x.name == name for x in bulbs):
            raise ConfigError(f"{where}.name: duplicate bulb {name!r}")
        bulbs.append(BulbConfig(
            name=name, ip=_str(b, "ip", where), mac=_str(b, "mac", where, False),
            port=int(b.get("port", 38899)), signing_key=_str(b, "signing_key", where, False),
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
        team = TeamConfig(
            league=_str(t, "league", where), id=_str(t, "id", where),
            abbr=_str(t, "abbr", where), bulbs=tuple(names),
            color=_color(t, "color", where), alt_color=_color(t, "alt_color", where),
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

    return Config(general, tuple(bulbs), tuple(teams), effect)
