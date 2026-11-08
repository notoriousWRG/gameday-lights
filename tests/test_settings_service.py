import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import settings
from app.config import ConfigError, load_config
from app.settings_service import SettingsService, config_to_toml
from app.store import RevisionConflict, Store

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def seed_cfg():
    return load_config(ROOT / "config.example.toml")


def make(store=None, seed=True):
    store = store or Store()
    cfg = seed_cfg()
    svc = SettingsService(store, settings.machine_raw_from_config(cfg), ROOT, now=lambda: NOW)
    if seed:
        svc.seed(cfg)
    svc.load()
    return svc, store, cfg


def edited(svc, section, fn):
    """A copy of a stored section with fn applied (what a UI would send back)."""
    value = copy.deepcopy(svc.sections()[section][1])
    fn(value)
    return value


def test_first_start_seeds_every_section_and_the_snapshot_equals_the_toml():
    svc, store, cfg = make()
    assert svc.config == cfg
    assert set(svc.sections()) == set(settings.SECTIONS)
    assert all(rev == 1 for rev, _ in svc.sections().values())
    assert {h.source for h in store.settings_history()} == {"config.toml"}


def test_seed_is_idempotent_and_never_overwrites_stored_settings():
    svc, store, cfg = make()
    svc.update("household", {"delay_s": 30}, 1)
    assert svc.seed(cfg) == []  # a restart re-seeds nothing
    assert svc.config.general.delay_s == 30 and svc.sections()["household"][0] == 2


def test_missing_section_is_seeded_alone_after_an_upgrade():
    store = Store()
    svc, _, cfg = make(store)
    store.db.execute("DELETE FROM settings WHERE section='advanced'")
    store.db.commit()
    assert svc.seed(cfg) == ["advanced"]
    assert svc.sections()["advanced"][0] == 1


def test_diverged_reports_toml_sections_that_differ_from_stored_and_force_reimports():
    svc, _, cfg = make()
    assert svc.diverged(cfg) == []
    svc.update("household", {"delay_s": 30}, 1)
    assert svc.diverged(cfg) == ["household"]  # config.toml still says 45
    assert svc.seed(cfg, force=True) == ["household"]
    assert svc.config.general.delay_s == 45 and svc.diverged(cfg) == []
    assert svc.sections()["household"][0] == 3  # import is a new revision, not a rewrite


def test_update_applies_stores_bumps_revision_and_notifies():
    svc, store, _ = make()
    seen = []
    svc.subscribe(lambda old, new: seen.append((old.general.delay_s, new.general.delay_s)))
    rev, cfg = svc.update("household", {"delay_s": 30}, 1)
    assert rev == 2 and cfg.general.delay_s == 30 and svc.config.general.delay_s == 30
    assert seen == [(45.0, 30.0)]
    assert store.get_setting("household") == (2, {"delay_s": 30.0})
    assert store.settings_history(section="household")[0].source == "ui"


def test_invalid_edit_is_refused_and_changes_nothing():
    svc, store, _ = make()
    seen = []
    svc.subscribe(lambda old, new: seen.append(1))
    with pytest.raises(ConfigError, match="poll_live_s"):
        svc.update("advanced", edited(svc, "advanced", lambda a: a.update(poll_live_s=5)), 1)
    assert svc.sections()["advanced"][0] == 1 and svc.config.general.poll_live_s == 15
    assert seen == [] and len(store.settings_history()) == len(settings.SECTIONS)


def test_cross_section_rule_blocks_removing_a_bulb_a_team_uses_then_allows_it_in_order():
    svc, _, _ = make()
    with pytest.raises(ConfigError, match="unknown bulb"):
        svc.update("bulbs", [], 1)
    svc.update("teams", [], 1)  # unfollow first ...
    svc.update("bulbs", [], 1)  # ... then the bulb can go
    assert svc.config.teams == () and svc.config.bulbs == ()


def test_stale_revision_is_a_conflict_and_the_first_save_wins():
    svc, _, _ = make()
    svc.update("household", {"delay_s": 30}, 1)  # phone A
    with pytest.raises(RevisionConflict) as e:  # phone B, still holding revision 1
        svc.update("household", {"delay_s": 99}, 1)
    assert e.value.current_revision == 2 and svc.config.general.delay_s == 30


def test_no_op_edit_writes_no_new_revision_or_history():
    svc, store, _ = make()
    before = len(store.settings_history())
    rev, _ = svc.update("household", {"delay_s": 45}, 1)  # same value as stored
    assert rev == 1 and len(store.settings_history()) == before


def test_a_failing_subscriber_does_not_undo_or_hide_a_saved_edit(caplog):
    svc, _, _ = make()

    def boom(old, new):
        raise RuntimeError("subscriber bug")

    svc.subscribe(boom)
    rev, _ = svc.update("household", {"delay_s": 30}, 1)
    assert rev == 2 and svc.config.general.delay_s == 30
    assert "subscriber failed" in caplog.text


def test_following_a_team_through_the_service():
    svc, _, _ = make()
    teams = edited(svc, "teams", lambda t: t.append(
        {"league": "nfl", "id": "17", "abbr": "NE", "bulbs": ["living-room"],
         "color": "#1f4fd8", "alt_color": None}))
    svc.update("teams", teams, 1)
    assert [t.abbr for t in svc.config.teams] == ["GB", "NE"]
    assert svc.config.teams[1].color == (0x1F, 0x4F, 0xD8)


# --- bulb secrets ---------------------------------------------------------------------------

def with_key(svc):
    bulbs = edited(svc, "bulbs", lambda b: b[0].update(signing_key="s3cret"))
    svc.update("bulbs", bulbs, 1)
    return svc


def test_signing_key_is_stored_but_never_in_public_view_or_history():
    svc = with_key(make()[0])
    assert svc.config.bulbs[0].signing_key == "s3cret"
    assert "s3cret" not in str(svc.public_sections())
    assert svc.public_sections()["bulbs"]["value"][0]["has_signing_key"] is True
    assert all("s3cret" not in str(h.value) for h in svc._store.settings_history())


def test_ui_round_trip_keeps_the_key_when_the_field_is_absent_or_only_flagged():
    svc = with_key(make()[0])
    public = svc.public_sections()["bulbs"]["value"]  # what the browser got: no key, a flag
    public[0]["name"] = "lounge"
    svc.update("teams", [], 1)  # the team references the old name; free it first
    svc.update("bulbs", public, 2)
    assert svc.config.bulbs[0].name == "lounge" and svc.config.bulbs[0].signing_key == "s3cret"


def test_null_or_empty_signing_key_clears_it_and_a_string_replaces_it():
    svc = with_key(make()[0])
    rev = svc.sections()["bulbs"][0]
    cleared = edited(svc, "bulbs", lambda b: b[0].update(signing_key=""))
    svc.update("bulbs", cleared, rev)
    assert svc.config.bulbs[0].signing_key is None
    replaced = edited(svc, "bulbs", lambda b: b[0].update(signing_key="newkey"))
    svc.update("bulbs", replaced, rev + 1)
    assert svc.config.bulbs[0].signing_key == "newkey"


def test_new_bulb_has_no_key_and_other_bulbs_keep_theirs():
    svc = with_key(make()[0])
    rev = svc.sections()["bulbs"][0]
    both = edited(svc, "bulbs", lambda b: b.append({"name": "den", "ip": "10.0.0.9"}))
    both[0].pop("signing_key")  # a UI that never saw the key
    svc.update("bulbs", both, rev)
    keys = {b.name: b.signing_key for b in svc.config.bulbs}
    assert keys == {"living-room": "s3cret", "den": None}


# --- export ---------------------------------------------------------------------------------

def test_export_round_trips_to_an_equal_config(tmp_path):
    svc, _, _ = make()
    svc.update("teams", edited(svc, "teams", lambda t: t.append(
        {"league": "nhl", "id": "16", "abbr": "PIT", "bulbs": ["living-room"],
         "color": None, "alt_color": "#fcb514"})), 1)
    svc.update("advanced", edited(svc, "advanced", lambda a: a.update(poll_live_s=12)), 1)
    out = tmp_path / "exported.toml"
    out.write_text(svc.export_toml())
    assert load_config(out) == svc.config


def test_export_can_leave_secrets_out(tmp_path):
    svc = with_key(make()[0])
    assert "s3cret" in svc.export_toml()
    without = svc.export_toml(include_secrets=False)
    assert "s3cret" not in without and "signing_key" not in without
    out = tmp_path / "x.toml"
    out.write_text(without)
    assert load_config(out).bulbs[0].signing_key is None


def test_export_handles_quotes_and_unicode_in_names(tmp_path):
    svc, _, _ = make()
    bulbs = edited(svc, "bulbs", lambda b: b[0].update(name='Kid\'s "room" ☃'))
    svc.update("teams", [], 1)
    svc.update("bulbs", bulbs, 1)
    out = tmp_path / "x.toml"
    out.write_text(config_to_toml(svc.config), encoding="utf-8")
    assert load_config(out).bulbs[0].name == 'Kid\'s "room" ☃'


def test_forced_import_refreshes_the_snapshot_and_notifies_running_components():
    svc, _, cfg = make()
    svc.update("household", {"delay_s": 30}, 1)
    seen = []
    svc.subscribe(lambda old, new: seen.append((old.general.delay_s, new.general.delay_s)))
    svc.seed(cfg, force=True)
    assert svc.config.general.delay_s == 45 and seen == [(30.0, 45.0)]


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
[teams.effects]
speed = 3.0
[teams.fixture_effects.strip]
kind = "chase"
alt_color = "#ff8c00"
[effects.fixtures.strip]
duration_s = 4.0
"""


def layered(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(LAYERED)
    cfg = load_config(p)
    svc = SettingsService(store := Store(), settings.machine_raw_from_config(cfg), tmp_path,
                          now=lambda: NOW)
    svc.seed(cfg)
    svc.load()
    return svc, store, cfg


def test_export_keeps_effect_layers_and_reads_back_equal(tmp_path):
    svc, _, cfg = layered(tmp_path)
    out = tmp_path / "exported.toml"
    out.write_text(config_to_toml(svc.config), encoding="utf-8")
    assert load_config(out) == cfg


def test_renaming_a_bulb_renames_its_effect_layers_too(tmp_path):
    svc, _, _ = layered(tmp_path)
    rev = lambda s: svc.sections()[s][0]  # noqa: E731
    cfg = svc.rename_bulb("strip", "porch", rev("bulbs"), rev("teams"))
    assert "porch" in cfg.teams[0].fixture_effects
    assert "porch" in cfg.fixture_effects
    assert "strip" not in cfg.teams[0].fixture_effects and "strip" not in cfg.fixture_effects
    assert cfg.teams[0].fixture_effects["porch"].kind == "chase"
