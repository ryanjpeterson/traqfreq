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
- stats: jimbo-dj's own stored summaries (library.stats, history.overview), trimmed to the counts and the
  top artists.

Usage: python scripts/make_fixture.py [out_path]   (default tests/fixtures/legacy.sqlite)
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
# rating_key, status, error
ANALYSIS = [(101, "ok", None), (102, "ok", None), (103, "ok", None), (105, "error", "decode failed")]
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
MATCHES = [("kollektivnord|westkreuz", 101), ("kollektivnord|ostkreuz", 102), ("paperlanterns|harbourlights", 103),
           ("paperlanterns|staticgulls", 104), ("adavey|coil", 105), ("nobodyknown|ghostsong", None)]

META = [("last_sync", str(SYNC)), ("history_version", "1793847900.5"), ("match_version", "3")]
# Shape of jimbo-dj's history_imports (history.py); times are Unix seconds.
IMPORTS = [
    (1, "lastfm", 1793840400, 120, 4, None),
    (2, "plex", 1793844300, 80, 2, None),
    (3, "spotify", 1793847900, 0, 0, "file not found"),
]
# jimbo-dj's stored summaries (statcache.py), cut down to the numbers traqfreq compares with.
STATS = [
    ("library.stats", {"last_sync": SYNC, "tracks": 5, "albums": 3, "artists": 3}, 1),
    ("history.overview", {"plays": 6, "songs": 6, "songs_matched": 5, "matched_pct": 83.3,
                          "years": [{"year": 2025, "plays": 1}, {"year": 2026, "plays": 5}],
                          "top_artists": [{"name": "Kollektiv Nord", "plays": 2, "artist_key": 301},
                                          {"name": "The Paper Lanterns", "plays": 2, "artist_key": 302},
                                          {"name": "Ada Vey", "plays": 1, "artist_key": 303},
                                          {"name": "Nobody Known", "plays": 1, "artist_key": None}],
                          "timezone": "America/Denver"}, 2),
]


def build(out: Path) -> Path:
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
            "INSERT INTO analysis (rating_key, version, status, error, analyzed_at) VALUES (?, 7, ?, ?, ?)",
            [(*r, SYNC) for r in ANALYSIS],
        )
        conn.executemany("INSERT INTO features (rating_key, bpm, camelot, loudness_lufs) VALUES (?, ?, ?, ?)", FEATURES)
        conn.executemany(
            "INSERT INTO listens (id, source, started_at, ms_played, artist, title, album, uri, counted, match_key,"
            " rating_key, dup_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(i, src, _t(at), *rest) for i, (src, at, *rest) in enumerate(LISTENS, 1)],
        )
        conn.executemany("INSERT INTO listen_matches VALUES (?, ?)", MATCHES)
        conn.executemany("INSERT INTO history_imports VALUES (?, ?, ?, ?, ?, ?)", IMPORTS)
        conn.executemany(
            "INSERT INTO stats VALUES (?, '', ?, ?, NULL, ?, 0.1)",
            [(name, json.dumps(value), version, SYNC + 60) for name, value, version in STATS],
        )
    conn.close()
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "tests/fixtures/legacy.sqlite"
    print(build(target))
