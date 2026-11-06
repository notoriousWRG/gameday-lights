import importlib.util
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_scoreboard.py"
spec = importlib.util.spec_from_file_location("probe_scoreboard", SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_scoreboard"] = probe
spec.loader.exec_module(probe)


def board(gb=0, chi=0, state="in", name="STATUS_IN_PROGRESS"):
    return {"events": [{
        "id": "401",
        "status": {"type": {"state": state, "name": name}},
        "competitions": [{"competitors": [
            {"score": str(gb), "team": {"abbreviation": "GB"}},
            {"score": str(chi), "team": {"abbreviation": "CHI"}},
        ]}],
    }]}


def test_find_game_and_scores():
    ev = probe.find_game(board(7, 3), "gb")
    assert ev["id"] == "401"
    assert probe.scores(ev) == {"GB": 7, "CHI": 3}
    assert probe.find_game(board(), "MIN") is None


def test_diff_scores():
    assert probe.diff_scores(None, {"GB": 0}) == []
    assert probe.diff_scores({"GB": 0, "CHI": 3}, {"GB": 6, "CHI": 3}) == [("GB", 0, 6)]
    assert probe.diff_scores({"GB": 7}, {"GB": 6}) == [("GB", 7, 6)]


def test_content_hash_stable_and_sensitive():
    assert probe.content_hash({"a": 1, "b": 2}) == probe.content_hash({"b": 2, "a": 1})
    assert probe.content_hash({"a": 1}) != probe.content_hash({"a": 2})


def test_pair_press_latest_unpaired():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    a = probe.Change(t0, "GB", 0, 6)
    b = probe.Change(t0 + timedelta(seconds=30), "GB", 6, 7)
    changes = [a, b]
    assert probe.pair_press(changes, t0 + timedelta(seconds=75)) is b
    assert b.lag_s == 45
    assert probe.pair_press(changes, t0 + timedelta(seconds=80)) is a
    assert probe.pair_press(changes, t0 + timedelta(seconds=90)) is None
    assert "2 paired" in probe.lag_summary(changes)


def test_save_fixture_roundtrip(tmp_path, monkeypatch):
    import gzip
    import json

    monkeypatch.setattr(probe, "FIXTURE_ROOT", tmp_path)
    p = probe.save_fixture(board(), "nfl", "401", 1, datetime(2026, 1, 1, tzinfo=UTC))
    assert p.name.startswith("0001_")
    assert json.load(gzip.open(p, "rt"))["events"][0]["id"] == "401"


def test_cli_rejects_fast_interval():
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--team", "GB", "--interval", "5"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "interval" in r.stderr


def test_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0


@pytest.mark.parametrize("n", [1])
def test_pair_without_changes(n):
    assert probe.pair_press([], datetime.now(UTC)) is None
