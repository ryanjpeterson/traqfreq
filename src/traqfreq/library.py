"""LIBRARY, read-only: jimbo-dj's library numbers (its ``library.stats``) and the rows behind each one.

``stats`` runs jimbo-dj's own ``library.stats`` (vendored unchanged, vendor/jimbodj_library.py) on the read-only
connection, so every number is jimbo-dj's, counted its way: live tracks are ``removed_at IS NULL``, codecs and
containers are the top 10 by tracks, bitrates fall in five half-open buckets, played is ``view_count > 0``,
rated is ``user_rating IS NOT NULL``, Plex sonic analysis is ``sonic_version IS NOT NULL``. The one part
traqfreq can't count is ``paths.folders`` (which of jimbo-dj's configured music folders its container can
read): that depends on jimbo-dj's config and disks, so it is shown as jimbo-dj last stored it, not compared.

traqfreq adds, each saying its rule (W3): jimbo-dj's own analyzer (``analysis.status = 'ok'`` at the current
analyzer version, as jimbo-dj's Analysis page counts it), Plex top artists with their ``artist_key``, and for
every number the query string of ``tracks`` that lists its rows. A track's plays anywhere outside HISTORY are
jimbo-dj's ``plays_of``: Plex's ``view_count`` or the history's plays, whichever is larger, never the sum.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from urllib.parse import urlencode

from . import history, legacy
from .vendor import jimbodj_library as jd
from .vendor.jimbodj_history import PRIORITY, in_zone

# Bump when the shape of what ``stats`` builds changes, so cached copies are rebuilt (store.py).
LIBRARY_VERSION = 2  # 2: all-source play history (plays_all)
LIVE = legacy.LIVE
ANALYZED = f"a.status = 'ok' AND a.version >= {jd.ANALYZER_VERSION}"  # jimbo-dj live.progress "analysed"
ANALYSIS_ERROR = f"a.status = 'error' AND a.version >= {jd.ANALYZER_VERSION}"  # its "errors"

# The rule behind each number (W3), as jimbo-dj's library.stats writes it (over tracks).
RULES = {
    "tracks": f"COUNT(*) WHERE {LIVE}",
    "albums": f"COUNT(DISTINCT album_key) WHERE {LIVE}",
    "artists": f"COUNT(DISTINCT artist_key) WHERE {LIVE}",
    "hours": f"SUM(duration_ms) / 3 600 000, rounded to 0.1, WHERE {LIVE}",
    "size_gb": f"SUM(file_size) / 1e9, rounded to 0.1, WHERE {LIVE}",
    "codecs": f"the 10 most common COALESCE(codec, '?') WHERE {LIVE}",
    "containers": f"the 10 most common COALESCE(container, '?') WHERE {LIVE}",
    "bitrate_kbps": f"bitrate >= low AND bitrate < high (kbps) WHERE {LIVE}; no bitrate is in no bucket",
    "played_tracks": f"view_count > 0 AND {LIVE} (Plex)",
    "total_plays": f"SUM(view_count) WHERE {LIVE} (Plex)",
    "rated_tracks": f"user_rating IS NOT NULL AND {LIVE}",
    "top_artists": f"SUM(view_count) GROUP BY artist_key WHERE {LIVE}, top 10 with plays (Plex)",
    "sonic_analysis": f"sonic_version IS NOT NULL AND {LIVE} (Plex sonic analysis)",
    "analyzer": f"analysis {ANALYZED} AND {LIVE} (jimbo-dj's analyzer, version {jd.ANALYZER_VERSION})",
    "analyzer_errors": f"analysis {ANALYSIS_ERROR} AND {LIVE}",
    "mapped": f"local_path IS NOT NULL AND {LIVE}",
    "multi_part_tracks": f"parts > 1 AND {LIVE}",
    "removed_since_first_sync": "removed_at IS NOT NULL (every track a sync no longer saw)",
    "pct": "100 × part / tracks, rounded to 0.1 (jimbo-dj's _pct)",
    "all.played_tracks": f"plays_of > 0 AND {LIVE}: played anywhere (Plex, Last.fm, Spotify, Apple Music)",
    "all.plays": f"SUM(plays_of) WHERE {LIVE}; per track the larger of Plex's view_count and the history's "
                 "counted listens, never the sum (Plexamp may scrobble to Last.fm too)",
    "all.by_source": f"counted listens per source matched to a track WHERE {LIVE} (jimbo-dj's _track_stats)",
    "all.top_artists": f"SUM(plays_of) GROUP BY artist_key WHERE {LIVE}, top 10 with plays (every source)",
    "plays": "max(Plex view_count, history plays), never the sum (jimbo-dj's plays_of)",
    "folders": "jimbo-dj's configured music folders and whether its container can read them: shown as "
               "jimbo-dj stored them (stats library.stats), not compared",
}

BUCKETS = {label: (lo, hi) for label, lo, hi in jd.BITRATE_BUCKETS}
ANALYSIS = ("ok", "error", "older", "none")  # the analysis filter: at the current version, older, never
SORTS = {
    "artist": "t.artist COLLATE NOCASE, t.album COLLATE NOCASE, t.disc, t.track_no, t.rating_key",
    "plex_plays": "COALESCE(t.view_count, 0) DESC, t.artist COLLATE NOCASE, t.title COLLATE NOCASE, t.rating_key",
    "added": "t.added_at DESC, t.rating_key DESC",
    "plays": "plays(t.rating_key, t.view_count) DESC, t.artist COLLATE NOCASE, t.title COLLATE NOCASE, t.rating_key",
}
# A track's counted listens, as jimbo-dj's _track_stats finds them (its own rating_key, else its match's).
HEARD_FROM = ("t.rating_key IN (SELECT COALESCE(l.rating_key, m.rating_key) FROM listens l LEFT JOIN listen_matches m "
              "ON m.match_key = l.match_key WHERE l.counted = 1 AND l.source = ?)")


class NoLibrary(LookupError):
    """jimbo-dj's database has no tracks table."""


def _tables(conn: sqlite3.Connection) -> set[str]:
    tables = legacy.table_names(conn)
    if "tracks" not in tables:
        raise NoLibrary("tracks")
    return tables


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def cache_key(conn: sqlite3.Connection) -> str:
    """What ``stats`` is built from: jimbo-dj's last Plex sync, its history version (statcache's stamp for
    library.stats), the analyzer version and the analyzer's results so far (count and newest), so a sync, an
    import or new analysis results give a new key."""
    tables = _tables(conn)
    meta = {k: _meta(conn, k) for k in ("last_sync", "history_version")} if "meta" in tables else {}
    a = conn.execute("SELECT COUNT(*), MAX(analyzed_at) FROM analysis").fetchone() if "analysis" in tables else (0, None)
    return "|".join([f"v{LIBRARY_VERSION}", meta.get("last_sync") or "-", meta.get("history_version") or "-",
                     f"a{jd.ANALYZER_VERSION}", str(a[0]), str(a[1] or "-")])


def _q(**params) -> str:
    """The query string for ``tracks`` that lists a number's rows."""
    return urlencode({k: ("true" if v is True else "false" if v is False else v) for k, v in params.items()})


def stats(conn: sqlite3.Connection, default_tz: str | None = None) -> dict:
    """jimbo-dj's ``library.stats`` for this data, number for number (folders as stored), plus jimbo-dj's
    analyzer, Plex top artists with keys, each number's rule and the query for its rows (uncached)."""
    tables = _tables(conn)
    with jd.using(conn):
        out = jd.stats(jd.Settings())
    total = out["tracks"]

    stored = legacy.stored_stat(conn, "library.stats", tables)
    theirs = stored[0] if stored else {}
    out["paths"]["folders"] = (theirs.get("paths") or {}).get("folders") or {}
    out["paths"]["folders_compared"] = False

    out["analyzer"] = {"version": jd.ANALYZER_VERSION, "tracks": 0, "pct": 0.0, "errors": 0}
    if "analysis" in tables:
        n, err = conn.execute(
            f"SELECT SUM({ANALYZED}), SUM({ANALYSIS_ERROR}) FROM analysis a JOIN tracks t USING (rating_key) "
            f"WHERE t.{LIVE}").fetchone()
        out["analyzer"].update(tracks=n or 0, pct=jd._pct(n or 0, total), errors=err or 0)

    top = conn.execute(  # library.stats' own query, keeping the key it groups by
        f"SELECT artist, artist_key, SUM(view_count) plays FROM tracks WHERE {LIVE} GROUP BY artist_key "
        "HAVING plays>0 ORDER BY plays DESC LIMIT 10").fetchall()
    out["top_artist_keys"] = [{"artist": r["artist"], "artist_key": r["artist_key"], "plays": r["plays"]} for r in top]

    out["plays_all"] = plays_all(conn, total, default_tz)

    out["rules"] = RULES
    out["rows"] = {
        "tracks": _q(), "albums": _q(), "artists": _q(), "hours": _q(), "size_gb": _q(),
        "codecs": {v: _q(codec=v) for v in out["codecs"]},
        "containers": {v: _q(container=v) for v in out["containers"]},
        "bitrate_kbps": {v: _q(bitrate=v) for v in out["bitrate_kbps"]},
        "played_tracks": _q(played=True), "total_plays": _q(played=True, sort="plex_plays"),
        "rated_tracks": _q(rated=True),
        "top_artists": {str(r["artist_key"]): _q(artist_key=r["artist_key"], played=True, sort="plex_plays")
                        for r in top},
        "sonic_analysis": _q(sonic=True), "analyzer": _q(analysis="ok"), "analyzer_errors": _q(analysis="error"),
        "mapped": _q(mapped=True), "unmapped": _q(mapped=False), "multi_part_tracks": _q(multi_part=True),
        "removed_since_first_sync": _q(removed=True),
        "all.played_tracks": _q(heard=True, sort="plays"), "all.plays": _q(heard=True, sort="plays"),
        "all.by_source": {s: _q(source=s, sort="plays") for s in out["plays_all"]["by_source"]},
        "all.top_artists": {str(a["artist_key"]): _q(artist_key=a["artist_key"], heard=True, sort="plays")
                            for a in out["plays_all"]["top_artists"]},
    }
    out["jimbodj"] = None
    if stored:
        row = conn.execute("SELECT stamp, version FROM stats WHERE name = 'library.stats' AND params = ''").fetchone()
        now = json.dumps([_meta(conn, "last_sync"), _meta(conn, "history_version")]) if "meta" in tables else None
        out["jimbodj"] = {"source": "stats.library.stats", "built_at": legacy._iso(stored[1]),
                          "stamp": row["stamp"], "fresh": row["stamp"] is not None and row["stamp"] == now}
    return out


def plays_all(conn: sqlite3.Connection, total: int, default_tz: str | None = None) -> dict:
    """The library's play history from every source, not Plex's alone: played tracks and plays by jimbo-dj's
    plays_of (Plex's count or the history's, the larger, per track), the history's counted listens per source
    on live tracks, and top artists by plays_of. traqfreq's numbers (jimbo-dj's library.stats counts Plex only)."""
    hist = track_plays(conn, default_tz)
    played = plays = history_plays = 0
    by_source: dict[str, int] = {}
    tracks_by_source: dict[str, int] = {}
    artists: dict[int, list] = {}
    for rk, vc, artist, ak in conn.execute(f"SELECT rating_key, view_count, artist, artist_key FROM tracks WHERE {LIVE}"):
        n = jd.plays_of({"rating_key": rk, "view_count": vc}, hist)
        h = hist.get(rk)
        if h:
            history_plays += h["plays"]
            for s, k in h["sources"].items():
                by_source[s] = by_source.get(s, 0) + k
                tracks_by_source[s] = tracks_by_source.get(s, 0) + 1
        if n:
            played += 1
            plays += n
            a = artists.setdefault(ak, [artist, 0])
            a[1] += n
    top = sorted(((v[1], k, v[0]) for k, v in artists.items()), key=lambda x: (-x[0], x[2] or "", x[1]))[:10]
    order = {s: i for i, s in enumerate(PRIORITY)}
    return {"played_tracks": played, "played_pct": jd._pct(played, total), "plays": plays,
            "history_plays": history_plays,
            "by_source": {s: by_source[s] for s in sorted(by_source, key=lambda s: order.get(s, 99))},
            "tracks_by_source": tracks_by_source,
            "top_artists": [{"artist": name, "artist_key": k, "plays": n} for n, k, name in top]}


# --- Rows ---------------------------------------------------------------------------------------------------

_hist: dict[str, dict] = {}
_hist_lock = threading.Lock()


def track_plays(conn: sqlite3.Connection, default_tz: str | None = None) -> dict[int, dict]:
    """jimbo-dj's ``_track_stats`` (every source's counted plays per library track), built once per data
    version (history.cache_key) and kept in memory. Empty without listens."""
    tables = legacy.table_names(conn)
    if not {"listens", "listen_matches"} <= tables:
        return {}
    key = history.cache_key(conn, default_tz)
    with _hist_lock:
        h = _hist.get(key)
        if h is None:
            _hist.clear()
            with in_zone(history.listen_tz(conn, default_tz)):
                h = _hist[key] = jd._track_stats(conn)
        return h


def _bool(v: bool, yes: str, no: str) -> str:
    return yes if v else no


def tracks(conn: sqlite3.Connection, codec: str | None = None, container: str | None = None,
           bitrate: str | None = None, played: bool | None = None, rated: bool | None = None,
           sonic: bool | None = None, analysis: str | None = None, mapped: bool | None = None,
           multi_part: bool | None = None, removed: bool = False, artist_key: int | None = None,
           album_key: int | None = None, sort: str = "artist", limit: int = 50, offset: int = 0,
           default_tz: str | None = None, facet: str | None = None, value: str | None = None,
           heard: bool | None = None, source: str | None = None) -> dict:
    """The rows behind a LIBRARY number: live tracks (or, with ``removed``, the tracks a sync no longer saw)
    with one codec or container (``?`` = none), in one bitrate bucket, played or not, rated or not, Plex
    sonic-analysed or not, analysed by jimbo-dj's analyzer (``analysis`` ok, error, older, none), mapped or
    not, multi-part or not, of one artist or album, or (T12) behind one bar of jimbo-dj's Library charts
    (``facet`` and ``value``, its facets.members); each with its plays (jimbo-dj's ``plays_of``)."""
    tables = _tables(conn)
    where, args = [("removed_at IS NOT NULL" if removed else LIVE).replace("removed_at", "t.removed_at")], []
    for col, v in (("codec", codec), ("container", container)):
        if v is not None:
            if v == "?":
                where.append(f"t.{col} IS NULL")
            else:
                where.append(f"t.{col} = ?")
                args.append(v)
    if bitrate is not None:
        if bitrate not in BUCKETS:
            raise ValueError(f"bitrate is one of {', '.join(BUCKETS)}")
        where.append("t.bitrate >= ? AND t.bitrate < ?")
        args += BUCKETS[bitrate]
    if played is not None:
        where.append(_bool(played, "t.view_count > 0", "(t.view_count IS NULL OR t.view_count <= 0)"))
    if rated is not None:
        where.append(f"t.user_rating IS {_bool(rated, 'NOT ', '')}NULL")
    if sonic is not None:
        where.append(f"t.sonic_version IS {_bool(sonic, 'NOT ', '')}NULL")
    if mapped is not None:
        where.append(f"t.local_path IS {_bool(mapped, 'NOT ', '')}NULL")
    if multi_part is not None:
        where.append(_bool(multi_part, "t.parts > 1", "(t.parts IS NULL OR t.parts <= 1)"))
    for col, v in (("artist_key", artist_key), ("album_key", album_key)):
        if v is not None:
            where.append(f"t.{col} = ?")
            args.append(v)
    chart_rule = keys_arg = None
    if facet is not None or value is not None:
        from . import library_gate  # the P2 gate's charts (T12)
        if facet is None or value is None:
            raise ValueError("facet and value go together")
        zone = library_gate.zone(conn, default_tz)
        where.append("t.rating_key IN (SELECT value FROM json_each(?))")
        keys_arg = json.dumps(library_gate.facet_keys(conn, facet, value, zone))
        args.append(keys_arg)
        chart_rule = f"{facet} is {value} (jimbo-dj's chart rule, facets.members; time zone {zone})"
    hist = track_plays(conn, default_tz)
    # plays(rating_key, view_count) = jimbo-dj's plays_of, for heard and the plays order (every source)
    conn.create_function("plays", 2, lambda rk, vc: jd.plays_of({"rating_key": rk, "view_count": vc}, hist),
                         deterministic=True)
    if heard is not None:
        where.append(f"plays(t.rating_key, t.view_count) {'>' if heard else '<='} 0")
    if source:
        if not {"listens", "listen_matches"} <= tables:
            raise ValueError("source needs jimbo-dj's listens")
        where.append(HEARD_FROM)
        args.append(source)
    has_analysis = "analysis" in tables
    has_features = "features" in tables
    if analysis is not None:
        if analysis not in ANALYSIS:
            raise ValueError(f"analysis is one of {', '.join(ANALYSIS)}")
        if not has_analysis:
            raise ValueError("analysis needs jimbo-dj's analysis table")
        where.append({"ok": ANALYZED, "error": ANALYSIS_ERROR, "older": f"a.version < {jd.ANALYZER_VERSION}",
                      "none": "a.rating_key IS NULL"}[analysis])
    if sort not in SORTS:
        raise ValueError(f"sort is one of {', '.join(SORTS)}")

    frm = "FROM tracks t" + (" LEFT JOIN analysis a ON a.rating_key = t.rating_key" if has_analysis else "")
    good = ANALYZED if has_analysis else "0"
    feats = ""
    if has_features:
        frm += " LEFT JOIN features f ON f.rating_key = t.rating_key"
        feats = f", CASE WHEN {good} THEN f.camelot END camelot, CASE WHEN {good} THEN f.bpm END bpm"
    else:
        feats = ", NULL camelot, NULL bpm"
    an = ", a.status analysis_status, a.version analysis_version" if has_analysis else \
        ", NULL analysis_status, NULL analysis_version"
    w = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) {frm} WHERE {w}", args).fetchone()[0]
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    rows = conn.execute(
        "SELECT t.rating_key, t.title, t.artist, t.track_artist, t.album, t.album_key, t.artist_key, t.disc, "
        "t.track_no, t.year, t.duration_ms, t.plex_path, t.local_path, t.parts, t.file_size, t.container, t.codec, "
        "t.bitrate, t.view_count, t.last_viewed_at, t.user_rating, t.sonic_version, t.added_at, t.removed_at"
        f"{an}{feats} {frm} WHERE {w} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    out_rows = []
    for r in rows:
        m = dict(r)
        h = hist.get(m["rating_key"])
        last = jd.last_of(m, hist)
        out_rows.append({**m, "plays": jd.plays_of(m, hist), "history_plays": h["plays"] if h else 0,
                         "last_played": legacy._iso(last) if last else None,
                         "last_viewed_at": legacy._iso(m["last_viewed_at"]) if m["last_viewed_at"] else None,
                         "added_at": legacy._iso(m["added_at"]) if m["added_at"] else None,
                         "removed_at": legacy._iso(m["removed_at"]) if m["removed_at"] else None})
    rule = w.replace("t.", "").replace("a.", "analysis.")
    if chart_rule:
        rule = rule.replace("rating_key IN (SELECT value FROM json_each(?))", chart_rule)
    shown = [a for a in args if a is not keys_arg]
    return {
        "filters": {"codec": codec, "container": container, "bitrate": bitrate, "played": played, "rated": rated,
                    "sonic": sonic, "analysis": analysis, "mapped": mapped, "multi_part": multi_part,
                    "removed": removed, "artist_key": artist_key, "album_key": album_key, "facet": facet,
                    "value": value, "heard": heard, "source": source},
        "sort": sort, "total": total, "limit": limit, "offset": offset,
        "rule": f"tracks WHERE {rule}", "params": shown, "plays_rule": RULES["plays"], "rows": out_rows,
    }
