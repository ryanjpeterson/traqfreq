"""T30: traqfreq's Plex sync (jimbo-dj's, vendored) and watcher, writing only library.sqlite and only once the plex
cut-over is owned; the runs log; the switch-off check. Plex is a stand-in (httpx.MockTransport), as T16–T18 did for
Jellyfin and Navidrome. Only against the fixture from scripts/make_fixture.py (invented rows)."""

import hashlib
import json
import sqlite3
from dataclasses import replace
from xml.sax.saxutils import quoteattr

import httpx
import pytest
from fastapi.testclient import TestClient

from traqfreq import own, plexsync
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import config, db, watcher

TOKEN = "invented-plex-token-0451"
# The fixture's local paths: three artists' folders mapped, Ada Vey's left out (track 105 has no local path).
PATH_MAP = ",".join(f"/music/{a}=/srv/music/{a}" for a in ("Kollektiv Nord", "The Paper Lanterns", "Former Band"))


def _digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rw(p):
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


def _a(**kw):
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


class FakePlex:
    """Plex's answers for the fixture's library: tracks 101–104 as the fixture has them, a new track 107, and 105
    gone from Plex. Records every request; anything but GET fails the test."""

    def __init__(self, scanning=False, down=False):
        self.requests: list[httpx.Request] = []
        self.scanning = scanning
        self.down = down
        self.tracks = [
            (101, "Westkreuz", 201, 301, "Kollektiv Nord", "Ringbahn", "/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac", 39400000),
            (102, "Ostkreuz", 201, 301, "Kollektiv Nord", "Ringbahn", "/music/Kollektiv Nord/Ringbahn/02 Ostkreuz.flac", 4800000),
            (103, "Harbour Lights", 202, 302, "The Paper Lanterns", "Low Tide Radio", "/music/The Paper Lanterns/Low Tide Radio/01 Harbour Lights.flac", 7100000),
            (104, "Static Gulls", 202, 302, "The Paper Lanterns", "Low Tide Radio", "/music/The Paper Lanterns/Low Tide Radio/02 Static Gulls.flac", 9800000),
            (107, "Neue Linie", 205, 301, "Kollektiv Nord", "Ringbahn II", "/music/Kollektiv Nord/Ringbahn II/01 Neue Linie.flac", 30100000),
        ]

    def transport(self):
        return httpx.MockTransport(self.handle)

    def _track(self, t, streams=False):
        rk, title, alk, ark, artist, album, path, size = t
        stream = f'<Stream {_a(streamType=2, bitDepth=24, samplingRate=96000)}/>' if streams else ""
        tags = '<Genre tag="Black Metal"/><Mood tag="Brooding"/>' if streams else ""
        return (f'<Track {_a(ratingKey=rk, guid=f"plex://track/{rk}", title=title, grandparentTitle=artist, parentTitle=album, parentRatingKey=alk, grandparentRatingKey=ark, index=1, parentIndex=1, parentYear=2024, duration=240000, addedAt=1794000000 + rk, updatedAt=1794100000 + rk, viewCount=3)}>'
                f'<Media {_a(audioCodec="flac", bitrate=1100, audioChannels=2, container="flac")}>'
                f'<Part {_a(file=path, size=size, container="flac")}>{stream}</Part></Media>{tags}</Track>')

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.method == "GET"
        if self.down:
            return httpx.Response(500, text="boom")
        path, q = request.url.path, request.url.params
        if path == "/":
            body = f'<MediaContainer {_a(friendlyName="Stand-in Plex", version="1.41.2", machineIdentifier="standin0", myPlexSubscription=1)}/>'
        elif path == "/library/sections":
            body = (f'<MediaContainer><Directory {_a(key=7, title="Audiobooks", type="artist")}/>'
                    f'<Directory {_a(key=5, title="Music", type="artist", refreshing=int(self.scanning))}/>'
                    f'<Directory {_a(key=2, title="Films", type="movie")}/></MediaContainer>')
        elif path == "/library/sections/5/all":
            kind = q.get("type")
            if kind == "10" and q.get("sort"):
                field = q["sort"].split(":")[0]
                newest = max(self.tracks, key=lambda t: t[0])
                body = (f'<MediaContainer totalSize="{len(self.tracks)}" size="1">'
                        f'<Track {_a(ratingKey=newest[0], **{field: 1794000000 + newest[0]})}/></MediaContainer>')
            elif kind == "10":
                start = int(q.get("X-Plex-Container-Start", 0))
                page = self.tracks[start:start + int(q.get("X-Plex-Container-Size", 2000))]
                body = (f'<MediaContainer totalSize="{len(self.tracks)}">'
                        + "".join(self._track(t) for t in page) + "</MediaContainer>")
            elif kind == "9":
                body = (f'<MediaContainer totalSize="2">'
                        f'<Directory {_a(ratingKey=201, title="Ringbahn", parentRatingKey=301, year=2019, originallyAvailableAt="2019-04-12", studio="Spree Tonträger")}><Genre tag="Black Metal"/></Directory>'
                        f'<Directory {_a(ratingKey=205, title="Ringbahn II", parentRatingKey=301, year=2024)}><Genre tag="Black Metal"/><Guid id="mbid://00000000-0000-4000-8000-000000000205"/></Directory>'
                        "</MediaContainer>")
            elif kind == "8":
                body = (f'<MediaContainer totalSize="1"><Directory {_a(ratingKey=301, title="Kollektiv Nord")}>'
                        '<Country tag="Germany"/><Genre tag="Black Metal"/></Directory></MediaContainer>')
            else:
                return httpx.Response(404)
        elif path.startswith("/library/metadata/"):
            keys = {int(k) for k in path.rsplit("/", 1)[1].split(",")}
            body = "<MediaContainer>" + "".join(self._track(t, True) for t in self.tracks if t[0] in keys) + "</MediaContainer>"
        else:
            return httpx.Response(404)
        return httpx.Response(200, text=body, headers={"Content-Type": "application/xml"})


@pytest.fixture
def settings(legacy_db, tmp_path):
    return Settings(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                    plex_url="http://plex.test:32400", plex_token=TOKEN, plex_section="Music", plex_path_map=PATH_MAP)


@pytest.fixture
def owned(settings):
    own.copy(settings.legacy_db, settings.data_dir, "plex", "T30 test")
    return settings


@pytest.fixture(autouse=True)
def _reset_watcher():
    yield
    config.CURRENT = None
    watcher._state.update(started=False, checked_at=None, changed_at=None, scanning=False, error=None)


def test_refused_before_the_copy(settings):
    plex = FakePlex()
    with pytest.raises(plexsync.SyncRefused, match="isn't owned by traqfreq"):
        plexsync.run(settings, "T30 test", plex.transport())
    assert not plex.requests  # Plex isn't even asked
    assert not own.path(settings.data_dir).exists()  # a refusal never creates library.sqlite
    with pytest.raises(db.NotOwned):  # the vendored db stand-in refuses by itself too
        db.connect(own.path(settings.data_dir))


def test_refused_after_rollback(owned):
    own.rollback(owned.data_dir, "plex", "T30 test")
    with pytest.raises(plexsync.SyncRefused, match="rolled back"):
        plexsync.run(owned, "T30 test", FakePlex().transport())
    r = own.runs(owned.data_dir)[0]
    assert r["job"] == "plex_sync" and not r["ok"] and r["note"].startswith("Refused:")
    assert r["undo"] == plexsync.NOTHING


def test_sync_writes_only_library_sqlite(owned):
    legacy_before = _digest(owned.legacy_db)
    plex = FakePlex()
    out = plexsync.run(owned, "T30 test", plex.transport())
    assert _digest(owned.legacy_db) == legacy_before  # jimbo-dj's file untouched
    assert out["ok"] and out["tracks"] == 5 and out["removed"] == 1 and out["albums"] == 2 and out["artists"] == 1
    # every request a GET, the token in its header, never in a URL
    assert plex.requests and all(r.method == "GET" for r in plex.requests)
    assert all(r.headers["X-Plex-Token"] == TOKEN and TOKEN not in str(r.url) for r in plex.requests)
    lib = _rw(own.path(owned.data_dir))
    t = {r["rating_key"]: r for r in lib.execute("SELECT * FROM tracks")}
    assert t[107]["title"] == "Neue Linie" and t[107]["local_path"] == "/srv/music/Kollektiv Nord/Ringbahn II/01 Neue Linie.flac"
    assert t[105]["removed_at"] is not None  # gone from Plex
    assert t[106]["removed_at"] == 1793239200  # already gone: untouched
    assert t[101]["local_path"] == "/srv/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac"  # jimbo-dj's path kept
    assert t[103]["bit_depth"] == 24 and t[103]["stream_size"] == 7100000  # streams read where size moved
    assert json.loads(t[103]["plex_genres"]) == ["Black Metal"]
    assert lib.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()[0] == str(t[107]["seen_at"])
    assert json.loads(lib.execute("SELECT value FROM meta WHERE key='server'").fetchone()[0])["section_key"] == "5"
    assert lib.execute("SELECT mbid FROM albums WHERE album_key=205").fetchone()[0] == "00000000-0000-4000-8000-000000000205"
    # the run log
    r = own.runs(owned.data_dir)[0]
    assert r["ok"] and r["reason"] == "T30 test" and r["counts"]["tracks"] == 5 and r["undo"] == plexsync.UNDO
    assert "5 tracks read from Plex" in r["note"] and r["seconds"] >= 0
    # every page reads it through the reading connection; jimbo-dj's own copy is unchanged
    conn = own.reader(owned.legacy_db, owned.data_dir)
    assert conn.execute("SELECT COUNT(*) FROM tracks WHERE removed_at IS NULL").fetchone()[0] == 5
    assert conn.execute("SELECT title FROM tracks WHERE rating_key=107").fetchone()[0] == "Neue Linie"
    assert _rw(owned.legacy_db).execute("SELECT COUNT(*) FROM tracks WHERE rating_key=107").fetchone()[0] == 0


def test_wrong_path_map_refused_before_writing(owned):
    lib_before = [tuple(r) for r in _rw(own.path(owned.data_dir)).execute("SELECT * FROM tracks ORDER BY rating_key")]
    plex = FakePlex()
    with pytest.raises(plexsync.SyncRefused, match="TRAQFREQ_PLEX_PATH_MAP doesn't give jimbo-dj's paths"):
        plexsync.run(replace(owned, plex_path_map="/music=/srv/music"), "T30 test", plex.transport())
    assert not plex.requests
    assert [tuple(r) for r in _rw(own.path(owned.data_dir)).execute("SELECT * FROM tracks ORDER BY rating_key")] == lib_before
    r = own.runs(owned.data_dir)[0]
    assert not r["ok"] and r["counts"]["path_map"]["differ"] == 1  # Ada Vey's track would get a path


def test_settings_needed(owned):
    with pytest.raises(plexsync.SyncRefused, match="TRAQFREQ_PLEX_TOKEN"):
        plexsync.run(replace(owned, plex_token=None), "T30 test", FakePlex().transport())
    with pytest.raises(plexsync.SyncRefused, match="TRAQFREQ_PLEX_URL"):
        plexsync.run(replace(owned, plex_url=None), "T30 test", FakePlex().transport())
    with pytest.raises(plexsync.SyncRefused, match="reason"):
        plexsync.run(owned, " ", FakePlex().transport())
    assert TOKEN not in repr(owned) and TOKEN not in repr(plexsync.config_for(owned))


def test_two_music_libraries_need_a_section(owned):
    # jimbo-dj's rule (plex.music_section): with two music libraries, PLEX_MUSIC_SECTION picks one
    with pytest.raises(plexsync.SyncFailed, match="Set PLEX_MUSIC_SECTION; music libraries found: Audiobooks, Music"):
        plexsync.run(replace(owned, plex_section=None), "T30 test", FakePlex().transport())


def test_plex_down_is_logged_without_the_token(owned):
    with pytest.raises(plexsync.SyncFailed) as e:
        plexsync.run(owned, "T30 test", FakePlex(down=True).transport())
    assert "500" in str(e.value) and TOKEN not in str(e.value)
    r = own.runs(owned.data_dir)[0]
    assert not r["ok"] and r["note"].startswith("Failed:") and TOKEN not in json.dumps(r)


def test_watcher(owned, monkeypatch):
    assert not watcher.enabled()  # off unless TRAQFREQ_WATCH is on
    assert plexsync.start_watcher(owned) is False
    monkeypatch.setenv("TRAQFREQ_WATCH", "on")
    monkeypatch.setenv("TRAQFREQ_WATCH_INTERVAL", "5")
    assert watcher.enabled() and watcher.interval() == 60  # at least a minute, as jimbo-dj's
    plex = FakePlex()
    config.CURRENT = plexsync.config_for(owned, plex.transport())
    on_change = lambda why: plexsync._on_change(owned, plex.transport(), why)  # noqa: E731
    assert watcher.check(on_change) == "synced: first look"
    assert watcher.check(on_change) == "nothing new"
    plex.tracks.append((108, "Spätzug", 205, 301, "Kollektiv Nord", "Ringbahn II",
                        "/music/Kollektiv Nord/Ringbahn II/02 Spätzug.flac", 28000000))
    plex.scanning = True
    assert watcher.check(on_change) == "Plex is scanning; waiting for it to finish"
    plex.scanning = False
    assert watcher.check(on_change) == "synced: +1 tracks"
    reasons = [r["reason"] for r in own.runs(owned.data_dir)]
    assert reasons == ["Watcher: Plex changed (+1 tracks)", "Watcher: Plex changed (first look)"]
    assert all(r.method == "GET" for r in plex.requests)


def test_watcher_never_writes_before_the_copy(settings):
    plex = FakePlex()
    config.CURRENT = plexsync.config_for(settings, plex.transport())
    with pytest.raises(db.NotOwned):
        watcher.check(lambda why: plexsync._on_change(settings, plex.transport(), why))
    assert not own.path(settings.data_dir).exists()


def test_switch_off_check(owned):
    rec = own.record(owned.data_dir, "plex")
    clean = own.switch_off(owned.legacy_db, rec)
    assert clean["clean"] and clean["missed"] == 0
    # traqfreq's own sync moves only traqfreq's copy: jimbo-dj's side stays clean
    plexsync.run(owned, "T30 test", FakePlex().transport())
    assert own.switch_off(owned.legacy_db, rec)["clean"]
    # jimbo-dj writes after the switch-off (stands in for a manual Sync and an import in jimbo-dj)
    j = _rw(owned.legacy_db)
    j.execute("INSERT INTO listens (id, source, started_at, artist, title, match_key) "
              "VALUES (10, 'lastfm', 1794200000, 'Ada Vey', 'Coil', 'ada vey|coil')")
    j.execute("INSERT INTO history_imports (id, source, at, rows, added) VALUES (4, 'lastfm', 1794200100, 1, 1)")
    j.execute("UPDATE tracks SET seen_at = 1794200200 WHERE rating_key = 101")
    j.execute("UPDATE meta SET value = '1794200200' WHERE key = 'last_sync'")
    j.commit()
    out = own.switch_off(owned.legacy_db, rec)
    assert not out["clean"] and out["missed"] == 3
    by = {t["table"]: t for t in out["tables"]}
    assert by["listens"]["new"] == 1 and by["listens"]["now"] == by["listens"]["copied"] + 1
    assert by["listens"]["examples"] == [{"id": 10, "source": "lastfm", "started_at": 1794200000, "artist": "Ada Vey",
                                          "title": "Coil"}]
    assert by["history_imports"]["examples"][0]["id"] == 4
    assert by["tracks"]["new"] == 1 and by["tracks"]["examples"][0]["rating_key"] == 101
    assert by["tracks"]["now"] == by["tracks"]["copied"]  # same count, still caught
    assert by["albums"]["new"] == 0 and not by["albums"]["moved"]
    assert out["marks"]["last_sync"] == {"copied": "1793844000", "now": "1794200200", "moved": True}
    assert out["marks"]["max_listen_id"]["moved"] and out["marks"]["last_import_at"]["moved"]


def test_api_cutovers(legacy_db, tmp_path, monkeypatch):
    s = Settings(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                 plex_url="http://plex.test:32400", plex_token=TOKEN, plex_section="Music", plex_path_map=PATH_MAP)
    c = TestClient(create_app(s))
    before = c.get("/api/cutovers")
    assert before.status_code == 200
    body = before.json()
    assert body["cutovers"][0]["switch_off"] is None and body["runs"] == []
    assert body["watcher"]["enabled"] is False
    assert body["plex"] == {"url": "http://plex.test:32400", "token_set": True, "section": "Music", "path_map": PATH_MAP,
                            "env": ["TRAQFREQ_PLEX_URL", "TRAQFREQ_PLEX_TOKEN", "TRAQFREQ_PLEX_MUSIC_SECTION",
                                    "TRAQFREQ_PLEX_PATH_MAP"]}
    own.copy(legacy_db, s.data_dir, "plex", "T30 test")
    plexsync.run(s, "T30 test", FakePlex().transport())
    r = c.get("/api/cutovers")
    assert TOKEN not in r.text
    rec = r.json()["cutovers"][0]
    assert rec["state"] == "owned" and rec["switch_off"]["clean"] is True
    assert r.json()["runs"][0]["ok"] is True


def test_command_sync_refused(legacy_db, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRAQFREQ_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TRAQFREQ_LEGACY_DB", str(legacy_db))
    monkeypatch.setenv("TRAQFREQ_PLEX_TOKEN", TOKEN)
    assert own.main(["sync", "--reason", "T30 test"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("refused:") and "isn't owned" in out and TOKEN not in out
