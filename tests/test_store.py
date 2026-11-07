from datetime import UTC, datetime, timedelta

import pytest

from app.store import Event, Game, Store, dedupe_key

T0 = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)


def ev(n=1, due=None, status="pending"):
    due = due or T0 + timedelta(seconds=45)
    detail = {"delta": 6, "label": "TD"}
    return Event(dedupe_key("g1", "9", n), "g1", "9", "score", T0, due, detail, status=status)


def test_first_score_is_baseline():
    s = Store()
    u = s.apply_score("g1", "9", 7)
    assert (u.prev_score, u.increase_n, u.increased) == (None, 0, False)


def test_increase_decrease_rescore_counter():
    s = Store()
    s.apply_score("g1", "9", 0)
    u1 = s.apply_score("g1", "9", 6)
    assert (u1.increased, u1.increase_n) == (True, 1)
    u2 = s.apply_score("g1", "9", 0)  # TD reversed
    assert (u2.increased, u2.increase_n) == (False, 1)
    u3 = s.apply_score("g1", "9", 6)  # re-score: still fires, new key
    assert (u3.increased, u3.increase_n) == (True, 2)
    assert dedupe_key("g1", "9", u1.increase_n) != dedupe_key("g1", "9", u3.increase_n)


def test_no_change_is_not_an_increase():
    s = Store()
    s.apply_score("g1", "9", 3)
    u = s.apply_score("g1", "9", 3)
    assert not u.increased and u.increase_n == 0


def test_multi_point_jump_is_one_increase():
    s = Store()
    s.apply_score("g1", "9", 0)
    assert s.apply_score("g1", "9", 8).increase_n == 1


def test_scores_isolated_per_team_and_game():
    s = Store()
    s.apply_score("g1", "9", 0)
    s.apply_score("g1", "3", 0)
    s.apply_score("g1", "9", 6)
    assert s.apply_score("g1", "3", 0).increase_n == 0
    assert s.apply_score("g2", "9", 0).prev_score is None


def test_event_dedupe():
    s = Store()
    assert s.insert_event(ev()) is True
    assert s.insert_event(ev()) is False
    assert s.get_event(ev().dedupe_key).detail == {"delta": 6, "label": "TD"}


def test_pending_and_mark():
    s = Store()
    s.insert_event(ev(2, due=T0 + timedelta(seconds=90)))
    s.insert_event(ev(1))
    s.insert_event(ev(3, status="skipped_restart"))
    assert [e.dedupe_key for e in s.pending_events()] == ["g1:9:1", "g1:9:2"]
    fired = T0 + timedelta(seconds=46)
    s.mark_event("g1:9:1", "fired", fired)
    e = s.get_event("g1:9:1")
    assert (e.status, e.fired_at) == ("fired", fired)
    assert [x.dedupe_key for x in s.pending_events()] == ["g1:9:2"]


def test_games_upsert_and_upcoming():
    s = Store()
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "pre"))
    s.upsert_game(Game("g2", "nfl", "later", T0 + timedelta(days=3), "pre"))
    s.upsert_game(Game("g3", "nfl", "done", T0 - timedelta(days=1), "post"))
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    assert s.get_game("g1").status == "in"
    assert [g.game_id for g in s.upcoming_games(T0, timedelta(hours=12))] == ["g1"]


def test_naive_datetime_rejected():
    s = Store()
    with pytest.raises(ValueError):
        s.upsert_game(Game("g1", "nfl", "x", datetime(2026, 1, 1), "pre"))


def test_persists_across_reopen(tmp_path):
    p = tmp_path / "s.db"
    s = Store(p)
    s.apply_score("g1", "9", 0)
    s.apply_score("g1", "9", 6)
    s.insert_event(ev())
    s.close()
    s2 = Store(p)
    assert s2.apply_score("g1", "9", 7).increase_n == 2
    assert s2.insert_event(ev()) is False


def test_newer_schema_refused(tmp_path):
    p = tmp_path / "s.db"
    Store(p).db.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        Store(p)


def test_recent_events_newest_first_and_limited():
    s = Store()
    for n in (1, 2, 3):
        s.insert_event(ev(n))
    assert [e.dedupe_key for e in s.recent_events(2)] == ["g1:9:3", "g1:9:2"]


def test_all_games_in_start_order():
    s = Store()
    s.upsert_game(Game("b", "nfl", "new", T0 - timedelta(days=7), "post"))
    s.upsert_game(Game("a", "nfl", "old", T0 - timedelta(days=14), "post"))
    s.upsert_game(Game("c", "nfl", "live", T0, "in"))
    assert [g.game_id for g in s.all_games()] == ["a", "b", "c"]


def test_game_scores_round_trip_and_none_never_erases():
    s = Store()
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in", "NE", 10, "GB", 14))
    got = s.get_game("g1")
    assert (got.home_abbr, got.home_score, got.away_abbr, got.away_score) == ("NE", 10, "GB", 14)
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))  # schedule data without scores
    assert s.get_game("g1").home_score == 10 and s.get_game("g1").away_abbr == "GB"
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "post", "NE", 13, "GB", 20))
    assert (s.get_game("g1").status, s.get_game("g1").away_score) == ("post", 20)


def test_zero_score_is_kept_not_treated_as_missing():
    s = Store()
    s.upsert_game(Game("g1", "nfl", "x", T0, "in", "NE", 0, "GB", 0))
    assert s.get_game("g1").home_score == 0


def test_v1_database_migrates_and_keeps_data(tmp_path):
    import sqlite3

    from app import store as store_mod

    p = tmp_path / "old.db"
    db = sqlite3.connect(p)
    db.executescript(store_mod._SCHEMA_V1)
    db.execute("INSERT INTO games VALUES ('g1','nfl','GB @ NE','2026-11-08T21:25:00+00:00','pre')")
    db.execute("PRAGMA user_version = 1")
    db.commit()
    db.close()
    s = Store(p)
    g = s.get_game("g1")
    assert g.name == "GB @ NE" and g.home_abbr is None and g.home_score is None
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == store_mod.SCHEMA_VERSION
    s.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "post", "NE", 3, "GB", 6))
    assert s.get_game("g1").away_score == 6


# --- settings -----------------------------------------------------------------------------

def test_settings_create_update_and_revisions():
    from app.store import RevisionConflict

    s = Store()
    assert s.get_setting("teams") is None and s.all_settings() == {}
    assert s.put_setting("teams", [{"abbr": "GB"}], 0, "seed", T0) == 1
    assert s.get_setting("teams") == (1, [{"abbr": "GB"}])
    assert s.put_setting("teams", [{"abbr": "GB"}, {"abbr": "NE"}], 1, "ui", T0) == 2
    assert s.all_settings() == {"teams": (2, [{"abbr": "GB"}, {"abbr": "NE"}])}
    assert isinstance(RevisionConflict("x", 1), Exception)


def test_stale_or_duplicate_create_is_refused_and_writes_nothing():
    from app.store import RevisionConflict

    s = Store()
    s.put_setting("household", {"delay_s": 45}, 0, "seed", T0)
    s.put_setting("household", {"delay_s": 50}, 1, "ui", T0)
    with pytest.raises(RevisionConflict) as e:  # another phone saved first: still at revision 1
        s.put_setting("household", {"delay_s": 60}, 1, "ui", T0)
    assert e.value.current_revision == 2 and e.value.section == "household"
    with pytest.raises(RevisionConflict):  # "create" when it already exists
        s.put_setting("household", {"delay_s": 1}, 0, "ui", T0)
    assert s.get_setting("household") == (2, {"delay_s": 50})
    assert len(s.settings_history()) == 2  # the refused writes left no history


def test_history_newest_first_filterable_and_can_hide_secrets():
    s = Store()
    s.put_setting("bulbs", [{"name": "a", "signing_key": "s3cret"}], 0, "seed", T0,
                  history_value=[{"name": "a", "has_signing_key": True}])
    s.put_setting("household", {"delay_s": 45}, 0, "seed", T0 + timedelta(seconds=1))
    s.put_setting("household", {"delay_s": 30}, 1, "ui", T0 + timedelta(seconds=2))
    hist = s.settings_history()
    assert [(h.section, h.revision, h.source) for h in hist] == [
        ("household", 2, "ui"), ("household", 1, "seed"), ("bulbs", 1, "seed")]
    assert [h.revision for h in s.settings_history(section="household")] == [2, 1]
    assert len(s.settings_history(limit=1)) == 1
    stored = s.get_setting("bulbs")[1][0]["signing_key"]
    assert stored == "s3cret" and "s3cret" not in str(hist[-1].value)  # secrets-free history


def test_v2_database_migrates_to_settings_tables(tmp_path):
    import sqlite3

    from app import store as store_mod

    p = tmp_path / "v2.db"
    db = sqlite3.connect(p)
    db.executescript(store_mod._SCHEMA_V1)
    db.executescript(store_mod._SCHEMA_V2)
    db.execute("INSERT INTO games (game_id, league, name, start_utc, status) "
               "VALUES ('g1','nfl','GB @ NE','2026-11-08T21:25:00+00:00','pre')")
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()
    s = Store(p)
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert s.get_game("g1").name == "GB @ NE"
    assert s.put_setting("teams", [], 0, "seed", T0) == 1


def test_database_file_is_private_new_and_existing(tmp_path):
    import os
    import stat

    fresh = tmp_path / "new.db"
    Store(fresh).close()
    assert stat.S_IMODE(os.stat(fresh).st_mode) == 0o600
    loose = tmp_path / "old.db"
    loose.write_bytes(b"")
    loose.chmod(0o664)  # like a database created before settings were stored
    Store(loose).close()
    assert stat.S_IMODE(os.stat(loose).st_mode) == 0o600
