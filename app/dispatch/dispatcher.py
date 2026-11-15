"""Delay, per-bulb serial queue, snapshot/restore, status and fired_at logging."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.bulbs.base import (
    BulbAdapter,
    BulbState,
    Color,
    Pattern,
    SegmentPattern,
    capabilities_for,
)
from app.config import Config, TeamConfig
from app.effects import DEFAULT_COLORS, build_effect, build_pattern, resolve_effect
from app.store import Event, Store

log = logging.getLogger(__name__)

AnyPattern = Pattern | SegmentPattern
Planner = Callable[[Event], list[tuple[str, AnyPattern]]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _provider(config: Config | Callable[[], Config]) -> Callable[[], Config]:
    """A Config, or a function returning the current one (settings edits apply live)."""
    return config if callable(config) else (lambda: config)


def _fixture_pattern(
    config: Config, team: TeamConfig, bulb_name: str, espn: tuple[Color, Color]
) -> AnyPattern:
    """The pattern `team` plays on one fixture: its resolved effect, built for that fixture."""
    bulb = next((b for b in config.bulbs if b.name == bulb_name), None)
    caps = capabilities_for(bulb.kind, bulb.segments) if bulb else capabilities_for("wiz")
    resolved = resolve_effect(config, team, bulb_name, espn)
    return build_effect(resolved.spec, resolved.primary, resolved.alternate, caps, bulb_name)


def make_planner(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
    store: Store,
) -> Planner:
    """Event -> [(bulb name, pattern)], one entry per bulb of the team, from the current config
    plus ESPN team colors. A bulb whose effect cannot be built is logged and left out; the
    others still play."""
    current = _provider(config)

    def plan(event: Event) -> list[tuple[str, AnyPattern]]:
        config = current()
        game = store.get_game(event.game_id)
        if game is None:
            raise LookupError(f"unknown game {event.game_id}")
        for team in config.teams:
            if team.league == game.league and team.id == event.team_id:
                espn = team_colors.get((team.league, team.id), DEFAULT_COLORS)
                plans: list[tuple[str, AnyPattern]] = []
                for name in team.bulbs:
                    try:
                        plans.append((name, _fixture_pattern(config, team, name, espn)))
                    except ValueError as e:
                        log.error("no effect for %s on bulb %s: %s", event.dedupe_key, name, e)
                return plans
        raise LookupError(f"team {game.league}/{event.team_id} is not followed")

    return plan


def make_bulb_pulse(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
) -> Callable[[str], AnyPattern]:
    """Bulb name -> the pattern a pulse check plays: what the first team using it plays there
    (the same resolution a real event uses), else the default."""
    current = _provider(config)

    def pattern_for(bulb: str) -> AnyPattern:
        config = current()
        for team in config.teams:
            if bulb in team.bulbs:
                espn = team_colors.get((team.league, team.id), DEFAULT_COLORS)
                return _fixture_pattern(config, team, bulb, espn)
        return build_pattern(config.score_effect, *DEFAULT_COLORS)

    return pattern_for


def make_cell_pattern(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
) -> Callable[[str, str, str], AnyPattern]:
    """(league, team id, bulb) -> the pattern that team plays on that bulb: exactly what a real
    event would play there. KeyError if the team is not followed or does not use the bulb."""
    current = _provider(config)

    def pattern_for(league: str, team_id: str, bulb: str) -> AnyPattern:
        config = current()
        for team in config.teams:
            if (team.league, team.id) == (league, team_id) and bulb in team.bulbs:
                espn = team_colors.get((league, team_id), DEFAULT_COLORS)
                return _fixture_pattern(config, team, bulb, espn)
        raise KeyError(f"{league}/{team_id} on {bulb}")

    return pattern_for


def make_team_test(
    config: Config | Callable[[], Config],
    team_colors: dict[tuple[str, str], tuple[Color, Color]],
) -> Callable[..., AnyPattern]:
    """(league, team id, bulb, color, alt_color, espn colors) -> the pattern that team plays on
    that bulb, with the team colors as given (they may not be saved yet). Everything else is the
    saved resolution a real event uses; an unsaved team or bulb falls back to the defaults."""
    current = _provider(config)

    def pattern_for(
        league: str, team_id: str, bulb: str, color: Color | None, alt_color: Color | None,
        espn: tuple[Color, Color] | None = None,
    ) -> AnyPattern:
        config = current()
        saved = next((t for t in config.teams if (t.league, t.id) == (league, team_id)), None)
        team = dataclasses.replace(saved or TeamConfig(league, team_id, "", (bulb,)),
                                   color=color, alt_color=alt_color)
        return _fixture_pattern(
            config, team, bulb, espn or team_colors.get((league, team_id), DEFAULT_COLORS))

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

    async def play_now(self, bulb_name: str, pattern: AnyPattern) -> datetime:
        """Play a pattern on one bulb right now (a manual pulse check); returns its start time.

        Uses the same per-bulb queue and snapshot/restore as real events, so it never
        overlaps one. Not recorded as an event.
        """
        if bulb_name not in self._bulbs:
            raise KeyError(bulb_name)
        return await self._play(bulb_name, pattern)

    async def set_state(self, bulb_name: str, state: BulbState) -> datetime:
        """Set a bulb's steady light state (a manual change, not an effect) on its queue: it waits
        for any effect to finish and restore first, so it is never undone by one. Not an event."""
        if bulb_name not in self._bulbs:
            raise KeyError(bulb_name)
        async with self._locks[bulb_name]:
            started = self._now()
            await self._bulbs[bulb_name].set_state(state)
            return started

    async def current_state(self, bulb_name: str) -> BulbState:
        if bulb_name not in self._bulbs:
            raise KeyError(bulb_name)
        async with self._locks[bulb_name]:
            return await self._bulbs[bulb_name].current_state()

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
            plan = self._planner(event)
            if not plan:
                self._store.mark_event(event.dedupe_key, "no_lights")
                log.info("event %s: the team has no lights, nothing to play", event.dedupe_key)
                return
            names = [n for n, _ in plan]
            results = await asyncio.gather(
                *(self._play(n, pattern) for n, pattern in plan), return_exceptions=True
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

    async def _play(self, name: str, pattern: AnyPattern) -> datetime:
        bulb = self._bulbs[name]
        async with self._locks[name]:
            started = self._now()
            snap = await bulb.snapshot()
            try:
                await bulb.play(pattern)
            finally:
                await bulb.restore(snap)
            return started
