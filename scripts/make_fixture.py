"""Build a small SQLite fixture with the shape of the part of jimbo-dj's database traqfreq reads.

Schema checked against jimbo-dj at 1d8a7cb (2026-11-22): src/jimbodj/db.py (tracks, meta, analysis,
features, albums, artists, plus ADDED_COLUMNS), history.py (listens, listen_matches, history_imports) and
statcache.py (stats). Only the tables traqfreq reads are here. All rows are invented sample data, chosen so
every counting rule has a case that tells it apart from a raw row count:

- tracks: 6 rows, one removed (removed_at set) on an album and artist no live track has, so live counts
  (5 tracks, 3 albums, 3 artists) differ from raw rows (6, 4, 4).
- listens: 9 rows, 6 plays (counted=1). The 3 that are not plays: one too short (< 30 s), one Plex
  duplicate of a Last.fm scrobble (dup_of='lastfm'), one Spotify repeat of itself (dup_of='spotify').
  One play has no library match (listen_matches.rating_key NULL). One play is on 2026-01-01 05:30 UTC,
  which is 2025 in America/Denver (jimbo-dj's default TZ), so years depend on the time zone.
- Spotify spells "The Paper Lanterns" as "Paper Lanterns"; jimbo-dj's Names makes them one artist (the
  library's spelling), so top artists has 4 names, not 5.
- stats: jimbo-dj's own stored summaries (library.stats, history.overview, T8: history.wrapped), trimmed to the counts and the
  top artists.

- T9, the library columns on those same 6 tracks (LIBRARY below), so T5-T8's counts stay: a lossless FLAC
  and a 128k MP3, a 256k AAC and a 320k MP3 (two parts), one FLAC with no bitrate or container (in no bucket,
  so the buckets add up to 4 of 5) and no local path (unmapped). Played and rated tracks, Plex sonic analysis
  on 3; the removed track is played 50 times, rated and analysed, so every live rule leaves it out. Track 101
  has view_count 3 and 1 history play: jimbo-dj's plays_of takes the larger (3), not the sum (4). jimbo-dj's
  analyzer: 2 tracks ok at version 2, 1 ok at version 1 (older), 1 error. jimbo-dj's stored library.stats has
  the full shape, worked out by hand.
- With --checks: T7's invented bursts, loop, steady rhythm and windows (CHECK_LISTENS), on top of the above.

Usage: python scripts/make_fixture.py [--checks] [out_path]   (default tests/fixtures/legacy.sqlite)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE tracks (
    rating_key INTEGER PRIMARY KEY, guid TEXT, title TEXT, artist TEXT, track_artist TEXT, album TEXT,
    album_key INTEGER, artist_key INTEGER, disc INTEGER, track_no INTEGER, year INTEGER, duration_ms INTEGER,
    plex_path TEXT, local_path TEXT, parts INTEGER, file_size INTEGER, container TEXT, codec TEXT,
    bitrate INTEGER, channels INTEGER, view_count INTEGER DEFAULT 0, skip_count INTEGER DEFAULT 0,
    last_viewed_at INTEGER, user_rating REAL, added_at INTEGER, updated_at INTEGER, sonic_version INTEGER,
    seen_at INTEGER NOT NULL, removed_at INTEGER,
    bit_depth INTEGER, sample_rate INTEGER, stream_size INTEGER, plex_genres TEXT, plex_moods TEXT
);
CREATE INDEX tracks_artist ON tracks(artist_key);
CREATE INDEX tracks_album ON tracks(album_key);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE analysis (
    rating_key INTEGER PRIMARY KEY, version INTEGER NOT NULL, plex_path TEXT, file_size INTEGER,
    status TEXT NOT NULL, error TEXT, analyzed_at INTEGER NOT NULL, seconds REAL, host TEXT
);
CREATE TABLE features (
    rating_key INTEGER PRIMARY KEY, duration_s REAL, bpm REAL, bpm_confidence REAL, key TEXT, scale TEXT,
    key_strength REAL, camelot TEXT, loudness_lufs REAL, loudness_range REAL, danceability REAL, happy REAL,
    sad REAL, aggressive REAL, relaxed REAL, party REAL, voice REAL, approachability REAL, engagement REAL,
    moods TEXT, genres TEXT
);
CREATE TABLE albums (
    album_key INTEGER PRIMARY KEY, title TEXT, artist_key INTEGER, year INTEGER, released TEXT, studio TEXT,
    genres TEXT, mbid TEXT, seen_at INTEGER
);
CREATE TABLE artists (
    artist_key INTEGER PRIMARY KEY, title TEXT, countries TEXT, genres TEXT, mbid TEXT, seen_at INTEGER
);
CREATE TABLE listens (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, started_at INTEGER NOT NULL, ms_played INTEGER,
    artist TEXT, title TEXT, album TEXT, uri TEXT, skipped INTEGER NOT NULL DEFAULT 0,
    counted INTEGER NOT NULL DEFAULT 1, match_key TEXT NOT NULL, rating_key INTEGER, dup_of TEXT,
    UNIQUE (source, started_at, match_key)
);
CREATE INDEX listens_time ON listens(started_at);
CREATE INDEX listens_match ON listens(match_key, started_at);
CREATE INDEX listens_rk ON listens(rating_key);
CREATE TABLE listen_matches (match_key TEXT PRIMARY KEY, rating_key INTEGER);
CREATE TABLE history_imports (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, at INTEGER NOT NULL, rows INTEGER, added INTEGER, note TEXT
);
CREATE TABLE stats (
    name TEXT NOT NULL, params TEXT NOT NULL, value TEXT NOT NULL, version INTEGER NOT NULL, stamp TEXT,
    built_at REAL NOT NULL, seconds REAL, PRIMARY KEY (name, params)
) WITHOUT ROWID;
"""

SYNC = 1793844000  # 2026-11-05T02:00:00Z, the last Plex sync
OLD_SYNC = 1793239200  # 2026-10-29T02:00:00Z

# rating_key, title, artist, album, album_key, artist_key, track_no, year, duration_ms, removed_at
TRACKS = [
    (101, "Westkreuz", "Kollektiv Nord", "Ringbahn", 201, 301, 1, 2019, 312000, None),
    (102, "Ostkreuz", "Kollektiv Nord", "Ringbahn", 201, 301, 2, 2019, 298000, None),
    (103, "Harbour Lights", "The Paper Lanterns", "Low Tide Radio", 202, 302, 1, 2021, 221000, None),
    (104, "Static Gulls", "The Paper Lanterns", "Low Tide Radio", 202, 302, 2, 2021, 245000, None),
    (105, "Coil", "Ada Vey", "Quiet Engines", 203, 303, 1, 2023, 402000, None),
    (106, "Old Signal", "Former Band", "Gone Album", 204, 304, 1, 2011, 199000, OLD_SYNC),
]
ALBUMS = [(201, "Ringbahn", 301, 2019), (202, "Low Tide Radio", 302, 2021), (203, "Quiet Engines", 303, 2023),
          (204, "Gone Album", 304, 2011)]
ARTISTS = [(301, "Kollektiv Nord"), (302, "The Paper Lanterns"), (303, "Ada Vey"), (304, "Former Band")]
# rating_key, version, status, error (jimbo-dj's ANALYZER_VERSION is 2: version 1 needs analysing again)
ANALYSIS = [(101, 2, "ok", None), (102, 1, "ok", None), (103, 2, "ok", None), (105, 2, "error", "decode failed")]

# T9: the library columns of TRACKS (rating_key: codec, container, bitrate kbps, file_size, parts, local_path,
# view_count, last_viewed_at, user_rating, sonic_version, added_at). local_path None = outside the music root.
LIBRARY = {
    101: ("flac", "flac", 1011, 39_400_000, 1, True, 3, "2026-10-30T18:00:00Z", None, 1, "2025-03-01T10:00:00Z"),
    102: ("mp3", "mp3", 128, 4_800_000, 1, True, 0, None, 4.0, None, "2025-03-01T10:00:00Z"),
    103: ("aac", "mp4", 256, 7_100_000, 1, True, 0, None, None, 1, "2026-06-12T09:00:00Z"),
    104: ("mp3", "mp3", 320, 9_800_000, 2, True, 2, "2026-11-04T21:00:00Z", 8.0, 1, "2026-06-12T09:00:00Z"),
    105: ("flac", None, None, 41_000_000, 1, False, 0, None, None, None, "2026-09-20T15:30:00Z"),
    106: ("flac", "flac", 900, 20_000_000, 1, True, 50, "2026-01-02T12:00:00Z", 10.0, 1, "2012-01-01T00:00:00Z"),
}
SERVER = {"name": "Fixture Plex", "version": "1.41.0", "machine_id": "fixture0", "plex_pass": True,
          "section": "Music", "section_key": "1"}
# rating_key, bpm, camelot, loudness_lufs
FEATURES = [(101, 128.0, "8A", -7.1), (102, 130.0, "9A", -6.8), (103, 104.0, "5B", -9.4)]


def _t(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


# source, started_at (UTC), ms_played, artist, title, album, uri, counted, match_key, rating_key, dup_of
LISTENS = [
    ("lastfm", "2026-11-01T20:15:00Z", None, "Kollektiv Nord", "Westkreuz", "Ringbahn", None, 1,
     "kollektivnord|westkreuz", None, None),
    ("plex", "2026-11-01T20:16:00Z", 312000, "Kollektiv Nord", "Westkreuz", "Ringbahn", "plex:101", 0,
     "kollektivnord|westkreuz", 101, "lastfm"),  # the same play as the Last.fm scrobble
    ("plex", "2026-11-01T20:21:00Z", 221000, "The Paper Lanterns", "Harbour Lights", "Low Tide Radio", "plex:103", 1,
     "paperlanterns|harbourlights", 103, None),
    ("spotify", "2026-11-02T08:02:00Z", 15000, "The Paper Lanterns", "Harbour Lights", "Low Tide Radio",
     "spotify:track:a1", 0, "paperlanterns|harbourlights", None, None),  # too short to be a play
    ("spotify", "2026-11-02T08:10:00Z", 245000, "Paper Lanterns", "Static Gulls (Remastered 2024)", None,
     "spotify:track:a2", 1, "paperlanterns|staticgulls", None, None),
    ("spotify", "2026-11-02T08:10:20Z", 245000, "Paper Lanterns", "Static Gulls (Remastered 2024)", None,
     "spotify:track:a2", 0, "paperlanterns|staticgulls", None, "spotify"),  # Spotify logging it twice
    ("applemusic", "2026-11-03T22:40:00Z", 402000, "Ada Vey", "Coil", "Quiet Engines", None, 1,
     "adavey|coil", None, None),
    ("lastfm", "2026-01-01T05:30:00Z", None, "Kollektiv Nord", "Ostkreuz", "Ringbahn", None, 1,
     "kollektivnord|ostkreuz", None, None),  # 2025-12-31 22:30 in America/Denver
    ("lastfm", "2026-11-04T19:05:00Z", None, "Nobody Known", "Ghost Song (Live)", None, None, 1,
     "nobodyknown|ghostsong", None, None),  # not in the library
]
# T7's checks, only with --checks (build(..., checks=True)), so T5/T6's counts above stay as they are. All
# invented, flagged the way jimbo-dj's dedupe would flag them:
# - a burst: 4 plays of 4 songs 10, 10 and 20 s apart (3 held);
# - a loop: one song 10 times, 200 s apart (one song, so not a steady rhythm);
# - a steady rhythm: 12 plays of 4 songs, 180-181 s apart;
# - an Apple Music daily-summary listen 40 min from the Last.fm play it duplicates (an hour's window);
# - a Plex listen flagged as a Last.fm duplicate with no Last.fm play in its window ("not found").
def _check_listens() -> list[tuple]:
    rows = []
    burst = [("Static Choir", f"Signal {i}", f"staticchoir|signal{i}") for i in range(1, 5)]
    for (a, t, mk), at in zip(burst, ("12:00:00", "12:00:10", "12:00:20", "12:00:40")):
        rows.append(("lastfm", f"2026-10-10T{at}Z", None, a, t, None, None, 1, mk, None, None))
    for i in range(10):
        m, sec = divmod(i * 200, 60)
        rows.append(("spotify", f"2026-10-11T10:{m:02d}:{sec:02d}Z", 190000, "Loop Garden", "Again", None,
                     "spotify:track:l1", 1, "loopgarden|again", None, None))
    gaps = [0, 180, 361, 541, 722, 902, 1083, 1263, 1444, 1624, 1805, 1985]
    for i, g in enumerate(gaps):
        m, sec = divmod(g, 60)
        n = i % 4 + 1
        rows.append(("plex", f"2026-10-12T03:{m:02d}:{sec:02d}Z", 180000, "Metronome Club", f"Tick {n}", None,
                     f"plex:9{n}", 1, f"metronomeclub|tick{n}", None, None))
    rows.append(("lastfm", "2026-10-14T18:00:00Z", None, "Ada Vey", "Coil", "Quiet Engines", None, 1, "adavey|coil", None, None))
    rows.append(("applemusic", "2026-10-14T18:40:00Z", 402000, "Ada Vey", "Coil", "Quiet Engines", "daily:2026-10-14:18", 0,
                 "adavey|coil", None, "lastfm"))
    rows.append(("plex", "2026-10-13T09:00:00Z", 200000, "Ghost Line", "Orphan", None, "plex:99", 0,
                 "ghostline|orphan", None, "lastfm"))
    return rows


CHECK_LISTENS = _check_listens()

MATCHES = [("kollektivnord|westkreuz", 101), ("kollektivnord|ostkreuz", 102), ("paperlanterns|harbourlights", 103),
           ("paperlanterns|staticgulls", 104), ("adavey|coil", 105), ("nobodyknown|ghostsong", None)]

META = [("last_sync", str(SYNC)), ("history_version", "1793847900.5"), ("match_version", "3"),
        ("server", json.dumps(SERVER))]
# Shape of jimbo-dj's history_imports (history.py); times are Unix seconds.
IMPORTS = [
    (1, "lastfm", 1793840400, 120, 4, None),
    (2, "plex", 1793844300, 80, 2, None),
    (3, "spotify", 1793847900, 0, 0, "file not found"),
]
# jimbo-dj's stored summaries (statcache.py), cut down to the numbers traqfreq compares with.
# T9: library.stats in full (library.py stats), by hand from TRACKS + LIBRARY: 5 live tracks, 1,478,000 ms =
# 0.4 h, 102.1 MB = 0.1 GB. Its stamp (statcache: [last_sync, history_version]) is fresh.
LIBRARY_STATS = {
    "server": SERVER, "last_sync": SYNC, "tracks": 5, "artists": 3, "albums": 3, "hours": 0.4, "size_gb": 0.1,
    "codecs": {"flac": 2, "mp3": 2, "aac": 1},
    "containers": {"mp3": 2, "flac": 1, "mp4": 1, "?": 1},
    "bitrate_kbps": {"<192k": 1, "192-255k": 0, "256-319k": 1, "320k": 1, ">320k (lossless)": 1},
    "play_history": {"played_tracks": 2, "played_pct": 40.0, "total_plays": 5, "rated_tracks": 2, "rated_pct": 40.0,
                     "top_artists": {"Kollektiv Nord": 3, "The Paper Lanterns": 2}},
    "sonic_analysis": {"tracks": 3, "pct": 60.0},
    "paths": {"folders": {"/music": {"read_from": "/srv/music", "readable_here": True, "tracks": 5}},
              "mapped": 4, "mapped_pct": 80.0, "unmapped_examples": ["/music/Ada Vey/Quiet Engines/01 Coil.flac"],
              "multi_part_tracks": 1, "removed_since_first_sync": 1},
}
LIBRARY_STAMP = json.dumps([str(SYNC), "1793847900.5"])
STATS = [
    ("library.stats", LIBRARY_STATS, 1),
    ("history.overview", {"plays": 6, "songs": 6, "songs_matched": 5, "matched_pct": 83.3,
                          "years": [{"year": 2025, "plays": 1}, {"year": 2026, "plays": 5}],
                          "top_artists": [{"name": "Kollektiv Nord", "plays": 2, "artist_key": 301},
                                          {"name": "The Paper Lanterns", "plays": 2, "artist_key": 302},
                                          {"name": "Ada Vey", "plays": 1, "artist_key": 303},
                                          {"name": "Nobody Known", "plays": 1, "artist_key": None}],
                          "timezone": "America/Denver"}, 2),
]

# T8: jimbo-dj's stored Wrapped rows (history.wrapped, params = the period), cut down to numbers worked out
# by hand from LISTENS above (America/Denver). Stamp = statcache._history_stamp for META (fresh), except
# 2026-10: built before the last import (an older stamp) with a play count that is no longer right, as a
# stale row is. families/decades are TAGS/LIBRARY numbers that P1 doesn't compare.
STAMP = json.dumps(["1793847900.5", str(SYNC), None])
OLD_STAMP = json.dumps(["1793240000.0", str(OLD_SYNC), None])
WRAPPED_STATS = [
    ("2025", {"year": 2025, "month": None, "day": None, "plays": 1, "hours": 0.1, "artists": 1, "songs": 1,
              "new_artists": 1, "in_library_pct": 100.0,
              "top_artists": [{"name": "Kollektiv Nord", "plays": 1, "artist_key": 301}],
              "decades": [{"label": "2010s", "value": 1}]}, STAMP),
    ("2026", {"year": 2026, "month": None, "day": None, "plays": 5, "hours": 0.4, "artists": 4, "songs": 5,
              "new_artists": 3, "in_library_pct": 80.0, "busiest_day": {"date": "2026-11-01", "plays": 2},
              "top_artists": [{"name": "The Paper Lanterns", "plays": 2, "artist_key": 302},
                              {"name": "Kollektiv Nord", "plays": 1, "artist_key": 301},
                              {"name": "Ada Vey", "plays": 1, "artist_key": 303},
                              {"name": "Nobody Known", "plays": 1, "artist_key": None}],
              "top_albums": [{"artist": "The Paper Lanterns", "album": "Low Tide Radio", "plays": 2, "album_key": 202},
                             {"artist": "Kollektiv Nord", "album": "Ringbahn", "plays": 1, "album_key": 201},
                             {"artist": "Ada Vey", "album": "Quiet Engines", "plays": 1, "album_key": 203}],
              "families": []}, STAMP),
    ("2026-10", {"year": 2026, "month": 10, "day": None, "plays": 3}, OLD_STAMP),
    ("2026-11-01", {"year": 2026, "month": 11, "day": 1, "plays": 2, "hours": 0.1, "artists": 2, "songs": 2,
                    "new_artists": 1, "every_play": [
                        {"time": "13:15", "artist": "Kollektiv Nord", "title": "Westkreuz", "album": "Ringbahn",
                         "source": "Last.fm", "rating_key": 101, "album_key": 201, "minutes": 5.2},
                        {"time": "13:21", "artist": "The Paper Lanterns", "title": "Harbour Lights", "album": "Low Tide Radio",
                         "source": "Plex", "rating_key": 103, "album_key": 202, "minutes": 3.7}]}, STAMP),
]


def build(out: Path, checks: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    conn = sqlite3.connect(out)
    with conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO meta VALUES (?, ?)", META)
        conn.executemany(
            "INSERT INTO tracks (rating_key, title, artist, album, album_key, artist_key, track_no, year, duration_ms,"
            " plex_path, seen_at, removed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(rk, t, a, al, ak, rk_a, n, y, d, f"/music/{a}/{al}/{n:02d} {t}.flac", OLD_SYNC if rm else SYNC, rm)
             for rk, t, a, al, ak, rk_a, n, y, d, rm in TRACKS],
        )
        conn.executemany("INSERT INTO albums (album_key, title, artist_key, year, seen_at) VALUES (?, ?, ?, ?, ?)",
                         [(*r, SYNC) for r in ALBUMS])
        conn.executemany("INSERT INTO artists (artist_key, title, seen_at) VALUES (?, ?, ?)",
                         [(*r, SYNC) for r in ARTISTS])
        conn.executemany(
            "UPDATE tracks SET codec = ?, container = ?, bitrate = ?, file_size = ?, parts = ?, local_path = ?,"
            " view_count = ?, last_viewed_at = ?, user_rating = ?, sonic_version = ?, added_at = ? WHERE rating_key = ?",
            [(c, ct, br, size, parts, plex_path.replace("/music/", "/srv/music/", 1) if mapped else None, views,
              _t(last) if last else None, rating, sonic, _t(added), rk)
             for rk, (c, ct, br, size, parts, mapped, views, last, rating, sonic, added) in LIBRARY.items()
             for (plex_path,) in conn.execute("SELECT plex_path FROM tracks WHERE rating_key = ?", (rk,))],
        )
        conn.executemany(
            "INSERT INTO analysis (rating_key, version, status, error, analyzed_at) VALUES (?, ?, ?, ?, ?)",
            [(*r, SYNC) for r in ANALYSIS],
        )
        conn.executemany("INSERT INTO features (rating_key, bpm, camelot, loudness_lufs) VALUES (?, ?, ?, ?)", FEATURES)
        conn.executemany(
            "INSERT INTO listens (id, source, started_at, ms_played, artist, title, album, uri, counted, match_key,"
            " rating_key, dup_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(i, src, _t(at), *rest) for i, (src, at, *rest) in enumerate(LISTENS + (CHECK_LISTENS if checks else []), 1)],
        )
        conn.executemany("INSERT INTO listen_matches VALUES (?, ?)", MATCHES)
        conn.executemany("INSERT INTO history_imports VALUES (?, ?, ?, ?, ?, ?)", IMPORTS)
        conn.executemany(
            "INSERT INTO stats VALUES (?, '', ?, ?, ?, ?, 0.1)",
            [(name, json.dumps(value), version, LIBRARY_STAMP if name == "library.stats" else None, SYNC + 60)
             for name, value, version in STATS],
        )
        conn.executemany(
            "INSERT INTO stats VALUES ('history.wrapped', ?, ?, 2, ?, ?, 0.1)",
            [(params, json.dumps(value), stamp, SYNC + 120) for params, value, stamp in WRAPPED_STATS],
        )
    conn.close()
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--checks"]
    target = Path(args[0]) if args else Path(__file__).resolve().parents[1] / "tests/fixtures/legacy.sqlite"
    print(build(target, checks="--checks" in sys.argv))
