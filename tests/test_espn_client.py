import httpx
import pytest

from app.espn.client import EspnClient, EspnError


class Harness:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.now = 0.0
        self.slept: list[float] = []

        def handler(req):
            self.requests.append(req)
            r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
            if isinstance(r, Exception):
                raise r
            return r

        async def sleep(t):
            self.slept.append(t)

        self.client = EspnClient(
            transport=httpx.MockTransport(handler), clock=lambda: self.now, sleep=sleep
        )


def ok(data=None):
    return httpx.Response(200, json=data or {"events": []})


async def test_scoreboard_cached_within_ttl_then_refetched():
    h = Harness([ok()])
    await h.client.scoreboard("nfl")
    h.now = 9.9
    await h.client.scoreboard("nfl")
    assert len(h.requests) == 1
    h.now = 10.1
    await h.client.scoreboard("nfl")
    assert len(h.requests) == 2


async def test_urls_and_params():
    h = Harness([ok()])
    await h.client.scoreboard("nfl", date="20261108")
    await h.client.team_schedule("nhl", "5", seasontype=3)
    await h.client.teams("football/nfl")
    urls = [str(r.url) for r in h.requests]
    assert urls[0].endswith("/football/nfl/scoreboard?dates=20261108")
    assert urls[1].endswith("/hockey/nhl/teams/5/schedule?seasontype=3")
    assert urls[2].endswith("/football/nfl/teams")


async def test_different_params_not_shared():
    h = Harness([ok()])
    await h.client.scoreboard("nfl", date="20261108")
    await h.client.scoreboard("nfl", date="20261109")
    assert len(h.requests) == 2


async def test_retries_5xx_with_exponential_backoff_then_succeeds():
    h = Harness([httpx.Response(503), httpx.Response(500), ok({"a": 1})])
    assert await h.client.scoreboard("nfl") == {"a": 1}
    assert h.slept == [1.0, 2.0]


async def test_retries_429_and_transport_errors():
    h = Harness([httpx.Response(429), httpx.ConnectTimeout("t"), ok()])
    await h.client.scoreboard("nfl")
    assert len(h.requests) == 3


async def test_gives_up_after_retries():
    h = Harness([httpx.Response(500)])
    with pytest.raises(EspnError, match="4 attempts"):
        await h.client.scoreboard("nfl")
    assert len(h.requests) == 4 and h.slept == [1.0, 2.0, 4.0]


async def test_4xx_fails_immediately():
    h = Harness([httpx.Response(404)])
    with pytest.raises(EspnError, match="404"):
        await h.client.scoreboard("nfl")
    assert len(h.requests) == 1 and h.slept == []


async def test_bad_json_and_unknown_league():
    h = Harness([httpx.Response(200, text="<html>")])
    with pytest.raises(EspnError, match="JSON"):
        await h.client.scoreboard("nfl")
    with pytest.raises(EspnError, match="unknown league"):
        await h.client.scoreboard("curling")


async def test_failure_not_cached():
    h = Harness([httpx.Response(500), httpx.Response(500), httpx.Response(500),
                 httpx.Response(500), ok()])
    with pytest.raises(EspnError):
        await h.client.scoreboard("nfl")
    await h.client.scoreboard("nfl")
