"""jimbo-dj's artist, album and track pages, the parts LIBRARY counts with, copied unchanged.

From pages.py: the track columns and ``_track`` (a track with its plays, jimbo-dj's plays_of), the listens of
an artist, of some copies, ``summarise`` (plays by source and year, first and last, time of day, top songs and
albums), ``resolve_artist``, ``_library_of`` (an artist's tracks and albums, oldest first, with plays),
``_top_songs`` (the most played songs, every copy's plays added up), ``resolve_album`` and ``_recent``. From
insights.py ``_release_years`` (an album's year: MusicBrainz's first release, else Plex's release date or
year). From browse.py ``GROUP_SORTS`` and ``_grouped`` (Library → Albums and Artists: tracks, plays, added,
year per album or artist).

Not copied (not in P2): MusicBrainz pages and lookups, the sound profile and "sounds like" (vectors), styles
and genres (TAGS, P4), story moments and journey phases. Stand-ins at the bottom give the copies the names
they call in jimbo-dj (``history``, ``insights``, ``songs``, browse's ``_with_plays``), so the copies stay as
they are. Never edit the copies; re-copy them from jimbo-dj when it changes.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import sqlite3
import types
from collections import Counter, defaultdict

from . import jimbodj_library as _lib
from . import jimbodj_songs as songs
from .jimbodj_history import PRIORITY, SOURCES, band_of, norm_artist, norm_title

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/pages.py, insights.py, browse.py"

# --- src/jimbodj/pages.py --------------------------------------------------------------------------------
TRACK_COLS = ("SELECT t.rating_key, t.title, t.artist, t.artist_key, t.album, t.album_key, t.year, t.duration_ms, t.disc, t.track_no, "
              "t.view_count, t.track_artist, f.bpm, f.camelot, f.key, f.scale, f.moods, f.genres FROM tracks t "
              "LEFT JOIN features f USING (rating_key) ")


def _track(r, hist: dict) -> dict:
    d = dict(r)
    moods = json.loads(d.pop("moods") or "{}")
    gen = json.loads(d.pop("genres") or "{}")
    d["moods"] = sorted(moods, key=moods.get, reverse=True)[:3]
    d["genres"] = [g for g in sorted(gen, key=gen.get, reverse=True) if gen[g] >= 0.15][:2]
    d["plays"] = history.plays_of(d, hist)
    return d


def _listens(con, where: str, args: list) -> list:
    return con.execute(
        "SELECT l.source, l.started_at, l.artist, l.title, l.album, l.match_key, COALESCE(l.rating_key, m.rating_key) rk, "
        "t.album_key, t.title lib_title FROM listens l LEFT JOIN listen_matches m ON m.match_key = l.match_key "
        f"LEFT JOIN tracks t ON t.rating_key = COALESCE(l.rating_key, m.rating_key) WHERE l.counted=1 AND ({where})", args).fetchall()


def _artist_where(con, name: str | None, keys: list[int]) -> tuple[str, list]:
    """Listens of an artist: by normalised name prefix, plus those matched to its library tracks."""
    parts, args = [], []
    for n in {norm_artist(name)} - {""}:
        parts.append("(l.match_key >= ? AND l.match_key < ?)")
        args += [n + "|", n + "}"]
    if keys:
        mks = [r[0] for r in con.execute(
            "SELECT match_key FROM listen_matches WHERE rating_key IN (SELECT value FROM json_each(?))", (json.dumps(keys),))]
        if mks:
            parts.append("l.match_key IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(mks))
    return (" OR ".join(parts) or "0"), args


def _keys_where(con, keys: list[int]) -> tuple[str, list]:
    """Plays of these exact copies: ones that say which copy they were (listens.rating_key), and the rest by
    the song's default copy — so a studio track's page doesn't count its live take's plays."""
    mks = [r[0] for r in con.execute(
        "SELECT match_key FROM listen_matches WHERE rating_key IN (SELECT value FROM json_each(?))", (json.dumps(keys),))]
    return ("l.rating_key IN (SELECT value FROM json_each(?)) OR (l.rating_key IS NULL AND l.match_key IN (SELECT value FROM json_each(?)))",
            [json.dumps(keys), json.dumps(mks)])


def summarise(rows: list, tz, songs: bool = True) -> dict:
    """Plays per source and year, first and last, time of day and hour (in `tz`), top songs and albums."""
    if not rows:
        return {"plays": 0}
    by_source, bands, hours = Counter(), Counter(), Counter()
    years: dict[int, Counter] = defaultdict(Counter)
    song, song_meta, album, album_meta = Counter(), {}, Counter(), {}
    for r in rows:
        when = dt.datetime.fromtimestamp(r["started_at"], tz)
        by_source[r["source"]] += 1
        years[when.year][r["source"]] += 1
        bands[band_of(when.hour)] += 1
        hours[when.hour] += 1
        k = norm_title(r["title"]) or (r["title"] or "").lower()
        song[k] += 1
        meta = song_meta.setdefault(k, {"title": r["lib_title"] or r["title"], "artist": r["artist"], "rating_key": r["rk"], "album_key": r["album_key"]})
        if r["rk"] and not meta["rating_key"]:
            meta.update(rating_key=r["rk"], album_key=r["album_key"], title=r["lib_title"] or meta["title"])
        if r["album"]:
            ak = norm_title(r["album"]) or r["album"].lower()
            album[ak] += 1
            am = album_meta.setdefault(ak, {"album": r["album"], "album_key": None})
            if r["album_key"] and not am["album_key"]:
                am["album_key"] = r["album_key"]
    order = {s: i for i, s in enumerate(history.PRIORITY)}
    out = {
        "plays": len(rows),
        "first": min(r["started_at"] for r in rows), "last": max(r["started_at"] for r in rows),
        "sources": [{"source": s, "name": SOURCES.get(s, s), "plays": n} for s, n in sorted(by_source.items(), key=lambda kv: order.get(kv[0], 99))],
        "years": [{"year": y, "plays": sum(c.values()), "by_source": dict(c)} for y, c in sorted(years.items())],
        "bands": dict(bands),
        "hours": [{"label": f"{h:02d}", "value": hours.get(h, 0)} for h in range(24)],
    }
    if songs:
        out["songs"] = len(song)
        out["top_songs"] = [{**song_meta[k], "plays": n} for k, n in song.most_common(25)]
        out["albums"] = [{**album_meta[k], "plays": n} for k, n in album.most_common(20)]
    return out


def resolve_artist(con, key: int | None, name: str | None, slug: str | None = None) -> tuple[int | None, str | None, str | None]:
    """(artist_key, name, mbid). A name or slug that is a library artist gets its key; a slug that isn't
    is looked for in the history (the most common spelling there)."""
    if slug and not key:
        key = songs.index(con).artist(slug)
        if not key:
            n = songs.squash(slug)
            r = con.execute("SELECT artist FROM listens WHERE match_key >= ? AND match_key < ? AND counted=1 LIMIT 2000", (n + "|", n + "}")).fetchall()
            if not r:  # an artist only recommended (related.py): MusicBrainz's name and ID
                from . import related
                hit = related.name_for_slug(con, slug)
                if not hit:
                    raise KeyError(f"no artist {slug}")
                return None, hit[0], hit[1]
            name = Counter(x[0] for x in r).most_common(1)[0][0]
    if key:
        r = con.execute("SELECT title, mbid FROM artists WHERE artist_key=?", (key,)).fetchone()
        if r:
            return key, r["title"], r["mbid"]
        r = con.execute("SELECT artist FROM tracks WHERE artist_key=? LIMIT 1", (key,)).fetchone()
        if not r:
            raise KeyError(f"no artist {key}")
        return key, r["artist"], None
    if not name or not norm_artist(name):
        raise KeyError("an artist key or name is needed")
    n = norm_artist(name)
    for r in con.execute("SELECT artist_key, title, mbid FROM artists"):
        if norm_artist(r["title"]) == n and con.execute(
                "SELECT 1 FROM tracks WHERE artist_key=? AND removed_at IS NULL LIMIT 1", (r["artist_key"],)).fetchone():
            return r["artist_key"], r["title"], r["mbid"]
    return None, name, None


def _library_of(con, key: int, name: str, hist: dict) -> tuple[list[dict], list[dict]]:
    """An artist's library tracks (their albums, and their songs on other people's — a compilation, a
    soundtrack — by track artist) and those albums, oldest first, with plays."""
    rows = con.execute(TRACK_COLS + "WHERE t.removed_at IS NULL AND (t.artist_key=? OR (t.artist_key != ? AND t.track_artist = ? COLLATE NOCASE))",
                       (key, key, name)).fetchall()
    tracks = [_track(r, hist) for r in rows]
    years = insights._release_years(con)
    albums: dict[int, dict] = {}
    for t in tracks:
        a = albums.setdefault(t["album_key"], {"album_key": t["album_key"], "title": t["album"], "artist": t["artist"],
                                               "year": years.get(t["album_key"]) or t["year"], "tracks": 0, "plays": 0,
                                               "appears_on": t["artist_key"] != key})
        a["tracks"] += 1
        a["plays"] += t["plays"]
    return tracks, sorted(albums.values(), key=lambda a: (a["year"] or 9999, a["title"] or ""))


def _top_songs(con, tracks: list[dict], n: int = 10) -> list[dict]:
    """The most played songs, each once: the plays of every copy added up, shown as the original copy,
    with how many copies there are ("versions") and on how many albums."""
    idx = songs.index(con)
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in tracks:
        groups[songs.Index.song_key(t)].append(t)
    out = []
    for g in groups.values():
        plays = {t["rating_key"]: t["plays"] for t in g}
        lead = min(g, key=lambda t: (idx.tracks[t["rating_key"]]["rank"] if t["rating_key"] in idx.tracks else 0, -t["plays"]))
        out.append({**lead, "plays": sum(plays.values()), "versions": len(g), "albums": len({t["album_key"] for t in g})})
    return sorted(out, key=lambda t: -t["plays"])[:n]


def resolve_album(con, ref: str) -> int:
    """An album by its slug ("afi-sing-the-sorrow"), or by its old numeric key."""
    key = int(ref) if ref.isdigit() else songs.index(con).album(ref)
    if not key:
        raise KeyError(f"no album {ref}")
    return key


def _recent(rows: list, tz, n: int = 30) -> list[dict]:
    return [{"at": r["started_at"], "source": r["source"], "name": SOURCES.get(r["source"], r["source"]), "rating_key": r["rk"],
             "local": dt.datetime.fromtimestamp(r["started_at"], tz).strftime("%Y-%m-%d %H:%M")}
            for r in sorted(rows, key=lambda r: -r["started_at"])[:n]]


# --- src/jimbodj/insights.py -----------------------------------------------------------------------------
def _release_years(con) -> dict[int, int]:
    """Album → the year it first came out: MusicBrainz's first release, else Plex's release date or year."""
    out = {}
    for r in con.execute("SELECT a.album_key, a.year, a.released, m.first_release FROM albums a "
                         "LEFT JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok'"):
        for v in (r["first_release"], r["released"]):
            if v and len(v) >= 4 and v[:4].isdigit() and int(v[:4]) > 1000:
                out[r["album_key"]] = int(v[:4])
                break
        else:
            if r["year"]:
                out[r["album_key"]] = r["year"]
    return out


# --- src/jimbodj/browse.py -------------------------------------------------------------------------------
GROUP_SORTS = {"plays": "plays DESC, tracks DESC", "bpm": "bpm IS NULL, bpm ASC", "added": "added DESC", "random": "RANDOM()"}


def _grouped(con: sqlite3.Connection, base: str, args: list, group: str, sort: str, limit: int, offset: int) -> tuple[int, list[dict]]:
    """The same tracks as albums or artists: how many of each match, their plays, a cover."""
    col = "t.album_key" if group == "albums" else "t.artist_key"
    total = con.execute(f"SELECT COUNT(DISTINCT {col}) {base}", args).fetchone()[0]
    name = "t.album" if group == "albums" else "t.artist"
    rows = con.execute(
        f"SELECT {col} key, MAX({name}) name, MAX(t.artist) artist, MAX(t.artist_key) artist_key, COUNT(*) tracks, "
        "COALESCE(SUM(plays(t.rating_key, t.view_count)), 0) plays, MAX(t.added_at) added, AVG(f.bpm) bpm, MAX(t.year) year, "
        "(SELECT t2.album_key FROM tracks t2 WHERE " + ("t2.album_key = t.album_key" if group == "albums" else "t2.artist_key = t.artist_key AND t2.removed_at IS NULL") +
        " ORDER BY t2.view_count DESC LIMIT 1) album_key "
        f"{base} GROUP BY {col} ORDER BY {GROUP_SORTS.get(sort, GROUP_SORTS['plays'])} LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    return total, [dict(r) for r in rows]


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
# The copies call jimbo-dj's history module (plays_of, PRIORITY, track_stats), insights._release_years and
# songs.index by those names. history.track_stats(con) is jimbo-dj's _track_stats; traqfreq builds it once per
# data version (library.track_plays) and hands it in with ``using``, so it isn't built again per page.
_HIST: contextvars.ContextVar = contextvars.ContextVar("track_stats")

history = types.SimpleNamespace(plays_of=_lib.plays_of, PRIORITY=PRIORITY, track_stats=lambda con: _HIST.get())
insights = types.SimpleNamespace(_release_years=_release_years)


def _with_plays(con: sqlite3.Connection) -> sqlite3.Connection:
    """browse._with_plays (its body imports jimbo-dj's history package, so it is written out here): gives the
    SQL a plays(rating_key, view_count) that is jimbo-dj's plays_of, Plex's count or the history's, the larger."""
    hist = history.track_stats(con)
    con.create_function("plays", 2, lambda rk, vc: history.plays_of({"rating_key": rk, "view_count": vc}, hist),
                        deterministic=True)
    return con


# traqfreq's two list orders, added next to jimbo-dj's (plays, bpm, added, random), which stay as they are:
# by name, and newest year first (MAX(t.year), the year _grouped shows).
GROUP_SORTS = {**GROUP_SORTS, "name": "name COLLATE NOCASE, key", "year": "year IS NULL, year DESC, name COLLATE NOCASE, key"}


@contextlib.contextmanager
def using(hist: dict):
    """Run the copies with ``hist``: jimbo-dj's _track_stats for this connection's data (library.track_plays)."""
    token = _HIST.set(hist)
    try:
        yield
    finally:
        _HIST.reset(token)
