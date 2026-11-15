"""The installer scripts, run with --dry-run: the service files they would write are checked, and
nothing is installed. Needs a POSIX sh."""

import configparser
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "bootstrap.sh"
posix = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("sh"), reason="needs a POSIX sh")


def dry_run(tmp_path, os_name, *args):
    home = tmp_path / "home with space"
    home.mkdir(exist_ok=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "GAMEDAY_OS": os_name,
           "XDG_CONFIG_HOME": str(home / ".config")}
    p = subprocess.run(["sh", str(SCRIPT), "--dry-run", "--version", "v1.2.3", *args],
                       env=env, capture_output=True, text=True, timeout=60)
    return p, home


def service_file(out: str) -> str:
    return out.split("----- begin service file -----\n")[1].split("----- end service file -----")[0]


@posix
def test_macos_plist_is_valid_and_has_no_leftover_placeholders(tmp_path):
    p, home = dry_run(tmp_path, "Darwin")
    assert p.returncode == 0, p.stderr
    plist = plistlib.loads(service_file(p.stdout).encode())
    assert plist["Label"] == "com.gameday-lights"
    assert plist["ProgramArguments"] == [
        "/usr/bin/caffeinate", "-i", str(home / ".local/bin/gameday-lights"), "run"]
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["StandardOutPath"] == str(home / "Library/Logs/gameday-lights.log")
    assert "$" not in service_file(p.stdout)


@posix
def test_linux_unit_is_valid(tmp_path):
    p, home = dry_run(tmp_path, "Linux")
    assert p.returncode == 0, p.stderr
    text = service_file(p.stdout)
    assert text.startswith("# managed by gameday-lights bootstrap.sh")
    unit = configparser.ConfigParser(strict=False)
    unit.optionxform = str
    unit.read_string(text)
    assert unit["Service"]["ExecStart"] == f"{home}/.local/bin/gameday-lights run"
    assert unit["Install"]["WantedBy"] == "default.target"
    assert "%h" not in text and "$" not in text and "WorkingDirectory" not in text


@posix
def test_dry_run_installs_the_release_wheel_and_changes_nothing(tmp_path):
    p, home = dry_run(tmp_path, "Linux")
    assert ("gameday-lights @ https://github.com/notoriousWRG/gameday-lights/releases/download/"
            "v1.2.3/gameday_lights-1.2.3-py3-none-any.whl") in p.stdout
    assert "nothing was changed" in p.stdout
    assert list(home.iterdir()) == []


@posix
def test_no_service_skips_the_service_file(tmp_path):
    p, _ = dry_run(tmp_path, "Linux", "--no-service")
    assert p.returncode == 0 and "begin service file" not in p.stdout


@posix
def test_bad_version_and_bad_option_are_refused(tmp_path):
    home = tmp_path
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    bad = subprocess.run(["sh", str(SCRIPT), "--dry-run", "--version", "latest"],
                         env=env, capture_output=True, text=True)
    assert bad.returncode == 1 and "version must look like" in bad.stderr
    odd = subprocess.run(["sh", str(SCRIPT), "--nope"], env=env, capture_output=True, text=True)
    assert odd.returncode == 2


@posix
def test_uninstall_dry_run_keeps_data(tmp_path):
    p, home = dry_run(tmp_path, "Darwin", "--uninstall")
    assert p.returncode == 0, p.stderr
    assert "Your settings and history were kept" in p.stdout
    assert str(home / "Library/Application Support/gameday-lights") in p.stdout
