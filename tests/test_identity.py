"""T13: track identity, the Plex side (docs/specs/t13-servers.md), and the three servers' status."""

import shutil
import sqlite3
import unicodedata

import pytest
from fastapi.testclient import TestClient

from traqfreq import identity, legacy, servers
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor.jimbodj_history import match_key

SYNC = 1793844000

# Invented problem cases, added to a scratch copy only (the shared fixture's counts stay as they are):
# rating_key, title, artist, track_artist, album, album_key, artist_key, disc, track_no, duration_ms, plex_path, parts
EXTRA = [
    # a live take of 101's song on another album: one song, two copies
    (107, "Westkreuz (Live)", "Kollektiv Nord", None, "Live am Ring", 205, 301, 1, 1, 330000,
     "/music/Kollektiv Nord/Live am Ring/01 Westkreuz (Live).flac", 1),
    # a compilation copy that points at 102's file: shared file, and the same song as 102
    (108, "Ostkreuz", "Various Artists", "Kollektiv Nord", "Berlin Mix", 206, 305, 1, 4, 298000,
     "/music/Kollektiv Nord/Ringbahn/02 Ostkreuz.flac", 1),
    # outside Plex's music folder
    (109, "Stray", "Ada Vey", None, "Loose Ends", 207, 303, 1, 1, 180000, "/downloads/Ada Vey/Stray.flac", 1),
    # no file at all, and no duration
    (110, "Ghost", "Ada Vey", None, "Loose Ends", 207, 303, 1, 2, None, None, 1),
    # a decomposed (NFD) path: its file key is NFC
    (111, "Kreuzberg", "Mötley Kru", None, "Über", 208, 306, 1, 1, 200000,
     unicodedata.normalize("NFD", "/music/Mötley Kru/Über/01 Kreuzberg.flac"), 1),
    # 105's file with other capitals: two file keys, one loose key
    (112, "Coil", "ADA VEY", None, "Quiet Engines", 209, 307, 1, 1, 402000, "/music/ADA VEY/Quiet Engines/01 Coil.flac", 1),
]


def _scratch(legacy_db, tmp_path, drop_folders=False):
    db = tmp_path / "scratch.sqlite"
    shutil.copy(legacy_db, db)
    conn = sqlite3.connect(db)
    with conn:
        conn.executemany(
            "INSERT INTO tracks (rating_key, title, artist, track_artist, album, album_key, artist_key, disc, track_no,"
            " duration_ms, plex_path, parts, seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(*r, SYNC) for r in EXTRA])
        if drop_folders:
            conn.execute("DELETE FROM stats WHERE name = 'library.stats'")
    conn.close()
    return db


def test_file_key_rules():
    roots = ["/music/sub", "/music"]
    assert identity.file_key("/music/A/B/01 x.flac", roots) == ("/music", "A/B/01 x.flac")
    assert identity.file_key("/music/sub/x.flac", roots) == ("/music/sub", "x.flac")  # the deeper folder wins
    assert identity.file_key("/music//A//x.flac", roots) == ("/music", "A/x.flac")
    assert identity.file_key("\\music\\A\\x.flac", roots) == ("/music", "A/x.flac")
    assert identity.file_key("/musicals/x.flac", roots) == (None, None)  # a prefix isn't a folder
    assert identity.file_key("/music", roots) == (None, None)  # the folder itself is no file
    assert identity.file_key(None, roots) == (None, None)
    assert identity.file_key("/a/b.flac", ["/"]) == ("/", "a/b.flac")
    nfd = unicodedata.normalize("NFD", "/music/Mötley/x.flac")
    assert identity.file_key(nfd, roots)[1] == "Mötley/x.flac" == unicodedata.normalize("NFC", "Mötley/x.flac")
    assert identity.loose_key("ADA VEY/Coil.flac") == identity.loose_key("Ada Vey/coil.flac")


def test_common_folder():
    assert identity.common_folder(["/music/A/x.flac", "/music/B/y.flac"]) == "/music"
    assert identity.common_folder(["/music/A/x.flac", "/music/A/y.flac"]) == "/music/A"
    assert identity.common_folder(["/music/x.flac", "/data/y.flac"]) == "/"
    assert identity.common_folder([]) is None


def test_fixture_identity(legacy_db):
    before = legacy_db.read_bytes()
    s = identity.summary(legacy.connect(legacy_db))
    # jimbo-dj stored its PATH_MAP folder /music in library.stats; 5 live copies, all under it
    assert (s["root_source"], s["roots"]) == ("jimbodj", [{"folder": "/music", "tracks": 5}])
    assert s["counts"] == {"copies": 5, "with_file": 5, "files": 5, "songs": 5, "songs_with_versions": 0,
                           "match_keys": 5}
    assert s["issues"] == {"no_path": 0, "outside_roots": 0, "shared_file": 0, "loose_clash": 0,
                           "multi_part": 1, "no_duration": 0}  # 104 has two parts
    assert s["clean"] == 4
    assert set(s["rules"]) >= set(s["counts"]) | set(s["issues"])
    assert set(s["rows"]) == set(s["counts"]) | set(s["issues"])
    assert [t["tier"] for t in s["tiers"]] == ["file", "mbid", "tags"]
    rows = identity.copies(legacy.connect(legacy_db), sort="key")["copies"]
    assert [r["rating_key"] for r in rows] == [101, 102, 103, 104, 105]  # 106 is removed
    w = rows[0]
    assert (w["file"], w["root"], w["song"], w["match_key"]) == (
        "Kollektiv Nord/Ringbahn/01 Westkreuz.flac", "/music", "kollektivnordwestkreuz", match_key("Kollektiv Nord", "Westkreuz"))
    assert legacy_db.read_bytes() == before  # read-only


def test_problem_cases(legacy_db, tmp_path):
    db = _scratch(legacy_db, tmp_path)
    c = legacy.connect(db)
    s = identity.summary(c)
    assert s["counts"] == {"copies": 11, "with_file": 9, "files": 8, "songs": 8, "songs_with_versions": 3,
                           "match_keys": 8}
    assert s["issues"] == {"no_path": 1, "outside_roots": 1, "shared_file": 2, "loose_clash": 2,
                           "multi_part": 1, "no_duration": 1}
    by = {r["rating_key"]: r for r in identity.copies(c, limit=200)["copies"]}
    assert by[109]["issues"] == ["outside_roots"] and by[109]["file"] is None
    assert by[110]["issues"] == ["no_path", "no_duration"]
    assert by[102]["issues"] == by[108]["issues"] == ["shared_file"]
    assert by[105]["issues"] == by[112]["issues"] == ["loose_clash"]
    assert by[105]["loose"] == by[112]["loose"] and by[105]["file"] != by[112]["file"]
    assert by[111]["file"] == unicodedata.normalize("NFC", "Mötley Kru/Über/01 Kreuzberg.flac")
    # one song, its copies: the live take with the album track; the compilation copy with 102
    assert by[107]["song"] == by[101]["song"] and by[107]["song_copies"] == 2
    assert by[108]["song"] == by[102]["song"]
    assert by[108]["match_key"] == by[102]["match_key"]  # track artist, not "Various Artists"
    # every count's rows: each issue lists as many copies as its number, with_file too
    for issue, n in s["issues"].items():
        assert identity.copies(c, issue=issue)["total"] == n
    assert identity.copies(c, has_file=True)["total"] == s["counts"]["with_file"]
    assert by[112]["song"] == by[105]["song"]  # "ADA VEY" and "Ada Vey": one song, two files
    assert identity.copies(c, versions=True)["total"] == 6  # three songs, two copies each
    assert {r["rating_key"] for r in identity.copies(c, song=by[101]["song"])["copies"]} == {101, 107}
    assert {r["rating_key"] for r in identity.copies(c, file="ada vey/quiet engines/01 coil.flac")["copies"]} == {105, 112}
    with pytest.raises(ValueError):
        identity.copies(c, issue="nope")
    with pytest.raises(ValueError):
        identity.copies(c, sort="nope")


def test_roots_fallbacks(legacy_db, tmp_path):
    db = _scratch(legacy_db, tmp_path, drop_folders=True)
    # no stored folders: the folder every path shares is "/" (109 is in /downloads), so nothing is outside
    s = identity.summary(legacy.connect(db))
    assert (s["root_source"], [r["folder"] for r in s["roots"]]) == ("common", ["/"])
    assert s["issues"]["outside_roots"] == 0
    assert identity.copies(legacy.connect(db), rating_key=101)["copies"][0]["file"] == "music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac"
    # TRAQFREQ_PLEX_ROOTS when jimbo-dj stored none
    s = identity.summary(legacy.connect(db), ("/music/", "/downloads"))
    assert s["root_source"] == "env"
    assert [r["folder"] for r in s["roots"]] == ["/downloads", "/music"]
    assert s["issues"]["outside_roots"] == 0 and s["counts"]["with_file"] == 10


def test_settings_from_env():
    s = Settings.from_env({"TRAQFREQ_PLEX_ROOTS": "/music, /more ,", "TRAQFREQ_JELLYFIN_URL": "http://mini:8096",
                           "TRAQFREQ_JELLYFIN_KEY": "k", "TRAQFREQ_NAVIDROME_USER": "u"})
    assert s.plex_roots == ("/music", "/more")
    assert (s.jellyfin_url, s.jellyfin_key, s.jellyfin_user) == ("http://mini:8096", "k", None)
    assert (s.navidrome_url, s.navidrome_user, s.navidrome_password) == (None, "u", None)


def test_status_never_shows_secrets(legacy_db, tmp_path):
    s = Settings(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                 jellyfin_url="http://ryan:pw@macmini:8096/jf?x=1", jellyfin_key="SECRET-KEY",
                 navidrome_url="http://macmini:4533", navidrome_user="traq", navidrome_password="SECRET-PW")
    body = TestClient(create_app(s)).get("/api/servers").json()
    text = str(body)
    assert "SECRET" not in text and "pw@" not in text and "x=1" not in text
    plex, jf, nd = body["servers"]
    assert [x["server"] for x in body["servers"]] == list(servers.SERVERS)
    assert (plex["server_name"], plex["version"], plex["tracks"], plex["last_sync"]) == ("Fixture Plex", "1.41.0", 5, SYNC)
    assert (jf["set_up"], jf["url"], jf["read"]) == (True, "http://macmini:8096/jf", False)
    assert {r["env"]: r["set"] for r in jf["settings"]} == {
        "TRAQFREQ_JELLYFIN_URL": True, "TRAQFREQ_JELLYFIN_KEY": True, "TRAQFREQ_JELLYFIN_USER": False}
    assert [r["value"] for r in jf["settings"] if r["secret"]] == [None]
    assert nd["set_up"] is True and nd["missing"] == []


def test_status_not_set_up(client):
    body = client.get("/api/servers").json()
    _, jf, nd = body["servers"]
    assert (jf["set_up"], jf["missing"]) == (False, ["TRAQFREQ_JELLYFIN_URL", "TRAQFREQ_JELLYFIN_KEY"])
    assert nd["missing"] == ["TRAQFREQ_NAVIDROME_URL", "TRAQFREQ_NAVIDROME_USER", "TRAQFREQ_NAVIDROME_PASSWORD"]
    assert "Every page works without it" in jf["note"]


def test_status_without_legacy_db(tmp_path):
    s = Settings(data_dir=tmp_path / "data", legacy_db=None, port=4492, host="127.0.0.1")
    plex = TestClient(create_app(s)).get("/api/servers").json()["servers"][0]
    assert plex["set_up"] is False and "TRAQFREQ_LEGACY_DB" in plex["note"]


def test_api(legacy_db, tmp_path):
    db = _scratch(legacy_db, tmp_path)
    s = Settings(data_dir=tmp_path / "data", legacy_db=db, port=4492, host="127.0.0.1")
    client = TestClient(create_app(s))
    body = client.get("/api/servers/identity").json()
    assert body["counts"]["copies"] == 11 and body["cache"]["hit"] is False
    assert client.get("/api/servers/identity").json()["cache"]["hit"] is True
    # every rows query, sent as a page would, lists as many copies as its issue count
    for issue, n in body["issues"].items():
        assert client.get(f"/api/servers/copies?{body['rows'][issue]}").json()["total"] == n
    assert client.get(f"/api/servers/copies?{body['rows']['with_file']}").json()["total"] == 9
    page = client.get("/api/servers/copies?sort=artist&limit=2&offset=2").json()
    assert (page["total"], page["limit"], page["offset"], len(page["copies"])) == (11, 2, 2, 2)
    assert client.get("/api/servers/copies?issue=nope").status_code == 400
    assert client.get("/api/servers/copies?rating_key=109").json()["copies"][0]["plex_path"] == "/downloads/Ada Vey/Stray.flac"


def test_api_without_tracks(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    s = Settings(data_dir=tmp_path / "data", legacy_db=db, port=4492, host="127.0.0.1")
    assert TestClient(create_app(s)).get("/api/servers/identity").status_code == 404
