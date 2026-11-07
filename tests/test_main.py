import asyncio
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


async def test_run_tasks_waits_for_children_to_finish_cleanup_on_cancel():
    import asyncio

    log = []

    async def child(name, cleanup_s):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await asyncio.sleep(cleanup_s)  # slow graceful shutdown
            log.append(name)
            raise

    runner = asyncio.ensure_future(app_main.run_tasks([
        asyncio.ensure_future(child("fast", 0)), asyncio.ensure_future(child("slow", 0.2))]))
    await asyncio.sleep(0.05)
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass
    assert sorted(log) == ["fast", "slow"]  # nothing abandoned mid-cleanup


# --- stored settings, live apply, config export/import ----------------------------------------

def stored(env):
    """Open the settings the way `run` does (seeding from config.toml on first use)."""
    return app_main.open_settings(env.cfg)


def test_first_start_seeds_the_database_and_later_toml_edits_are_reported_not_applied(env, caplog):
    service, store = stored(env)
    assert [t.abbr for t in service.config.teams] == ["GB"]
    store.close()
    (env.tmp / "config.toml").write_text(CONFIG.replace('abbr = "GB"', 'abbr = "NE"'))
    caplog.set_level("WARNING", logger="gameday-lights")
    service, store = stored(env)
    assert [t.abbr for t in service.config.teams] == ["GB"]  # the stored settings win
    assert "differs from the stored settings for: teams" in caplog.text
    assert "config import --force" in caplog.text
    store.close()


def test_config_export_prints_toml_that_loads_back_to_the_stored_settings(env, capsys):
    from app.config import load_config

    assert main(["--config", env.cfg, "config", "export"]) == 0
    out = capsys.readouterr().out
    exported = env.tmp / "exported.toml"
    exported.write_text(out)
    service, store = stored(env)
    assert load_config(exported) == service.config
    store.close()


def test_config_export_no_secrets_and_the_secret_warning(env, capsys):
    service, store = stored(env)
    bulbs = [dict(b, signing_key="s3cret") for b in service.sections()["bulbs"][1]]
    service.update("bulbs", bulbs, 1)
    store.close()
    assert main(["--config", env.cfg, "config", "export"]) == 0
    captured = capsys.readouterr()
    assert "s3cret" in captured.out and "contains bulb signing keys" in captured.err
    assert main(["--config", env.cfg, "config", "export", "--no-secrets"]) == 0
    assert "s3cret" not in capsys.readouterr().out


def test_config_import_requires_force_and_then_replaces_stored_settings(env, capsys):
    service, store = stored(env)
    service.update("household", {"delay_s": 99}, 1)
    store.close()
    assert main(["--config", env.cfg, "config", "import"]) == 2
    assert "pass --force" in capsys.readouterr().err
    service, store = stored(env)
    assert service.config.general.delay_s == 99  # nothing was overwritten
    store.close()
    assert main(["--config", env.cfg, "config", "import", "--force"]) == 0
    assert "imported: household" in capsys.readouterr().out
    service, store = stored(env)
    assert service.config.general.delay_s == 45
    store.close()


def test_test_effect_uses_stored_settings_including_teams_only_added_through_the_ui(env, capsys):
    service, store = stored(env)
    teams = [*service.sections()["teams"][1], {"league": "nfl", "id": "17", "abbr": "NE",
                                                "bulbs": ["lamp"], "color": "#1f4fd8",
                                                "alt_color": None}]
    service.update("teams", teams, 1)
    store.close()
    assert "NE" not in (env.tmp / "config.toml").read_text()  # not in the file
    assert main(["--config", env.cfg, "test-effect", "score", "--team", "NE", "--dry-run"]) == 0
    assert "NE: 10 steps over 6.0s on lamp (dry-run)" in capsys.readouterr().out


def test_reconcile_bulbs_keeps_unchanged_adapters_and_replaces_changed_ones():
    from dataclasses import replace

    from app.config import BulbConfig, Config, GeneralConfig
    from app.effects import EffectConfig

    def cfg(*bulbs):
        return Config(GeneralConfig(False, "x.db"), tuple(bulbs), (), EffectConfig())

    a, b = BulbConfig("a", "1.1.1.1"), BulbConfig("b", "2.2.2.2")
    old = cfg(a, b)
    existing = app_main.make_bulbs(old, dry=True)
    moved_b = replace(b, ip="2.2.2.9")  # b's IP changed; c is new; a untouched
    c = BulbConfig("c", "3.3.3.3")
    out = app_main.reconcile_bulbs(existing, old, cfg(a, moved_b, c), dry=True)
    assert list(out) == ["a", "b", "c"]
    assert out["a"] is existing["a"]  # unchanged: same adapter, same queue
    assert out["b"] is not existing["b"]  # changed: a fresh adapter
    assert "c" not in existing and out["c"].name == "c"  # new: created
    assert list(app_main.reconcile_bulbs(existing, old, cfg(b), dry=True)) == ["b"]  # a removed


async def test_live_apply_pushes_settings_edits_into_the_running_components(env):
    from app.dispatch.dispatcher import Dispatcher, make_planner
    from app.watcher import Watcher

    service, store = stored(env)
    colors, tasks = {}, set()
    queried = []

    class FakeClient:
        async def team(self, league, team_id):
            queried.append(team_id)
            return {"team": {"color": "1f4fd8", "alternateColor": "ffffff"}}

        async def team_schedule(self, *a, **k):
            return {"events": []}

    cfg = service.config
    dispatcher = Dispatcher(store, app_main.make_bulbs(cfg, True),
                            make_planner(lambda: service.config, colors, store), dry_run=True)
    watcher = Watcher(lambda: service.config, store, FakeClient(), dispatcher, app_main.utc_now)
    service.subscribe(app_main.make_live_apply(watcher, dispatcher, colors, FakeClient(), True,
                                               tasks))
    lamp = dispatcher.bulbs["lamp"]

    bulbs = [*service.sections()["bulbs"][1], {"name": "den", "ip": "10.0.0.9", "mac": None,
                                               "port": 38899, "signing_key": None}]
    service.update("bulbs", bulbs, 1)
    assert set(dispatcher.bulbs) == {"lamp", "den"} and dispatcher.bulbs["lamp"] is lamp

    teams = [*service.sections()["teams"][1], {"league": "nfl", "id": "17", "abbr": "NE",
                                                "bulbs": ["den"], "color": None, "alt_color": None}]
    service.update("teams", teams, 1)
    assert watcher._sync_requested is True  # a followed team triggers a schedule sync
    await asyncio.gather(*tasks)
    assert queried == ["9", "17"] and ("nfl", "17") in colors  # ESPN colors for the new team

    watcher._sync_requested = False
    service.update("household", {"delay_s": 20}, 1)  # a delay edit needs neither
    assert watcher._sync_requested is False and service.config.general.delay_s == 20
    store.close()
