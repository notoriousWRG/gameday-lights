"""Pure parsing of ESPN schedule and team JSON."""

from __future__ import annotations

from datetime import UTC, datetime

from app.bulbs.base import Color
from app.effects import parse_color
from app.espn.detect import parse_score
from app.store import Game


def _start(date: str) -> datetime:
    dt = datetime.fromisoformat(date)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def game_teams_and_scores(competition: dict) -> dict:
    """Game fields for home/away abbreviations and scores from an ESPN competition."""
    out: dict = {}
    for c in competition.get("competitors", []):
        side = c.get("homeAway")
        if side in ("home", "away"):
            out[f"{side}_abbr"] = (c.get("team") or {}).get("abbreviation")
            out[f"{side}_score"] = parse_score(c.get("score"))
    return out


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
            **game_teams_and_scores(comp),
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


def _record(competitor: dict) -> str | None:
    for r in competitor.get("records") or []:
        if r.get("name") == "overall" or r.get("type") == "total":
            return r.get("summary")
    return None


def _situation(comp: dict, abbr_by_id: dict[str, str]) -> dict | None:
    """Down/distance and possession for a live game. Read defensively: ESPN only sends it live."""
    sit = comp.get("situation")
    if not isinstance(sit, dict):
        return None
    text = sit.get("downDistanceText") or sit.get("shortDownDistanceText")
    possession = sit.get("possession")
    poss_abbr = abbr_by_id.get(str(possession)) if possession is not None else None
    if not (text or poss_abbr or sit.get("possessionText")):
        return None
    return {
        "text": text,
        "possession": poss_abbr,
        "possession_text": sit.get("possessionText"),
        "red_zone": bool(sit.get("isRedZone")),
    }


def parse_scoreboard_game(event: dict) -> dict:
    """Everything a scoreboard needs from one ESPN scoreboard event; missing -> None."""
    comp = (event.get("competitions") or [{}])[0]
    status = event.get("status") or comp.get("status") or {}
    stype = status.get("type") or {}
    sides: dict[str, dict] = {}
    abbr_by_id: dict[str, str] = {}
    for c in comp.get("competitors", []):
        team = c.get("team") or {}
        if team.get("id") is not None and team.get("abbreviation"):
            abbr_by_id[str(team["id"])] = team["abbreviation"]
        side = c.get("homeAway")
        if side in ("home", "away"):
            sides[side] = {
                "abbr": team.get("abbreviation"),
                "name": team.get("shortDisplayName") or team.get("displayName"),
                "score": parse_score(c.get("score")),
                "record": _record(c),
                "linescores": [parse_score(ls) for ls in c.get("linescores") or []],
            }
    empty = {"abbr": None, "name": None, "score": None, "record": None, "linescores": []}
    venue = comp.get("venue") or {}
    return {
        "game_id": str(event.get("id", "")),
        "name": event.get("shortName") or event.get("name") or "",
        "state": stype.get("state", ""),
        "status_name": stype.get("name", ""),
        "detail": stype.get("shortDetail") or stype.get("detail"),
        "clock": status.get("displayClock"),
        "period": status.get("period"),
        "home": sides.get("home", empty),
        "away": sides.get("away", empty),
        "broadcast": comp.get("broadcast") or None,
        "venue": venue.get("fullName"),
        "situation": _situation(comp, abbr_by_id),
    }
