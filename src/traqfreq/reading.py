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
``snapshots.snapshot`` shape. Jellyfin's (``read_jellyfin``, T17) reads System/Info, the music folders, every
audio item and one user's play counts; Navidrome's (``read_navidrome``, T18) reads ping, the music folders, the
scan status, every album and every song over Subsonic. Tests run
them on the invented answers (``scripts/fixture_*.json``) over ``httpx.MockTransport``.

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

from . import snapshots, store
from .servers import NAMES, READER, REQUIRED, SETTINGS
from .settings import Settings

log = logging.getLogger("traqfreq.reading")
# httpx logs each request's full URL at INFO; Navidrome's carries its token and salt (replayable), so keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)

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
        # Jellyfin's own auth header; 12.x refuses the old X-Emby-Token (401), 10.x takes this too.
        return Client("jellyfin", settings.jellyfin_url or "", headers={"Authorization": f'MediaBrowser Token="{key}"'},
                      secrets=(key,),
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


# --- Jellyfin (T17) ------------------------------------------------------------------------------------------

JELLYFIN_PAGE = PAGE_SIZE  # items per /Items page (tests make it smaller)
JELLYFIN_FIELDS = "Path,ProviderIds,MediaSources,ParentId,DateCreated"  # DateCreated: the stamp's newest item


def _jellyfin_pages(client: Client, path: str, params: dict) -> list[dict]:
    """Every page of a Jellyfin item list (``StartIndex``/``Limit``, total ``TotalRecordCount``)."""
    size = JELLYFIN_PAGE
    return list(pages(lambda o: client.get(path, {**params, "StartIndex": o, "Limit": size}),
                      count=lambda p: len(p.get("Items") or []), size=size, total=lambda p: p.get("TotalRecordCount")))


def _norm_id(v: str) -> str:
    return str(v or "").replace("-", "").lower()


def jellyfin_user(client: Client, wanted: str) -> dict:
    """The Jellyfin user ``TRAQFREQ_JELLYFIN_USER`` names, by ID (with or without dashes) or by name (any case).
    ServerError when no user or more than one has that name."""
    users = client.get("/Users")
    users = users if isinstance(users, list) else []
    by_id = [u for u in users if _norm_id(u.get("Id")) == _norm_id(wanted)]
    if by_id:
        return by_id[0]
    by_name = [u for u in users if str(u.get("Name") or "").casefold() == wanted.strip().casefold()]
    if len(by_name) == 1:
        return by_name[0]
    why = "two users have that name" if by_name else "no user has that name or ID"
    raise ServerError("jellyfin", f"Jellyfin has no single user {wanted!r} (TRAQFREQ_JELLYFIN_USER): {why}. "
                                  f"Its users: {', '.join(sorted(str(u.get('Name')) for u in users)) or 'none'}.")


def _whole(items: list[dict]) -> None:
    """ServerError when the pages don't add up to one whole list: an item came twice, or the distinct items
    aren't Jellyfin's own final ``TotalRecordCount`` (the library changed while it was read)."""
    ids = [it.get("Id") for p in items for it in p.get("Items") or []]
    total = items[-1].get("TotalRecordCount") if items else 0
    twice = len(ids) - len(set(ids))
    if twice or (total is not None and len(set(ids)) != total):
        raise ServerError("jellyfin", (
            f"Jellyfin's item list changed while traqfreq read it ({len(set(ids))} distinct items of {total}"
            f"{f', {twice} read twice' if twice else ''}); a library scan may be running. Nothing was stored: "
            f"refresh again when the scan is done."))


def read_jellyfin(client: Client, settings: Settings) -> tuple[dict, dict]:
    """Jellyfin, GET only: ``/System/Info/Public`` (name, version), ``/Library/VirtualFolders`` (music folders),
    every audio item through ``/Items`` page by page, and, when ``TRAQFREQ_JELLYFIN_USER`` is set, that user's
    play counts through ``/Users/{id}/Items`` (played items only). The item list doesn't depend on the user: a
    user who can't see a library takes no items away. Without a user there are no play counts (an API key
    belongs to no user).

    The pages are sorted oldest first (``DateCreated``, then ``SortName``), so items a running scan adds land at
    the end instead of shifting the pages still to come. A read that still came out torn (an item twice, or not
    as many items as Jellyfin's own final total) is not stored: the refresh fails and says so (``_whole``)."""
    info = client.get("/System/Info/Public")
    info = info if isinstance(info, dict) else {}
    folders = client.get("/Library/VirtualFolders")
    items = _jellyfin_pages(client, "/Items", {"IncludeItemTypes": "Audio", "Recursive": "true",
                                               "Fields": JELLYFIN_FIELDS, "EnableUserData": "false",
                                               "SortBy": "DateCreated,SortName", "SortOrder": "Ascending"})
    _whole(items)
    for page in items:  # play counts come only from the named user, below
        for it in page.get("Items") or []:
            it.pop("UserData", None)
    user, user_pages, played = None, [], {}
    if settings.jellyfin_user:
        u = jellyfin_user(client, settings.jellyfin_user)
        user = u.get("Name")
        user_pages = _jellyfin_pages(client, f"/Users/{u.get('Id')}/Items",
                                     {"IncludeItemTypes": "Audio", "Recursive": "true", "Filters": "IsPlayed",
                                      "EnableUserData": "true", "Fields": "ParentId"})
        played = {it.get("Id"): it.get("UserData") or {} for p in user_pages for it in p.get("Items") or []}
        for page in items:
            for it in page.get("Items") or []:
                it["UserData"] = played.get(it.get("Id"), {"PlayCount": 0})
    snap = snapshots.from_jellyfin(folders, items, info=info, user=user)
    return snap, {"pages": len(items) + len(user_pages), "server_name": info.get("ServerName"),
                  "version": info.get("Version"), "user": user, "played": len(played) if user else None}


# --- Navidrome (T18) -----------------------------------------------------------------------------------------

NAVIDROME_PAGE = PAGE_SIZE  # songs per search3 page and albums per getAlbumList2 page (Subsonic caps lists at 500)


def _sub(answer: dict, key: str) -> dict:
    """The ``key`` part of a Subsonic answer; ServerError with Navidrome's own message when it says failed."""
    r = (answer or {}).get("subsonic-response") if isinstance(answer, dict) else None
    if not isinstance(r, dict):
        raise ServerError("navidrome", "Navidrome answered with something that isn't a Subsonic answer.")
    if r.get("status") != "ok":
        err = r.get("error") or {}
        code = f" (Subsonic error {err['code']})" if err.get("code") is not None else ""
        raise ServerError("navidrome", f"Navidrome said {err.get('message') or r.get('status')!r}{code}.")
    return r.get(key) or {}


def _songs(page: dict) -> list[dict]:
    return _sub(page, "searchResult3").get("song") or []


def _navidrome_whole(before: dict, after: dict, song_pages: list[dict]) -> None:
    """ServerError when the songs read aren't one whole list. Subsonic's ``search3`` has no sort order to ask
    for, so a scan during the read can shift the pages: the read counts only when no scan ran (``scanning``
    false and the same ``lastScan`` and ``count`` before and after), no song came twice, and the distinct
    songs are the scan's own ``count``."""
    b, a = _sub(before, "scanStatus"), _sub(after, "scanStatus")
    ids = [s.get("id") for p in song_pages for s in _songs(p)]
    twice = len(ids) - len(set(ids))
    count = a.get("count")
    why = None
    if b.get("scanning") or a.get("scanning"):
        why = "a library scan was running"
    elif (b.get("lastScan"), b.get("count")) != (a.get("lastScan"), a.get("count")):
        why = "a library scan finished during the read"
    elif twice or (count is not None and len(set(ids)) != int(count)):
        why = "the song list moved under the pages"
    if why:
        raise ServerError("navidrome", (
            f"Navidrome's song list changed while traqfreq read it ({len(set(ids))} distinct songs of {count}"
            f"{f', {twice} read twice' if twice else ''}; {why}). Nothing was stored: refresh again when the "
            f"scan is done."))


def read_navidrome(client: Client, settings: Settings) -> tuple[dict, dict]:
    """Navidrome over Subsonic, GET only: ``ping`` (``type``, ``serverVersion``, OpenSubsonic or not),
    ``getMusicFolders`` (names only: Subsonic gives no paths), ``getScanStatus``, every album through
    ``getAlbumList2`` (``alphabeticalByName``, paged; each album's ``musicBrainzId`` is the release), every
    song through ``search3`` with an empty query (``songCount``/``songOffset``), then ``getScanStatus`` again.
    OpenSubsonic songs carry ``musicBrainzId``, ``path`` (real only with "Report Real Path"), ``played`` and
    ``playCount`` (the logged-in user's; absent = never played = 0). A read a scan tore is not stored
    (``_navidrome_whole``). The music folder is ``TRAQFREQ_NAVIDROME_ROOTS`` if set, else the folder every real
    path shares."""
    size = NAVIDROME_PAGE
    info = client.get("/rest/ping")
    _sub(info, "")  # a wrong user or password stops here, with Navidrome's own message
    music_folders = client.get("/rest/getMusicFolders")
    _sub(music_folders, "musicFolders")
    before = client.get("/rest/getScanStatus")
    _sub(before, "scanStatus")
    albums = list(pages(lambda o: client.get("/rest/getAlbumList2", {"type": "alphabeticalByName", "size": size,
                                                                     "offset": o}),
                        count=lambda p: len(_sub(p, "albumList2").get("album") or []), size=size))
    songs = list(pages(lambda o: client.get("/rest/search3", {"query": "", "songCount": size, "songOffset": o,
                                                              "albumCount": 0, "artistCount": 0}),
                       count=lambda p: len(_songs(p)), size=size))
    after = client.get("/rest/getScanStatus")
    _navidrome_whole(before, after, songs)
    for page in songs:
        for s in _songs(page):
            s.setdefault("playCount", 0)  # OpenSubsonic leaves it out for a song never played
    user = settings.navidrome_user
    snap = snapshots.from_navidrome(after, albums, songs, folders=settings.navidrome_roots, info=info, user=user,
                                    music_folders=music_folders)
    ping = info.get("subsonic-response") or {}
    return snap, {"pages": len(albums) + len(songs), "album_pages": len(albums), "song_pages": len(songs),
                  "albums": sum(len(_sub(p, "albumList2").get("album") or []) for p in albums),
                  "server_name": ping.get("type"), "version": ping.get("serverVersion"), "user": user,
                  "music_folders": len(_sub(music_folders, "musicFolders").get("musicFolder") or []),
                  "played": sum(1 for i in snap["items"] if i.get("play_count"))}


# Each reader returns (snapshot, counts) with counts at least {"pages": n}.
READERS: dict[str, Reader] = {"jellyfin": read_jellyfin, "navidrome": read_navidrome}


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
