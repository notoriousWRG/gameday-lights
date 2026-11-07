"""Stored, editable settings: seed from config.toml, current snapshot, validated edits, export."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.config import Config, ConfigError
from app.dispatch.dispatcher import utc_now
from app.settings import (
    SECRET,
    SECTIONS,
    build_config,
    machine_raw_from_config,
    redact,
    sections_from_config,
)
from app.store import RevisionConflict, Store

log = logging.getLogger(__name__)

Subscriber = Callable[[Config, Config], None]


class SettingsService:
    def __init__(
        self,
        store: Store,
        machine_raw: dict,
        base_dir: Path,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._machine = machine_raw
        self._base_dir = base_dir
        self._now = now
        self._config: Config | None = None
        self._subscribers: list[Subscriber] = []

    # -- seeding -------------------------------------------------------------------------
    def seed(self, cfg: Config, force: bool = False) -> list[str]:
        """Import missing sections from a TOML-derived config; `force` overwrites differing ones."""
        want = sections_from_config(cfg)
        written = []
        for name in SECTIONS:
            stored = self._store.get_setting(name)
            if stored is None:
                self._write(name, want[name], 0, "config.toml")
            elif force and stored[1] != want[name]:
                self._write(name, want[name], stored[0], "config import")
            else:
                continue
            written.append(name)
        if written:
            self._reload_and_notify()  # a forced import must reach the running components too
        return written

    def _reload_and_notify(self) -> None:
        old = self._config
        new = self.load()
        if old is not None and old != new:
            self._notify(old, new)

    def _notify(self, old: Config, new: Config) -> None:
        for callback in list(self._subscribers):
            try:
                callback(old, new)
            except Exception:  # a failing subscriber must not undo or hide a saved edit
                log.exception("settings subscriber failed")

    def diverged(self, cfg: Config) -> list[str]:
        """Stored sections that differ from what config.toml says (stored settings win)."""
        want = sections_from_config(cfg)
        stored = self.sections()
        return [n for n in SECTIONS if n in stored and stored[n][1] != want[n]]

    def _write(self, section: str, value: object, expected: int, source: str) -> int:
        return self._store.put_setting(
            section, value, expected, source, self._now(), history_value=redact(section, value)
        )

    # -- reading -------------------------------------------------------------------------
    def load(self) -> Config:
        """Build the current snapshot from the stored sections."""
        stored = {name: value for name, (_, value) in self._store.all_settings().items()}
        self._config = build_config(self._machine, stored, self._base_dir)
        return self._config

    @property
    def config(self) -> Config:
        if self._config is None:
            self.load()
        return self._config  # type: ignore[return-value]

    def sections(self) -> dict[str, tuple[int, object]]:
        """Stored sections with their revisions, secrets included. Internal use only."""
        return self._store.all_settings()

    def public_sections(self) -> dict[str, dict]:
        return {
            name: {"revision": rev, "value": redact(name, value)}
            for name, (rev, value) in self.sections().items()
        }

    def history(self, limit: int = 50, section: str | None = None) -> list[dict]:
        """Recent changes, newest first. Values are stored secrets-free."""
        return [
            {"section": c.section, "revision": c.revision, "source": c.source,
             "changed_at": c.changed_at.isoformat(), "value": c.value}
            for c in self._store.settings_history(limit, section)
        ]

    # -- editing -------------------------------------------------------------------------
    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def update(
        self, section: str, value: object, expected_revision: int, source: str = "ui"
    ) -> tuple[int, Config]:
        """Validate and store an edit, then apply it. Nothing changes if anything is refused."""
        stored = {name: (rev, val) for name, (rev, val) in self.sections().items()}
        if section == "bulbs":
            value = self._merge_bulb_secrets(value, stored.get("bulbs", (0, []))[1])
        candidate = {name: val for name, (_, val) in stored.items()}
        candidate[section] = value
        new_config = build_config(self._machine, candidate, self._base_dir)  # ConfigError: no write
        normalized = sections_from_config(new_config)[section]

        current = stored.get(section)
        if current and current[0] == expected_revision and current[1] == normalized:
            return current[0], self.config  # nothing changed: no new revision, no history noise
        revision = self._write(section, normalized, expected_revision, source)  # RevisionConflict

        old, self._config = self.config, new_config
        self._notify(old, new_config)
        return revision, new_config

    def rename_bulb(
        self, old: str, new: str, bulbs_revision: int, teams_revision: int, source: str = "ui"
    ) -> Config:
        """Rename a bulb and every team reference to it in one step. Both sections are validated
        together and both revisions checked before anything is written, so a refusal changes
        nothing and teams never point at a name that no longer exists."""
        stored = self.sections()
        new = new.strip()
        bulbs = copy.deepcopy(stored.get("bulbs", (0, []))[1])
        teams = copy.deepcopy(stored.get("teams", (0, []))[1])
        if not any(b.get("name") == old for b in bulbs):  # type: ignore[union-attr]
            raise ConfigError(f"bulbs: unknown bulb {old!r}")
        for b in bulbs:  # type: ignore[union-attr]
            if b.get("name") == old:
                b["name"] = new
        for t in teams:  # type: ignore[union-attr]
            t["bulbs"] = [new if n == old else n for n in t.get("bulbs", [])]
        candidate = {name: val for name, (_, val) in stored.items()}
        candidate.update(bulbs=bulbs, teams=teams)
        new_config = build_config(self._machine, candidate, self._base_dir)
        for section, expected in (("bulbs", bulbs_revision), ("teams", teams_revision)):
            have = stored[section][0] if section in stored else 0
            if have != expected:
                raise RevisionConflict(section, have)
        if old == new:
            return self.config
        normalized = sections_from_config(new_config)
        self._write("bulbs", normalized["bulbs"], bulbs_revision, source)
        self._write("teams", normalized["teams"], teams_revision, source)
        old_config, self._config = self.config, new_config
        self._notify(old_config, new_config)
        return new_config

    @staticmethod
    def _merge_bulb_secrets(value: object, stored_bulbs: object) -> object:
        """Incoming bulbs without a signing_key keep the stored one; null or "" clears it."""
        if not isinstance(value, list):
            return value  # the shape check reports it
        known = [b for b in stored_bulbs if isinstance(b, dict)]  # type: ignore[union-attr]

        def stored_key(bulb: dict):
            """The stored key for this bulb: same name, else (a rename) same MAC, else same IP."""
            for field in ("name", "mac", "ip"):
                if bulb.get(field):
                    for old in known:
                        if old.get(field) == bulb[field]:
                            return old.get(SECRET), True
            return None, False

        merged = []
        for bulb in value:
            if not isinstance(bulb, dict):
                merged.append(bulb)
                continue
            bulb = {k: v for k, v in bulb.items() if k != "has_signing_key"}
            if SECRET not in bulb:
                key, found = stored_key(bulb)
                if found:
                    bulb[SECRET] = key
            elif not bulb[SECRET]:
                bulb[SECRET] = None
            merged.append(bulb)
        return merged

    # -- export --------------------------------------------------------------------------
    def export_toml(self, include_secrets: bool = True) -> str:
        return config_to_toml(self.config, include_secrets)


def _v(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_v(x) for x in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # a TOML basic string


def _table(header: str, fields: dict) -> list[str]:
    lines = [header]
    lines += [f"{k} = {_v(v)}" for k, v in fields.items() if v is not None]
    return [*lines, ""]


def config_to_toml(cfg: Config, include_secrets: bool = True) -> str:
    """A config.toml that load_config reads back to an equal Config."""
    sections = copy.deepcopy(sections_from_config(cfg))
    machine = machine_raw_from_config(cfg)
    adv, hh = sections["advanced"], sections["household"]
    general = {**machine["general"], "delay_s": hh["delay_s"]}
    general.update({k: adv[k] for k in ("schedule_sync_hours", "watch_lead_min",
                                        "poll_live_s", "poll_break_s")})
    web = {**machine["web"], **{k: adv[k] for k in ("pulse_cooldown_s", "final_hold_min")}}
    out = [
        "# Exported by `gameday-lights config export`.",
        "# Teams, bulbs, effects and timings are stored in the database after first start;",
        "# this file only seeds an empty database (or `config import --force`).",
        "",
        *_table("[general]", general),
    ]
    for bulb in sections["bulbs"]:
        if not include_secrets:
            bulb.pop(SECRET, None)
        out += _table("[[bulbs]]", bulb)
    for team in sections["teams"]:
        out += _table("[[teams]]", team)
    out += _table("[effects.score]", sections["effects"]["score"])
    out += _table("[web]", web)
    return "\n".join(out)


__all__ = ["RevisionConflict", "SettingsService", "config_to_toml"]
