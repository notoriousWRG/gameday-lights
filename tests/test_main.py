import gzip
import json
import re
from types import SimpleNamespace

import pytest

from app import main as app_main
from app.main import main

CONFIG = """
[general]
dispatch_enabled = true
db_path = "gl.db"
delay_s = 45
[[bulbs]]
name = "lamp"
ip = "10.0.0.5"
[[teams]]
league = "nfl"
id = "9"
abbr = "GB"
bulbs = ["lamp"]
color = "#00FF00"
alt_color = "#FFB612"
"""


def board(gb, state="in", name="STATUS_IN_PROGRESS"):
    return {"events": [{
        "id": "g1", "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
        "status": {"type": {"state": state, "name": name}},
        "competitions": [{"competitors": [
            {"score": str(gb), "team": {"id": "9", "abbreviation": "GB"}},
            {"score": "0", "team": {"id": "17", "abbreviation": "NE"}},
        ]}],
    }]}


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)
    frames = tmp_path / "frames"
    frames.mkdir()
    seq = [board(0), board(6), board(7), board(7, "post", "STATUS_FINAL")]
    for i, b in enumerate(seq, 1):
        with gzip.open(frames / f"{i:04d}_x.json.gz", "wt") as f:
            json.dump(b, f)
    return SimpleNamespace(cfg=str(cfg), frames=str(frames), tmp=tmp_path)


def test_replay_end_to_end(env, capsys):
    rc = main(["--config", env.cfg, "run", "--replay", env.frames, "--speed", "100000", "--fresh"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "g1:9:1" in out and "g1:9:2" in out and "g1:9:3" not in out
    assert out.count("dry_run") == 2
    gaps = [int(g) for g in re.findall(r"fired (\d+)s after detection", out)]
    assert len(gaps) == 2 and all(g >= 45 for g in gaps)  # never earlier than the delay
    assert (env.tmp / "gl.replay.db").exists() and not (env.tmp / "gl.db").exists()


def test_replay_restart_does_not_duplicate(env, capsys):
    args = ["--config", env.cfg, "run", "--replay", env.frames, "--speed", "100000"]
    main([*args, "--fresh"])
    capsys.readouterr()
    main(args)
    out = capsys.readouterr().out
    assert out.count("g1:9:") == 2 and "skipped_restart" not in out


def test_config_error_returns_2(env, capsys):
    (env.tmp / "config.toml").write_text("[general]\n")
    assert main(["--config", env.cfg, "run", "--dry-run"]) == 2
    assert "dispatch_enabled" in capsys.readouterr().err


def test_missing_config_returns_2(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "nope.toml"), "run"]) == 2
    assert "not found" in capsys.readouterr().err


def test_replay_missing_dir_returns_2(env, capsys):
    assert main(["--config", env.cfg, "run", "--replay", str(env.tmp / "empty")]) == 2


def test_test_effect_dry_run(env, capsys):
    assert main(["--config", env.cfg, "test-effect", "score", "--team", "gb", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "GB: 10 steps over 6.0s on lamp (dry-run)" in out and "Done." in out


def test_test_effect_unknown_team(env, capsys):
    assert main(["--config", env.cfg, "test-effect", "score", "--team", "XYZ"]) == 2


def test_discover(monkeypatch, capsys):
    async def fake(broadcast_space, wait_time):
        return [SimpleNamespace(ip="1.2.3.4", mac="aabbccddeeff")]

    monkeypatch.setattr("pywizlight.discovery.discover_lights", fake)
    assert main(["discover"]) == 0
    assert "1.2.3.4  mac aabbccddeeff" in capsys.readouterr().out


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    assert "test-effect" in capsys.readouterr().out


async def test_make_bulbs_dry_vs_real():
    from app.config import load_config

    cfg = load_config(app_main.__file__.replace("app/main.py", "config.example.toml"))
    assert type(app_main.make_bulbs(cfg, True)["living-room"]).__name__ == "DryRunBulb"
    assert type(app_main.make_bulbs(cfg, False)["living-room"]).__name__ == "WizBulb"
