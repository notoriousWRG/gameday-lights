from pathlib import Path

from app.paths import default_data_dir, resolve_config_path, resolve_data_dir

HOME = Path("/home/pat")


def test_os_defaults():
    assert default_data_dir("linux", {}, HOME) == HOME / ".local/share/gameday-lights"
    assert default_data_dir("linux", {"XDG_DATA_HOME": "/x/data"}, HOME) == Path(
        "/x/data/gameday-lights")
    assert default_data_dir("darwin", {}, HOME) == (
        HOME / "Library/Application Support/gameday-lights")
    assert default_data_dir("win32", {"LOCALAPPDATA": "/c/Local"}, HOME) == Path(
        "/c/Local/gameday-lights")
    assert default_data_dir("win32", {}, HOME) == HOME / "AppData/Local/gameday-lights"


def test_overrides_in_order(tmp_path):
    env = {"GAMEDAY_HOME": str(tmp_path / "env")}
    assert resolve_data_dir(None, "linux", env, HOME) == (tmp_path / "env").resolve()
    assert resolve_data_dir(str(tmp_path / "cli"), "linux", env, HOME) == (
        tmp_path / "cli").resolve()
    assert resolve_data_dir(None, "linux", {}, HOME) == default_data_dir("linux", {}, HOME)


def test_config_path_rules(tmp_path):
    data = tmp_path / "data"
    cwd = tmp_path / "checkout"
    cwd.mkdir()
    assert resolve_config_path(None, data, cwd) == data / "config.toml"  # nothing local
    (cwd / "config.toml").write_text("x")
    assert resolve_config_path(None, data, cwd) == cwd / "config.toml"  # dev checkout still works
    assert resolve_config_path(None, data, cwd, data_dir_chosen=True) == data / "config.toml"
    assert resolve_config_path("/etc/mine.toml", data, cwd) == Path("/etc/mine.toml")
