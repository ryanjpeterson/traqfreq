"""Build a small SQLite fixture shaped like the subset of jimbo-dj's schema traqfreq reads.

PROVISIONAL SCHEMA: written without access to jimbo-dj's src/jimbodj/db.py (see
HANDOFF.md). Verify table and column names against that file before P1 (T5).
All rows are invented sample data.

Usage: python scripts/make_fixture.py [out_path]   (default tests/fixtures/legacy.sqlite)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE artists (id INTEGER PRIMARY KEY, name TEXT NOT NULL, sort_name TEXT, plex_key TEXT);
CREATE TABLE albums (
  id INTEGER PRIMARY KEY, artist_id INTEGER REFERENCES artists(id), title TEXT NOT NULL,
  year INTEGER, plex_key TEXT
);
CREATE TABLE tracks (
  id INTEGER PRIMARY KEY, album_id INTEGER REFERENCES albums(id), artist_id INTEGER REFERENCES artists(id),
  title TEXT NOT NULL, track_no INTEGER, duration_ms INTEGER, path TEXT, plex_key TEXT, genre TEXT
);
CREATE TABLE listens (
  id INTEGER PRIMARY KEY, track_id INTEGER REFERENCES tracks(id), listened_at TEXT NOT NULL,
  source TEXT NOT NULL, dedupe_key TEXT UNIQUE
);
CREATE TABLE track_analysis (
  track_id INTEGER PRIMARY KEY REFERENCES tracks(id), bpm REAL, musical_key TEXT,
  energy REAL, loudness_db REAL, analyzed_at TEXT
);
CREATE TABLE track_tags (track_id INTEGER REFERENCES tracks(id), tag TEXT NOT NULL, source TEXT,
  PRIMARY KEY (track_id, tag));
"""

ARTISTS = [(1, "Kollektiv Nord", "Kollektiv Nord"), (2, "The Paper Lanterns", "Paper Lanterns, The"), (3, "Ada Vey", "Vey, Ada")]
ALBUMS = [(1, 1, "Ringbahn", 2019), (2, 2, "Low Tide Radio", 2021), (3, 3, "Quiet Engines", 2023)]
TRACKS = [
    (1, 1, 1, "Westkreuz", 1, 312000, "/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac", "Techno"),
    (2, 1, 1, "Ostkreuz", 2, 298000, "/music/Kollektiv Nord/Ringbahn/02 Ostkreuz.flac", "Techno"),
    (3, 2, 2, "Harbour Lights", 1, 221000, "/music/The Paper Lanterns/Low Tide Radio/01 Harbour Lights.mp3", "Indie"),
    (4, 2, 2, "Static Gulls", 2, 245000, "/music/The Paper Lanterns/Low Tide Radio/02 Static Gulls.mp3", "Indie"),
    (5, 3, 3, "Coil", 1, 402000, "/music/Ada Vey/Quiet Engines/01 Coil.flac", "Ambient"),
]
LISTENS = [
    (1, 1, "2026-11-01T20:15:00Z", "plex"),
    (2, 3, "2026-11-01T20:21:00Z", "plex"),
    (3, 3, "2026-11-02T08:02:00Z", "lastfm"),
    (4, 5, "2026-11-03T22:40:00Z", "plex"),
    (5, 2, "2026-11-04T19:05:00Z", "plex"),
    (6, 4, "2026-11-05T18:30:00Z", "lastfm"),
]
ANALYSIS = [(1, 128.0, "8A", 0.82, -7.1), (2, 130.0, "9A", 0.85, -6.8), (3, 104.0, "5B", 0.55, -9.4), (5, 72.0, "2A", 0.21, -16.0)]
TAGS = [(1, "peak-time", "user"), (3, "sunday", "user"), (5, "late-night", "rules")]
META = [
    ("schema_version", "1"),
    ("last_plex_sync", "2026-11-05T03:00:00Z"),
    ("last_lastfm_import", "2026-11-05T03:05:00Z"),
    ("last_library_scan", "2026-11-04T02:00:00Z"),
]


def build(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    conn = sqlite3.connect(out)
    with conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO meta VALUES (?, ?)", META)
        conn.executemany("INSERT INTO artists VALUES (?, ?, ?, NULL)", ARTISTS)
        conn.executemany("INSERT INTO albums VALUES (?, ?, ?, ?, NULL)", ALBUMS)
        conn.executemany("INSERT INTO tracks VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)", TRACKS)
        conn.executemany(
            "INSERT INTO listens VALUES (?, ?, ?, ?, ?)",
            [(i, t, at, src, f"{t}:{at}") for i, t, at, src in LISTENS],
        )
        conn.executemany(
            "INSERT INTO track_analysis VALUES (?, ?, ?, ?, ?, '2026-11-04T02:30:00Z')", ANALYSIS
        )
        conn.executemany("INSERT INTO track_tags VALUES (?, ?, ?)", TAGS)
    conn.close()
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "tests/fixtures/legacy.sqlite"
    print(build(target))
