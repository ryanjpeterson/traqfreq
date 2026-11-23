"""T9: LIBRARY numbers (jimbo-dj's library.stats, vendored) and the rows behind each one, on the fixture."""

import sqlite3
from urllib.parse import parse_qsl

import pytest
from fastapi.testclient import TestClient

from traqfreq import legacy, library
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import jimbodj_library as jd


def _stats(legacy_db):
    return library.stats(legacy.connect(legacy_db))


def _rows(legacy_db, **kw):
    return library.tracks(legacy.connect(legacy_db), **kw)


def _keys(body):
    return [r["rating_key"] for r in body["rows"]]


def test_stats_equal_jimbodj_stored(legacy_db):
    """Every field of jimbo-dj's stored library.stats (folders aside: shown as stored) equals traqfreq's."""
    ours = _stats(legacy_db)
    theirs, _ = legacy.stored_stat(legacy.connect(legacy_db), "library.stats")
    for field, value in theirs.items():
        if field == "paths":
            for k, v in value.items():
                assert ours["paths"][k] == v, k
        else:
            assert ours[field] == value, field
    assert ours["paths"]["folders_compared"] is False
    assert ours["jimbodj"]["fresh"] is True and ours["jimbodj"]["source"] == "stats.library.stats"


def test_rules_differ_from_raw_counts(legacy_db):
    s = _stats(legacy_db)
    raw = legacy.connect(legacy_db).execute("SELECT COUNT(*), SUM(view_count) FROM tracks").fetchone()
    assert (s["tracks"], raw[0]) == (5, 6)  # the removed track is left out
    assert (s["play_history"]["total_plays"], raw[1]) == (5, 55)  # its 50 Plex plays too
    assert sum(s["bitrate_kbps"].values()) == 4  # one live track has no bitrate: in no bucket
    assert s["containers"]["?"] == 1
    assert s["paths"]["mapped"] == 4 and s["paths"]["multi_part_tracks"] == 1
    assert s["paths"]["removed_since_first_sync"] == 1
    # jimbo-dj's analyzer: 3 live rows say ok, but one is from analyzer version 1; one error.
    assert s["analyzer"] == {"version": 2, "tracks": 2, "pct": 40.0, "errors": 1}
    assert s["sonic_analysis"] == {"tracks": 3, "pct": 60.0}  # Plex's, a different number


def test_every_number_opens_its_rows(legacy_db):
    """Each number's query lists exactly as many rows as the number says."""
    s = _stats(legacy_db)

    def count(q):
        params = {k: (v == "true" if v in ("true", "false") else v) for k, v in parse_qsl(q)}
        for k in ("artist_key", "album_key"):
            if k in params:
                params[k] = int(params[k])
        return _rows(legacy_db, **params)["total"]

    rows = s["rows"]
    assert count(rows["tracks"]) == s["tracks"]
    for group in ("codecs", "containers", "bitrate_kbps"):
        for v, n in s[group].items():
            assert count(rows[group][v]) == n, (group, v)
    ph = s["play_history"]
    assert count(rows["played_tracks"]) == ph["played_tracks"]
    assert count(rows["rated_tracks"]) == ph["rated_tracks"]
    assert count(rows["sonic_analysis"]) == s["sonic_analysis"]["tracks"]
    assert count(rows["analyzer"]) == s["analyzer"]["tracks"]
    assert count(rows["analyzer_errors"]) == s["analyzer"]["errors"]
    assert count(rows["mapped"]) == s["paths"]["mapped"]
    assert count(rows["unmapped"]) == s["tracks"] - s["paths"]["mapped"]
    assert count(rows["multi_part_tracks"]) == s["paths"]["multi_part_tracks"]
    assert count(rows["removed_since_first_sync"]) == s["paths"]["removed_since_first_sync"]
    for a in s["top_artist_keys"]:
        body = _rows(legacy_db, **{**dict(parse_qsl(rows["top_artists"][str(a["artist_key"])])),
                                   "artist_key": a["artist_key"], "played": True})
        assert sum(r["view_count"] for r in body["rows"]) == a["plays"] == ph["top_artists"][a["artist"]]


def test_bitrate_buckets_as_in_stats(legacy_db):
    """The vendored bucket list (read for rows) is the one stats counts with."""
    s = _stats(legacy_db)
    assert list(s["bitrate_kbps"]) == [b[0] for b in jd.BITRATE_BUCKETS]
    assert _keys(_rows(legacy_db, bitrate="<192k")) == [102]
    assert _keys(_rows(legacy_db, bitrate=">320k (lossless)")) == [101]
    assert _keys(_rows(legacy_db, bitrate="320k")) == [104]


def test_plays_of_takes_the_larger(legacy_db):
    rows = {r["rating_key"]: r for r in _rows(legacy_db)["rows"]}
    r = rows[101]
    assert (r["view_count"], r["history_plays"], r["plays"]) == (3, 1, 3)  # max, not 4
    assert (rows[102]["view_count"], rows[102]["history_plays"], rows[102]["plays"]) == (0, 1, 1)
    # last_of: the later of Plex's last view and the last history play
    assert r["last_played"] == "2026-11-01T20:15:00Z"
    assert rows[104]["last_played"] == "2026-11-04T21:00:00Z"
    assert rows[105]["last_played"] == "2026-11-03T22:40:00Z"


def test_rows_filters_and_keys(legacy_db):
    assert _keys(_rows(legacy_db, codec="?")) == []
    assert _keys(_rows(legacy_db, container="?")) == [105]
    assert _keys(_rows(legacy_db, mapped=False)) == [105]
    assert _keys(_rows(legacy_db, played=True, sort="plex_plays")) == [101, 104]
    assert _keys(_rows(legacy_db, removed=True)) == [106]
    assert _keys(_rows(legacy_db, analysis="older")) == [102]
    assert _keys(_rows(legacy_db, analysis="none")) == [104]
    body = _rows(legacy_db, analysis="ok")
    assert _keys(body) == [101, 103]
    by = {r["rating_key"]: r for r in body["rows"]}
    assert (by[101]["camelot"], by[101]["bpm"]) == ("8A", 128.0)
    # 102 has features but from analyzer version 1: no key or BPM shown
    r102 = _rows(legacy_db, analysis="older")["rows"][0]
    assert r102["camelot"] is None and r102["bpm"] is None
    page = _rows(legacy_db, limit=2, offset=2)
    assert page["total"] == 5 and len(page["rows"]) == 2
    assert "removed_at IS NULL" in page["rule"]
    with pytest.raises(ValueError):
        _rows(legacy_db, bitrate="loud")
    with pytest.raises(ValueError):
        _rows(legacy_db, sort="color")


def test_api_stats_cached(client, tmp_path, legacy_db):
    before = legacy_db.read_bytes()
    a = client.get("/api/library/stats").json()
    b = client.get("/api/library/stats").json()
    assert a["tracks"] == 5 and a["cache"]["hit"] is False and b["cache"]["hit"] is True
    assert a["cache"]["key"].startswith("v2|1793844000|1793847900.5|a2|4|")
    assert a["paths"]["folders"] == {"/music": {"read_from": "/srv/music", "readable_here": True, "tracks": 5}}
    assert legacy_db.read_bytes() == before  # read-only


def test_api_cache_key_changes_with_data(legacy_db, tmp_path):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    c = TestClient(create_app(Settings(data_dir=tmp_path / "d", legacy_db=copy, port=4492, host="127.0.0.1")))
    k1 = c.get("/api/library/stats").json()["cache"]["key"]
    w = sqlite3.connect(copy)  # a scratch copy of the fixture, never the legacy DB
    w.execute("UPDATE analysis SET version = 2 WHERE rating_key = 102")
    w.execute("UPDATE analysis SET analyzed_at = analyzed_at + 60 WHERE rating_key = 102")
    w.commit()
    w.close()
    body = c.get("/api/library/stats").json()
    assert body["cache"]["key"] != k1 and body["cache"]["hit"] is False
    assert body["analyzer"]["tracks"] == 3


def test_api_tracks(client):
    body = client.get("/api/library/tracks", params={"codec": "mp3"}).json()
    assert [r["rating_key"] for r in body["rows"]] == [102, 104] and body["total"] == 2
    assert body["params"] == ["mp3"]
    assert client.get("/api/library/tracks", params={"analysis": "maybe"}).status_code == 400
    assert client.get("/api/library/tracks", params={"removed": "true"}).json()["total"] == 1


def test_api_without_tracks_table(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    c = TestClient(create_app(Settings(data_dir=tmp_path / "d", legacy_db=db, port=4492, host="127.0.0.1")))
    assert c.get("/api/library/stats").status_code == 404
    assert c.get("/api/library/tracks").status_code == 404


def test_api_rows_queries_as_the_page_sends_them(client):
    """T10: the LIBRARY page sends each `rows` query string as is (encoded `?`, `<`, `>`, spaces) to
    /api/library/tracks; every one is accepted and lists as many tracks as its number."""
    s = client.get("/api/library/stats").json()
    total = lambda q: client.get(f"/api/library/tracks?{q}" if q else "/api/library/tracks").json()["total"]  # noqa: E731
    for k, q in s["rows"].items():
        for sub in (q.values() if isinstance(q, dict) else [q]):
            r = client.get(f"/api/library/tracks?{sub}")
            assert r.status_code == 200, (k, sub)
    for group in ("codecs", "containers", "bitrate_kbps"):
        for v, n in s[group].items():
            assert total(s["rows"][group][v]) == n, (group, v)
    assert total(s["rows"]["tracks"]) == s["tracks"]
    assert total(s["rows"]["unmapped"]) == s["tracks"] - s["paths"]["mapped"]
    assert total(s["rows"]["containers"]["?"]) == 1  # container=%3F: no container given


def test_play_history_from_every_source(legacy_db):
    """Plays from Plex, Last.fm, Spotify and Apple Music (plays_of per track), beside jimbo-dj's Plex-only numbers."""
    s = _stats(legacy_db)
    a = s["plays_all"]
    assert (s["play_history"]["played_tracks"], a["played_tracks"]) == (2, 5)  # Plex alone misses 3 played tracks
    assert (s["play_history"]["total_plays"], a["plays"]) == (5, 8)
    # 101: Plex 3, history 1 → 3 (not 4); 102, 103, 105 only in the history; 104 Plex 2, history 1 → 2
    by = {r["rating_key"]: r["plays"] for r in _rows(legacy_db, heard=True, sort="plays")["rows"]}
    assert by == {101: 3, 104: 2, 102: 1, 103: 1, 105: 1} and sum(by.values()) == a["plays"]
    assert a["by_source"] == {"lastfm": 2, "plex": 1, "spotify": 1, "applemusic": 1}  # jimbo-dj's source order
    assert a["history_plays"] == sum(a["by_source"].values()) == 5
    assert [(x["artist"], x["plays"]) for x in a["top_artists"]] == [
        ("Kollektiv Nord", 4), ("The Paper Lanterns", 3), ("Ada Vey", 1)]
    assert "never the sum" in s["rules"]["all.plays"]


def test_every_source_number_opens_its_rows(client):
    s = client.get("/api/library/stats").json()
    a = s["plays_all"]
    total = lambda q: client.get(f"/api/library/tracks?{q}").json()["total"]  # noqa: E731
    assert total(s["rows"]["all.played_tracks"]) == a["played_tracks"]
    for src, q in s["rows"]["all.by_source"].items():
        assert total(q) == a["tracks_by_source"][src], src
    for art in a["top_artists"]:
        rows = client.get(f"/api/library/tracks?{s['rows']['all.top_artists'][str(art['artist_key'])]}").json()["rows"]
        assert sum(r["plays"] for r in rows) == art["plays"]
    assert client.get("/api/library/tracks", params={"heard": "false"}).json()["total"] == 0
    assert [r["rating_key"] for r in client.get("/api/library/tracks", params={"sort": "plays"}).json()["rows"]][:2] == [101, 104]
