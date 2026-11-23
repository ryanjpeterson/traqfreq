"""T16–T18: reading servers (docs/specs/t13-servers.md): the read-only client, paging, errors, refresh and its log,
Jellyfin's reader (T17) and Navidrome's (T18).

No network: every answer comes from ``httpx.MockTransport`` serving the invented answers in
``scripts/fixture_jellyfin.json`` and ``fixture_navidrome.json``, read by the real readers
(``reading.read_jellyfin``, ``reading.read_navidrome``).
"""

import hashlib
import importlib.util
import inspect
import json
import logging
import re
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from traqfreq import reading, snapshots, store
from traqfreq.app import create_app
from traqfreq.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
KEY = "jf-key-sekrit-0001"
PASSWORD = "nd-pass-sekrit-0002"


def _make_fixture():
    spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


JF, ND = _make_fixture().snapshot_answers()
JF_PAGE = len(JF["items_pages"][0]["Items"])  # 10
JF_ITEMS = [it for p in JF["items_pages"] for it in p["Items"]]
JF_PLAYED = {it["Id"]: it["UserData"]["PlayCount"] for it in JF["user_played"]["Items"]}
ND_PAGE = len(ND["song_pages"][0]["subsonic-response"]["searchResult3"]["song"])  # 5
ND_SONGS = [s for p in ND["song_pages"] for s in p["subsonic-response"]["searchResult3"]["song"]]
ND_ALBUMS = [a for p in ND["album_pages"] for a in p["subsonic-response"]["albumList2"]["album"]]


def _nd(key: str, **body) -> dict:
    """A Subsonic answer in the fixture's envelope."""
    return {"subsonic-response": {**{k: v for k, v in ND["ping"]["subsonic-response"].items()}, **({key: body} if key else {})}}


class Servers:
    """A MockTransport serving the fixture answers; records every request. ``fail`` replaces one path's answer."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.fail: dict[str, object] = {}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path, q = req.url.path, req.url.params
        if path in self.fail:
            f = self.fail[path]
            if isinstance(f, Exception):
                raise f
            return f
        if req.url.host == "jellyfin.test":
            if path == "/System/Info/Public":  # public: no key needed, as on Jellyfin
                return httpx.Response(200, json=JF["system_info"])
            if req.headers.get("Authorization") != f'MediaBrowser Token="{KEY}"':  # as Jellyfin 12: no X-Emby-Token
                return httpx.Response(401, text="Access token is invalid or expired.")
            start, limit = int(q.get("StartIndex", 0)), int(q.get("Limit", 100))
            if path == "/Library/VirtualFolders":
                return httpx.Response(200, json=JF["virtual_folders"])
            if path == "/Users":
                return httpx.Response(200, json=JF["users"])
            if path == "/Items":  # as Jellyfin: no user, no UserData
                page = [{k: v for k, v in it.items() if k != "UserData"} for it in JF_ITEMS[start:start + limit]]
                return httpx.Response(200, json={"Items": page, "TotalRecordCount": len(JF_ITEMS), "StartIndex": start})
            if path == f"/Users/{JF['users'][1]['Id']}/Items":
                played = JF["user_played"]["Items"]
                return httpx.Response(200, json={"Items": played[start:start + limit], "TotalRecordCount": len(played),
                                                 "StartIndex": start})
            if path.startswith("/Users/"):
                return httpx.Response(200, json={"Items": [], "TotalRecordCount": 0, "StartIndex": start})
        if req.url.host == "navidrome.test":
            if q.get("t") != hashlib.md5((PASSWORD + q.get("s", "")).encode()).hexdigest():
                return httpx.Response(200, json={"subsonic-response": {
                    "status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}})
            if path == "/rest/ping":
                return httpx.Response(200, json=ND["ping"])
            if path == "/rest/getMusicFolders":
                return httpx.Response(200, json=ND["music_folders"])
            if path == "/rest/getScanStatus":
                return httpx.Response(200, json=self.scan_status())
            if path == "/rest/getAlbumList2":
                o, n = int(q.get("offset", 0)), int(q.get("size", 10))
                return httpx.Response(200, json=_nd("albumList2", album=ND_ALBUMS[o:o + n]))
            if path == "/rest/search3":  # as Navidrome: an empty query lists every song, sliced by offset
                o, n = int(q.get("songOffset", 0)), int(q.get("songCount", 20))
                return httpx.Response(200, json=_nd("searchResult3", song=self.songs()[o:o + n]))
        return httpx.Response(404, json={"message": f"No route {path}"})

    def scan_status(self) -> dict:
        return ND["scan_status"]

    def songs(self) -> list[dict]:
        return ND_SONGS


READERS = {"jellyfin": reading.read_jellyfin, "navidrome": reading.read_navidrome}


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    """The fixture's 14 Jellyfin items in pages of 10 and 9 Navidrome songs (7 albums) in pages of 5, so paging
    shows (the default page is 500)."""
    monkeypatch.setattr(reading, "JELLYFIN_PAGE", JF_PAGE)
    monkeypatch.setattr(reading, "NAVIDROME_PAGE", ND_PAGE)


def _settings(tmp_path, legacy_db=None, **over):
    base = dict(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                jellyfin_url="http://jellyfin.test", jellyfin_key=KEY, jellyfin_user="listener",
                navidrome_url="http://navidrome.test", navidrome_user="reader", navidrome_password=PASSWORD)
    base.update(over)
    return Settings(**base)


@pytest.fixture
def srv():
    return Servers()


@pytest.fixture
def app_client(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db), server_transport=httpx.MockTransport(srv))
    app.state.readers = READERS
    return TestClient(app)


# --- the client --------------------------------------------------------------------------------------------

def test_client_code_has_no_verb_but_get():
    src = inspect.getsource(reading)
    assert not re.search(r"\.(post|put|patch|delete|request|stream|send|head|options)\(", src)
    assert not any(hasattr(reading.Client, v) for v in ("post", "put", "patch", "delete", "request", "stream", "send"))
    c = reading.Client("jellyfin", "http://jellyfin.test")
    try:  # the real transport: no retries, no redirects, a timeout
        assert c._http._transport._pool._retries == 0
        assert c._http.follow_redirects is False
        assert c._http.timeout.read == reading.TIMEOUT.read and c._http.timeout.connect == 5.0
    finally:
        c.close()


def test_refresh_sends_only_gets_and_stores_the_snapshot(app_client, srv, tmp_path):
    r = app_client.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    c = body["refresh"]["counts"]
    assert body["refresh"]["ok"] and body["refresh"]["error"] is None
    assert (c["items"], c["pages"], c["requests"], c["added"], c["removed"], c["before"]) == (14, 3, 6, 14, 0, None)
    assert {q.method for q in srv.requests} == {"GET"}
    assert [q.url.params.get("StartIndex") for q in srv.requests if q.url.path == "/Items"] == ["0", "10"]
    snap = store.snapshots(tmp_path / "data")["jellyfin"]
    assert len(snap["items"]) == 14 and snap["folders"] == ["/data/music"]
    # again: nothing new, logged twice, newest first
    c2 = app_client.post("/api/servers/jellyfin/refresh").json()["refresh"]["counts"]
    assert (c2["added"], c2["removed"], c2["before"]) == (0, 0, 14)
    log = app_client.get("/api/servers/jellyfin/refreshes").json()
    assert [e["counts"]["before"] for e in log["log"]] == [14, None] and log["last"]["ok"] and not log["running"]
    # the match now reads the new snapshot
    m = app_client.get("/api/servers/matches").json()
    assert {s["server"]: s["snapshot"] for s in m["snapshots"]} == {"jellyfin": True, "navidrome": False}


def test_navidrome_token_auth_never_sends_the_password(app_client, srv):
    r = app_client.post("/api/servers/navidrome/refresh")
    assert r.status_code == 200, r.text
    c = r.json()["refresh"]["counts"]
    assert (c["items"], c["pages"], c["requests"], c["hidden_paths"]) == (9, 4, 8, 4)
    salts = [q.url.params["s"] for q in srv.requests]
    assert len(set(salts)) == len(salts)  # a new salt per request
    assert all(PASSWORD not in str(q.url) and q.method == "GET" for q in srv.requests)
    assert all(q.url.params["u"] == "reader" and q.url.params["f"] == "json" for q in srv.requests)


def test_server_errors_show_the_servers_own_message(app_client, srv, tmp_path):
    app_client.post("/api/servers/jellyfin/refresh")
    srv.fail["/Items"] = httpx.Response(500, json={"Message": f"Database is locked (token {KEY})"})
    r = app_client.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["error"] == "server" and d["status"] == 500
    assert "Jellyfin answered 500 Internal Server Error (GET /Items): Database is locked" in d["message"]
    assert KEY not in r.text  # a secret the server echoes is blanked
    log = app_client.get("/api/servers/jellyfin/refreshes").json()["log"]
    assert not log[0]["ok"] and log[0]["error"] == d["message"] and log[0]["counts"]["requests"] == 3
    assert len(store.snapshots(tmp_path / "data")["jellyfin"]["items"]) == 14  # the snapshot before is kept


def test_wrong_key_and_wrong_password(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db, jellyfin_key="wrong", navidrome_password="wrong"),
                     server_transport=httpx.MockTransport(srv))
    app.state.readers = READERS
    c = TestClient(app)
    r = c.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 502 and r.json()["detail"]["message"] == (
        "Jellyfin answered 401 Unauthorized (GET /Library/VirtualFolders): Access token is invalid or expired.")
    r = c.post("/api/servers/navidrome/refresh")
    assert r.status_code == 502 and "Wrong username or password" in r.json()["detail"]["message"]


def test_timeouts_and_unreachable_servers_are_not_retried(app_client, srv):
    srv.fail["/Library/VirtualFolders"] = httpx.ReadTimeout("slow")
    r = app_client.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 502 and r.json()["detail"]["message"] == (
        "Jellyfin didn't answer in time (GET /Library/VirtualFolders).")
    assert len(srv.requests) == 2  # System/Info, then the folders once
    srv.fail["/Library/VirtualFolders"] = httpx.ConnectError("refused")
    r = app_client.post("/api/servers/jellyfin/refresh")
    assert r.json()["detail"]["message"] == "Couldn't reach Jellyfin (GET /Library/VirtualFolders): ConnectError."
    assert len(srv.requests) == 4  # one request each: no retries


def test_not_set_up_reads_nothing(legacy_db, tmp_path, srv):
    app = create_app(Settings(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1"),
                     server_transport=httpx.MockTransport(srv))
    app.state.readers = READERS
    c = TestClient(app)
    r = c.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["error"] == "not_set_up" and d["missing"] == ["TRAQFREQ_JELLYFIN_URL", "TRAQFREQ_JELLYFIN_KEY"]
    assert d["message"].startswith("Jellyfin is not set up")
    assert srv.requests == [] and store.refreshes(tmp_path / "data") == []
    s = {x["server"]: x for x in c.get("/api/servers").json()["servers"]}
    assert "refresh" not in s["plex"]
    assert s["jellyfin"]["refresh"]["set_up"] is False and s["jellyfin"]["refresh"]["last"] is None


def test_one_refresh_at_a_time_per_server(app_client, srv, tmp_path):
    lock = reading._lock(tmp_path / "data", "jellyfin")
    lock.acquire()
    try:
        r = app_client.post("/api/servers/jellyfin/refresh")
        assert r.status_code == 409 and r.json()["detail"]["error"] == "busy"
        assert app_client.get("/api/servers/jellyfin/refreshes").json()["running"] is True
        assert app_client.post("/api/servers/navidrome/refresh").status_code == 200  # the other server isn't held
    finally:
        lock.release()
    assert app_client.post("/api/servers/jellyfin/refresh").status_code == 200


def test_two_refreshes_at_once(legacy_db, tmp_path):
    gate, go = threading.Event(), threading.Event()

    def slow(client, settings):
        gate.set()
        go.wait(5)
        return reading.read_jellyfin(client, settings)

    s = _settings(tmp_path, legacy_db)
    t = httpx.MockTransport(Servers())
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("a", reading.refresh("jellyfin", s, t, {"jellyfin": slow})))
    th.start()
    gate.wait(5)
    with pytest.raises(reading.Busy):
        reading.refresh("jellyfin", s, t, READERS)
    go.set()
    th.join(5)
    assert out["a"]["ok"] and len(store.refreshes(s.data_dir, "jellyfin")) == 1


def test_shipped_readers_are_the_real_ones(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db), server_transport=httpx.MockTransport(srv))
    c = TestClient(app)  # the shipped readers
    assert reading.READERS == {"jellyfin": reading.read_jellyfin, "navidrome": reading.read_navidrome}
    assert c.post("/api/servers/navidrome/refresh").status_code == 200
    assert c.post("/api/servers/jellyfin/refresh").status_code == 200
    assert {s["server"]: s.get("note") for s in c.get("/api/servers").json()["servers"]}["navidrome"].startswith(
        "Set up; traqfreq reads it when you refresh it")


def test_plex_and_unknown_servers(app_client):
    r = app_client.post("/api/servers/plex/refresh")
    assert r.status_code == 400 and "jimbo-dj" in r.json()["detail"]["message"]
    assert app_client.post("/api/servers/emby/refresh").status_code == 404
    assert app_client.get("/api/servers/emby/refreshes").status_code == 404


def test_secrets_never_logged_or_returned(app_client, srv, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    srv.fail["/rest/search3"] = httpx.Response(503, text=f"upstream sad, p={PASSWORD}")
    texts = [app_client.post("/api/servers/jellyfin/refresh").text, app_client.post("/api/servers/navidrome/refresh").text,
             app_client.get("/api/servers").text, app_client.get("/api/servers/jellyfin/refreshes").text,
             app_client.get("/api/servers/navidrome/refreshes").text, caplog.text,
             (tmp_path / "data" / "traqfreq.sqlite").read_bytes().decode("latin-1")]
    for t in texts:
        assert KEY not in t and PASSWORD not in t
    tokens = [q.url.params["t"] for q in srv.requests if q.url.host == "navidrome.test"]
    assert tokens and not any(tok in caplog.text for tok in tokens)  # nor Navidrome's token (httpx's own log)
    assert "refresh jellyfin: 14 items" in caplog.text


def test_plays_on_servers_stay_beside(app_client, legacy_db):
    before_db = hashlib.sha256(Path(legacy_db).read_bytes()).hexdigest()
    track = app_client.get("/api/library/track/101").json()
    overview = app_client.get("/api/history/overview").json()
    assert app_client.post("/api/servers/jellyfin/refresh").status_code == 200
    assert app_client.post("/api/servers/navidrome/refresh").status_code == 200
    rows = app_client.get("/api/servers/matches?rating_key=101").json()["rows"]["rows"]
    assert any((r["right"] or {}).get("play_count") for r in rows)  # the server's plays are read, labelled
    t2 = app_client.get("/api/library/track/101").json()
    assert (t2["plays"], t2["history"]) == (track["plays"], track["history"])
    o2 = app_client.get("/api/history/overview").json()
    assert {k: v for k, v in o2.items() if k != "cache"} == {k: v for k, v in overview.items() if k != "cache"}
    assert hashlib.sha256(Path(legacy_db).read_bytes()).hexdigest() == before_db  # jimbo-dj's DB untouched


# --- paging ------------------------------------------------------------------------------------------------

def test_pages_stop_at_the_total_a_short_page_or_the_limit():
    data = list(range(23))
    fetch = lambda o: {"items": data[o:o + 10], "total": len(data)}  # noqa: E731
    got = list(reading.pages(fetch, lambda p: len(p["items"]), 10, lambda p: p["total"]))
    assert [len(p["items"]) for p in got] == [10, 10, 3]
    exact = list(range(20))
    calls = []
    def f2(o):
        calls.append(o)
        return {"items": exact[o:o + 10], "total": 20}
    assert len(list(reading.pages(f2, lambda p: len(p["items"]), 10, lambda p: p["total"]))) == 2 and calls == [0, 10]
    calls.clear()
    assert len(list(reading.pages(f2, lambda p: len(p["items"]), 10))) == 3 and calls == [0, 10, 20]  # no total: empty page ends it
    with pytest.raises(reading.ServerError, match="didn't end"):
        list(reading.pages(lambda o: {"items": [0] * 10}, lambda p: len(p["items"]), 10, max_pages=3))


# --- Jellyfin's reader (T17) -------------------------------------------------------------------------------

def _jf(srv, tmp_path, **over):
    s = _settings(tmp_path, **over)
    with reading.client_for("jellyfin", s, httpx.MockTransport(srv)) as client:
        return reading.read_jellyfin(client, s)


def test_jellyfin_reads_info_folders_items_and_one_users_plays(srv, tmp_path):
    snap, counts = _jf(srv, tmp_path)
    assert [q.url.path for q in srv.requests] == [
        "/System/Info/Public", "/Library/VirtualFolders", "/Items", "/Items", "/Users",
        f"/Users/{JF['users'][1]['Id']}/Items"]
    assert {q.method for q in srv.requests} == {"GET"}
    items_q = [q.url.params for q in srv.requests if q.url.path == "/Items"]
    assert [(p["StartIndex"], p["Limit"]) for p in items_q] == [("0", "10"), ("10", "10")]
    assert all(p["IncludeItemTypes"] == "Audio" and p["Recursive"] == "true"
               and p["Fields"] == "Path,ProviderIds,MediaSources,ParentId,DateCreated" for p in items_q)
    user_q = srv.requests[-1].url.params
    assert user_q["Filters"] == "IsPlayed" and user_q["IncludeItemTypes"] == "Audio"
    assert counts == {"pages": 3, "server_name": "Invented Jellyfin", "version": "10.10.3", "user": "listener", "played": 4}
    assert snap["stamp"] == {"items": 14, "newest_created": snap["stamp"]["newest_created"],
                             "server_name": "Invented Jellyfin", "version": "10.10.3", "user": "listener"}
    assert snap["folders"] == ["/data/music"] and len(snap["items"]) == 14
    assert {i["id"]: i["play_count"] for i in snap["items"] if i["play_count"]} == JF_PLAYED
    assert all(i["play_count"] == 0 for i in snap["items"] if i["id"] not in JF_PLAYED)
    # the same snapshot as the T14 parser makes from the fixture's own answers
    want = snapshots.from_jellyfin(JF["virtual_folders"], JF["items_pages"])
    assert [{k: v for k, v in i.items()} for i in snap["items"]] == want["items"]


def test_jellyfin_without_a_user_has_no_play_counts(srv, tmp_path):
    snap, counts = _jf(srv, tmp_path, jellyfin_user=None)
    assert not any(q.url.path.startswith("/Users") for q in srv.requests)
    assert all(i["play_count"] is None for i in snap["items"])
    assert counts["user"] is None and counts["played"] is None and snap["stamp"]["user"] is None


def test_jellyfin_user_by_id_or_name(srv, tmp_path):
    uid = JF["users"][1]["Id"]
    dashed = f"{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}".upper()
    for who in (uid, dashed, "LISTENER", " listener "):
        srv.requests.clear()
        assert _jf(srv, tmp_path, jellyfin_user=who)[1]["user"] == "listener"
        assert srv.requests[-1].url.path == f"/Users/{uid}/Items"


def test_jellyfin_unknown_user_fails_and_keeps_the_snapshot(legacy_db, tmp_path, srv):
    s = _settings(tmp_path, legacy_db)
    t = httpx.MockTransport(srv)
    reading.refresh("jellyfin", s, t)
    bad = _settings(tmp_path, legacy_db, jellyfin_user="nobody")
    with pytest.raises(reading.ServerError) as e:
        reading.refresh("jellyfin", bad, t)
    assert "no user has that name or ID" in e.value.message and "admin, listener" in e.value.message
    assert len(store.snapshots(s.data_dir)["jellyfin"]["items"]) == 14
    assert store.refreshes(s.data_dir, "jellyfin")[0]["ok"] is False


def test_jellyfin_items_dont_depend_on_the_user(srv, tmp_path):
    """A user who sees no library gives no play counts, and takes no items away."""
    s = _settings(tmp_path)
    other = dict(JF["users"][0])
    JF["users"].append({**other, "Name": "kid", "Id": "e0000000000000000000000000000003"})
    try:
        snap, counts = _jf(srv, tmp_path, jellyfin_user="kid")
    finally:
        JF["users"].pop()
    assert len(snap["items"]) == 14 and counts["played"] == 0
    assert all(i["play_count"] == 0 for i in snap["items"])
    assert s.jellyfin_user == "listener"


def test_jellyfin_default_page_is_one_request_for_the_fixture(srv, tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "JELLYFIN_PAGE", reading.PAGE_SIZE)
    snap, counts = _jf(srv, tmp_path)
    assert [q.url.params["Limit"] for q in srv.requests if q.url.path == "/Items"] == ["500"]
    assert counts["pages"] == 2 and len(snap["items"]) == 14


def test_jellyfin_name_and_version_on_servers(app_client):
    assert app_client.post("/api/servers/jellyfin/refresh").status_code == 200
    m = app_client.get("/api/servers/matches").json()
    jf = next(x for x in m["snapshots"] if x["server"] == "jellyfin")
    assert (jf["stamp"]["server_name"], jf["stamp"]["version"], jf["stamp"]["user"]) == ("Invented Jellyfin", "10.10.3", "listener")
    log = app_client.get("/api/servers/jellyfin/refreshes").json()["last"]["counts"]
    assert (log["server_name"], log["version"], log["user"], log["play_counts"]) == ("Invented Jellyfin", "10.10.3", "listener", 4)
    pair = next(p for p in m["pairs"] if p["pair"] == "jellyfin")
    assert pair["tiers"].get("file", 0) >= 4


class Scanning(Servers):
    """Jellyfin with a scan running: after the first /Items page, a new item appears at the front of the list."""

    def __init__(self, sort_ok: bool):
        super().__init__()
        self.sort_ok, self.calls = sort_ok, 0

    def __call__(self, req):
        global JF_ITEMS
        if req.url.path == "/Items":
            self.calls += 1
            if self.calls == 2:
                new = dict(JF_ITEMS[0], Id="a00000000000000000000000000new01", Path="/data/music/New/Song.flac")
                # sorted oldest first, the new item goes last; unsorted (as before T17's fix) it goes first
                JF_ITEMS = JF_ITEMS + [new] if self.sort_ok else [new] + JF_ITEMS
        return super().__call__(req)


def test_jellyfin_torn_read_is_not_stored(legacy_db, tmp_path, monkeypatch):
    s = _settings(tmp_path, legacy_db)
    reading.refresh("jellyfin", s, httpx.MockTransport(Servers()))
    monkeypatch.setattr(__import__(__name__), "JF_ITEMS", list(JF_ITEMS))
    with pytest.raises(reading.ServerError) as e:  # an item read twice: the list moved under the pages
        reading.refresh("jellyfin", s, httpx.MockTransport(Scanning(sort_ok=False)))
    assert "changed while traqfreq read it (14 distinct items of 15, 1 read twice)" in e.value.message
    assert len(store.snapshots(s.data_dir)["jellyfin"]["items"]) == 14 and not store.refreshes(s.data_dir, "jellyfin")[0]["ok"]


def test_jellyfin_reads_oldest_first_so_a_scan_adds_at_the_end(legacy_db, tmp_path, monkeypatch):
    s = _settings(tmp_path, legacy_db)
    monkeypatch.setattr(__import__(__name__), "JF_ITEMS", list(JF_ITEMS))
    srv = Scanning(sort_ok=True)
    entry = reading.refresh("jellyfin", s, httpx.MockTransport(srv))
    assert entry["ok"] and entry["counts"]["items"] == 15
    q = [r.url.params for r in srv.requests if r.url.path == "/Items"][0]
    assert (q["SortBy"], q["SortOrder"]) == ("DateCreated,SortName", "Ascending")


# --- Navidrome's reader (T18) ------------------------------------------------------------------------------

def _read_nd(srv, tmp_path, **over):
    s = _settings(tmp_path, **over)
    with reading.client_for("navidrome", s, httpx.MockTransport(srv)) as client:
        return reading.read_navidrome(client, s)


def test_navidrome_reads_ping_folders_scan_albums_and_songs(srv, tmp_path):
    snap, counts = _read_nd(srv, tmp_path)
    assert [q.url.path for q in srv.requests] == [
        "/rest/ping", "/rest/getMusicFolders", "/rest/getScanStatus", "/rest/getAlbumList2", "/rest/getAlbumList2",
        "/rest/search3", "/rest/search3", "/rest/getScanStatus"]
    assert {q.method for q in srv.requests} == {"GET"}
    albums_q = [q.url.params for q in srv.requests if q.url.path == "/rest/getAlbumList2"]
    assert [(p["type"], p["size"], p["offset"]) for p in albums_q] == [("alphabeticalByName", "5", "0"),
                                                                       ("alphabeticalByName", "5", "5")]
    songs_q = [q.url.params for q in srv.requests if q.url.path == "/rest/search3"]
    assert [(p["query"], p["songCount"], p["songOffset"], p["albumCount"], p["artistCount"]) for p in songs_q] == [
        ("", "5", "0", "0", "0"), ("", "5", "5", "0", "0")]
    assert counts == {"pages": 4, "album_pages": 2, "song_pages": 2, "albums": 7, "server_name": "navidrome",
                      "version": "0.53.3 (invented)", "user": "reader", "music_folders": 1, "played": 4}
    st = snap["stamp"]
    assert (st["server_name"], st["version"], st["user"], st["open_subsonic"]) == ("navidrome", "0.53.3 (invented)", "reader", True)
    assert (st["items"], st["scan_count"], st["last_scan"], st["hidden_paths"]) == (9, 9, "2026-11-23T03:00:00Z", 4)
    assert st["music_folders"] == ["Invented Music"]


def test_navidrome_items_are_t14s(srv, tmp_path):
    snap, _ = _read_nd(srv, tmp_path)
    t14 = snapshots.from_navidrome(ND["scan_status"], ND["album_pages"], ND["song_pages"])
    assert snap["items"] == t14["items"] and (snap["folders"], snap["folder_source"]) == (["/music"], "common")
    assert sum(1 for i in snap["items"] if i["mb_release"]) == sum(1 for i in t14["items"] if i["mb_release"]) > 0


class NoPlayCount(Servers):
    """As OpenSubsonic: a song never played has no playCount at all."""

    def songs(self):
        return [{k: v for k, v in s.items() if not (k == "playCount" and not v)} for s in ND_SONGS]


def test_navidrome_unplayed_songs_count_zero(tmp_path):
    snap, counts = _read_nd(NoPlayCount(), tmp_path)
    assert sorted(i["play_count"] for i in snap["items"]) == [0, 0, 0, 0, 0, 1, 2, 3, 5] and counts["played"] == 4


def test_navidrome_roots_setting(srv, tmp_path, legacy_db):
    snap, _ = _read_nd(srv, tmp_path, navidrome_roots=("/music/Kollektiv Nord/",))
    assert (snap["folders"], snap["folder_source"]) == (["/music/Kollektiv Nord"], "server")
    assert [i["file"] for i in snap["items"] if i["path"] == "/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac"] == [
        "Ringbahn/01 Westkreuz.flac"]
    s = Settings.from_env({"TRAQFREQ_NAVIDROME_ROOTS": " /music , /other/ "})
    assert s.navidrome_roots == ("/music", "/other/")
    c = TestClient(create_app(_settings(tmp_path, legacy_db, navidrome_roots=("/music",))))
    nd = {x["server"]: x for x in c.get("/api/servers").json()["servers"]}["navidrome"]
    assert {r["env"]: r["value"] for r in nd["settings"]}["TRAQFREQ_NAVIDROME_ROOTS"] == "/music"


class NavidromeScanning(Servers):
    """Navidrome while its library changes: ``mode`` says how."""

    def __init__(self, mode: str):
        super().__init__()
        self.mode, self.scans, self.search = mode, 0, 0

    def scan_status(self):
        self.scans += 1
        st = dict(ND["scan_status"]["subsonic-response"]["scanStatus"])
        if self.mode == "running":
            st["scanning"] = True
        if self.mode == "finished" and self.scans == 2:
            st["lastScan"] = "2026-11-23T04:00:00Z"
        if self.mode == "count":
            st["count"] = 10
        return _nd("scanStatus", **st)

    def songs(self):
        if self.mode == "shift" and self.search >= 1:  # a new song lands at the front after the first page
            return [dict(ND_SONGS[0], id="b00000000000000000000000000new01")] + ND_SONGS
        return ND_SONGS

    def __call__(self, req):
        out = super().__call__(req)
        if req.url.path == "/rest/search3":
            self.search += 1
        return out


@pytest.mark.parametrize("mode,why", [
    ("running", "9 distinct songs of 9; a library scan was running"),
    ("finished", "9 distinct songs of 9; a library scan finished during the read"),
    ("count", "9 distinct songs of 10; the song list moved under the pages"),
    ("shift", "9 distinct songs of 9, 1 read twice; the song list moved under the pages"),
])
def test_navidrome_torn_read_is_not_stored(legacy_db, tmp_path, mode, why):
    s = _settings(tmp_path, legacy_db)
    reading.refresh("navidrome", s, httpx.MockTransport(Servers()))
    with pytest.raises(reading.ServerError) as e:
        reading.refresh("navidrome", s, httpx.MockTransport(NavidromeScanning(mode)))
    assert f"Navidrome's song list changed while traqfreq read it ({why}). Nothing was stored" in e.value.message
    assert len(store.snapshots(s.data_dir)["navidrome"]["items"]) == 9
    assert [r["ok"] for r in store.refreshes(s.data_dir, "navidrome")] == [False, True]


def test_navidrome_failed_answer_is_its_own_message(srv, tmp_path):
    srv.fail["/rest/getMusicFolders"] = httpx.Response(200, json={"subsonic-response": {
        "status": "failed", "error": {"code": 50, "message": "User not authorized"}}})
    with pytest.raises(reading.ServerError) as e:
        _read_nd(srv, tmp_path)
    assert e.value.message == "Navidrome said 'User not authorized' (Subsonic error 50)."
    assert [q.url.path for q in srv.requests] == ["/rest/ping", "/rest/getMusicFolders"]


def test_navidrome_default_page_is_one_request_each_for_the_fixture(srv, tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "NAVIDROME_PAGE", reading.PAGE_SIZE)
    snap, counts = _read_nd(srv, tmp_path)
    assert [q.url.params["songCount"] for q in srv.requests if q.url.path == "/rest/search3"] == ["500"]
    assert counts["pages"] == 2 and len(snap["items"]) == 9


def test_navidrome_name_and_version_on_servers(app_client):
    assert app_client.post("/api/servers/navidrome/refresh").status_code == 200
    m = app_client.get("/api/servers/matches").json()
    nd = next(x for x in m["snapshots"] if x["server"] == "navidrome")
    assert (nd["stamp"]["server_name"], nd["stamp"]["version"], nd["stamp"]["user"]) == ("navidrome", "0.53.3 (invented)", "reader")
    log = app_client.get("/api/servers/navidrome/refreshes").json()["last"]["counts"]
    assert (log["items"], log["albums"], log["play_counts"], log["hidden_paths"]) == (9, 7, 4, 4)
    pair = next(p for p in m["pairs"] if p["pair"] == "navidrome")
    assert pair["unmatched_left"].get("hidden_path", 0) >= 1 and sum(pair["tiers"].values()) >= 1
