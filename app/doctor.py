"""`gameday-lights doctor`: pass/fail lines for the things that go wrong on a new install. Each
check is a small function returning a Check; the network and socket pieces are passed in so the
logic is testable without a LAN."""

from __future__ import annotations

import asyncio
import errno
import socket
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import Config, ConfigError, load_config

PASS, WARN, FAIL = "ok", "warn", "FAIL"
PING_TIMEOUT_S = 4.0


@dataclass(frozen=True)
class Check:
    status: str  # PASS, WARN or FAIL
    name: str
    detail: str = ""

    def line(self) -> str:
        text = f"[{self.status:>4}] {self.name}"
        return f"{text}: {self.detail}" if self.detail else text


def firewall_hint(platform: str = sys.platform) -> str:
    """What to check when no bulb can be found or reached on this computer."""
    if platform == "win32":
        return ("Windows Firewall may be blocking local network traffic: open Windows Security > "
                "Firewall & network protection > Allow an app through firewall, and tick "
                "Private for Python (or Gameday Lights). Also make sure the Wi-Fi is set to "
                "a Private network.")
    if platform == "darwin":
        return ("macOS may be blocking local network access: open System Settings > Privacy & "
                "Security > Local Network and turn it on for Terminal (or the app that runs "
                "Gameday Lights).")
    return ("A firewall may be blocking UDP on the home network: allow UDP ports 38899 (WiZ) "
            "and 4001/4002/4003 (Govee) on the local network.")


def check_config(path: Path) -> tuple[Check, Config | None]:
    try:
        cfg = load_config(path)
    except ConfigError as e:
        hint = "; run `gameday-lights init` to create one" if "not found" in str(e) else ""
        return Check(FAIL, "settings file", f"{e}{hint}"), None
    return Check(PASS, "settings file", str(path)), cfg


def check_data_dir(directory: Path) -> Check:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory):
            pass
    except OSError as e:
        return Check(FAIL, "data folder", f"{directory} is not writable ({e})")
    return Check(PASS, "data folder", str(directory))


def check_port(host: str, port: int) -> Check:
    """Free to bind? In use usually means Gameday Lights is already running, which is fine."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1), 10048):
                return Check(WARN, f"web port {port}",
                             "already in use (is Gameday Lights already running?)")
            return Check(FAIL, f"web port {port}", f"cannot listen on {host}: {e}")
    return Check(PASS, f"web port {port}", f"free on {host}")


async def check_espn(fetch: Callable[[], Awaitable[object]]) -> Check:
    try:
        await fetch()
    except Exception as e:
        return Check(FAIL, "ESPN", f"no answer ({e}); check this computer's internet connection")
    return Check(PASS, "ESPN", "answers")


def check_broadcast_socket() -> Check:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", 0))
    except OSError as e:
        return Check(FAIL, "bulb discovery socket", f"cannot open a UDP broadcast socket ({e})")
    return Check(PASS, "bulb discovery socket", "can open")


async def check_bulbs(
    cfg: Config,
    ping: Callable[[object], Awaitable[float | None]],
    make: Callable[[object], object],
    discover: Callable[[], Awaitable[list[dict]]],
    platform: str = sys.platform,
) -> list[Check]:
    """Every saved bulb answers; with none saved (or none answering) look for bulbs on the
    network and, if that finds nothing either, say what blocks it."""
    out: list[Check] = []
    answered = 0
    for b in cfg.bulbs:
        try:
            ms = await asyncio.wait_for(ping(make(b)), PING_TIMEOUT_S)
        except Exception:
            ms = None
        if ms is None:
            out.append(Check(FAIL, f"bulb {b.name}", f"{b.ip} is not answering"))
        else:
            answered += 1
            out.append(Check(PASS, f"bulb {b.name}", f"{b.ip} answers ({round(ms * 1000)} ms)"))
    if answered:
        return out
    try:
        found = await asyncio.wait_for(discover(), 15)
    except Exception as e:
        found = []
        out.append(Check(WARN, "bulb search", f"could not search ({e})"))
    if found:
        names = ", ".join(f"{b['ip']} ({b.get('kind', '?')})" for b in found)
        out.append(Check(PASS, "bulb search", f"found {names}; add it on the Bulbs tab"))
    else:
        out.append(Check(WARN, "bulb search", "no bulbs found. " + firewall_hint(platform)))
    return out
