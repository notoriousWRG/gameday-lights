"""Schedule-sync and game-watcher loops."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from app.config import Config
from app.dispatch.dispatcher import Dispatcher
from app.espn.client import EspnError
from app.espn.detect import detect, score_label, team_scores
from app.espn.schedule import merge_schedules, parse_schedule
from app.store import Event, Store, dedupe_key

log = logging.getLogger(__name__)

BREAK_STATUSES = {"STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_DELAYED", "STATUS_RAIN_DELAY"}
_ORDER = {"pre": 0, "in": 1, "post": 2}


class Watcher:
    def __init__(
        self,
        config: Config,
        store: Store,
        client,
        dispatcher: Dispatcher,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._cfg = config
        self._store = store
        self._client = client
        self._dispatcher = dispatcher
        self._now = now
        self._sleep = sleep
        self._followed: dict[str, set[str]] = {}
        for t in config.teams:
            self._followed.setdefault(t.league, set()).add(t.id)
        self._prev: dict[str, dict] = {}
        self._seen_status: dict[str, str] = {}  # game_id -> last status name logged

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
                if existing and _ORDER.get(existing.status, 0) > _ORDER.get(game.status, 0):
                    game = dataclasses.replace(game, status=existing.status)
                self._store.upsert_game(game)

    # polling
    async def poll_once(self) -> float:
        cfg = self._cfg.general
        now = self._now()
        windows = self._store.upcoming_games(now, timedelta(minutes=cfg.watch_lead_min))
        if not windows:
            return cfg.poll_break_s
        ids = {g.game_id for g in windows}
        for g in windows:
            if g.game_id not in self._seen_status:
                self._seen_status[g.game_id] = ""
                log.info("watching %s (kickoff %s UTC); polling started",
                         g.name, g.start_utc.strftime("%Y-%m-%d %H:%M"))
        live = False
        for league in {g.league for g in windows}:
            try:
                board = await self._client.scoreboard(league)
            except EspnError as e:
                log.warning("scoreboard failed for %s: %s", league, e)
                continue
            self._process(league, board, now)
            for event in board.get("events", []):
                if str(event["id"]) not in ids:
                    continue
                st = (event.get("status") or {}).get("type", {})
                self._log_status(str(event["id"]), st.get("name", ""))
                self._update_status(str(event["id"]), st.get("state", ""))
                if st.get("state") == "in" and st.get("name") not in BREAK_STATUSES:
                    live = True
        return cfg.poll_live_s if live else cfg.poll_break_s

    def _log_status(self, game_id: str, status_name: str) -> None:
        if status_name and self._seen_status.get(game_id) != status_name:
            self._seen_status[game_id] = status_name
            game = self._store.get_game(game_id)
            log.info("%s: %s", game.name if game else game_id, status_name)

    def _update_status(self, game_id: str, state: str) -> None:
        game = self._store.get_game(game_id)
        if game and state in _ORDER and _ORDER[state] > _ORDER.get(game.status, 0):
            self._store.upsert_game(dataclasses.replace(game, status=state))

    def _process(self, league: str, board: dict, now: datetime) -> None:
        followed = self._followed.get(league, set())
        prev = self._prev.get(league)
        known = {(t.game_id, t.team_id) for t in team_scores(prev, followed)} if prev else set()

        # First sight in this process: baseline through the store. Anything the store
        # missed while we were down is recorded but never fires.
        for t in team_scores(board, followed):
            if (t.game_id, t.team_id) in known:
                continue
            u = self._store.apply_score(t.game_id, t.team_id, t.score)
            if u.increased:
                self._record(league, t.game_id, t.team_id, t.abbr, u.prev_score, t.score,
                             u.increase_n, now, "skipped_restart")

        for c in detect(prev, board, followed):
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
        cfg = self._cfg.general
        next_sync = None
        while True:
            try:
                now = self._now()
                if next_sync is None or now >= next_sync:
                    await self.sync_schedule()
                    next_sync = now + timedelta(hours=cfg.schedule_sync_hours)
                delay = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("watcher loop error")
                delay = cfg.poll_break_s
            await self._sleep(delay)
