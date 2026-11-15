"""What the status page and the effects matrix show, built from the store and the config.
Plain functions: no web framework in here."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime, timedelta
from importlib import metadata

from app.bulbs.base import capabilities_for
from app.config import Config
from app.effects import CHASE_DEFAULTS, effect_layers, resolve_effect, to_hex
from app.store import Store
from app.watcher import WatcherStats
from app.web.common import iso

THIS_WEEK = timedelta(days=7)
MAX_NEXT_GAMES = 3  # how many followed teams' next games the Scoreboard shows at once


def setup_items(cfg: Config, pings: dict[str, float | None], dry_run: bool) -> list[dict]:
    """What is left to set up, and what is wrong right now. `done` items show progress; the page
    lists only the unfinished ones."""
    items = [
        {"id": "bulb", "text": "Add a bulb", "done": bool(cfg.bulbs), "fix": "#/bulbs"},
        {"id": "team", "text": "Follow a team", "done": bool(cfg.teams), "fix": "#/teams"},
    ]
    used = {n for t in cfg.teams for n in t.bulbs}
    for b in cfg.bulbs:
        if pings.get(b.name, 0.0) is None:
            items.append({"id": f"reach:{b.name}", "text": f"{b.name} isn't answering",
                          "done": False, "fix": "#/bulbs"})
        if cfg.teams and b.name not in used:
            items.append({"id": f"unused:{b.name}", "text": f"No team uses {b.name} yet",
                          "done": False, "fix": "#/teams"})
    if dry_run:
        items.append({"id": "live", "text": "Dry-run: effects are logged, not sent to bulbs",
                      "done": False, "fix": None,
                      "hint": "Set dispatch_enabled = true in config.toml on the machine "
                              "that should drive the bulbs."})
    return items

def describe_cell(config: Config, team, bulb) -> dict:
    """What `team` plays on `bulb`, with the layer each setting comes from. The values come from
    the same resolver a real event uses; only the origins are added here."""
    caps = capabilities_for(bulb.kind, bulb.segments)
    resolved = resolve_effect(config, team, bulb.name, ((0, 0, 0), (0, 0, 0)))
    origin: dict[str, str] = {}
    for name, layer in effect_layers(config, team, bulb.name):
        if layer is None:
            continue
        if layer.kind:
            origin["kind"] = name
        for key in layer.params:
            origin[key] = name
        for key, value in (("color", layer.color), ("alt_color", layer.alt_color)):
            if value:
                origin[key] = name
    spec = resolved.spec
    values = {**(CHASE_DEFAULTS if spec.kind == "chase" else {}), **spec.params}
    params = {k: {"value": v, "from": origin.get(k, "built-in")}
              for k, v in values.items() if k != "brightness"}
    return {
        "league": team.league, "id": team.id, "abbr": team.abbr, "bulb": bulb.name,
        "segments": bulb.segments, "kinds": sorted(caps.kinds),
        "kind": spec.kind, "kind_from": origin.get("kind", "built-in"), "params": params,
        "color": {"value": to_hex(resolved.primary) if "color" in origin else None,
                  "from": origin.get("color")},
        "alt_color": {"value": to_hex(resolved.alternate) if "alt_color" in origin else None,
                      "from": origin.get("alt_color")},
    }

def team_key(league: str, abbr: str) -> str:
    return f"{league}:{abbr.upper()}"

def team_entries(cfg: Config) -> list[dict]:
    """Followed teams with a stable key, a label that is unambiguous, and the configured color."""
    counts: dict[str, int] = {}
    for t in cfg.teams:
        counts[t.abbr.upper()] = counts.get(t.abbr.upper(), 0) + 1
    out = []
    for t in cfg.teams:
        ambiguous = counts[t.abbr.upper()] > 1  # e.g. PIT in the NFL and the NHL
        color = "#{:02x}{:02x}{:02x}".format(*t.color) if t.color else None
        out.append({
            "league": t.league, "abbr": t.abbr, "bulbs": list(t.bulbs),
            "key": team_key(t.league, t.abbr),
            "label": f"{t.abbr} · {t.league.upper()}" if ambiguous else t.abbr,
            "color": color,
        })
    return out

def schedule_rows(store: Store, cfg: Config) -> list[dict]:
    """Every stored game in order, one row per followed team in it, from that team's side
    (us vs opp, W/L when final). Two followed teams in one game get a row on each schedule."""
    followed = {team_key(t.league, t.abbr) for t in cfg.teams}
    order = {team_key(t.league, t.abbr): i for i, t in enumerate(cfg.teams)}
    rows = []
    for g in store.all_games():
        sides = {"home": (g.home_abbr, g.home_score), "away": (g.away_abbr, g.away_score)}
        base = {"id": g.game_id, "name": g.name, "start_utc": iso(g.start_utc),
                "status": g.status, "league": g.league, "team_key": None, "us": None,
                "opp": None, "home": None, "us_score": None, "opp_score": None, "result": None}
        mine = [
            (side, other) for side, other in (("home", "away"), ("away", "home"))
            if sides[side][0] and team_key(g.league, sides[side][0]) in followed
        ]
        if not mine:
            if not (g.home_abbr or g.away_abbr):
                rows.append(base)  # no team data yet (a legacy row); shown under "All teams" only
            continue  # else: a game of a team that is no longer followed
        mine.sort(key=lambda m: order[team_key(g.league, sides[m[0]][0])])
        for side, other in mine:
            row = dict(base)
            row.update(team_key=team_key(g.league, sides[side][0]), us=sides[side][0],
                       opp=sides[other][0], home=side == "home", us_score=sides[side][1],
                       opp_score=sides[other][1])
            if g.status == "post" and row["us_score"] is not None and row["opp_score"] is not None:
                diff = row["us_score"] - row["opp_score"]
                row["result"] = "W" if diff > 0 else "L" if diff < 0 else "T"
            rows.append(row)
    return rows

def _scoreboard_game(store: Store, live: dict, followed: set[str]) -> dict:
    game = store.get_game(live["game_id"])

    def side(s: dict) -> dict:
        us = bool(game and s["abbr"] and team_key(game.league, s["abbr"]) in followed)
        return {**s, "us": us}

    return {
        "id": live["game_id"],
        "league": game.league if game else None,
        "name": live["name"],
        "start_utc": iso(game.start_utc) if game else None,
        "state": live["state"],
        "status_name": live["status_name"],
        "detail": live["detail"],
        "clock": live["clock"],
        "period": live["period"],
        "home": side(live["home"]),
        "away": side(live["away"]),
        "broadcast": live["broadcast"],
        "venue": live["venue"],
        "situation": live["situation"],
        "updated_at": iso(live["updated_at"]),
        "ended_at": iso(live["ended_at"]),
    }

def scoreboard_card(
    store: Store, cfg: Config, stats: WatcherStats, now: datetime, schedule: list[dict]
) -> dict:
    """What the Scoreboard card shows: games in their window (live/pre), a game that just
    finished (for `final_hold_min`), or else the next game of each followed team (at most
    MAX_NEXT_GAMES)."""
    followed = {team_key(t.league, t.abbr) for t in cfg.teams}
    hold = timedelta(minutes=cfg.web.final_hold_min)
    games = []
    for gid, live in stats.live.items():
        active = gid in stats.watching_ids and live["state"] in ("pre", "in")
        just_finished = (
            live["state"] == "post" and live["ended_at"] is not None
            and now - live["ended_at"] <= hold
        )
        if active or just_finished:
            games.append(_scoreboard_game(store, live, followed))
    games.sort(key=lambda g: (g["state"] != "in", g["start_utc"] or ""))
    states = {g["state"] for g in games}
    shown = {g["id"] for g in games}
    # "Next" means not started: a game already in progress without live data yet is not next.
    # One per followed team (its first such game), soonest first; a game two followed teams
    # share is one card, kept on the team that comes first in the list (schedule is in that order).
    first_per_team: dict[str, dict] = {}
    for r in schedule:
        if r["status"] == "pre" and r["id"] not in shown:
            first_per_team.setdefault(r["team_key"] or "", r)
    next_games, seen = [], set()
    for r in sorted(first_per_team.values(), key=lambda r: r["start_utc"]):
        if r["id"] not in seen:
            seen.add(r["id"])
            in_week = datetime.fromisoformat(r["start_utc"]) - now <= THIS_WEEK
            next_games.append({**r, "in_week": in_week})
    next_games = next_games[:MAX_NEXT_GAMES]
    if "in" in states:
        mode = "live"
    elif "pre" in states:
        mode = "pre"
    elif games:
        mode = "final"
    else:
        mode = "next" if next_games else "idle"
    return {
        "mode": mode,
        "polling": {
            "active": bool(stats.watching_ids),
            "interval_s": stats.poll_interval_s,
            "last_poll_at": iso(stats.last_poll_at),
            "lead_min": cfg.general.watch_lead_min,
        },
        "games": games,
        "next_games": next_games,
    }

def build_status(
    store: Store,
    cfg: Config,
    stats: WatcherStats,
    pings: dict[str, float | None],
    dry_run: bool,
    now: datetime,
) -> dict:
    events = []
    for e in store.recent_events(25):
        game = store.get_game(e.game_id)
        events.append({
            "key": e.dedupe_key,
            "game": game.name if game else e.game_id,
            "team": e.detail.get("abbr", e.team_id),
            "label": e.detail.get("label", e.type),
            "delta": e.detail.get("delta"),
            "status": e.status,
            "detected_at": iso(e.detected_at),
            "due_at": iso(e.due_at),
            "fired_at": iso(e.fired_at),
            "fire_delay_s": (e.fired_at - e.detected_at).total_seconds() if e.fired_at else None,
            "seen_at": iso(e.seen_at),
            "lag_s": e.lag_s,
        })
    schedule = schedule_rows(store, cfg)
    try:
        version = metadata.version("gameday-lights")
    except metadata.PackageNotFoundError:
        version = "dev"
    started = stats.started_at
    return {
        "version": version,
        "now": iso(now),
        "uptime_s": (now - started).total_seconds() if started else None,
        "mode": "dry_run" if dry_run else "live",
        "delay_s": cfg.general.delay_s,
        "teams": team_entries(cfg),
        "bulbs": [
            {"name": b.name, "ip": b.ip,
             "ping_ms": None if pings.get(b.name) is None else round(pings[b.name] * 1000)}
            for b in cfg.bulbs
        ],
        "watcher": {
            "last_sync_at": iso(stats.last_sync_at),
            "last_poll_at": iso(stats.last_poll_at),
            "last_ok_at": iso(stats.last_ok_at),
            "polls": stats.polls,
            "errors": stats.errors,
            "last_error": stats.last_error,
            "watching": stats.watching,
        },
        "schedule": schedule,
        "scoreboard": scoreboard_card(store, cfg, stats, now, schedule),
        "events": events,
    }


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile of a sorted, non-empty list."""
    index = max(0, math.ceil(fraction * len(sorted_values)) - 1)
    return sorted_values[index]


def _lag_summary(lags: list[float]) -> dict:
    lags = sorted(lags)
    if not lags:
        return {"n": 0, "median_s": None, "min_s": None, "max_s": None, "suggested_delay_s": None}
    return {
        "n": len(lags), "median_s": round(statistics.median(lags), 1),
        "min_s": round(lags[0], 1), "max_s": round(lags[-1], 1),
        "suggested_delay_s": max(0, math.ceil(_percentile(lags, 0.75))),
    }


# Older scores and plays leave the Calibrate list; their lags still count in the readings.
CALIBRATION_RECENT_H = 12


def calibration(store: Store, cfg: Config, shown: int = 12, now: datetime | None = None) -> dict:
    """The delay calibration: recent score events to mark as seen on the TV, and what the marks so
    far say. The suggested delay is the 75th percentile of the lags (rounded up, never below 0):
    a late flash is a small miss, an early one spoils the play, so it leans high."""
    seen = store.seen_events(50)
    summary = _lag_summary([e.lag_s for e in seen])
    # A touchdown and an extra point do not lag the same amount (ESPN posts them at different
    # moments relative to the picture), so each kind of score gets its own readings and delay.
    groups: dict[str, list[float]] = {}
    for e in seen:
        groups.setdefault(e.detail.get("label", e.type), []).append(e.lag_s)
    by_label = [
        {"label": label, "delay_s": cfg.general.delay_by_label.get(label, cfg.general.delay_s),
         "has_own_delay": label in cfg.general.delay_by_label, **_lag_summary(lags)}
        for label, lags in sorted(
            groups.items(), key=lambda kv: (-len(kv[1]), kv[0] != "TD", kv[0]))
    ]
    # Only today's game is worth marking: last week's events stay in the readings, not the list.
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=CALIBRATION_RECENT_H)
    window = timedelta(minutes=cfg.web.mark_window_min)

    def markable(rows):
        """Marked rows stay (so a reading can be undone); an unmarked one stays only while it is
        recent and nothing newer has been marked: a reading minutes late calibrates nothing, and
        marking a later play makes the earlier ones moot."""
        newest_marked = max((e.detected_at for e in rows if e.seen_at), default=None)
        return [
            e for e in rows
            if e.detected_at >= cutoff and (e.seen_at or (
                now - e.detected_at <= window
                and (newest_marked is None or e.detected_at > newest_marked)))
        ]

    events = []
    for e in markable(store.recent_events(shown)):
        game = store.get_game(e.game_id)
        events.append({
            "key": e.dedupe_key,
            "game": game.name if game else e.game_id,
            "team": e.detail.get("abbr", e.team_id),
            "label": e.detail.get("label", e.type),
            "detected_at": iso(e.detected_at),
            "seen_at": iso(e.seen_at),
            "lag_s": None if e.lag_s is None else round(e.lag_s, 1),
        })
    plays = []
    for e in markable(store.recent_plays(30)):
        plays.append({
            "key": e.dedupe_key, "text": e.detail.get("text"), "period": e.detail.get("period"),
            "clock": e.detail.get("clock"), "detected_at": iso(e.detected_at),
            "seen_at": iso(e.seen_at),
            "lag_s": None if e.lag_s is None else round(e.lag_s, 1),
        })
    play_summary = _lag_summary([e.lag_s for e in store.seen_events(50, plays=True)])
    return {"delay_s": cfg.general.delay_s, "events": events, "by_label": by_label,
            "plays": plays, "play_summary": play_summary, **summary}
