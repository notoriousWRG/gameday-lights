import socket
from dataclasses import replace

import pytest

from app.config import BulbConfig, ConfigError, load_config
from app.doctor import (
    FAIL,
    PASS,
    WARN,
    check_bulbs,
    check_config,
    check_data_dir,
    check_espn,
    check_port,
    firewall_hint,
)
from app.main import STARTER, main
from tests.support import cfg


def test_starter_file_is_a_valid_config(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(STARTER.read_text(encoding="utf-8"))
    c = load_config(f)
    assert c.bulbs == () and c.teams == () and c.web.host == "127.0.0.1"
    assert c.general.db_path == tmp_path / "gameday-lights.db"  # relative to the file's folder


def test_init_creates_once_and_never_overwrites(tmp_path, capsys):
    data = tmp_path / "data"
    assert main(["--data-dir", str(data), "init"]) == 0
    f = data / "config.toml"
    assert f.is_file() and "http://127.0.0.1:8787/" in capsys.readouterr().out
    f.write_text(f.read_text() + "\n# my edit\n")
    assert main(["--data-dir", str(data), "init"]) == 0
    assert "# my edit" in f.read_text()
    assert "left untouched" in capsys.readouterr().out


def test_gameday_home_env_chooses_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMEDAY_HOME", str(tmp_path / "home"))
    assert main(["init"]) == 0
    assert (tmp_path / "home" / "config.toml").is_file()


def test_run_without_a_settings_file_points_at_init(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path / "nothing"), "run"]) == 2
    assert "gameday-lights init" in capsys.readouterr().err


def test_check_config_missing_and_broken(tmp_path):
    c, loaded = check_config(tmp_path / "nope.toml")
    assert c.status == FAIL and "init" in c.detail and loaded is None
    bad = tmp_path / "bad.toml"
    bad.write_text("[general]\n")
    c, loaded = check_config(bad)
    assert c.status == FAIL and loaded is None


def test_data_dir_writable_and_not(tmp_path):
    assert check_data_dir(tmp_path / "new" / "dir").status == PASS
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert check_data_dir(blocker / "sub").status == FAIL


def test_port_free_and_in_use():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen()
        assert check_port("127.0.0.1", port).status == WARN
    assert check_port("127.0.0.1", port).status == PASS


async def test_espn_check():
    async def ok():
        return {}

    async def boom():
        raise RuntimeError("timed out")

    assert (await check_espn(ok)).status == PASS
    c = await check_espn(boom)
    assert c.status == FAIL and "timed out" in c.detail


class Bulb:
    def __init__(self, answer):
        self.answer = answer

    async def ping(self):
        return self.answer


def with_bulbs(*bulbs):
    return replace(cfg(), bulbs=bulbs)


async def test_bulbs_that_answer_skip_the_search():
    searched = []

    async def discover():
        searched.append(1)
        return []

    config = with_bulbs(BulbConfig("lamp", "10.0.0.5"))
    out = await check_bulbs(config, lambda b: b.ping(), lambda b: Bulb(0.012), discover)
    assert [c.status for c in out] == [PASS] and "12 ms" in out[0].detail and not searched


async def test_silent_bulb_and_empty_search_give_the_os_hint():
    async def none():
        return []

    config = with_bulbs(BulbConfig("lamp", "10.0.0.5"))
    out = await check_bulbs(config, lambda b: b.ping(), lambda b: Bulb(None), none, "win32")
    assert [c.status for c in out] == [FAIL, WARN]
    assert "Private" in out[1].detail and out[1].detail.endswith(firewall_hint("win32"))


async def test_no_saved_bulbs_but_discovery_finds_one():
    async def found():
        return [{"ip": "10.0.0.9", "kind": "wiz"}]

    out = await check_bulbs(with_bulbs(), lambda b: b.ping(), lambda b: Bulb(0), found)
    assert [c.status for c in out] == [PASS] and "10.0.0.9" in out[0].detail


def test_firewall_hints_differ_per_os():
    assert "Windows Firewall" in firewall_hint("win32")
    assert "Local Network" in firewall_hint("darwin")
    assert "UDP" in firewall_hint("linux")


def test_load_config_error_type():
    with pytest.raises(ConfigError):
        load_config("/definitely/not/here.toml")
