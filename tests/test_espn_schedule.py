import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.espn.schedule import merge_schedules, parse_schedule, parse_team_colors
from app.store import Game

FIX = Path(__file__).resolve().parent / "fixtures" / "nfl_schedule"


def load(name):
    return json.loads((FIX / name).read_text())


def test_real_schedule_parses():
    data = load("gb_regular.json")
    games = parse_schedule(data, "nfl")
    skipped = sum(1 for e in data["events"] if not e["competitions"][0]["timeValid"])
    assert len(games) == len(data["events"]) - skipped
    first = games[0]
    assert first.game_id == "401872927"
    assert first.name == "GB @ MIN"
    assert first.start_utc == datetime(2026, 9, 13, 20, 25, tzinfo=UTC)
    assert first.status == "post" and first.league == "nfl"
    assert games == sorted(games, key=lambda g: g.start_utc)


def test_placeholder_time_skipped():
    data = load("gb_regular.json")
    ids = {g.game_id for g in parse_schedule(data, "nfl")}
    assert "401873176" not in ids  # week 18 "TBD"


def test_empty_postseason():
    assert parse_schedule(load("gb_post_empty.json"), "nfl") == []


def test_merge_dedupes_later_wins():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    a = [Game("1", "nfl", "x", t, "pre")]
    b = [Game("1", "nfl", "x", t, "in"), Game("2", "nfl", "y", t, "pre")]
    merged = merge_schedules(a, b)
    assert {g.game_id: g.status for g in merged} == {"1": "in", "2": "pre"}


def test_team_colors():
    primary, alt = parse_team_colors(load("gb_team.json"))
    assert primary == (0x20, 0x4E, 0x32)
    assert alt == (0xFF, 0xB6, 0x12)


def test_team_colors_missing():
    with pytest.raises(ValueError, match="alternateColor"):
        parse_team_colors({"team": {"color": "000000"}})
