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
