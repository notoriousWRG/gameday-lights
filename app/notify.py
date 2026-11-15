"""Failure messages to the owner of an install. The app is alive but unhealthy (ESPN failing, a
bulb not answering): say so through one pluggable notifier. A crashed or powered-off server cannot
report itself; that is the heartbeat's job (see health.py).

Optional: with `notify = "none"` a problem is only logged."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.config import Config, HealthConfig
from app.watcher import WatcherStats

log = logging.getLogger(__name__)
CHECK_EVERY_S = 60.0
SEND_TIMEOUT_S = 15.0


class Notifier(Protocol):
    async def send(self, subject: str, body: str) -> None: ...


class WebhookNotifier:
    """POST {"subject", "body", "text"} as JSON; `text` is both joined, for chat webhooks."""

    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url, self._transport = url, transport

    async def send(self, subject: str, body: str) -> None:
        async with httpx.AsyncClient(transport=self._transport, timeout=SEND_TIMEOUT_S) as c:
            r = await c.post(self.url, json={"subject": subject, "body": body,
                                             "text": f"{subject}\n{body}"})
            r.raise_for_status()


class SmtpNotifier:
    def __init__(self, h: HealthConfig, smtp_factory=None) -> None:
        self.h = h
        self._factory = smtp_factory

    def _send_sync(self, subject: str, body: str) -> None:
        h = self.h
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, h.smtp_from, h.smtp_to
        msg.set_content(body)
        factory = self._factory or (smtplib.SMTP_SSL if h.smtp_port == 465 else smtplib.SMTP)
        with factory(h.smtp_host, h.smtp_port, timeout=SEND_TIMEOUT_S) as smtp:
            if h.smtp_port != 465 and self._factory is None:
                smtp.starttls()
            if h.smtp_user:
                smtp.login(h.smtp_user, h.smtp_password or "")
            smtp.send_message(msg)

    async def send(self, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_sync, subject, body)


def make_notifier(h: HealthConfig) -> Notifier | None:
    if h.notify == "webhook" and h.webhook_url:
        return WebhookNotifier(h.webhook_url)
    if h.notify == "smtp":
        return SmtpNotifier(h)
    return None


@dataclass
class _Problem:
    since: datetime
    alerted_at: datetime | None = None
    text: str = ""


class HealthMonitor:
    """Watches for a problem that lasts. One message when it has lasted `fail_after_min`, a
    reminder at most every `renotify_min`, and one message when it clears. A bulb is only checked
    while a game is being watched, so a bulb unplugged for the summer sends nothing."""

    def __init__(
        self,
        config: Callable[[], Config],
        stats: WatcherStats,
        ping_bulbs: Callable[[], Awaitable[dict[str, float | None]]],
        now: Callable[[], datetime],
        notifier: Callable[[HealthConfig], Notifier | None] = make_notifier,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config, self._stats, self._ping = config, stats, ping_bulbs
        self._now, self._make, self._sleep = now, notifier, sleep
        self._problems: dict[str, _Problem] = {}

    async def _active(self, cfg: Config, now: datetime) -> dict[str, str]:
        found: dict[str, str] = {}
        s = self._stats
        recent = timedelta(seconds=max(3 * cfg.general.poll_break_s, 180))
        if s.last_error and s.last_poll_at and now - s.last_poll_at < recent:
            found["espn"] = f"ESPN is not answering ({s.last_error})"
        if s.watching:
            for name, ping in (await self._ping()).items():
                if ping is None:
                    found[f"bulb:{name}"] = f"bulb {name} is not answering"
        return found

    async def check(self) -> None:
        cfg = self._config()
        h, now = cfg.health, self._now()
        active = await self._active(cfg, now)
        notifier = self._make(h)
        for key, text in active.items():
            p = self._problems.setdefault(key, _Problem(now))
            p.text = text
            due = p.alerted_at is None or now - p.alerted_at >= timedelta(minutes=h.renotify_min)
            if now - p.since >= timedelta(minutes=h.fail_after_min) and due:
                p.alerted_at = now
                mins = round((now - p.since).total_seconds() / 60)
                await self._deliver(notifier, f"{h.name}: {text}", f"Ongoing for {mins} min.")
        for key in [k for k in self._problems if k not in active]:
            p = self._problems.pop(key)
            if p.alerted_at is not None:  # only say "fixed" about something that was reported
                await self._deliver(notifier, f"{h.name}: back to normal", p.text + " (cleared)")

    async def _deliver(self, notifier: Notifier | None, subject: str, body: str) -> None:
        log.warning("health: %s. %s", subject, body)
        if notifier is None:
            return
        try:
            await notifier.send(subject, body)
        except Exception as e:  # a broken notifier must never stop the server
            log.warning("could not send the health message (%s: %s)", type(e).__name__, e)

    async def run(self) -> None:
        while True:
            try:
                await self.check()
            except Exception:
                log.exception("health check failed")
            await self._sleep(CHECK_EVERY_S)
