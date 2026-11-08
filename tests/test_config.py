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
    assert cfg.general.db_path == ROOT / "gameday-lights.db"


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


def test_web_defaults_and_override(tmp_path):
    assert load_config(write(tmp_path, BASE)).web.host == "127.0.0.1"
    web = '[web]\nenabled = false\nhost = "192.168.0.20"\nport = 9000\n'
    cfg = load_config(write(tmp_path, BASE + web))
    assert (cfg.web.enabled, cfg.web.host, cfg.web.port) == (False, "192.168.0.20", 9000)


@pytest.mark.parametrize("body,needle", [
    ('port = 0', "web.port"), ('port = "80"', "web.port"), ('port = 70000', "web.port"),
    ('host = ""', "web.host"), ('enabled = "yes"', "web.enabled"),
    ('pulse_cooldown_s = 0', "pulse_cooldown_s"), ('final_hold_min = -1', "final_hold_min"),
])
def test_web_rules(tmp_path, body, needle):
    with pytest.raises(ConfigError, match=needle):
        load_config(write(tmp_path, BASE + f"[web]\n{body}\n"))


def test_pulse_cooldown_default_and_override(tmp_path):
    assert load_config(write(tmp_path, BASE)).web.pulse_cooldown_s == 10
    cfg = load_config(write(tmp_path, BASE + "[web]\npulse_cooldown_s = 3\n"))
    assert cfg.web.pulse_cooldown_s == 3


def test_final_hold_default_and_override(tmp_path):
    assert load_config(write(tmp_path, BASE)).web.final_hold_min == 30
    cfg = load_config(write(tmp_path, BASE + "[web]\nfinal_hold_min = 0\n"))
    assert cfg.web.final_hold_min == 0


def test_bulb_name_and_ip_must_not_be_blank():
    import pytest as _pytest

    from app.config import ConfigError, parse_config

    for bad in ({"name": "  ", "ip": "10.0.0.1"}, {"name": "lamp", "ip": ""}):
        with _pytest.raises(ConfigError, match="must not be empty"):
            parse_config({"general": {"dispatch_enabled": False}, "bulbs": [bad]}, ".")


def test_bulb_kind_defaults_to_wiz_and_sets_the_default_port():
    from app.config import ConfigError, parse_config

    def bulbs(*items):
        raw = {"general": {"dispatch_enabled": False}, "bulbs": list(items)}
        return parse_config(raw, ".").bulbs

    old, strip, custom = bulbs(
        {"name": "a", "ip": "10.0.0.1"},
        {"name": "b", "ip": "10.0.0.2", "kind": "govee"},
        {"name": "c", "ip": "10.0.0.3", "kind": "govee", "port": 4999},
    )
    assert (old.kind, old.port) == ("wiz", 38899)
    assert (strip.kind, strip.port) == ("govee", 4003)
    assert custom.port == 4999
    with pytest.raises(ConfigError, match=r"bulbs\[0\]\.kind"):
        bulbs({"name": "a", "ip": "10.0.0.1", "kind": "hue"})


STRIP = """
[general]
dispatch_enabled = false
[[bulbs]]
name = "lamp"
ip = "1.2.3.4"
[[bulbs]]
name = "strip"
ip = "1.2.3.5"
kind = "govee"
segments = 20
[[teams]]
league = "nfl"
id = "9"
abbr = "GB"
bulbs = ["lamp", "strip"]
"""


def test_segments_default_and_wiz_cannot_have_them(tmp_path):
    cfg = load_config(write(tmp_path, BASE))
    assert cfg.bulbs[0].segments == 1
    bad = BASE.replace('ip = "1.2.3.4"', 'ip = "1.2.3.4"\nsegments = 5')
    with pytest.raises(ConfigError, match=r"bulbs\[0\].segments"):
        load_config(write(tmp_path, bad))


def test_layers_parse_at_every_level(tmp_path):
    text = STRIP + """
[teams.effects]
speed = 3.0
[teams.fixture_effects.strip]
kind = "chase"
chunk = 4
alt_color = "#ff8c00"
[effects.fixtures.lamp]
pulses = 3
"""
    cfg = load_config(write(tmp_path, text))
    team = cfg.teams[0]
    assert team.effect.params == {"speed": 3.0}
    assert team.fixture_effects["strip"].kind == "chase"
    assert team.fixture_effects["strip"].params == {"chunk": 4}
    assert team.fixture_effects["strip"].alt_color == (255, 140, 0)
    assert cfg.fixture_effects["lamp"].params == {"pulses": 3}


@pytest.mark.parametrize("extra, needle", [
    ('[teams.fixture_effects.nope]\nkind = "pulse"', "fixture_effects.nope: unknown bulb"),
    ('[teams.fixture_effects.strip]\nbogus = 1', "fixture_effects.strip.bogus: unknown field"),
    ('[teams.fixture_effects.strip]\nkind = "sparkle"', "kind: must be one of"),
    ('[teams.fixture_effects.strip]\nkind = "pulse"\nchunk = 3', "not a pulse parameter"),
    ('[effects.fixtures.gone]\nkind = "pulse"', "effects.fixtures.gone: unknown bulb"),
    ('[teams.effects]\ncolor = "#fff000"', "teams[0].effects.color: unknown field"),
])
def test_bad_layers_name_the_field(tmp_path, extra, needle):
    with pytest.raises(ConfigError, match=needle.replace("[", r"\[").replace("]", r"\]")):
        load_config(write(tmp_path, STRIP + "\n" + extra + "\n"))


def test_chase_on_a_whole_fixture_bulb_is_refused(tmp_path):
    text = STRIP + '\n[teams.fixture_effects.lamp]\nkind = "chase"\n'
    with pytest.raises(ConfigError, match="'lamp'.*does not support 'chase'"):
        load_config(write(tmp_path, text))


def test_chase_over_the_per_segment_cap_is_refused(tmp_path):
    text = STRIP + '\n[teams.fixture_effects.strip]\nkind = "chase"\nspeed = 10\nchunk = 4\n'
    with pytest.raises(ConfigError, match="cap"):
        load_config(write(tmp_path, text))


def test_config_without_layers_is_unchanged(tmp_path):
    cfg = load_config(write(tmp_path, BASE))
    assert cfg.fixture_effects == {}
    assert cfg.teams[0].effect is None and cfg.teams[0].fixture_effects == {}
