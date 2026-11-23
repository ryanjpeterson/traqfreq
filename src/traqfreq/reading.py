"""Reading Jellyfin and Navidrome (T16, spec docs/specs/t13-servers.md): the read-only client and snapshot refresh.

**The client** (``Client``) is built on ``httpx`` and has one verb, GET: it has no method that sends anything else,
and the transport underneath it is never handed out. Each request has a timeout (``TIMEOUT``), redirects are not
followed (a redirect could carry the key elsewhere) and nothing is retried (``retries=0``): a failed read is
reported, not repeated. A server's error answer is shown with the server's own message (``ServerError``).
Secrets (Jellyfin's API key, Navidrome's password and token) are added to each request inside the client and are
never logged, returned or put in an error: URLs in messages carry the path only, and any secret a server echoes
back is blanked.

**Paging** (``pages``): one page after another from an offset, until a short page, an empty page or the server's
own total; at most ``MAX_PAGES`` pages.

**Readers** (``READERS``): one per server, ``read(client, settings) -> (snapshot, counts)`` with the snapshot in
``snapshots.snapshot`` shape. Jellyfin's reader is T17 and Navidrome's T18; until then each says so
(``ReaderMissing``). Tests plug in readers that page through the invented answers (``scripts/fixture_*.json``)
over ``httpx.MockTransport``.

**Refresh** (``refresh``): reads one server whole and stores its snapshot in traqfreq's own database, replacing the
one before (``store.save_snapshot``); nothing is written anywhere else. One refresh at a time per server (a second
one is refused while the first runs). Each refresh, done or failed, is logged in ``store.refreshes`` with its
counts (items, pages, requests, added, removed, hidden paths, seconds) or its error; a failed refresh keeps the
snapshot before it. Plays read from a server stay in its snapshot, shown beside traqfreq's; they are never added
to the history or to ``plays_of``.
"""

from __future__ import annotations

import hashlib
import logging
import secrets as _secrets
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

import httpx

from . import store
from .servers import NAMES, READER, REQUIRED, SETTINGS
from .settings import Settings

log = logging.getLogger("traqfreq.reading")

TIMEOUT = httpx.Timeout(20.0, connect=5.0)
PAGE_SIZE = 500
MAX_PAGES = 10_000
CLIENT_NAME = "traqfreq"


class ServerError(Exception):
    """A server answered with an error, or didn't answer. ``message`` is safe to show (no secrets)."""

    def __init__(self, server: str, message: str, status: int | None = None):
        super().__init__(message)
        self.server, self.message, self.status = server, message, status


class ReaderMissing(Exception):
    """The server has no reader yet (Jellyfin: T17, Navidrome: T18)."""


class NotSetUp(Exception):
    """The server's settings are missing."""


class Busy(Exception):
    """A refresh of this server is already running."""


def _server_message(r: httpx.Response) -> str:
    """The server's own words for an error answer: a JSON message if it gave one, else its text."""
    try:
        body = r.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        sub = body.get("subsonic-response")
        if isinstance(sub, dict) and isinstance(sub.get("error"), dict):
            return str(sub["error"].get("message") or "")
        for k in ("message", "Message", "error", "title", "detail"):
            v = body.get(k)
            if isinstance(v, dict):
                v = v.get("message")
            if v:
                return str(v)
    return " ".join((r.text or "").split())[:300]


class Client:
    """A read-only HTTP client for one server. GET is its only verb."""

    def __init__(self, server: str, base_url: str, *, headers: dict[str, str] | None = None,
                 auth_params: Callable[[], dict[str, str]] | None = None, secrets: tuple[str, ...] = (),
                 transport: httpx.BaseTransport | None = None, timeout: httpx.Timeout = TIMEOUT):
        self.server = server
        self._auth_params = auth_params
        self._secrets = tuple(s for s in secrets if s)
        self.requests = 0
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers={"Accept": "application/json", **(headers or {})},
            timeout=timeout, follow_redirects=False,
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0))

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _clean(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "…")
        return text

    def get(self, path: str, params: dict | None = None) -> dict | list:
        """GET ``path`` and return its JSON. Raises ServerError with the server's own message on any failure."""
        name = NAMES.get(self.server, self.server)
        q = {k: v for k, v in (params or {}).items() if v is not None}
        if self._auth_params:
            q.update(self._auth_params())
        where = f"GET {path}"  # the path only: the query may carry a token
        self.requests += 1
        try:
            r = self._http.get(path, params=q)
        except httpx.TimeoutException:
            raise ServerError(self.server, f"{name} didn't answer in time ({where}).") from None
        except httpx.HTTPError as e:
            raise ServerError(self.server, self._clean(f"Couldn't reach {name} ({where}): {type(e).__name__}.")) from None
        if r.status_code >= 300:
            msg = _server_message(r)
            text = f"{name} answered {r.status_code} {r.reason_phrase} ({where})" + (f": {msg}" if msg else ".")
            raise ServerError(self.server, self._clean(text), r.status_code)
        try:
            return r.json()
        except ValueError:
            raise ServerError(self.server, f"{name} answered {where} with something that isn't JSON.", r.status_code) from None


def pages(fetch: Callable[[int], dict], count: Callable[[dict], int], size: int = PAGE_SIZE,
          total: Callable[[dict], int | None] | None = None, max_pages: int = MAX_PAGES) -> Iterator[dict]:
    """Yield answers page by page: ``fetch(offset)`` for offset 0, size, 2·size, … until a page holds fewer than
    ``size`` items, the server's ``total`` is reached, or ``max_pages`` (then ServerError: the list never ended)."""
    offset = 0
    for _ in range(max_pages):
        page = fetch(offset)
        yield page
        n = count(page)
        offset += n
        t = total(page) if total else None
        if n < size or n == 0 or (t is not None and offset >= t):
            return
    raise ServerError("", f"Stopped after {max_pages} pages: the server's list didn't end.")


# --- each server's client and reader ----------------------------------------------------------------------

def _navidrome_auth(user: str, password: str) -> Callable[[], dict[str, str]]:
    """Subsonic token auth: a new salt per request, t = md5(password + salt). The password itself never leaves."""
    def params() -> dict[str, str]:
        salt = _secrets.token_hex(8)
        return {"u": user, "t": hashlib.md5((password + salt).encode()).hexdigest(), "s": salt,
                "v": "1.16.1", "c": CLIENT_NAME, "f": "json"}
    return params


def client_for(server: str, settings: Settings, transport: httpx.BaseTransport | None = None) -> Client:
    """The read-only client for a set-up server, with its key or token added to each request."""
    if server == "jellyfin":
        key = settings.jellyfin_key or ""
        return Client("jellyfin", settings.jellyfin_url or "", headers={"X-Emby-Token": key}, secrets=(key,),
                      transport=transport)
    if server == "navidrome":
        pw = settings.navidrome_password or ""
        return Client("navidrome", settings.navidrome_url or "",
                      auth_params=_navidrome_auth(settings.navidrome_user or "", pw), secrets=(pw,), transport=transport)
    raise KeyError(server)


Reader = Callable[[Client, Settings], tuple[dict, dict]]


def _missing(server: str) -> Reader:
    def read(client: Client, settings: Settings) -> tuple[dict, dict]:
        raise ReaderMissing(f"traqfreq can't read {NAMES[server]} yet: its reader comes in {READER[server]}.")
    return read


# T17 replaces READERS["jellyfin"] (System/Info/Public, Library/VirtualFolders, paged /Items → from_jellyfin);
# T18 replaces READERS["navidrome"] (ping, getMusicFolders, getScanStatus, paged getAlbumList2 and search3 →
# from_navidrome). Each returns (snapshot, counts) with counts at least {"pages": n}.
READERS: dict[str, Reader] = {"jellyfin": _missing("jellyfin"), "navidrome": _missing("navidrome")}


# --- refresh -----------------------------------------------------------------------------------------------

_running: dict[tuple[str, str], threading.Lock] = {}
_running_guard = threading.Lock()


def _lock(data_dir: Path, server: str) -> threading.Lock:
    k = (str(store.path(data_dir).resolve()), server)
    with _running_guard:
        return _running.setdefault(k, threading.Lock())


def running(data_dir: Path, server: str) -> bool:
    return _lock(data_dir, server).locked()


def missing_settings(server: str, settings: Settings) -> list[str]:
    return [env for env, field, _ in SETTINGS[server] if field in REQUIRED[server] and not getattr(settings, field)]


def refresh(server: str, settings: Settings, transport: httpx.BaseTransport | None = None,
            readers: dict[str, Reader] | None = None) -> dict:
    """Read ``server`` whole and store its snapshot in traqfreq's database. Returns the log entry.
    Raises KeyError (no such server), NotSetUp, Busy, ReaderMissing or ServerError (both logged)."""
    if server not in READERS:
        raise KeyError(server)
    missing = missing_settings(server, settings)
    if missing:
        raise NotSetUp(f"{NAMES[server]} is not set up: {', '.join(missing)} missing. Nothing was read.")
    lock = _lock(settings.data_dir, server)
    if not lock.acquire(blocking=False):
        raise Busy(f"A refresh of {NAMES[server]} is already running. Try again when it's done.")
    started = time.time()
    t0 = time.perf_counter()
    client = None
    try:
        before = store.snapshots(settings.data_dir).get(server)
        client = client_for(server, settings, transport)
        try:
            snap, counts = (readers or READERS)[server](client, settings)
        except (ServerError, ReaderMissing, ValueError) as e:
            msg = e.message if isinstance(e, ServerError) else str(e)
            if isinstance(e, ValueError):  # an answer the parser couldn't read (snapshots.py says which)
                e = ServerError(server, msg)
            store.log_refresh(settings.data_dir, server, started, time.time(), False,
                              {"requests": client.requests, "seconds": round(time.perf_counter() - t0, 3)}, msg)
            log.warning("refresh %s failed after %d requests: %s", server, client.requests, msg)
            raise e from None
        store.save_snapshot(settings.data_dir, snap)
        old = {i["id"] for i in before["items"]} if before else set()
        new = {i["id"] for i in snap["items"]}
        out = {
            "items": len(snap["items"]), "pages": counts.get("pages"), "requests": client.requests,
            "added": len(new - old), "removed": len(old - new), "before": len(before["items"]) if before else None,
            "hidden_paths": sum(1 for i in snap["items"] if i.get("hidden")), "folders": len(snap["folders"]),
            "play_counts": sum(1 for i in snap["items"] if i.get("play_count")),
            "seconds": round(time.perf_counter() - t0, 3),
        }
        out.update({k: v for k, v in counts.items() if k not in out})
        entry = store.log_refresh(settings.data_dir, server, started, time.time(), True, out, None)
        log.info("refresh %s: %d items, %s pages, %d requests, %d added, %d removed in %.1f s", server, out["items"],
                 out["pages"], out["requests"], out["added"], out["removed"], out["seconds"])
        return entry
    finally:
        if client is not None:
            client.close()
        lock.release()


def state(settings: Settings, server: str, limit: int = 5) -> dict:
    """What SETUP shows beside a server: can it be refreshed, is one running, the last refresh and the log."""
    missing = missing_settings(server, settings)
    rows = store.refreshes(settings.data_dir, server, limit)
    return {"server": server, "set_up": not missing, "missing": missing, "running": running(settings.data_dir, server),
            "last": rows[0] if rows else None, "log": rows,
            "rule": "POST /api/servers/{server}/refresh: GET requests to the server only; writes traqfreq's own "
                    "database (its snapshot and this log), nothing else."}
