"""T16/T17: reading servers (docs/specs/t13-servers.md): the read-only client, paging, errors, refresh and its log,
and Jellyfin's reader (T17).

No network: every answer comes from ``httpx.MockTransport`` serving the invented answers in
``scripts/fixture_jellyfin.json`` and ``fixture_navidrome.json``. Jellyfin is read by the real reader
(``reading.read_jellyfin``); the Navidrome reader here stands in for T18's.
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
            if req.headers.get("X-Emby-Token") != KEY:
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
            if path == "/rest/getScanStatus":
                return httpx.Response(200, json=ND["scan_status"])
            if path == "/rest/getAlbumList2":
                return httpx.Response(200, json=ND["album_pages"][0])
            if path == "/rest/search3":
                i = int(q.get("songOffset", 0)) // ND_PAGE
                pages = ND["song_pages"]
                return httpx.Response(200, json=pages[i] if i < len(pages) else {
                    "subsonic-response": {"status": "ok", "searchResult3": {}}})
        return httpx.Response(404, json={"message": f"No route {path}"})


def read_navidrome(client, settings):
    """Stands in for T18's reader: scan status, albums, then every song through search3."""
    scan = client.get("/rest/getScanStatus")
    albums = [client.get("/rest/getAlbumList2", {"type": "alphabeticalByName", "size": 500, "offset": 0})]
    songs = list(reading.pages(
        lambda o: client.get("/rest/search3", {"query": "", "songCount": ND_PAGE, "songOffset": o, "albumCount": 0, "artistCount": 0}),
        count=lambda p: len(((p.get("subsonic-response") or {}).get("searchResult3") or {}).get("song") or []), size=ND_PAGE))
    return snapshots.from_navidrome(scan, albums, songs), {"pages": len(albums) + len(songs)}


READERS = {"jellyfin": reading.read_jellyfin, "navidrome": read_navidrome}


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    """The fixture's 14 items in pages of 10, so paging shows (Jellyfin's default page is 500)."""
    monkeypatch.setattr(reading, "JELLYFIN_PAGE", JF_PAGE)


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
    assert (c["items"], c["pages"], c["hidden_paths"]) == (9, 3, 4)
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


def test_navidrome_reader_waits_for_t18(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db), server_transport=httpx.MockTransport(srv))
    c = TestClient(app)  # the shipped readers
    assert reading.READERS["jellyfin"] is reading.read_jellyfin
    r = c.post("/api/servers/navidrome/refresh")
    assert r.status_code == 501 and "reader comes in T18" in r.json()["detail"]["message"]
    assert srv.requests == []
    assert c.get("/api/servers/navidrome/refreshes").json()["last"]["ok"] is False
    assert c.post("/api/servers/jellyfin/refresh").status_code == 200  # Jellyfin's is T17's, shipped


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
               and p["Fields"] == "Path,ProviderIds,MediaSources,ParentId" for p in items_q)
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
