"""Editable settings: which parts of the config are stored (and UI-editable) and how they map
to and from a Config.

Machine config stays in config.toml only: db_path, dispatch_enabled and the [web] address.
Everything else is household state, stored as sections:

    bulbs, teams, effects  - the same shapes as their TOML tables
    household              - delay_s
    advanced               - poll/sync/lead timings, pulse_cooldown_s, final_hold_min

Validation is config.parse_config, so the file and the UI follow one set of rules.
"""

from __future__ import annotations

import copy
from pathlib import Path

from app.config import Config, ConfigError, parse_config

SECTIONS = ("bulbs", "teams", "effects", "household", "advanced")

_ADVANCED_GENERAL = ("schedule_sync_hours", "watch_lead_min", "poll_live_s", "poll_break_s")
_ADVANCED_WEB = ("pulse_cooldown_s", "final_hold_min")
_ALLOWED = {
    "household": {"delay_s"},
    "advanced": {*_ADVANCED_GENERAL, *_ADVANCED_WEB},
}
_BULB_KEYS = {"name", "ip", "mac", "port", "signing_key"}
_TEAM_KEYS = {"league", "id", "abbr", "bulbs", "color", "alt_color"}
_EFFECT_KEYS = {"pulses", "duration_s", "color", "alt_color", "brightness"}
SECRET = "signing_key"


def _hex(color) -> str | None:
    return "#{:02x}{:02x}{:02x}".format(*color) if color else None


def machine_raw_from_config(cfg: Config) -> dict:
    """The machine-level (TOML only) part of a config, in TOML shape."""
    return {
        "general": {"dispatch_enabled": cfg.general.dispatch_enabled,
                    "db_path": str(cfg.general.db_path)},
        "web": {"enabled": cfg.web.enabled, "host": cfg.web.host, "port": cfg.web.port},
    }


def sections_from_config(cfg: Config) -> dict[str, object]:
    """Complete, normalized, JSON-safe sections for a config."""
    g, w, e = cfg.general, cfg.web, cfg.score_effect
    return {
        "bulbs": [
            {"name": b.name, "ip": b.ip, "mac": b.mac, "port": b.port, "signing_key": b.signing_key}
            for b in cfg.bulbs
        ],
        "teams": [
            {"league": t.league, "id": t.id, "abbr": t.abbr, "bulbs": list(t.bulbs),
             "color": _hex(t.color), "alt_color": _hex(t.alt_color)}
            for t in cfg.teams
        ],
        "effects": {"score": {
            "pulses": e.pulses, "duration_s": e.duration_s, "color": _hex(e.color),
            "alt_color": _hex(e.alt_color), "brightness": e.brightness,
        }},
        "household": {"delay_s": g.delay_s},
        "advanced": {
            "schedule_sync_hours": g.schedule_sync_hours, "watch_lead_min": g.watch_lead_min,
            "poll_live_s": g.poll_live_s, "poll_break_s": g.poll_break_s,
            "pulse_cooldown_s": w.pulse_cooldown_s, "final_hold_min": w.final_hold_min,
        },
    }


def _unknown(path: str, value: dict, allowed: set[str]) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise ConfigError(f"{path}: unknown field {extra[0]!r}")


def check_section_shape(section: str, value: object) -> None:
    """Strict shape check for a section arriving from the UI: right container, no unknown fields."""
    if section not in SECTIONS:
        raise ConfigError(f"unknown settings section {section!r}")
    if section in ("bulbs", "teams"):
        if not isinstance(value, list):
            raise ConfigError(f"{section}: must be a list")
        allowed = _BULB_KEYS if section == "bulbs" else _TEAM_KEYS
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise ConfigError(f"{section}[{i}]: must be an object")
            _unknown(f"{section}[{i}]", item, allowed)
        return
    if not isinstance(value, dict):
        raise ConfigError(f"{section}: must be an object")
    if section == "effects":
        _unknown("effects", value, {"score"})
        score = value.get("score", {})
        if not isinstance(score, dict):
            raise ConfigError("effects.score: must be an object")
        _unknown("effects.score", score, _EFFECT_KEYS)
    else:
        _unknown(section, value, _ALLOWED[section])


def merge_raw(machine_raw: dict, sections: dict[str, object]) -> dict:
    """A TOML-shaped config document from the machine part plus the stored sections."""
    raw = {
        "general": dict(machine_raw.get("general", {})),
        "web": dict(machine_raw.get("web", {})),
        "bulbs": copy.deepcopy(sections.get("bulbs", [])),
        "teams": copy.deepcopy(sections.get("teams", [])),
        "effects": copy.deepcopy(sections.get("effects", {})),
    }
    household = sections.get("household", {})
    advanced = sections.get("advanced", {})
    if "delay_s" in household:
        raw["general"]["delay_s"] = household["delay_s"]
    for key in _ADVANCED_GENERAL:
        if key in advanced:
            raw["general"][key] = advanced[key]
    for key in _ADVANCED_WEB:
        if key in advanced:
            raw["web"][key] = advanced[key]
    return raw


def build_config(machine_raw: dict, sections: dict[str, object], base_dir: Path) -> Config:
    """Validate and assemble a Config. Raises ConfigError naming the field."""
    for name, value in sections.items():
        check_section_shape(name, value)
    return parse_config(merge_raw(machine_raw, sections), base_dir)


def error_location(path: str) -> tuple[str, str]:
    """Where a validation error belongs in the editor: (section, field).

    Validation speaks in config.toml terms ("general.delay_s"); the UI edits sections
    ("household" -> "delay_s"), so a screen knows which field to mark.
    """
    head = path.split(".")[0].split("[")[0]
    if head in ("bulbs", "teams", "effects"):
        return head, path
    if "." in path:
        table, field = path.split(".", 1)
        if table == "general" and field == "delay_s":
            return "household", field
        if (table == "general" and field in _ADVANCED_GENERAL) or (
            table == "web" and field in _ADVANCED_WEB
        ):
            return "advanced", field
    return (head if head in SECTIONS else ""), path


def redact(section: str, value: object) -> object:
    """The view of a section that is safe to send to the browser: signing keys are never shown."""
    if section != "bulbs":
        return copy.deepcopy(value)
    out = []
    for bulb in value:  # type: ignore[union-attr]
        bulb = dict(bulb)
        bulb["has_signing_key"] = bool(bulb.pop(SECRET, None))
        out.append(bulb)
    return out
