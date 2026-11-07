"""Pure score-change detection over ESPN scoreboard JSON."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

_NFL_LABELS = {
    6: "TD", 7: "TD+PAT", 8: "TD+2pt", 3: "FG", 2: "safety/2pt", 1: "PAT",
}


@dataclass(frozen=True)
class TeamScore:
    game_id: str
    team_id: str
    abbr: str
    score: int
    state: str
    status_name: str


@dataclass(frozen=True)
class ScoreChange:
    game_id: str
    team_id: str
    abbr: str
    old: int
    new: int
    state: str

    @property
    def delta(self) -> int:
        return self.new - self.old


def parse_score(value) -> int | None:
    """ESPN scores arrive as "14", 14 or {"displayValue": "14"}; missing means None."""
    if isinstance(value, dict):
        value = value.get("displayValue", value.get("value"))
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _score(value) -> int:
    return parse_score(value) or 0


def team_scores(scoreboard: dict, followed_ids: Iterable[str]) -> list[TeamScore]:
    followed = {str(i) for i in followed_ids}
    out: list[TeamScore] = []
    for event in scoreboard.get("events", []):
        comps = event.get("competitions") or [{}]
        status = (event.get("status") or comps[0].get("status") or {}).get("type", {})
        for c in comps[0].get("competitors", []):
            team = c.get("team", {})
            team_id = str(team.get("id", c.get("id", "")))
            if team_id in followed:
                out.append(TeamScore(
                    game_id=str(event["id"]), team_id=team_id,
                    abbr=team.get("abbreviation", ""), score=_score(c.get("score")),
                    state=status.get("state", ""), status_name=status.get("name", ""),
                ))
    return out


def detect(prev: dict | None, curr: dict, followed_ids: Iterable[str]) -> list[ScoreChange]:
    if prev is None:
        return []
    followed = list(followed_ids)
    before = {(t.game_id, t.team_id): t.score for t in team_scores(prev, followed)}
    changes: list[ScoreChange] = []
    for t in team_scores(curr, followed):
        old = before.get((t.game_id, t.team_id))
        if old is not None and old != t.score:
            changes.append(ScoreChange(t.game_id, t.team_id, t.abbr, old, t.score, t.state))
    return changes


def score_label(league: str, delta: int) -> str:
    if league == "nfl":
        return _NFL_LABELS.get(delta, "score")
    return "score"
