from pathlib import Path

import pytest

from app.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent
BASE = """
[general]
dispatch_enabled = false
[[bulbs]]
name = "a"
ip = "1.2.3.4"
[[teams]]
league = "nfl"
id = "9"
abbr = "GB"
bulbs = ["a"]
"""


def write(tmp_path, text):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def test_example_loads():
    cfg = load_config(ROOT / "config.example.toml")
    assert cfg.general.delay_s == 45
    assert cfg.bulbs[0].mac == "cc4085e692f4"
    assert cfg.teams[0].color == (0, 255, 0)
    assert cfg.teams[0].alt_color == (255, 182, 18)
    assert cfg.general.db_path == ROOT / "game-lights.db"


def test_defaults(tmp_path):
    cfg = load_config(write(tmp_path, BASE))
    g = cfg.general
    assert (g.delay_s, g.poll_live_s, g.poll_break_s) == (45, 15, 60)
    assert cfg.score_effect.pulses == 5
    assert g.dispatch_enabled is False


@pytest.mark.parametrize(
    "extra,needle",
    [
        ("poll_live_s = 5", "poll_live_s"),
        ("poll_break_s = 9", "poll_break_s"),
        ("delay_s = -1", "delay_s"),
        ('delay_s = "x"', "delay_s"),
    ],
)
def test_general_rules(tmp_path, extra, needle):
    with pytest.raises(ConfigError, match=needle):
        load_config(write(tmp_path, BASE.replace("[general]", f"[general]\n{extra}")))


def test_dispatch_enabled_required(tmp_path):
    with pytest.raises(ConfigError, match="dispatch_enabled"):
        load_config(write(tmp_path, BASE.replace("dispatch_enabled = false", "")))


def test_unknown_team_bulb(tmp_path):
    with pytest.raises(ConfigError, match="unknown bulb"):
        load_config(write(tmp_path, BASE.replace('bulbs = ["a"]', 'bulbs = ["zz"]')))


def test_duplicates(tmp_path):
    with pytest.raises(ConfigError, match="duplicate bulb"):
        load_config(write(tmp_path, BASE + '[[bulbs]]\nname = "a"\nip = "5.6.7.8"\n'))
    with pytest.raises(ConfigError, match="duplicate team"):
        load_config(write(tmp_path, BASE + BASE.split("[[teams]]")[1].join(["[[teams]]", ""])))


def test_bad_color(tmp_path):
    with pytest.raises(ConfigError, match="color"):
        load_config(write(tmp_path, BASE + 'color = "nope"\n'))


def test_effect_over_flash_cap(tmp_path):
    with pytest.raises(ConfigError, match="effects.score"):
        load_config(write(tmp_path, BASE + "[effects.score]\npulses = 10\nduration_s = 6\n"))


def test_missing_and_invalid_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(write(tmp_path, "[[[bad"))
