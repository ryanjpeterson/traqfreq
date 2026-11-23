"""LIBRARY, read-only (T11): albums, artists and a track, the way jimbo-dj's pages show them.

Every number here is jimbo-dj's, counted with its own code (vendored unchanged, vendor/jimbodj_pages.py and
vendor/jimbodj_songs.py): the lists are its Library → Albums and Artists (browse._grouped: live tracks grouped
by album_key or artist_key, plays = SUM of plays_of per track); an album is pages.album's tracks in disc and
track order with each one's plays_of and its other copies, and the listens of those exact copies
(pages._keys_where) summarised by source and year; an artist is pages._library_of (its tracks, and its songs on
other people's albums by track artist), pages._top_songs (each song once, every copy's plays added up) and its
listens (pages._artist_where: by normalised name, plus those matched to its tracks); a track is one copy of a
song (pages.song: the song's listens, every copy, and this copy's).

Not in P2, and the pages say so: MusicBrainz lookups (only what jimbo-dj already cached is shown), the sound
profile and "sounds like", styles and genres (TAGS, P4), story moments and phases, album art (jimbo-dj fetches
it from Plex with its token; traqfreq doesn't call Plex).
"""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlencode

from . import history, legacy, library
from .vendor import jimbodj_library as jl
from .vendor import jimbodj_pages as jp
from .vendor import jimbodj_songs as songs
from .vendor.jimbodj_history import SOURCES

LIVE = legacy.LIVE
LIST_SORTS = ("plays", "added", "name", "year")
KINDS = ("albums", "artists")
PLAYS_OF = library.RULES["plays"]

RULES = {
    "list.albums": f"COUNT(DISTINCT album_key) WHERE {LIVE} (jimbo-dj's Library → Albums, browse._grouped)",
    "list.artists": f"COUNT(DISTINCT artist_key) WHERE {LIVE} (jimbo-dj's Library → Artists, browse._grouped)",
    "list.tracks": f"COUNT(*) of its tracks WHERE {LIVE}",
    "list.plays": f"SUM(plays_of) over its live tracks; plays_of = {PLAYS_OF}",
    "list.added": "MAX(added_at) of its live tracks (Plex)",
    "list.year": "MAX(year) of its live tracks (Plex's year, as jimbo-dj's list shows it)",
    "list.sort.plays": "plays, most first; ties: more tracks first (jimbo-dj's order)",
    "list.sort.added": "newest added first (jimbo-dj's order)",
    "list.sort.name": "name A to Z, ignoring case (traqfreq's order)",
    "list.sort.year": "newest year first, no year last (traqfreq's order)",
    "album.tracks": f"tracks WHERE album_key = ? AND {LIVE} ORDER BY disc, track_no, title",
    "album.year": "MusicBrainz's first release year, else Plex's release date, else Plex's year (insights._release_years)",
    "album.minutes": "SUM(duration_ms) / 60 000, rounded",
    "album.plays": f"SUM(plays_of) over its tracks; plays_of = {PLAYS_OF}",
    "album.history": "counted listens of these exact copies: those that say they were this copy (listens.rating_key), "
                     "and the rest by the song's default copy (listen_matches); pages._keys_where",
    "track.versions": "other live copies of the same song: the same artist (track artist first) and title without "
                      "its version, like (Live) or - Remastered (songs.Index)",
    "artist.tracks": f"tracks WHERE (artist_key = ? OR track_artist = its name, ignoring case) AND {LIVE} "
                     "(pages._library_of: its albums, and its songs on other people's)",
    "artist.albums": "the albums of those tracks, oldest first (year as album.year); appears on = someone else's album",
    "artist.plays": f"SUM(plays_of) over those tracks; plays_of = {PLAYS_OF}",
    "artist.top": "its 10 most played songs, each once: every copy's plays_of added up, shown as the original copy "
                  "(pages._top_songs)",
    "artist.history": "counted listens whose match key starts with its normalised name, plus those matched to its "
                      "tracks (pages._artist_where)",
    "track.plays": PLAYS_OF,
    "track.history": "counted listens of this copy: COALESCE(listens.rating_key, listen_matches.rating_key) = it "
                     "(jimbo-dj's _track_stats; on a song with more copies, pages.song's version history)",
    "song.history": "counted listens of every copy of the song (pages._keys_where over its versions)",
    "track.analysis": "jimbo-dj's analyzer: analysis.status and version (current = ok at version "
                      f"{jl.ANALYZER_VERSION}); key, BPM and moods from its features row",
    "history.sources": "counted listens per source, in jimbo-dj's source order",
    "history.years": "counted listens per year, in the listening time zone",
}


class NotFound(LookupError):
    """No such album, artist or track."""


def _q(**params) -> str:
    return urlencode({k: v for k, v in params.items() if v is not None})


def _ctx(conn: sqlite3.Connection, default_tz: str | None):
    """The tracks table must be there (library.NoLibrary otherwise); jimbo-dj's _track_stats for this data."""
    library._tables(conn)
    return jp.using(library.track_plays(conn, default_tz))


def _has_listens(conn: sqlite3.Connection) -> bool:
    return {"listens", "listen_matches"} <= legacy.table_names(conn)


def _iso(v) -> str | None:
    return legacy._iso(v) if v else None


# --- Lists ------------------------------------------------------------------------------------------------

def entity_list(conn: sqlite3.Connection, kind: str, sort: str = "plays", limit: int = 50, offset: int = 0,
                default_tz: str | None = None) -> dict:
    """jimbo-dj's Library → Albums or Artists (browse._grouped over every live track): each with its tracks,
    plays (SUM of plays_of), newest added and year; 50 a page."""
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}")
    if sort not in LIST_SORTS:
        raise ValueError(f"sort is one of {', '.join(LIST_SORTS)}")
    limit, offset = max(1, min(limit, 500)), max(0, offset)
    base = ("FROM tracks t LEFT JOIN features f ON f.rating_key = t.rating_key "
            "LEFT JOIN analysis a ON a.rating_key = t.rating_key WHERE t.removed_at IS NULL")
    with _ctx(conn, default_tz):
        jp._with_plays(conn)
        total, rows = jp._grouped(conn, base, [], kind, sort, limit, offset)
    items = []
    for r in rows:
        key = {"albums": "album_key", "artists": "artist_key"}[kind]
        items.append({"key": r["key"], "name": r["name"], "artist": r["artist"], "artist_key": r["artist_key"],
                      "tracks": r["tracks"], "plays": r["plays"], "added": _iso(r["added"]), "year": r["year"],
                      "rows": _q(**{key: r["key"]}, name=r["name"] if kind == "artists" else None)})
    return {"kind": kind, "sort": sort, "total": total, "limit": limit, "offset": offset, "items": items,
            "rules": {k.split(".", 1)[1]: v for k, v in RULES.items() if k.startswith("list.")}
            | {"total": RULES[f"list.{kind}"]}}


# --- History of some tracks -------------------------------------------------------------------------------

def _history(conn: sqlite3.Connection, rows: list, tz, top: bool) -> dict:
    """jimbo-dj's summarise (plays by source and year, first and last, top songs and albums) plus the newest
    30 listens (_recent), times as ISO and in the listening zone."""
    h = jp.summarise(rows, tz, songs=top)
    if h.get("plays"):
        h["first"], h["last"] = _iso(h["first"]), _iso(h["last"])
    h.pop("bands", None)  # time of day: HISTORY's (not shown on LIBRARY's pages)
    h.pop("hours", None)
    h["recent"] = [{**x, "at": _iso(x["at"])} for x in jp._recent(rows, tz)]
    h["timezone"] = getattr(tz, "key", str(tz))
    return h


def _keys_rows(conn: sqlite3.Connection, keys: list[int]) -> list:
    if not keys or not _has_listens(conn):
        return []
    where, args = jp._keys_where(conn, keys)
    return jp._listens(conn, where, args)


def _artist_rows(conn: sqlite3.Connection, name: str | None, keys: list[int]) -> list:
    if not _has_listens(conn):
        return []
    where, args = jp._artist_where(conn, name, keys)
    return jp._listens(conn, where, args)


def _track_out(t: dict) -> dict:
    t = dict(t)
    t.pop("genres", None)  # the analyzer's genres: TAGS (P4)
    return t


# --- Album ------------------------------------------------------------------------------------------------

def album(conn: sqlite3.Connection, key: int, default_tz: str | None = None) -> dict:
    """jimbo-dj's album page, its LIBRARY part: the album (year, Plex's release date and label, MusicBrainz as
    jimbo-dj cached it), its tracks in disc and track order with plays and other copies, and their listens."""
    tz = history.listen_tz(conn, default_tz)
    with _ctx(conn, default_tz):
        hist = jp.history.track_stats(conn)
        rows = conn.execute(jp.TRACK_COLS + "WHERE t.album_key=? AND t.removed_at IS NULL ORDER BY t.disc, t.track_no, t.title",
                            (key,)).fetchall()
        if not rows:
            raise NotFound(f"no album {key}")
        tracks = [jp._track(r, hist) for r in rows]
        idx = songs.index(conn)
        for t in tracks:
            t["versions"] = len(idx.versions_of(t["rating_key"])) or 1
        keys = [t["rating_key"] for t in tracks]
        info = {"album_key": key, "slug": songs.album_slug(rows[0]["artist"], rows[0]["album"]), "title": rows[0]["album"],
                "artist": rows[0]["artist"], "artist_key": rows[0]["artist_key"],
                "year": jp.insights._release_years(conn).get(key) or rows[0]["year"]}
        a = conn.execute("SELECT a.*, m.title mb_title, m.date mb_date, m.country mb_country, m.labels mb_labels, m.first_release, "
                         "m.primary_type, m.secondary_types FROM albums a "
                         "LEFT JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok' WHERE a.album_key=?", (key,)).fetchone()
        if a:
            info |= {"released": a["released"], "label": a["studio"], "mbid": a["mbid"], "plex_year": a["year"]}
            if a["mb_title"] is not None or a["first_release"]:
                info["musicbrainz"] = {"first_release": a["first_release"], "date": a["mb_date"], "country": a["mb_country"],
                                       "labels": json.loads(a["mb_labels"] or "[]"), "type": a["primary_type"],
                                       "secondary": json.loads(a["secondary_types"] or "[]")}
        h = _history(conn, _keys_rows(conn, keys), tz, top=False)
    return {"album": info, "tracks": [_track_out(t) for t in tracks],
            "plays": sum(t["plays"] for t in tracks), "minutes": round(sum(t["duration_ms"] or 0 for t in tracks) / 60000),
            "history": h, "rows": {"tracks": _q(album_key=key), "plays": _q(album=key)},
            "rules": {k.split(".", 1)[1]: v for k, v in RULES.items() if k.startswith(("album.", "history."))}
            | {"versions": RULES["track.versions"]}}


# --- Artist -----------------------------------------------------------------------------------------------

def artist(conn: sqlite3.Connection, key: int, default_tz: str | None = None) -> dict:
    """jimbo-dj's artist page, its LIBRARY part: its albums (oldest first), top songs and plays, and its listens."""
    tz = history.listen_tz(conn, default_tz)
    with _ctx(conn, default_tz):
        hist = jp.history.track_stats(conn)
        try:
            key, name, mbid = jp.resolve_artist(conn, key, None)
        except KeyError as e:
            raise NotFound(str(e)) from e
        tracks, albums = jp._library_of(conn, key, name, hist)
        if not tracks:
            raise NotFound(f"no live tracks for artist {key}")
        keys = [t["rating_key"] for t in tracks]
        top = [_track_out(t) for t in jp._top_songs(conn, tracks)]
        h = _history(conn, _artist_rows(conn, name, keys), tz, top=True)
    h.pop("albums", None)  # its albums are the library's, above
    h["top_songs"] = h.get("top_songs", [])[:10]
    for a in albums:
        a["rows"] = _q(album_key=a["album_key"])
    return {"artist": {"artist_key": key, "name": name, "slug": songs.slugify(name), "mbid": mbid},
            "tracks": len(tracks), "albums": albums, "top_tracks": top, "plays": sum(t["plays"] for t in tracks),
            "history": h, "rows": {"tracks": _q(artist_key=key, name=name), "plays": _q(artist=key)},
            "rules": {k.split(".", 1)[1]: v for k, v in RULES.items() if k.startswith(("artist.", "history."))}}


# --- Track ------------------------------------------------------------------------------------------------

TRACK_FACTS = ("rating_key, title, artist, track_artist, album, album_key, artist_key, disc, track_no, year, "
               "duration_ms, plex_path, local_path, parts, file_size, container, codec, bitrate, bit_depth, "
               "sample_rate, channels, view_count, skip_count, last_viewed_at, user_rating, sonic_version, "
               "added_at, updated_at, removed_at")
FEATURES = ("bpm, bpm_confidence, key, scale, key_strength, camelot, loudness_lufs, loudness_range, danceability, "
            "moods")


def _cols(conn: sqlite3.Connection, table: str, wanted: str) -> list[str]:
    have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    return [c.strip() for c in wanted.split(",") if c.strip() in have]


def track(conn: sqlite3.Connection, key: int, default_tz: str | None = None) -> dict:
    """One copy: its file facts, jimbo-dj's analysis of it, its plays (plays_of), its listens by source, and
    the song it is a copy of (every copy's listens, pages.song)."""
    tz = history.listen_tz(conn, default_tz)
    tables = legacy.table_names(conn)
    with _ctx(conn, default_tz):
        hist = jp.history.track_stats(conn)
        r = conn.execute(f"SELECT {', '.join(_cols(conn, 'tracks', TRACK_FACTS))} FROM tracks WHERE rating_key = ?",
                         (key,)).fetchone()
        if not r:
            raise NotFound(f"no track {key}")
        t = dict(r)
        h = hist.get(key)
        plays = {"plays": jl.plays_of(t, hist), "plex": t.get("view_count") or 0, "history": h["plays"] if h else 0,
                 "last_played": _iso(jl.last_of(t, hist))}
        for c in ("last_viewed_at", "added_at", "updated_at", "removed_at"):
            if c in t:
                t[c] = _iso(t[c])
        analysis = None
        if "analysis" in tables:
            a = conn.execute("SELECT status, version, error, analyzed_at, seconds FROM analysis WHERE rating_key = ?",
                             (key,)).fetchone()
            if a:
                analysis = {**dict(a), "analyzed_at": _iso(a["analyzed_at"]),
                            "current": a["status"] == "ok" and a["version"] >= jl.ANALYZER_VERSION}
        features = None
        if "features" in tables:
            f = conn.execute(f"SELECT {', '.join(_cols(conn, 'features', FEATURES))} FROM features WHERE rating_key = ?",
                             (key,)).fetchone()
            if f:
                features = dict(f)
                moods = json.loads(features.pop("moods", None) or "{}")
                features["moods"] = sorted(moods, key=moods.get, reverse=True)[:3]  # as pages._track
        idx = songs.index(conn)
        keys = idx.versions_of(key) or [key]
        song_rows = _keys_rows(conn, keys)
        mine = [x for x in song_rows if x["rk"] == key]
        copy_h = _history(conn, mine, tz, top=False)
        song_h = _history(conn, song_rows, tz, top=False) if len(keys) > 1 else None
        versions = []
        for k in keys:
            v = idx.tracks.get(k)
            if v and k != key:
                versions.append({"rating_key": k, "title": v["title"], "album": v["album"], "album_key": v["album_key"],
                                 "artist": v["artist"], "year": v["year"], "kind": v["kind"], "plays": jl.plays_of(v, hist)})
        me = idx.tracks.get(key)
    versions.sort(key=lambda v: (idx.tracks[v["rating_key"]]["rank"], -v["plays"], v["year"] or 9999, v["rating_key"]))
    return {"track": t, "kind": me["kind"] if me else None, "live": t.get("removed_at") is None,
            "plays": plays, "analysis": analysis, "features": features,
            "analyzer_version": jl.ANALYZER_VERSION, "history": copy_h,
            "song": {"title": songs.base_title(t["title"]), "artist": songs.base_artist(songs.song_artist(t)),
                     "copies": len(keys), "versions": versions, "history": song_h},
            "rows": {"plays": _q(track=key), "song": _q(track=key, song="true") if len(keys) > 1 else None},
            "rules": {"plays": RULES["track.plays"], "history": RULES["track.history"],
                      "song_history": RULES["song.history"], "versions": RULES["track.versions"],
                      "analysis": RULES["track.analysis"], "sources": RULES["history.sources"],
                      "years": RULES["history.years"]}}


# --- The listens behind a history number -------------------------------------------------------------------

def plays(conn: sqlite3.Connection, track: int | None = None, album: int | None = None, artist: int | None = None,
          song: bool = False, source: str | None = None, limit: int = 50, offset: int = 0,
          default_tz: str | None = None) -> dict:
    """The counted listens a page's history numbers count (the same rows its summarise saw), newest first: of
    one copy (``track``; with ``song``, every copy of its song), an album's copies or an artist."""
    if sum(x is not None for x in (track, album, artist)) != 1:
        raise ValueError("give one of track, album or artist")
    tz = history.listen_tz(conn, default_tz)
    with _ctx(conn, default_tz):
        hist = jp.history.track_stats(conn)
        if track is not None:
            if not conn.execute("SELECT 1 FROM tracks WHERE rating_key = ?", (track,)).fetchone():
                raise NotFound(f"no track {track}")
            keys = songs.index(conn).versions_of(track) or [track]
            rows = _keys_rows(conn, keys)
            if not song:
                rows = [x for x in rows if x["rk"] == track]
            what, rule = {"track": track, "song": song}, RULES["song.history" if song else "track.history"]
        elif album is not None:
            keys = [x[0] for x in conn.execute(f"SELECT rating_key FROM tracks WHERE album_key = ? AND {LIVE}", (album,))]
            if not keys:
                raise NotFound(f"no album {album}")
            rows, what, rule = _keys_rows(conn, keys), {"album": album}, RULES["album.history"]
        else:
            try:
                key, name, _ = jp.resolve_artist(conn, artist, None)
            except KeyError as e:
                raise NotFound(str(e)) from e
            tracks, _ = jp._library_of(conn, key, name, hist)
            rows = _artist_rows(conn, name, [t["rating_key"] for t in tracks])
            what, rule = {"artist": artist, "name": name}, RULES["artist.history"]
    sources = sorted({x["source"] for x in rows})
    if source:
        rows = [x for x in rows if x["source"] == source]
    rows = sorted(rows, key=lambda x: (-x["started_at"], x["source"]))
    limit, offset = max(1, min(limit, 500)), max(0, offset)
    out = [{"started_at": _iso(x["started_at"]), "source": x["source"], "name": SOURCES.get(x["source"], x["source"]),
            "artist": x["artist"], "title": x["title"], "album": x["album"],
            "rating_key": x["rk"], "album_key": x["album_key"]} for x in rows[offset:offset + limit]]
    return {**what, "source": source, "sources": sources, "total": len(rows), "limit": limit, "offset": offset,
            "rule": rule, "timezone": getattr(tz, "key", str(tz)), "rows": out}
