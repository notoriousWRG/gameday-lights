import copy
from pathlib import Path

import pytest

from app import settings
from app.config import ConfigError, load_config, load_raw, parse_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.toml"


def example():
    cfg = load_config(EXAMPLE)
    return cfg, settings.machine_raw_from_config(cfg), settings.sections_from_config(cfg)


def test_round_trip_example_is_exact():
    cfg, machine, sections = example()
    assert settings.build_config(machine, sections, ROOT) == cfg


def test_round_trip_with_several_teams_colors_and_secret(tmp_path):
    toml = tmp_path / "c.toml"
    toml.write_text('''
[general]
dispatch_enabled = false
delay_s = 30
poll_live_s = 12
[[bulbs]]
name = "a"
ip = "1.1.1.1"
mac = "aa"
signing_key = "abcd"
[[bulbs]]
name = "b"
ip = "2.2.2.2"
[[teams]]
league = "nfl"
id = "9"
abbr = "GB"
bulbs = ["a"]
color = "#00FF00"
[[teams]]
league = "nhl"
id = "16"
abbr = "PIT"
bulbs = ["a", "b"]
[effects.score]
pulses = 4
duration_s = 8
[web]
port = 9001
final_hold_min = 5
''')
    cfg = load_config(toml)
    machine, sections = settings.machine_raw_from_config(cfg), settings.sections_from_config(cfg)
    assert settings.build_config(machine, sections, tmp_path) == cfg
    assert sections["advanced"]["poll_live_s"] == 12 and sections["household"]["delay_s"] == 30
    assert sections["teams"][0]["color"] == "#00ff00" and sections["teams"][1]["color"] is None


def test_machine_part_is_only_the_machine_settings():
    cfg, machine, sections = example()
    assert set(machine["general"]) == {"dispatch_enabled", "db_path"}
    assert set(machine["web"]) == {"enabled", "host", "port"}
    assert set(sections) == set(settings.SECTIONS)
    assert "dispatch_enabled" not in str(sections) and "db_path" not in str(sections)


@pytest.mark.parametrize("section,value,needle", [
    ("household", {"delay_s": 45, "dispatch_enabled": True}, "unknown field 'dispatch_enabled'"),
    ("advanced", {"poll_live_s": 15, "db_path": "x"}, "unknown field 'db_path'"),
    ("bulbs", [{"name": "a", "ip": "1.1.1.1", "colour": 1}], "bulbs[0]: unknown field 'colour'"),
    ("teams", [{"league": "nfl", "id": "9", "abbr": "GB", "bulbs": ["a"], "x": 1}],
     "unknown field"),
    ("effects", {"score": {"pulses": 5, "bogus": 1}}, "effects.score: unknown field 'bogus'"),
    ("effects", {"other": {}}, "unknown field 'other'"),
    ("bulbs", {"name": "a"}, "bulbs: must be a list"),
    ("household", [1], "household: must be an object"),
    ("nope", {}, "unknown settings section"),
])
def test_strict_shape_rejects_unknown_fields_and_wrong_containers(section, value, needle):
    _, machine, sections = example()
    sections = {**sections, section: value} if section in settings.SECTIONS else {section: value}
    with pytest.raises(ConfigError, match=needle.replace("[", r"\[").replace("]", r"\]")):
        settings.build_config(machine, sections, ROOT)


@pytest.mark.parametrize("section,mutate,needle", [
    ("advanced", lambda s: s.update(poll_live_s=5), "poll_live_s"),
    ("advanced", lambda s: s.update(poll_break_s=9), "poll_break_s"),
    ("household", lambda s: s.update(delay_s=-1), "delay_s"),
    ("effects", lambda s: s["score"].update(pulses=10, duration_s=6), "effects.score"),
])
def test_ui_edits_get_the_same_rules_as_the_file(section, mutate, needle):
    _, machine, sections = example()
    sections = copy.deepcopy(sections)
    mutate(sections[section])
    with pytest.raises(ConfigError, match=needle):
        settings.build_config(machine, sections, ROOT)


def test_team_must_reference_an_existing_bulb():
    _, machine, sections = example()
    sections = copy.deepcopy(sections)
    sections["teams"][0]["bulbs"] = ["ghost"]
    with pytest.raises(ConfigError, match="unknown bulb 'ghost'"):
        settings.build_config(machine, sections, ROOT)
    sections["teams"][0]["bulbs"] = ["living-room"]
    sections["bulbs"] = []  # removing a bulb a team still uses is refused
    with pytest.raises(ConfigError, match="unknown bulb"):
        settings.build_config(machine, sections, ROOT)


def test_null_color_means_not_set_and_machine_settings_are_not_overridable():
    cfg, machine, sections = example()
    sections = copy.deepcopy(sections)
    sections["teams"][0]["color"] = None
    sections["teams"][0]["alt_color"] = ""
    built = settings.build_config(machine, sections, ROOT)
    assert built.teams[0].color is None and built.teams[0].alt_color is None
    assert built.general.dispatch_enabled == cfg.general.dispatch_enabled


def test_redact_hides_signing_keys_but_says_whether_one_is_set():
    sections = {"bulbs": [{"name": "a", "ip": "1", "signing_key": "s3cret"},
                          {"name": "b", "ip": "2", "signing_key": None}]}
    public = settings.redact("bulbs", sections["bulbs"])
    assert "s3cret" not in str(public)
    assert [b["has_signing_key"] for b in public] == [True, False]
    assert "signing_key" not in public[0]
    assert sections["bulbs"][0]["signing_key"] == "s3cret"  # the original is untouched
    assert settings.redact("teams", [{"x": 1}]) == [{"x": 1}]


def test_parse_config_matches_load_config_and_load_raw_reports_toml_errors(tmp_path):
    raw, base = load_raw(EXAMPLE)
    assert parse_config(raw, base) == load_config(EXAMPLE)
    bad = tmp_path / "bad.toml"
    bad.write_text("[[[nope")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_raw(bad)


@pytest.mark.parametrize("path,where", [
    ("general.delay_s", ("household", "delay_s")),
    ("general.poll_live_s", ("advanced", "poll_live_s")),
    ("general.poll_break_s", ("advanced", "poll_break_s")),
    ("general.schedule_sync_hours", ("advanced", "schedule_sync_hours")),
    ("web.pulse_cooldown_s", ("advanced", "pulse_cooldown_s")),
    ("web.final_hold_min", ("advanced", "final_hold_min")),
    ("bulbs[0].name", ("bulbs", "bulbs[0].name")),
    ("teams[2].bulbs", ("teams", "teams[2].bulbs")),
    ("effects.score", ("effects", "effects.score")),
    ("household", ("household", "household")),
    ("general.dispatch_enabled", ("", "general.dispatch_enabled")),  # machine: not an editor field
    ("", ("", "")),
])
def test_error_location_maps_config_paths_to_the_editor_section_and_field(path, where):
    assert settings.error_location(path) == where


def test_bulb_kind_round_trips_and_is_an_allowed_field(tmp_path):
    toml = tmp_path / "config.toml"
    toml.write_text('[general]\ndispatch_enabled = false\n'
                    '[[bulbs]]\nname = "strip"\nip = "10.0.0.5"\nkind = "govee"\n')
    cfg = load_config(toml)
    machine, sections = settings.machine_raw_from_config(cfg), settings.sections_from_config(cfg)
    assert sections["bulbs"][0]["kind"] == "govee" and sections["bulbs"][0]["port"] == 4003
    assert settings.build_config(machine, sections, tmp_path) == cfg
    settings.check_section_shape("bulbs", sections["bulbs"])


LAYERED = """
[general]
dispatch_enabled = false
[[bulbs]]
name = "strip"
ip = "1.2.3.5"
kind = "govee"
segments = 20
[[teams]]
league = "nfl"
id = "9"
abbr = "GB"
bulbs = ["strip"]
color = "#00ff00"
[teams.effects]
speed = 3.0
[teams.fixture_effects.strip]
kind = "chase"
alt_color = "#ff8c00"
[effects.fixtures.strip]
duration_s = 4.0
"""


def layered_cfg(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(LAYERED)
    return load_config(p)


def test_layers_round_trip_through_sections(tmp_path):
    cfg = layered_cfg(tmp_path)
    sections = settings.sections_from_config(cfg)
    assert sections["bulbs"][0]["segments"] == 20
    assert sections["teams"][0]["effects"] == {"speed": 3.0}
    assert sections["teams"][0]["fixture_effects"]["strip"] == {
        "kind": "chase", "alt_color": "#ff8c00"}
    assert sections["effects"]["fixtures"]["strip"] == {"duration_s": 4.0}
    machine = settings.machine_raw_from_config(cfg)
    assert settings.build_config(machine, sections, tmp_path) == cfg


def test_unset_layers_are_left_out_of_sections():
    _, _, sections = example()
    assert "effects" not in sections["teams"][0]
    assert "fixture_effects" not in sections["teams"][0]
    assert "fixtures" not in sections["effects"]


@pytest.mark.parametrize("section, value, needle", [
    ("effects", {"score": {}, "fixtures": {"strip": {"bogus": 1}}}, "bogus"),
    ("effects", {"fixtures": []}, "must be an object"),
    ("teams", [{"league": "nfl", "id": "9", "abbr": "GB", "bulbs": ["strip"],
                "fixture_effects": {"strip": {"color": "#fff", "nope": 1}}}], "nope"),
    ("teams", [{"league": "nfl", "id": "9", "abbr": "GB", "bulbs": ["strip"],
                "effects": {"color": "#fff"}}], "color"),
])
def test_shape_check_covers_layers(section, value, needle):
    with pytest.raises(ConfigError, match=needle):
        settings.check_section_shape(section, value)
