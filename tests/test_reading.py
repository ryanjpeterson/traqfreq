"""T16: reading servers (docs/specs/t13-servers.md): the read-only client, paging, errors, refresh and its log.

No network: every answer comes from ``httpx.MockTransport`` serving the invented answers in
``scripts/fixture_jellyfin.json`` and ``fixture_navidrome.json``. The readers here stand in for T17's and T18's.
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
            if req.headers.get("X-Emby-Token") != KEY:
                return httpx.Response(401, text="Access token is invalid or expired.")
            if path == "/Library/VirtualFolders":
                return httpx.Response(200, json=JF["virtual_folders"])
            if path == "/Items":
                start = int(q.get("StartIndex", 0))
                return httpx.Response(200, json=JF["items_pages"][start // JF_PAGE])
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


def read_jellyfin(client, settings):
    """Stands in for T17's reader: folders, then /Items page by page."""
    folders = client.get("/Library/VirtualFolders")
    got = list(reading.pages(
        lambda o: client.get("/Items", {"IncludeItemTypes": "Audio", "Recursive": "true", "StartIndex": o, "Limit": JF_PAGE}),
        count=lambda p: len(p.get("Items") or []), size=JF_PAGE, total=lambda p: p.get("TotalRecordCount")))
    return snapshots.from_jellyfin(folders, got), {"pages": len(got)}


def read_navidrome(client, settings):
    """Stands in for T18's reader: scan status, albums, then every song through search3."""
    scan = client.get("/rest/getScanStatus")
    albums = [client.get("/rest/getAlbumList2", {"type": "alphabeticalByName", "size": 500, "offset": 0})]
    songs = list(reading.pages(
        lambda o: client.get("/rest/search3", {"query": "", "songCount": ND_PAGE, "songOffset": o, "albumCount": 0, "artistCount": 0}),
        count=lambda p: len(((p.get("subsonic-response") or {}).get("searchResult3") or {}).get("song") or []), size=ND_PAGE))
    return snapshots.from_navidrome(scan, albums, songs), {"pages": len(albums) + len(songs)}


READERS = {"jellyfin": read_jellyfin, "navidrome": read_navidrome}


def _settings(tmp_path, legacy_db=None, **over):
    base = dict(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                jellyfin_url="http://jellyfin.test", jellyfin_key=KEY,
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
    assert (c["items"], c["pages"], c["requests"], c["added"], c["removed"], c["before"]) == (14, 2, 3, 14, 0, None)
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
    assert not log[0]["ok"] and log[0]["error"] == d["message"] and log[0]["counts"]["requests"] == 2
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
    assert len(srv.requests) == 1
    srv.fail["/Library/VirtualFolders"] = httpx.ConnectError("refused")
    r = app_client.post("/api/servers/jellyfin/refresh")
    assert r.json()["detail"]["message"] == "Couldn't reach Jellyfin (GET /Library/VirtualFolders): ConnectError."
    assert len(srv.requests) == 2  # one request each: no retries


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
        return read_jellyfin(client, settings)

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


def test_readers_wait_for_t17_and_t18(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db), server_transport=httpx.MockTransport(srv))
    c = TestClient(app)  # the shipped readers
    r = c.post("/api/servers/jellyfin/refresh")
    assert r.status_code == 501 and "reader comes in T17" in r.json()["detail"]["message"]
    assert "T18" in c.post("/api/servers/navidrome/refresh").json()["detail"]["message"]
    assert srv.requests == []
    assert c.get("/api/servers/jellyfin/refreshes").json()["last"]["ok"] is False


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
