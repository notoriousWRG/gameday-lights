"""Schedule-sync and game-watcher loops."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.config import Config
from app.dispatch.dispatcher import Dispatcher
from app.espn.client import EspnError
from app.espn.detect import detect, score_label, team_scores
from app.espn.schedule import (
    game_teams_and_scores,
    merge_schedules,
    parse_schedule,
    parse_scoreboard_game,
)
from app.store import Event, Store, dedupe_key

log = logging.getLogger(__name__)

BREAK_STATUSES = {"STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_DELAYED", "STATUS_RAIN_DELAY"}
_ORDER = {"pre": 0, "in": 1, "post": 2}


@dataclass
class WatcherStats:
    started_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_poll_at: datetime | None = None
    last_ok_at: datetime | None = None
    polls: int = 0
    errors: int = 0
    last_error: str | None = None
    watching: list[str] = field(default_factory=list)  # games currently in their window
    watching_ids: list[str] = field(default_factory=list)
    poll_interval_s: float | None = None  # seconds between polls right now; None = not polling
    # Latest parsed scoreboard details per game (in memory only), for the status page.
    # Each value is parse_scoreboard_game(...) plus updated_at and ended_at (set once final).
    live: dict[str, dict] = field(default_factory=dict)


class Watcher:
    def __init__(
        self,
        config: Config | Callable[[], Config],
        store: Store,
        client,
        dispatcher: Dispatcher,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        # A Config, or a function returning the current one (settings edits apply live).
        self._config_fn = config if callable(config) else (lambda: config)
        self._store = store
        self._client = client
        self._dispatcher = dispatcher
        self._now = now
        self._sleep = sleep
        self._prev: dict[str, dict] = {}
        # (league, game, team) already baselined in this process; see _process
        self._baselined: set[tuple[str, str, str]] = set()
        self._wake = asyncio.Event()
        self._sync_requested = False
        self.stats = WatcherStats(started_at=now())
        self._seen_status: dict[str, str] = {}  # game_id -> last status name logged

    @property
    def _cfg(self) -> Config:
        return self._config_fn()

    def _followed_ids(self, league: str) -> set[str]:
        return {t.id for t in self._cfg.teams if t.league == league}

    def _involves_followed(self, game) -> bool:
        """Is a followed team in this game? Rows with no team data yet count as yes."""
        if not (game.home_abbr or game.away_abbr):
            return True
        abbrs = {t.abbr.upper() for t in self._cfg.teams if t.league == game.league}
        return bool({(game.home_abbr or "").upper(), (game.away_abbr or "").upper()} & abbrs)

    def request_sync(self) -> None:
        """Sync schedules as soon as possible (a team was just followed)."""
        self._sync_requested = True
        self._wake.set()

    def on_config_changed(self, old: Config, new: Config) -> None:
        followed = lambda c: {(t.league, t.id) for t in c.teams}  # noqa: E731
        if followed(old) != followed(new):
            self.request_sync()

    # schedule
    async def sync_schedule(self) -> None:
        for team in self._cfg.teams:
            lists = []
            for seasontype in (None, 3):
                try:
                    data = await self._client.team_schedule(team.league, team.id, seasontype)
                except EspnError as e:
                    log.warning("schedule sync failed for %s/%s: %s", team.league, team.abbr, e)
                    continue
                lists.append(parse_schedule(data, team.league))
            for game in merge_schedules(*lists):
                existing = self._store.get_game(game.game_id)
                rank = _ORDER.get(existing.status, 0) if existing else 0
                if existing and rank > 0 and rank >= _ORDER.get(game.status, 0):
                    # Live polls are fresher than a (cached) schedule: keep their status and
                    # any scores they recorded; the schedule only fills in what is missing.
                    def keep(old, new):
                        return old if old is not None else new

                    game = dataclasses.replace(
                        game, status=existing.status,
                        home_score=keep(existing.home_score, game.home_score),
                        away_score=keep(existing.away_score, game.away_score),
                    )
                self._store.upsert_game(game)
        self.stats.last_sync_at = self._now()

    # polling
    async def poll_once(self) -> float:
        cfg = self._cfg.general
        now = self._now()
        windows = [
            g for g in self._store.upcoming_games(now, timedelta(minutes=cfg.watch_lead_min))
            if self._involves_followed(g)
        ]
        self.stats.watching = [g.name for g in windows]
        self.stats.watching_ids = [g.game_id for g in windows]
        self._prune_live(now)
        if not windows:
            self.stats.poll_interval_s = None
            return cfg.poll_break_s
        ids = {g.game_id for g in windows}
        for g in windows:
            if g.game_id not in self._seen_status:
                self._seen_status[g.game_id] = ""
                log.info("watching %s (kickoff %s UTC); polling started",
                         g.name, g.start_utc.strftime("%Y-%m-%d %H:%M"))
        live = False
        for league in {g.league for g in windows}:
            self.stats.polls += 1
            self.stats.last_poll_at = now
            try:
                board = await self._client.scoreboard(league)
            except EspnError as e:
                log.warning("scoreboard failed for %s: %s", league, e)
                self.stats.errors += 1
                self.stats.last_error = str(e)
                continue
            self.stats.last_ok_at = now
            self.stats.last_error = None
            self._process(league, board, now)
            for event in board.get("events", []):
                if str(event["id"]) not in ids:
                    continue
                st = (event.get("status") or {}).get("type", {})
                self._log_status(str(event["id"]), st.get("name", ""))
                self._update_game(event)
                self._capture_live(event, now)
                if st.get("state") == "in" and st.get("name") not in BREAK_STATUSES:
                    live = True
        interval = cfg.poll_live_s if live else cfg.poll_break_s
        self.stats.poll_interval_s = interval
        return interval

    def _capture_live(self, event: dict, now: datetime) -> None:
        game = parse_scoreboard_game(event)
        previous = self.stats.live.get(game["game_id"], {})
        ended = previous.get("ended_at") or (now if game["state"] == "post" else None)
        self.stats.live[game["game_id"]] = {**game, "updated_at": now, "ended_at": ended}

    def _prune_live(self, now: datetime) -> None:
        for gid, g in list(self.stats.live.items()):
            if g["ended_at"] and now - g["ended_at"] > timedelta(hours=24):
                del self.stats.live[gid]

    def _log_status(self, game_id: str, status_name: str) -> None:
        if status_name and self._seen_status.get(game_id) != status_name:
            self._seen_status[game_id] = status_name
            game = self._store.get_game(game_id)
            log.info("%s: %s", game.name if game else game_id, status_name)

    def _update_game(self, event: dict) -> None:
        """Keep a watched game's status and live/final score current from the scoreboard."""
        game = self._store.get_game(str(event["id"]))
        if game is None:
            return
        state = (event.get("status") or {}).get("type", {}).get("state", "")
        fields = game_teams_and_scores((event.get("competitions") or [{}])[0])
        if state == "pre":  # the scoreboard reports 0-0 before kickoff; that is not a score
            fields = {k: v for k, v in fields.items() if k.endswith("_abbr")}
        status = state if _ORDER.get(state, -1) > _ORDER.get(game.status, 0) else game.status
        updated = dataclasses.replace(game, status=status, **fields)
        if updated != game:
            self._store.upsert_game(updated)

    def _process(self, league: str, board: dict, now: datetime) -> None:
        followed = self._followed_ids(league)
        prev = self._prev.get(league)
        # Forget teams that are no longer followed, so following one again baselines it afresh.
        self._baselined = {
            k for k in self._baselined if k[0] != league or k[2] in followed
        }
        known = set(self._baselined)  # baselined on an earlier poll

        # First sight of a team in this process: baseline through the store. Anything the store
        # missed while we were down (or while the team was not followed) is recorded but never
        # fires. Tracked explicitly, not inferred from the previous board: a team followed
        # mid-game is already on that board.
        for t in team_scores(board, followed):
            key = (league, t.game_id, t.team_id)
            if key in known:
                continue
            self._baselined.add(key)
            u = self._store.apply_score(t.game_id, t.team_id, t.score)
            if u.increased:
                self._record(league, t.game_id, t.team_id, t.abbr, u.prev_score, t.score,
                             u.increase_n, now, "skipped_restart")

        for c in detect(prev, board, followed):
            if (league, c.game_id, c.team_id) not in known:
                continue
            u = self._store.apply_score(c.game_id, c.team_id, c.new)
            if u.increased:
                self._record(league, c.game_id, c.team_id, c.abbr, c.old, c.new,
                             u.increase_n, now, "pending")
        self._prev[league] = board

    def _record(self, league, game_id, team_id, abbr, old, new, n, now, status) -> None:
        delta = new - old
        event = Event(
            dedupe_key=dedupe_key(game_id, team_id, n), game_id=game_id, team_id=team_id,
            type="score", detected_at=now,
            due_at=now + timedelta(seconds=self._cfg.general.delay_s),
            detail={"old": old, "new": new, "delta": delta,
                    "label": score_label(league, delta), "abbr": abbr},
            status=status,
        )
        if not self._store.insert_event(event):
            return
        log.info("%s %s %d->%d (%s) [%s]", abbr, event.detail["label"], old, new,
                 event.dedupe_key, status)
        if status == "pending":
            self._dispatcher.schedule(event)

    async def run(self) -> None:
        next_sync = None
        while True:
            cfg = self._cfg.general  # re-read each round: edits apply without a restart
            try:
                now = self._now()
                if self._sync_requested or next_sync is None or now >= next_sync:
                    self._sync_requested = False
                    await self.sync_schedule()
                    next_sync = now + timedelta(hours=cfg.schedule_sync_hours)
                delay = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("watcher loop error")
                self.stats.errors += 1
                self.stats.last_error = "internal error; see log"
                delay = cfg.poll_break_s
            await self._nap(delay)

    async def _nap(self, delay: float) -> None:
        """Sleep, but wake early if a sync is requested."""
        if self._sync_requested:
            return
        self._wake.clear()
        waiter = asyncio.ensure_future(self._wake.wait())
        sleeper = asyncio.ensure_future(self._sleep(delay))
        try:
            await asyncio.wait({waiter, sleeper}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (waiter, sleeper):
                task.cancel()
            await asyncio.gather(waiter, sleeper, return_exceptions=True)
