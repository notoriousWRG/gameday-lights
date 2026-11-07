"""Pure parsing of ESPN schedule and team JSON."""

from __future__ import annotations

from datetime import UTC, datetime

from app.bulbs.base import Color
from app.effects import parse_color
from app.store import Game


def _start(date: str) -> datetime:
    dt = datetime.fromisoformat(date)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def parse_schedule(data: dict, league: str) -> list[Game]:
    games: list[Game] = []
    for event in data.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        if not comp.get("timeValid", event.get("timeValid", True)):
            continue  # placeholder kickoff; ESPN fills in a real time later
        state = comp.get("status", {}).get("type", {}).get("state", "pre")
        games.append(Game(
            game_id=str(event["id"]),
            league=league,
            name=event.get("shortName") or event.get("name", ""),
            start_utc=_start(event["date"]),
            status=state,
        ))
    return sorted(games, key=lambda g: g.start_utc)


def merge_schedules(*lists: list[Game]) -> list[Game]:
    by_id: dict[str, Game] = {}
    for games in lists:
        for g in games:
            by_id[g.game_id] = g
    return sorted(by_id.values(), key=lambda g: g.start_utc)


def parse_team_colors(team_data: dict) -> tuple[Color, Color]:
    """(primary, alternate) from ESPN's hex `color` and `alternateColor`."""
    team = team_data.get("team", team_data)
    try:
        return parse_color(team["color"]), parse_color(team["alternateColor"])
    except KeyError as e:
        raise ValueError(f"team data has no {e.args[0]}") from None
