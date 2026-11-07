"""Delay, per-bulb serial queue, snapshot/restore, status and fired_at logging."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.bulbs.base import BulbAdapter, Color, Pattern
from app.config import Config, TeamConfig
from app.effects import build_pattern
from app.store import Event, Store

log = logging.getLogger(__name__)

Planner = Callable[[Event], tuple[Pattern, list[str]]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_pattern(
    config: Config, team: TeamConfig, primary: Color, alternate: Color
) -> Pattern:
    """Score pattern for a team: its config colors override the given (ESPN) ones."""
    effect = config.score_effect
    if team.color or team.alt_color:
        effect = dataclasses.replace(
            effect, color=team.color or effect.color, alt_color=team.alt_color or effect.alt_color
        )
    return build_pattern(effect, primary, alternate)


def _provider(config: Config | Callable[[], Config]) -> Callable[[], Config]:
    """A Config, or a function returning the current one (settings edits apply live)."""
    return config if callable(config) else (lambda: config)


def make_planner(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
    store: Store,
) -> Planner:
    """Event -> (pattern, bulb names), from the current config plus ESPN team colors."""
    current = _provider(config)

    def plan(event: Event) -> tuple[Pattern, list[str]]:
        config = current()
        game = store.get_game(event.game_id)
        if game is None:
            raise LookupError(f"unknown game {event.game_id}")
        for team in config.teams:
            if team.league == game.league and team.id == event.team_id:
                primary, alternate = team_colors.get(
                    (team.league, team.id), ((0, 255, 0), (255, 255, 255))
                )
                return resolve_pattern(config, team, primary, alternate), list(team.bulbs)
        raise LookupError(f"team {game.league}/{event.team_id} is not followed")

    return plan


def make_bulb_pulse(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
) -> Callable[[str], Pattern]:
    """Bulb name -> the pattern a pulse check plays: the first team using it, else the default."""
    current = _provider(config)

    def pattern_for(bulb: str) -> Pattern:
        config = current()
        for team in config.teams:
            if bulb in team.bulbs:
                primary, alternate = team_colors.get(
                    (team.league, team.id), ((0, 255, 0), (255, 255, 255))
                )
                return resolve_pattern(config, team, primary, alternate)
        return build_pattern(config.score_effect, (0, 255, 0), (255, 255, 255))

    return pattern_for


def make_team_pulse(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
) -> Callable[..., Pattern]:
    """(league, team id, color, alt_color, espn colors) -> the pattern that team's score would play,
    for colors that may not be saved yet. Precedence is the real one: the team's own colors, then
    the effect's, then ESPN's (the given ones, else those already loaded, else green and white)."""
    current = _provider(config)

    def pattern_for(
        league: str, team_id: str, color: Color | None, alt_color: Color | None,
        espn: tuple[Color, Color] | None = None,
    ) -> Pattern:
        primary, alternate = espn or team_colors.get(
            (league, team_id), ((0, 255, 0), (255, 255, 255))
        )
        team = TeamConfig(league, team_id, "", (), color, alt_color)
        return resolve_pattern(current(), team, primary, alternate)

    return pattern_for


class Dispatcher:
    def __init__(
        self,
        store: Store,
        bulbs: dict[str, BulbAdapter],
        planner: Planner,
        now: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        dry_run: bool = False,
    ) -> None:
        self._store = store
        self._bulbs = dict(bulbs)
        self._planner = planner
        self._now = now
        self._sleep = sleep
        self._dry_run = dry_run
        self._locks = {name: asyncio.Lock() for name in bulbs}
        self._tasks: set[asyncio.Task] = set()

    @property
    def bulbs(self) -> dict[str, BulbAdapter]:
        return self._bulbs

    def set_bulbs(self, bulbs: dict[str, BulbAdapter]) -> None:
        """Swap the bulb registry (settings changed). A bulb that stays keeps its lock, so its
        serial queue is unbroken; effects already playing finish on the adapter they began on."""
        self._locks = {
            name: self._locks[name]
            if name in self._locks and self._bulbs.get(name) is adapter else asyncio.Lock()
            for name, adapter in bulbs.items()
        }
        self._bulbs = dict(bulbs)

    def schedule(self, event: Event) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(self._run(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def play_now(self, bulb_name: str, pattern: Pattern) -> datetime:
        """Play a pattern on one bulb right now (a manual pulse check); returns its start time.

        Uses the same per-bulb queue and snapshot/restore as real events, so it never
        overlaps one. Not recorded as an event.
        """
        if bulb_name not in self._bulbs:
            raise KeyError(bulb_name)
        return await self._play(bulb_name, pattern)

    def recover(self) -> None:
        """After a restart: past-due pending events never fire; future ones do."""
        now = self._now()
        for event in self._store.pending_events():
            if event.due_at <= now:
                self._store.mark_event(event.dedupe_key, "skipped_restart")
            else:
                self.schedule(event)

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _run(self, event: Event) -> None:
        wait = (event.due_at - self._now()).total_seconds()
        if wait > 0:
            await self._sleep(wait)
        try:
            pattern, names = self._planner(event)
            results = await asyncio.gather(
                *(self._play(n, pattern) for n in names), return_exceptions=True
            )
        except Exception:
            log.exception("could not plan event %s", event.dedupe_key)
            self._store.mark_event(event.dedupe_key, "failed")
            return
        started = [r for r in results if isinstance(r, datetime)]
        for name, r in zip(names, results, strict=True):
            if isinstance(r, BaseException):
                log.error("event %s failed on bulb %s: %r", event.dedupe_key, name, r)
        if started:
            status = "dry_run" if self._dry_run else "fired"
            self._store.mark_event(event.dedupe_key, status, min(started))
            log.info("event %s %s (detected %s)", event.dedupe_key, status, event.detected_at)
        else:
            self._store.mark_event(event.dedupe_key, "failed")

    async def _play(self, name: str, pattern: Pattern) -> datetime:
        bulb = self._bulbs[name]
        async with self._locks[name]:
            started = self._now()
            snap = await bulb.snapshot()
            try:
                await bulb.flash(pattern)
            finally:
                await bulb.restore(snap)
            return started
