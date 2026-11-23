"""T11: albums, artists and a track, counted with jimbo-dj's page code (vendored), on the fixture."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from traqfreq import entities, legacy, library
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import jimbodj_songs as songs


def _c(db):
    return legacy.connect(db)


def _tracks(db, **kw):
    return {r["rating_key"]: r for r in library.tracks(_c(db), limit=500, **kw)["rows"]}


def test_lists_count_like_library_stats(legacy_db):
    s = library.stats(_c(legacy_db))
    albums = entities.entity_list(_c(legacy_db), "albums")
    artists = entities.entity_list(_c(legacy_db), "artists")
    assert (albums["total"], artists["total"]) == (s["albums"], s["artists"]) == (3, 3)
    plays_of = sum(r["plays"] for r in _tracks(legacy_db).values())
    # SUM(plays_of) per album: nothing counts twice, the removed album (204, 50 Plex plays) isn't there
    assert sum(i["plays"] for i in albums["items"]) == sum(i["plays"] for i in artists["items"]) == plays_of == 8
    assert [(i["name"], i["plays"], i["tracks"]) for i in albums["items"]] == [
        ("Ringbahn", 4, 2), ("Low Tide Radio", 3, 2), ("Quiet Engines", 1, 1)]
    assert "Gone Album" not in [i["name"] for i in albums["items"]]


def test_list_sorts(legacy_db):
    names = lambda kind, sort: [i["name"] for i in entities.entity_list(_c(legacy_db), kind, sort)["items"]]  # noqa: E731
    assert names("albums", "name") == ["Low Tide Radio", "Quiet Engines", "Ringbahn"]
    assert names("albums", "added") == ["Quiet Engines", "Low Tide Radio", "Ringbahn"]
    assert names("albums", "year") == ["Quiet Engines", "Low Tide Radio", "Ringbahn"]
    assert names("artists", "name") == ["Ada Vey", "Kollektiv Nord", "The Paper Lanterns"]
    assert names("artists", "plays") == ["Kollektiv Nord", "The Paper Lanterns", "Ada Vey"]
    page = entities.entity_list(_c(legacy_db), "albums", "name", limit=2, offset=2)
    assert page["total"] == 3 and [i["name"] for i in page["items"]] == ["Ringbahn"]
    with pytest.raises(ValueError):
        entities.entity_list(_c(legacy_db), "albums", "colour")
    with pytest.raises(ValueError):
        entities.entity_list(_c(legacy_db), "songs")


def test_list_rows_open_their_tracks(client):
    for kind in ("albums", "artists"):
        body = client.get(f"/api/library/{kind}").json()
        for i in body["items"]:
            q = i["rows"].split("&name=")[0]
            assert client.get(f"/api/library/tracks?{q}").json()["total"] == i["tracks"], (kind, i["name"])


def test_album_page(legacy_db):
    a = entities.album(_c(legacy_db), 202)
    # disc, then track number: disc 1's "Static Gulls" (track 2) before disc 2's "Harbour Lights" (track 1)
    assert [t["rating_key"] for t in a["tracks"]] == [104, 103]
    # jimbo-dj's year: MusicBrainz's first release (2020), not Plex's 2021 (what the list shows)
    assert (a["album"]["year"], a["album"]["plex_year"], a["album"]["label"]) == (2020, 2021, "Harbour House")
    assert a["album"]["musicbrainz"]["first_release"] == "2020-10-01"
    by = _tracks(legacy_db, album_key=202)
    assert [t["plays"] for t in a["tracks"]] == [by[104]["plays"], by[103]["plays"]] == [2, 1]
    assert a["plays"] == 3 and a["minutes"] == 8
    # The listens of these copies: Plex's Harbour Lights and Spotify's Static Gulls (the too-short one and the
    # repeat aren't plays)
    assert a["history"]["plays"] == 2
    assert {s["source"]: s["plays"] for s in a["history"]["sources"]} == {"plex": 1, "spotify": 1}
    assert a["tracks"][1]["camelot"] == "5B" and a["tracks"][1]["moods"] == ["relaxed", "happy"]
    assert "genres" not in a["tracks"][0]  # TAGS (P4)
    with pytest.raises(entities.NotFound):
        entities.album(_c(legacy_db), 204)  # removed


def test_artist_page(legacy_db):
    a = entities.artist(_c(legacy_db), 302)
    assert a["artist"]["name"] == "The Paper Lanterns" and a["tracks"] == 2
    assert [(x["title"], x["year"], x["plays"]) for x in a["albums"]] == [("Low Tide Radio", 2020, 3)]
    assert [(t["title"], t["plays"], t["versions"]) for t in a["top_tracks"]] == [("Static Gulls", 2, 1), ("Harbour Lights", 1, 1)]
    assert a["plays"] == 3
    # Spotify's "Paper Lanterns" counts too: matched to its tracks (pages._artist_where)
    assert a["history"]["plays"] == 2 and a["history"]["songs"] == 2
    k = entities.artist(_c(legacy_db), 301)
    assert k["history"]["plays"] == 2 and [y["year"] for y in k["history"]["years"]] == [2025, 2026]  # Denver
    with pytest.raises(entities.NotFound):
        entities.artist(_c(legacy_db), 304)  # only a removed track


def test_track_page(legacy_db):
    t = entities.track(_c(legacy_db), 101)
    row = _tracks(legacy_db)[101]
    # plays_of: Plex 3, history 1 → 3, not 4
    assert t["plays"] == {"plays": 3, "plex": 3, "history": 1, "last_played": row["last_played"]} and row["plays"] == 3
    assert t["history"]["plays"] == row["history_plays"] == 1
    assert t["history"]["sources"] == [{"source": "lastfm", "name": "Last.fm", "plays": 1}]
    assert t["analysis"]["current"] is True and t["features"]["camelot"] == "8A"
    assert t["features"]["moods"] == ["party", "aggressive", "happy"]  # top three, as pages._track
    assert t["track"]["codec"] == "flac" and t["track"]["bitrate"] == 1011
    assert t["song"] == {"title": "Westkreuz", "artist": "Kollektiv Nord", "copies": 1, "versions": [], "history": None}
    older = entities.track(_c(legacy_db), 102)
    assert older["analysis"]["current"] is False and older["analysis"]["version"] == 1
    gone = entities.track(_c(legacy_db), 106)
    assert gone["live"] is False and gone["plays"]["plays"] == 50
    with pytest.raises(entities.NotFound):
        entities.track(_c(legacy_db), 999)


def test_plays_rows_are_the_numbers_rows(legacy_db):
    c = _c(legacy_db)
    for kw, n in (({"track": 101}, entities.track(c, 101)["history"]["plays"]),
                  ({"album": 202}, entities.album(c, 202)["history"]["plays"]),
                  ({"artist": 302}, entities.artist(c, 302)["history"]["plays"])):
        assert entities.plays(c, **kw)["total"] == n, kw
    one = entities.plays(c, artist=302, source="plex")
    assert one["total"] == 1 and one["sources"] == ["plex", "spotify"]
    with pytest.raises(ValueError):
        entities.plays(c)


@pytest.fixture
def live_copy(legacy_db, tmp_path):
    """A scratch copy of the fixture with one more invented copy of Westkreuz (a live album) and one play
    that says it was that copy; history_version moves, as an import would move it. Never the legacy DB."""
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    w = sqlite3.connect(copy)
    w.execute("INSERT INTO tracks (rating_key, title, artist, album, album_key, artist_key, disc, track_no, year, "
              "duration_ms, view_count, seen_at, added_at) VALUES (107, 'Westkreuz (Live)', 'Kollektiv Nord', "
              "'Ringbahn Live', 205, 301, 1, 1, 2024, 330000, 2, 1793844000, 1793800000)")
    w.execute("INSERT INTO albums (album_key, title, artist_key, year) VALUES (205, 'Ringbahn Live', 301, 2024)")
    w.execute("INSERT INTO listens (source, started_at, ms_played, artist, title, album, counted, match_key, rating_key) "
              "VALUES ('plex', 1793900000, 330000, 'Kollektiv Nord', 'Westkreuz (Live)', 'Ringbahn Live', 1, "
              "'kollektivnord|westkreuz', 107)")
    w.execute("UPDATE meta SET value = '1793900001.0' WHERE key = 'history_version'")
    w.commit()
    w.close()
    return copy


def test_song_copies(live_copy):
    c = _c(live_copy)
    assert songs.index(c).versions_of(101) == [101, 107]
    k = entities.artist(c, 301)
    assert [x["title"] for x in k["albums"]] == ["Ringbahn", "Ringbahn Live"]  # oldest first
    top = k["top_tracks"][0]
    # one song: the original copy, every copy's plays_of added up (101: 3; 107: max(2, 1) = 2)
    assert (top["rating_key"], top["plays"], top["versions"], top["albums"]) == (101, 5, 2, 2)
    assert [t["versions"] for t in entities.album(c, 201)["tracks"]] == [2, 1]
    live = entities.track(c, 107)
    assert live["kind"] == "live" and live["song"]["copies"] == 2
    assert [v["rating_key"] for v in live["song"]["versions"]] == [101]
    # this copy's listens vs the song's: the live play is 107's, the Last.fm one is 101's (its default copy)
    assert live["history"]["plays"] == 1 and live["song"]["history"]["plays"] == 2
    assert entities.track(c, 101)["history"]["plays"] == 1
    assert entities.plays(c, track=107, song=True)["total"] == 2
    assert entities.plays(c, track=107)["total"] == 1


def test_api(client, legacy_db):
    before = legacy_db.read_bytes()
    assert client.get("/api/library/albums", params={"sort": "name"}).json()["items"][0]["name"] == "Low Tide Radio"
    assert client.get("/api/library/artists").json()["total"] == 3
    assert client.get("/api/library/album/202").json()["album"]["year"] == 2020
    assert client.get("/api/library/artist/301").json()["plays"] == 4
    assert client.get("/api/library/track/104").json()["plays"]["plays"] == 2
    assert client.get("/api/library/plays", params={"album": 202}).json()["total"] == 2
    assert client.get("/api/library/album/999").status_code == 404
    assert client.get("/api/library/track/999").status_code == 404
    assert client.get("/api/library/albums", params={"sort": "colour"}).status_code == 400
    assert client.get("/api/library/plays").status_code == 400
    assert legacy_db.read_bytes() == before  # read-only


def test_api_without_tracks_table(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    c = TestClient(create_app(Settings(data_dir=tmp_path / "d", legacy_db=db, port=4492, host="127.0.0.1")))
    for path in ("/api/library/albums", "/api/library/artists", "/api/library/album/1", "/api/library/track/1"):
        assert c.get(path).status_code == 404, path
