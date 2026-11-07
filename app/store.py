"""SQLite state: games, per-team scores and increase counters, events."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = 3

_SCHEMA_V1 = """
CREATE TABLE games (
    game_id   TEXT PRIMARY KEY,
    league    TEXT NOT NULL,
    name      TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    status    TEXT NOT NULL
);
CREATE TABLE team_scores (
    game_id    TEXT NOT NULL,
    team_id    TEXT NOT NULL,
    score      INTEGER NOT NULL,
    increase_n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, team_id)
);
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key  TEXT NOT NULL UNIQUE,
    game_id     TEXT NOT NULL,
    team_id     TEXT NOT NULL,
    type        TEXT NOT NULL,
    detail      TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    fired_at    TEXT,
    status      TEXT NOT NULL
);
CREATE INDEX events_status ON events (status, due_at);
"""


_SCHEMA_V2 = """
ALTER TABLE games ADD COLUMN home_abbr TEXT;
ALTER TABLE games ADD COLUMN home_score INTEGER;
ALTER TABLE games ADD COLUMN away_abbr TEXT;
ALTER TABLE games ADD COLUMN away_score INTEGER;
"""


_SCHEMA_V3 = """
CREATE TABLE settings (
    section    TEXT PRIMARY KEY,
    revision   INTEGER NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE settings_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    section    TEXT NOT NULL,
    revision   INTEGER NOT NULL,
    value      TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    source     TEXT NOT NULL
);
CREATE INDEX settings_history_section ON settings_history (section, revision);
"""


class RevisionConflict(Exception):
    """A settings edit was based on a stale revision."""

    def __init__(self, section: str, current_revision: int) -> None:
        super().__init__(f"{section} changed since you loaded it (now revision {current_revision})")
        self.section = section
        self.current_revision = current_revision


@dataclass(frozen=True)
class SettingsChange:
    section: str
    revision: int
    value: object
    changed_at: datetime
    source: str


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; store only timezone-aware values")
    return dt.astimezone(UTC).isoformat()


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


@dataclass(frozen=True)
class Game:
    game_id: str
    league: str
    name: str
    start_utc: datetime
    status: str
    home_abbr: str | None = None
    home_score: int | None = None
    away_abbr: str | None = None
    away_score: int | None = None


@dataclass(frozen=True)
class ScoreUpdate:
    prev_score: int | None
    score: int
    increase_n: int
    increased: bool


@dataclass
class Event:
    dedupe_key: str
    game_id: str
    team_id: str
    type: str
    detected_at: datetime
    due_at: datetime
    detail: dict = field(default_factory=dict)
    fired_at: datetime | None = None
    status: str = "pending"


def dedupe_key(game_id: str, team_id: str, n: int) -> str:
    return f"{game_id}:{team_id}:{n}"


log = logging.getLogger(__name__)


def _private_file(path: Path) -> None:
    """Create the database file readable only by its owner; tighten an existing one."""
    if not path.exists():
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    elif path.stat().st_mode & 0o077:
        path.chmod(0o600)
        log.info("restricted %s to its owner (it stores bulb credentials)", path)


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            _private_file(Path(path))
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.db.close()

    def _migrate(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"database schema {version} is newer than this app")
        if version < 1:
            with self.db:
                self.db.executescript(_SCHEMA_V1)
                self.db.execute("PRAGMA user_version = 1")
        if version < 2:
            with self.db:
                self.db.executescript(_SCHEMA_V2)
                self.db.execute("PRAGMA user_version = 2")
        if version < 3:
            with self.db:
                self.db.executescript(_SCHEMA_V3)
                self.db.execute("PRAGMA user_version = 3")

    # games
    def upsert_game(self, g: Game) -> None:
        """Insert or update a game. Teams and scores that arrive as None never erase known ones."""
        with self.db:
            self.db.execute(
                "INSERT INTO games (game_id, league, name, start_utc, status, home_abbr, "
                "home_score, away_abbr, away_score) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(game_id) DO UPDATE SET league=excluded.league, name=excluded.name, "
                "start_utc=excluded.start_utc, status=excluded.status, "
                "home_abbr=COALESCE(excluded.home_abbr, home_abbr), "
                "home_score=COALESCE(excluded.home_score, home_score), "
                "away_abbr=COALESCE(excluded.away_abbr, away_abbr), "
                "away_score=COALESCE(excluded.away_score, away_score)",
                (g.game_id, g.league, g.name, _iso(g.start_utc), g.status, g.home_abbr,
                 g.home_score, g.away_abbr, g.away_score),
            )

    def _game(self, r: sqlite3.Row) -> Game:
        return Game(
            r["game_id"], r["league"], r["name"], _dt(r["start_utc"]), r["status"],
            r["home_abbr"], r["home_score"], r["away_abbr"], r["away_score"],
        )

    def get_game(self, game_id: str) -> Game | None:
        r = self.db.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
        return self._game(r) if r else None

    def upcoming_games(self, now: datetime, horizon: timedelta) -> list[Game]:
        """Games starting within `horizon` of now that are not final."""
        rows = self.db.execute(
            "SELECT * FROM games WHERE start_utc <= ? AND status != 'post' "
            "ORDER BY start_utc",
            (_iso(now + horizon),),
        ).fetchall()
        return [self._game(r) for r in rows]

    def all_games(self) -> list[Game]:
        rows = self.db.execute("SELECT * FROM games ORDER BY start_utc, game_id").fetchall()
        return [self._game(r) for r in rows]

    # scores
    def apply_score(self, game_id: str, team_id: str, score: int) -> ScoreUpdate:
        with self.db:
            r = self.db.execute(
                "SELECT score, increase_n FROM team_scores WHERE game_id=? AND team_id=?",
                (game_id, team_id),
            ).fetchone()
            if r is None:
                self.db.execute(
                    "INSERT INTO team_scores VALUES (?,?,?,0)", (game_id, team_id, score)
                )
                return ScoreUpdate(None, score, 0, False)
            prev, n = r["score"], r["increase_n"]
            increased = score > prev
            if increased:
                n += 1
            if score != prev:
                self.db.execute(
                    "UPDATE team_scores SET score=?, increase_n=? WHERE game_id=? AND team_id=?",
                    (score, n, game_id, team_id),
                )
            return ScoreUpdate(prev, score, n, increased)

    # events
    def insert_event(self, e: Event) -> bool:
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO events (dedupe_key, game_id, team_id, type, detail, "
                "detected_at, due_at, fired_at, status) VALUES (?,?,?,?,?,?,?,?,?)",
                (e.dedupe_key, e.game_id, e.team_id, e.type, json.dumps(e.detail),
                 _iso(e.detected_at), _iso(e.due_at),
                 _iso(e.fired_at) if e.fired_at else None, e.status),
            )
        return cur.rowcount == 1

    def _event(self, r: sqlite3.Row) -> Event:
        return Event(
            dedupe_key=r["dedupe_key"], game_id=r["game_id"], team_id=r["team_id"],
            type=r["type"], detail=json.loads(r["detail"]), detected_at=_dt(r["detected_at"]),
            due_at=_dt(r["due_at"]), fired_at=_dt(r["fired_at"]), status=r["status"],
        )

    def get_event(self, key: str) -> Event | None:
        r = self.db.execute("SELECT * FROM events WHERE dedupe_key=?", (key,)).fetchone()
        return self._event(r) if r else None

    def recent_events(self, limit: int = 25) -> list[Event]:
        rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._event(r) for r in rows]

    def pending_events(self) -> list[Event]:
        rows = self.db.execute(
            "SELECT * FROM events WHERE status='pending' ORDER BY due_at, id"
        ).fetchall()
        return [self._event(r) for r in rows]

    def mark_event(self, key: str, status: str, fired_at: datetime | None = None) -> None:
        with self.db:
            self.db.execute(
                "UPDATE events SET status=?, fired_at=COALESCE(?, fired_at) WHERE dedupe_key=?",
                (status, _iso(fired_at) if fired_at else None, key),
            )

    # settings
    def get_setting(self, section: str) -> tuple[int, object] | None:
        r = self.db.execute(
            "SELECT revision, value FROM settings WHERE section=?", (section,)
        ).fetchone()
        return (r["revision"], json.loads(r["value"])) if r else None

    def all_settings(self) -> dict[str, tuple[int, object]]:
        rows = self.db.execute("SELECT section, revision, value FROM settings").fetchall()
        return {r["section"]: (r["revision"], json.loads(r["value"])) for r in rows}

    def put_setting(
        self,
        section: str,
        value: object,
        expected_revision: int,
        source: str,
        now: datetime,
        history_value: object | None = None,
    ) -> int:
        """Write a section if `expected_revision` is still current (0 = not stored yet)."""
        with self.db:  # one transaction: check, write and history succeed or fail together
            current = self.get_setting(section)
            have = current[0] if current else 0
            if have != expected_revision:
                raise RevisionConflict(section, have)
            revision = have + 1
            text = json.dumps(value, ensure_ascii=False)
            self.db.execute(
                "INSERT INTO settings (section, revision, value, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(section) DO UPDATE SET revision=excluded.revision, "
                "value=excluded.value, updated_at=excluded.updated_at",
                (section, revision, text, _iso(now)),
            )
            shown = value if history_value is None else history_value
            self.db.execute(
                "INSERT INTO settings_history (section, revision, value, changed_at, source) "
                "VALUES (?,?,?,?,?)",
                (section, revision, json.dumps(shown, ensure_ascii=False), _iso(now), source),
            )
        return revision

    def settings_history(self, limit: int = 50, section: str | None = None) -> list[SettingsChange]:
        sql, args = "SELECT * FROM settings_history", []
        if section:
            sql, args = sql + " WHERE section=?", [section]
        rows = self.db.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [
            SettingsChange(r["section"], r["revision"], json.loads(r["value"]),
                           _dt(r["changed_at"]), r["source"])
            for r in rows
        ]
