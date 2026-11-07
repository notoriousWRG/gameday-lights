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


def test_real_schedule_has_teams_and_final_scores():
    games = {g.game_id: g for g in parse_schedule(load("gb_regular.json"), "nfl")}
    g = games["401872927"]  # GB @ MIN, final 22-39
    assert (g.home_abbr, g.home_score, g.away_abbr, g.away_score) == ("MIN", 39, "GB", 22)
    ot = games["401872936"]  # GB @ NYJ, final/OT 20-17
    assert (ot.home_abbr, ot.home_score, ot.away_abbr, ot.away_score) == ("NYJ", 17, "GB", 20)


def test_unplayed_game_has_teams_but_no_scores():
    upcoming = [g for g in parse_schedule(load("gb_regular.json"), "nfl") if g.status == "pre"][0]
    assert upcoming.home_abbr and upcoming.away_abbr
    assert upcoming.home_score is None and upcoming.away_score is None


def test_parse_score_forms():
    from app.espn.detect import parse_score

    assert parse_score("14") == 14 and parse_score(14) == 14 and parse_score(0) == 0
    assert parse_score({"displayValue": "7", "value": 7.0}) == 7
    assert parse_score(None) is None and parse_score("") is None and parse_score("x") is None


def _fixture_event():
    import glob
    import gzip

    path = sorted(glob.glob(str(FIX.parent / "nfl" / "*" / "*.json.gz")))[0]
    return json.loads(gzip.open(path, "rt").read())["events"][0]


def test_parse_scoreboard_game_from_real_final():
    from app.espn.schedule import parse_scoreboard_game

    g = parse_scoreboard_game(_fixture_event())
    assert g["state"] == "post" and g["detail"] == "Final" and g["period"] == 4
    assert (g["home"]["abbr"], g["home"]["score"], g["home"]["record"]) == ("BAL", 10, "4-5")
    assert (g["away"]["abbr"], g["away"]["score"], g["away"]["record"]) == ("JAX", 33, "6-2")
    assert g["away"]["linescores"] == [10, 7, 3, 13] and g["home"]["linescores"] == [3, 0, 0, 7]
    assert g["broadcast"] == "Prime Video" and g["venue"] == "M&T Bank Stadium"
    assert g["situation"] is None and g["name"] == "JAX @ BAL"


def test_parse_scoreboard_game_tolerates_sparse_events():
    from app.espn.schedule import parse_scoreboard_game

    g = parse_scoreboard_game({"id": 7})
    assert g["game_id"] == "7" and g["home"]["score"] is None and g["away"]["linescores"] == []
    assert g["situation"] is None and g["detail"] is None and g["venue"] is None


def test_parse_scoreboard_game_live_situation():
    from app.espn.schedule import parse_scoreboard_game

    event = {
        "id": "1", "shortName": "GB @ NE",
        "status": {"displayClock": "4:21", "period": 3,
                   "type": {"state": "in", "name": "STATUS_IN_PROGRESS",
                            "shortDetail": "4:21 - 3rd"}},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "10", "team": {"id": "17", "abbreviation": "NE"}},
                {"homeAway": "away", "score": "14", "team": {"id": "9", "abbreviation": "GB"}},
            ],
            "situation": {"downDistanceText": "2nd & 7 at NE 35", "possession": "9",
                          "isRedZone": True},
        }],
    }
    g = parse_scoreboard_game(event)
    assert (g["clock"], g["period"], g["detail"]) == ("4:21", 3, "4:21 - 3rd")
    assert g["situation"] == {"text": "2nd & 7 at NE 35", "possession": "GB",
                              "possession_text": None, "red_zone": True}
    event["competitions"][0]["situation"] = {"lastPlay": {"x": 1}}  # unknown shape -> ignored
    assert parse_scoreboard_game(event)["situation"] is None
