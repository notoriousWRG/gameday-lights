import gzip
import json
from pathlib import Path

import pytest

from app.espn.detect import detect, score_label, team_scores

FIX = Path(__file__).resolve().parent / "fixtures" / "nfl"


def board(gb=0, chi=0, state="in", game="g1", extra=None):
    ev = {
        "id": game,
        "status": {"type": {"state": state, "name": "STATUS_IN_PROGRESS"}},
        "competitions": [{"competitors": [
            {"score": str(gb), "team": {"id": "9", "abbreviation": "GB"}},
            {"score": str(chi), "team": {"id": "3", "abbreviation": "CHI"}},
        ]}],
    }
    return {"events": [ev] + (extra or [])}


def test_first_poll_is_baseline():
    assert detect(None, board(7, 3), {"9"}) == []


def test_td_then_pat_are_two_changes():
    a, b, c = board(0), board(6), board(7)
    c1 = detect(a, b, {"9"})
    c2 = detect(b, c, {"9"})
    assert [(x.old, x.new, x.delta) for x in c1 + c2] == [(0, 6, 6), (6, 7, 1)]


def test_only_followed_teams():
    changes = detect(board(0, 0), board(0, 7), {"9"})
    assert changes == []
    assert [c.abbr for c in detect(board(0, 0), board(0, 7), {"9", "3"})] == ["CHI"]


def test_decrease_reported_negative():
    (c,) = detect(board(6), board(0), {"9"})
    assert c.delta == -6


def test_no_change_and_new_game_baseline():
    assert detect(board(3), board(3), {"9"}) == []
    other = board(extra=None)["events"][0] | {"id": "g2"}
    curr = {"events": board(3)["events"] + [other | {"competitions": [{"competitors": [
        {"score": "14", "team": {"id": "9", "abbreviation": "GB"}}]}]}]}
    assert detect(board(3), curr, {"9"}) == []


def test_score_object_form():
    b = board()
    b["events"][0]["competitions"][0]["competitors"][0]["score"] = {"displayValue": "13"}
    assert team_scores(b, {"9"})[0].score == 13


def test_real_fixture_parses():
    path = next(FIX.glob("*/*.json.gz"))
    data = json.loads(gzip.open(path, "rt").read())
    scores = team_scores(data, {"4", "33"})  # whichever teams played: must not crash
    assert isinstance(scores, list)
    assert all(isinstance(s.score, int) for s in team_scores(data, {t["team"]["id"] for t in
        data["events"][0]["competitions"][0]["competitors"]}))


@pytest.mark.parametrize("delta,label", [(6, "TD"), (7, "TD+PAT"), (3, "FG"), (2, "safety/2pt"),
                                          (1, "PAT"), (5, "score")])
def test_labels(delta, label):
    assert score_label("nfl", delta) == label
    assert score_label("nhl", delta) == "score"
