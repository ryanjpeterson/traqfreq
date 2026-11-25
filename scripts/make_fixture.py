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
- T11, still on those 6 tracks (no count above changes): disc numbers, so Low Tide Radio's order (disc 1
  "Static Gulls", then disc 2 "Harbour Lights") differs from track_no order; Plex release dates and labels on
  two albums, and a cached MusicBrainz release (mb_releases, jimbo-dj's shape) whose first release (2020) is
  older than Plex's year (2021), so an album's year is jimbo-dj's _release_years, not tracks.year; key, scale
  and moods on the analysed tracks. Tests that need a second copy of a song add one to a scratch copy.
- T12, the P2 gate: bit depth, sample rate, channels and stream size on the 6 tracks (FILES), Plex and
  MusicBrainz places for two artists (ARTIST_INFO, an mb_artists table in jimbo-dj's shape), and jimbo-dj's
  stored library.charts (fixture_library_charts.json: Files, Time, Place, keys and Sound worked out by hand from
  the rows here, in America/Denver; genres and styles invented, as TAGS doesn't count them in P2). That row is
  stale: its stamp is from before the last sync, when Old Signal (FLAC) was still live, so its FLAC count is 3,
  not 2, the one explained difference the gate shows. No count above changes.
- T20, TAGS (P4): invented genre tags in jimbo-dj's shape on those same rows (TAGS below; no count above
  changes): Plex album, artist and track genres (albums.genres, artists.genres, tracks.plex_genres, JSON lists) and
  MusicBrainz genre votes (mb_releases.genres, mb_artists.genres, JSON {genre: votes}). Chosen so the ladder has
  every case: three rungs (Metal, Black Metal, Atmospheric Black Metal), a tag with two parents (Death-Doom
  Metal under Death Metal and Doom Metal), an album missing its broad tag (Low Tide Radio has no Metal), a
  misspelling ("doom metal") and an alias ("Hip-Hop"), a tag that isn't a genre ("2010s"), a tag with no broad
  tag (Soundtrack), a name inside another under a different broad tag (Post-Punk is Rock, not Punk), a tag only
  tracks carry (Ambient, on Westkreuz, an ambient intro on a black metal album), and the removed album's tag
  (jimbo-dj's tags read every album row). jimbo-dj's stored library.tags (TAGS_STORED, trimmed to its families,
  worked out by hand with tags.py's rules) is fresh.
- T21, tracks tagged one by one (P4; STYLES and FILE_TAGS below; no count above changes): the analyzer's Discogs
  styles on the three analysed tracks (features.genres, JSON {"Rock---Black Metal": score}), chosen so jimbo-dj's
  strict test (genres.Styles) keeps a style its metadata names (Black Metal, Ambient), one of a family the metadata
  names (Dark Ambient: Electronic, from Westkreuz's Ambient; Shoegaze: Rock, from Post-Punk), and drops one too weak
  (Drone, under GENRE_MIN), one of another family (Punk on Westkreuz) and one the sound alone is sure of but the
  metadata contradicts (Synth-Pop on Ostkreuz, 0.9). And jimbo-dj's file_tags table (filetags.py's shape): the
  files' genres of the live tracks, one with a tag Plex didn't keep (Ostkreuz's Atmospheric Black Metal), one with a
  tag no album, artist or track has (Drone, so it is on no rung), and one file that couldn't be read. The stored
  library.tags stamp takes the file tags' newest read, so it stays fresh.
- T22, the proposals inbox and gate check 3 (P4; no row changes, so no count above changes): jimbo-dj's stored
  library.tags gains the rest of what check 3 compares (TAGS_STORED: every tag's numbers and issues, the album
  issue counts, the fixes and the suggestions), worked out by hand. The rows above already hold one proposal of
  each kind: a junk tag, a casing fix, two missing broad tags, niche tags, suggestions, and one ladder proposal of
  traqfreq's (Low Tide Radio carries Death-Doom Metal and Doom Metal but not Death Metal, its other parent).
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
CREATE TABLE mb_releases (
    mbid TEXT PRIMARY KEY, fetched_at INTEGER NOT NULL, status TEXT NOT NULL, title TEXT, date TEXT, country TEXT,
    labels TEXT, first_release TEXT, primary_type TEXT, secondary_types TEXT, genres TEXT
);
CREATE TABLE artists (
    artist_key INTEGER PRIMARY KEY, title TEXT, countries TEXT, genres TEXT, mbid TEXT, seen_at INTEGER
);
CREATE TABLE mb_artists (
    mbid TEXT PRIMARY KEY, fetched_at INTEGER NOT NULL, status TEXT NOT NULL, name TEXT, type TEXT, country TEXT,
    area TEXT, begin_area TEXT, begin_year INTEGER, end_year INTEGER, genres TEXT
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
CREATE TABLE file_tags (
    rating_key INTEGER PRIMARY KEY, size INTEGER, mtime INTEGER, genres TEXT, read_at INTEGER NOT NULL, error TEXT
);
CREATE TABLE stats (
    name TEXT NOT NULL, params TEXT NOT NULL, value TEXT NOT NULL, version INTEGER NOT NULL, stamp TEXT,
    built_at REAL NOT NULL, seconds REAL, PRIMARY KEY (name, params)
) WITHOUT ROWID;
CREATE TABLE saved_playlists (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL UNIQUE, summary TEXT, keys TEXT NOT NULL, source TEXT,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, in_plex INTEGER NOT NULL DEFAULT 0, plex_key INTEGER,
    pushed_at INTEGER, plex_error TEXT, stale INTEGER NOT NULL DEFAULT 0, stale_in_plex INTEGER
);
CREATE TABLE mixes (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, period TEXT NOT NULL, created_at INTEGER NOT NULL,
    title TEXT NOT NULL, tracks TEXT NOT NULL, summary TEXT, pushed_at INTEGER, push_result TEXT
);
CREATE TABLE cluster_runs (
    id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL, tracks INTEGER, clusters INTEGER, noise INTEGER, params TEXT, seconds REAL
);
CREATE TABLE clusters (
    run_id INTEGER NOT NULL, id INTEGER NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL, stats TEXT, art TEXT,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE cluster_members (
    run_id INTEGER NOT NULL, cluster_id INTEGER NOT NULL, rating_key INTEGER NOT NULL, prob REAL,
    PRIMARY KEY (run_id, rating_key)
) WITHOUT ROWID;
CREATE TABLE bans (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL, label TEXT NOT NULL, created_at INTEGER NOT NULL,
    UNIQUE (kind, ref)
);
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
# T11: rating_key: disc. album_key: Plex released, studio (label), MusicBrainz release mbid.
DISCS = {101: 1, 102: 1, 103: 2, 104: 1, 105: 1, 106: 1}
ALBUM_INFO = {201: ("2019-04-12", "Spree Tonträger", None),
              202: ("2021-02-05", "Harbour House", "00000000-0000-4000-8000-000000000202")}
# mbid, title, date, country, labels, first_release, primary_type, secondary_types
MB_RELEASES = [("00000000-0000-4000-8000-000000000202", "Low Tide Radio", "2021-02-05", "GB", ["Harbour House"],
                "2020-10-01", "Album", [])]
# rating_key: key, scale, moods (jimbo-dj's analyzer: {mood: score})
KEYS = {101: ("A", "minor", {"party": 0.8, "aggressive": 0.4, "happy": 0.3, "sad": 0.1}),
        102: ("E", "minor", {"sad": 0.6, "relaxed": 0.5}),
        103: ("G", "major", {"relaxed": 0.7, "happy": 0.6})}
# T12: the file and place columns jimbo-dj's Library charts read (library.charts). rating_key: bit_depth,
# sample_rate, channels, stream_size. 101 is hi-res (24-bit, 96 kHz), 105 CD-quality; 104 is mono.
FILES = {101: (24, 96000, 2, 39_100_000), 102: (None, 44100, 2, 4_700_000), 103: (None, 44100, 2, None),
         104: (None, 48000, 1, None), 105: (16, 44100, 2, None), 106: (16, 44100, 2, 19_900_000)}
# artist_key: Plex countries, MusicBrainz artist mbid. The Paper Lanterns' country comes from MusicBrainz
# (its long name, which jimbo-dj shortens), with a hometown; Ada Vey has neither.
ARTIST_INFO = {301: (["Germany"], None), 302: (None, "00000000-0000-4000-8000-000000000302")}
# mbid, name, type, country, area, begin_area, begin_year
MB_ARTISTS = [("00000000-0000-4000-8000-000000000302", "The Paper Lanterns", "Group", "GB",
               "United Kingdom of Great Britain and Northern Ireland", "Brighton", 2016)]

# T20: genre tags (invented). album_key: Plex album genres; artist_key: Plex artist genres; rating_key: Plex track
# genres; mbid: MusicBrainz genre votes (release, artist).
TAGS = {
    "albums": {201: ["Atmospheric Black Metal", "Black Metal", "Metal"], 202: ["Death-Doom Metal", "doom metal"],
               203: ["Lo-Fi Hip Hop", "Soundtrack", "2010s"], 204: ["Punk"]},
    "artists": {301: ["Black Metal"], 302: ["Death Metal", "Post-Punk"], 303: ["Hip-Hop"]},
    "tracks": {101: ["Ambient", "Black Metal"], 102: ["Black Metal"], 103: ["Doom Metal"], 104: ["Doom Metal"]},
    "mb_releases": {"00000000-0000-4000-8000-000000000202": {"death-doom metal": 3, "doom metal": 2}},
    "mb_artists": {"00000000-0000-4000-8000-000000000302": {"death metal": 4, "post-punk": 2}},
}
# jimbo-dj's stored library.tags (statcache: tags.Library.overview), trimmed to the families (the broad tags, each
# with the albums under it, those carrying it, those missing it, and its children with albums), by hand:
# - Metal: Ringbahn carries it; Low Tide Radio's Death-Doom Metal and Doom Metal call for it: 2 albums, 1 tagged,
#   1 missing. Children by albums, then name: Atmospheric Black Metal, Black Metal, Death-Doom Metal, Doom Metal
#   (1 each; Death Metal is only an artist's tag, so no albums).
# - Hip Hop: Quiet Engines' Lo-Fi Hip Hop calls for it (Ada Vey's Hip-Hop is an artist tag): 1 album, 0, 1.
# - Punk: Gone Album carries it: 1, 1, 0, no children. Soundtrack has no broad tag; 2010s is junk; Ambient
#   (Electronic) and Post-Punk (Rock) have no albums, so Electronic and Rock aren't families.
# Stamp (tags.stamp): MusicBrainz releases' and artists' newest fetched_at, last_sync, genres.version(), the
# rules file's mtime, file tags, Fix in Plex: fresh.
TAGS_STORED = {"families": [
    {"tag": "Metal", "key": "metal", "albums": 2, "tagged": 1, "missing": 1, "children": [
        {"tag": "Atmospheric Black Metal", "key": "atmospheric black metal", "albums": 1},
        {"tag": "Black Metal", "key": "black metal", "albums": 1},
        {"tag": "Death-Doom Metal", "key": "death-doom metal", "albums": 1},
        {"tag": "Doom Metal", "key": "doom metal", "albums": 1}]},
    {"tag": "Hip Hop", "key": "hip hop", "albums": 1, "tagged": 0, "missing": 1, "children": [
        {"tag": "Lo-Fi Hip Hop", "key": "lo-fi hip hop", "albums": 1}]},
    {"tag": "Punk", "key": "punk", "albums": 1, "tagged": 1, "missing": 0, "children": []}]}
# T22: the rest of the stored row gate check 3 compares (tags.Library.overview's tags, summary.issues, fixes and
# suggestions), trimmed to the compared fields, by hand with tags.py's rules on the rows here:
# - Tags (albums, artists, tracks = live tracks' Plex genres, MusicBrainz = release and artist rows naming it,
#   sound = albums whose analysed tracks have the style on at least 0.4 of them, issues). "doom metal" is a
#   spelling of Doom Metal, "Hip-Hop" of Hip Hop; 2010s is junk (decades); Atmospheric Black Metal, Lo-Fi Hip Hop
#   and Soundtrack are on one album each and unknown to MusicBrainz: niche.
# - Album issues: Quiet Engines (junk 2010s, niche Lo-Fi Hip Hop and Soundtrack, broad Hip Hop), Low Tide Radio
#   (case "doom metal", broad Metal), Ringbahn (niche Atmospheric Black Metal); Gone Album is clean.
# - Fixes (biggest first, then by tag): remove 2010s, add Hip Hop, add Metal, rename "doom metal" to Doom Metal.
# - Suggestions: Ambient for Ringbahn (half its tracks and files, and its sound), Death Metal, Post-Punk (the
#   artist's MusicBrainz votes) and Drone (half Low Tide Radio's files) for Low Tide Radio.
_NICHE = [{"kind": "niche", "op": "remove"}]
TAGS_STORED.update({
    "summary": {"albums": 4, "artists": 4, "clean": 1,
                "issues": {"junk": 1, "split": 0, "spelling": 0, "case": 1, "broad": 2, "niche": 2, "untagged": 0}},
    "tags": [
        {"key": "black metal", "name": "Black Metal", "albums": 1, "artists": 1, "tracks": 2, "musicbrainz": 0, "sound": 1, "issues": []},
        {"key": "doom metal", "name": "Doom Metal", "albums": 1, "artists": 0, "tracks": 2, "musicbrainz": 1, "sound": 1,
         "issues": [{"kind": "spelling", "op": "rename", "from": ["doom metal"], "to": "Doom Metal"}]},
        {"key": "2010s", "name": "2010s", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0,
         "issues": [{"kind": "junk", "op": "remove", "rule": "decades"}]},
        {"key": "atmospheric black metal", "name": "Atmospheric Black Metal", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0, "issues": _NICHE},
        {"key": "death metal", "name": "Death Metal", "albums": 0, "artists": 1, "tracks": 0, "musicbrainz": 1, "sound": 0, "issues": []},
        {"key": "death-doom metal", "name": "Death-Doom Metal", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 1, "sound": 0, "issues": []},
        {"key": "hip hop", "name": "Hip Hop", "albums": 0, "artists": 1, "tracks": 0, "musicbrainz": 0, "sound": 0,
         "issues": [{"kind": "spelling", "op": "rename", "from": ["Hip-Hop"], "to": "Hip Hop"}]},
        {"key": "lo-fi hip hop", "name": "Lo-Fi Hip Hop", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0, "issues": _NICHE},
        {"key": "metal", "name": "Metal", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0, "issues": []},
        {"key": "post-punk", "name": "Post-Punk", "albums": 0, "artists": 1, "tracks": 0, "musicbrainz": 1, "sound": 0, "issues": []},
        {"key": "punk", "name": "Punk", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0, "issues": []},
        {"key": "soundtrack", "name": "Soundtrack", "albums": 1, "artists": 0, "tracks": 0, "musicbrainz": 0, "sound": 0, "issues": _NICHE},
        {"key": "ambient", "name": "Ambient", "albums": 0, "artists": 0, "tracks": 1, "musicbrainz": 0, "sound": 1, "issues": []}],
    "fixes": [
        {"op": "remove", "kind": "junk", "tag": "2010s", "to": [], "albums": 1},
        {"op": "add", "kind": "broad", "tag": "Hip Hop", "to": [], "albums": 1},
        {"op": "add", "kind": "broad", "tag": "Metal", "to": [], "albums": 1},
        {"op": "rename", "kind": "case", "tag": "doom metal", "to": ["Doom Metal"], "albums": 1}],
    "suggestions": [
        {"tag": "Ambient", "albums": 1, "key": "ambient", "in_use": True},
        {"tag": "Death Metal", "albums": 1, "key": "death metal", "in_use": True},
        {"tag": "Post-Punk", "albums": 1, "key": "post-punk", "in_use": True},
        {"tag": "Drone", "albums": 1, "key": "drone", "in_use": False}],
})
# T21: the analyzer's Discogs styles (features.genres) and the files' genres (file_tags), invented.
STYLES = {101: {"Rock---Black Metal": 0.62, "Electronic---Ambient": 0.48, "Electronic---Dark Ambient": 0.3, "Rock---Punk": 0.2},
          102: {"Rock---Black Metal": 0.7, "Electronic---Synth-pop": 0.9},
          103: {"Rock---Doom Metal": 0.55, "Rock---Shoegaze": 0.25, "Electronic---Drone": 0.1}}
FILE_TAGS_READ = SYNC + 1800
# rating_key: (genres as the file has them, or None; error)
FILE_TAGS = {101: (["Black Metal", "Ambient"], None), 102: (["Black Metal", "Atmospheric Black Metal"], None),
             103: (["Doom Metal"], None), 104: (["Doom Metal", "Drone"], None), 105: (None, "unreadable")}
TAGS_STAMP = json.dumps([SYNC, SYNC, str(SYNC), 7, 1795000000.0, FILE_TAGS_READ, None])


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

# T24: jimbo-dj's saved playlists (store.py saved_playlists), its mixes, its current cluster run and Never in mixes,
# in their shapes at 1d8a7cb. Invented: one row per kind, one stale, three trees (AND, OR, NOT, a nested group, in:
# scopes), an old Explore filter and a genre blend. Nothing earlier counts these tables, so T5-T23's numbers stay.
_NIGHT = {"n": 20, "per_artist": 3, "shuffle": 0, "branches": [
    {"id": "a", "label": "Ringbahn, not sad", "share": 8,
     "match": {"all": [{"f": "decade", "v": "2010s"}], "not": [{"f": "mood", "v": "sad"}]}},
    {"id": "b", "share": 6, "match": {"all": [{"any": [{"f": "artist", "v": "Ada Vey"}, {"f": "listened", "v": "2025"}]}]}},
    {"id": "c", "share": 6, "match": {"all": [{"f": "mood", "v": "happy"},
                                              {"any": [{"f": "bpm", "v": "100-110"}, {"f": "key", "v": "8A"}]}]}}]}
_INSIDE = {"n": 20, "per_artist": 3, "shuffle": 2, "branches": [
    {"id": "a", "share": 10, "match": {"all": [{"f": "in", "v": "saved:from-the-2020s"}],
                                       "not": [{"f": "in", "v": "cluster:quiet-engines"}]}},
    {"id": "b", "share": 10, "match": {"all": [{"f": "in", "v": "mix:daily"}]}}]}
# id, kind, title, keys, source, in_plex, plex_key, pushed_at, plex_error, stale, stale_in_plex, updated_at
SAVED = [
    (1, "explore", "\U0001F9ED Night lines", [101, 103, 102, 105],
     {"make": {"type": "rules", "rules": _NIGHT}, "from": "/library/tracks?b=decade:2010s,!mood:sad~8~Ringbahn%2C not sad"},
     1, 9001, SYNC + 200, None, 0, None, SYNC + 200),
    (2, "blend", "\U0001F3A7 Blend: Black Metal / Doom Metal", [101, 103, 102],
     {"parts": [{"style": "black metal", "weight": 60}, {"style": "doom metal", "weight": 40}], "n": 20, "per_artist": 3,
      "shuffle": 0}, 0, None, None, None, 0, None, SYNC + 210),
    (3, "explore", "\U0001F9ED From the 2020s", [103, 104, 105],
     {"make": {"type": "filter", "filters": {"decade": "2020s"}}, "from": "/library/tracks?decade=2020s"},
     0, None, None, None, 0, None, SYNC + 220),
    (4, "mix", "\U0001F3A7 Daily mix", [101, 103, 104], {"mix": "daily", "period": "2026-11-05"},
     1, 9002, SYNC + 230, None, 0, None, SYNC + 230),
    (5, "cluster", "\U0001FAA9 Quiet Engines", [105, 103], {"cluster_id": 1}, 0, None, None, None, 0, None, SYNC + 240),
    (6, "cluster", "\U0001FAA9 Gone Grey", [106], {"cluster_id": 7}, 0, None, OLD_SYNC, None, 1, 1, OLD_SYNC + 60),
    (7, "like", "\U0001F501 More like Westkreuz", [101, 102], {"seed": {"type": "track", "key": 101}},
     1, None, None, "Plex didn't answer", 0, None, SYNC + 250),
    (8, "history", "\U0001F3A7 Top songs of 2026", [103, 105, 101], {"make": {"type": "period", "period": "2026"}, "from": "/history/wrapped/2026"},
     0, None, None, None, 0, None, SYNC + 260),
    (9, "setlist", "\U0001F3A4 Kollektiv Nord live", [102, 101], {"setlist": "fixture-1"}, 0, None, None, None, 0, None, SYNC + 270),
    (10, "explore", "\U0001F9ED Inside the lines", [104, 101, 103], {"make": {"type": "rules", "rules": _INSIDE}},
     0, None, None, None, 0, None, SYNC + 280),
]
MIXES = [(1, "daily", "2026-11-05", SYNC + 230, "Daily mix", [[101, "favourite"], [103, "new"], [104, "overlooked"]],
          "3 tracks", SYNC + 230)]
CLUSTER_RUN = (1, SYNC - 3600, 5, 2, 0, "{}", 12.5)
CLUSTERS = [(1, 1, "Quiet Engines", 2), (1, 2, "Harbour Haze", 1)]
CLUSTER_MEMBERS = [(1, 1, 103, 0.9), (1, 1, 105, 0.8), (1, 2, 104, 0.7)]
BANS = [(1, "artist", "formerband", "Former Band", SYNC + 300)]

META = [("last_sync", str(SYNC)), ("history_version", "1793847900.5"), ("match_version", "3"),
        ("server", json.dumps(SERVER)), ("cluster_run", "1")]
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
# T12: jimbo-dj's stored library.charts (statcache._library_charts) and its stamp (statcache._library_stamp:
# [cache.data_stamp = analysis rows, newest analyzed_at, last_sync; mb_artists and mb_releases rows and newest
# fetched_at; genres.version(), an in-memory counter; history_version]), from before the last sync: stale.
LIBRARY_CHARTS = json.loads((Path(__file__).with_name("fixture_library_charts.json")).read_text(encoding="utf-8"))
CHARTS_STAMP = json.dumps([[3, OLD_SYNC, str(OLD_SYNC)], [[1, OLD_SYNC], [1, OLD_SYNC]], 5, "1793240000.0"])
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
        conn.executemany("UPDATE tracks SET disc = ? WHERE rating_key = ?", [(d, rk) for rk, d in DISCS.items()])
        conn.executemany("UPDATE albums SET released = ?, studio = ?, mbid = ? WHERE album_key = ?",
                         [(*v, ak) for ak, v in ALBUM_INFO.items()])
        conn.executemany(
            "INSERT INTO mb_releases VALUES (?, ?, 'ok', ?, ?, ?, ?, ?, ?, ?, '{}')",
            [(m, SYNC, title, date, c, json.dumps(labels), first, kind, json.dumps(sec))
             for m, title, date, c, labels, first, kind, sec in MB_RELEASES])
        conn.executemany("UPDATE features SET key = ?, scale = ?, moods = ? WHERE rating_key = ?",
                         [(k, sc, json.dumps(m), rk) for rk, (k, sc, m) in KEYS.items()])
        conn.executemany("UPDATE tracks SET bit_depth = ?, sample_rate = ?, channels = ?, stream_size = ? WHERE rating_key = ?",
                         [(*v, rk) for rk, v in FILES.items()])
        conn.executemany("UPDATE artists SET countries = ?, mbid = ? WHERE artist_key = ?",
                         [(json.dumps(c) if c else None, m, ak) for ak, (c, m) in ARTIST_INFO.items()])
        conn.executemany("INSERT INTO mb_artists VALUES (?, ?, 'ok', ?, ?, ?, ?, ?, ?, NULL, '{}')",
                         [(m, SYNC, *rest) for m, *rest in MB_ARTISTS])
        conn.executemany("UPDATE albums SET genres = ? WHERE album_key = ?",
                         [(json.dumps(g), k) for k, g in TAGS["albums"].items()])
        conn.executemany("UPDATE artists SET genres = ? WHERE artist_key = ?",
                         [(json.dumps(g), k) for k, g in TAGS["artists"].items()])
        conn.executemany("UPDATE tracks SET plex_genres = ? WHERE rating_key = ?",
                         [(json.dumps(g), k) for k, g in TAGS["tracks"].items()])
        conn.executemany("UPDATE features SET genres = ? WHERE rating_key = ?",
                         [(json.dumps(g), rk) for rk, g in STYLES.items()])
        conn.executemany("INSERT INTO file_tags VALUES (?, NULL, NULL, ?, ?, ?)",
                         [(rk, json.dumps(g) if g is not None else None, FILE_TAGS_READ, err)
                          for rk, (g, err) in FILE_TAGS.items()])
        for table in ("mb_releases", "mb_artists"):
            conn.executemany(f"UPDATE {table} SET genres = ? WHERE mbid = ?",
                             [(json.dumps(g), m) for m, g in TAGS[table].items()])
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
        conn.execute("INSERT INTO stats VALUES ('library.charts', '', ?, 1, ?, ?, 0.4)",
                     (json.dumps(LIBRARY_CHARTS, ensure_ascii=False, separators=(",", ":")), CHARTS_STAMP, OLD_SYNC + 60))
        conn.execute("INSERT INTO stats VALUES ('library.tags', '', ?, 1, ?, ?, 0.2)",
                     (json.dumps(TAGS_STORED), TAGS_STAMP, SYNC + 90))
        conn.executemany(
            "INSERT INTO stats VALUES ('history.wrapped', ?, ?, 2, ?, ?, 0.1)",
            [(params, json.dumps(value), stamp, SYNC + 120) for params, value, stamp in WRAPPED_STATS],
        )
        conn.executemany(
            "INSERT INTO saved_playlists (id, kind, title, summary, keys, source, created_at, updated_at, in_plex, plex_key,"
            " pushed_at, plex_error, stale, stale_in_plex) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(i, kind, title, f"{len(keys)} tracks. Made by jimbo-dj.", json.dumps(keys), json.dumps(src), SYNC - 86400,
              updated, plex, pk, pushed, err, stale, stale_plex)
             for i, kind, title, keys, src, plex, pk, pushed, err, stale, stale_plex, updated in SAVED])
        conn.executemany("INSERT INTO mixes VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                         [(i, k, p, at, t, json.dumps(tr), sm, pushed) for i, k, p, at, t, tr, sm, pushed in MIXES])
        conn.execute("INSERT INTO cluster_runs VALUES (?, ?, ?, ?, ?, ?, ?)", CLUSTER_RUN)
        conn.executemany("INSERT INTO clusters (run_id, id, name, size) VALUES (?, ?, ?, ?)", CLUSTERS)
        conn.executemany("INSERT INTO cluster_members VALUES (?, ?, ?, ?)", CLUSTER_MEMBERS)
        conn.executemany("INSERT INTO bans VALUES (?, ?, ?, ?, ?)", BANS)
    conn.close()
    return out


# T14: invented Jellyfin and Navidrome answers, in each API's shape (scripts/fixture_jellyfin.json,
# fixture_navidrome.json). They are matched against the live copies 101-105 here and, in tests, against a
# scratch copy with the problem cases (tests/test_identity.py EXTRA, 107-112), so between them they cover every
# tier and every reason. The legacy DB is untouched: T5-T13's counts stay.
SNAPSHOT_READ_AT = SYNC + 3600


def snapshot_answers() -> tuple[dict, dict]:
    here = Path(__file__).resolve().parent
    return tuple(json.loads((here / f"fixture_{s}.json").read_text(encoding="utf-8")) for s in ("jellyfin", "navidrome"))


def load_snapshots(data_dir: Path) -> list[str]:
    """Parse the invented answers into snapshots and store them in traqfreq's database under data_dir
    (needs traqfreq importable: PYTHONPATH=src). Never a real data dir."""
    from traqfreq import snapshots, store
    jf, nd = snapshot_answers()
    snaps = [snapshots.from_jellyfin(jf["virtual_folders"], jf["items_pages"], read_at=SNAPSHOT_READ_AT,
                                     info=jf["system_info"], user="listener"),
             snapshots.from_navidrome(nd["scan_status"], nd["album_pages"], nd["song_pages"], read_at=SNAPSHOT_READ_AT,
                                      info=nd["ping"], user="listener", music_folders=nd["music_folders"])]
    for snap in snaps:
        store.save_snapshot(Path(data_dir), snap)
    return [s["server"] for s in snaps]


if __name__ == "__main__":
    if "--snapshots" in sys.argv:  # python scripts/make_fixture.py --snapshots <data dir>
        print(load_snapshots(Path(sys.argv[sys.argv.index("--snapshots") + 1])))
        sys.exit(0)
    args = [a for a in sys.argv[1:] if a != "--checks"]
    target = Path(args[0]) if args else Path(__file__).resolve().parents[1] / "tests/fixtures/legacy.sqlite"
    print(build(target, checks="--checks" in sys.argv))
