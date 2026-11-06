"""SQLite state: games, per-team scores and increase counters, events."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = 1

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


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
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
                self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # games
    def upsert_game(self, g: Game) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO games VALUES (?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET "
                "league=excluded.league, name=excluded.name, "
                "start_utc=excluded.start_utc, status=excluded.status",
                (g.game_id, g.league, g.name, _iso(g.start_utc), g.status),
            )

    def _game(self, r: sqlite3.Row) -> Game:
        return Game(r["game_id"], r["league"], r["name"], _dt(r["start_utc"]), r["status"])

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
