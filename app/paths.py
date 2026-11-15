"""Where an installed copy keeps its settings file and database. An install has no checkout to
live in, so each OS gets its usual per-user data folder. Everything is passed in (platform,
environment, home, working directory) so every OS can be tested from any OS."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_DIR = "gameday-lights"
HOME_ENV = "GAMEDAY_HOME"
CONFIG_NAME = "config.toml"


def default_data_dir(
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path:
    home = home or Path.home()
    if platform == "win32":
        base = env.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_DIR
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR
    base = env.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / APP_DIR


def resolve_data_dir(
    cli: str | None = None,
    platform: str = sys.platform,
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path:
    """`--data-dir`, then GAMEDAY_HOME, then the OS default."""
    if cli:
        return Path(cli).expanduser().resolve()
    if env.get(HOME_ENV):
        return Path(env[HOME_ENV]).expanduser().resolve()
    return default_data_dir(platform, env, home)


def resolve_config_path(
    cli_config: str | None,
    data_dir: Path,
    cwd: Path | None = None,
    data_dir_chosen: bool = False,
) -> Path:
    """`--config` wins. Otherwise a config.toml in the working directory keeps working (the
    development checkout), unless the data dir was chosen explicitly; then the data dir's file."""
    if cli_config:
        return Path(cli_config)
    local = (cwd or Path.cwd()) / CONFIG_NAME
    if not data_dir_chosen and local.is_file():
        return local
    return data_dir / CONFIG_NAME
