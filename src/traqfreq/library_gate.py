"""The P2 gate: every LIBRARY number jimbo-dj stored, next to traqfreq's. Read-only.

jimbo-dj keeps its LIBRARY numbers in its ``stats`` table: ``library.stats`` (the counts: Server → Plex & files)
and ``library.charts`` (Library's charts: keys, files, time, place, genres and the sound). ``compare`` puts every
stored field next to the one traqfreq works out with jimbo-dj's own code (vendored unchanged) and says whether
they match, as P1's gate does for HISTORY (``periods.compare``). Not compared: ``paths.folders`` (jimbo-dj's
configured music folders and its disks: shown as stored), and genres and styles (TAGS, P4).

A stored row is fresh when its stamp is the one jimbo-dj would give it now (statcache.py):

- ``library.stats``: ``[last_sync, history_version]``.
- ``library.charts``: ``[cache.data_stamp, MusicBrainz counts, genres.version(), history_version]``. The third is
  an in-memory counter in jimbo-dj's process (bumped when its styles are rebuilt); traqfreq can't see it, so
  freshness checks the other three parts.

The gate passes when every stored row matches, or each row that differs is stale (older than jimbo-dj's data).
"""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import legacy, library
from .periods import _field, _norm
from .vendor import jimbodj_facets as jf
from .vendor import jimbodj_insights as ji

# Bump when the shape of what ``compare`` or ``charts`` builds changes (store.py rebuilds cached copies).
GATE_VERSION = 1
STATS_VERSION = 1  # jimbo-dj's statcache: library.stats and library.charts are registered at version 1
CHARTS_VERSION = 1
CHART_TABLES = ("tracks", "analysis", "features", "albums", "artists", "mb_artists", "mb_releases")
SECTIONS = ("keys", "files", "time", "place", "sound")  # library.charts' parts P2 compares, in this order
SKIP = {"built_at", "seconds"}  # not numbers about the library: when and how long jimbo-dj's build took

NOT_IN_P2 = {
    "paths.folders": "jimbo-dj's configured music folders and whether its container can read them: its config "
                     "and disks, shown as stored",
    "genres": "genre families and styles are TAGS (P4)",
    "sound.genres": "the analyzer's Discogs genres, kept by jimbo-dj's styles: TAGS (P4)",
}

# The rule behind each part of library.charts (W3), as jimbo-dj's insights.py and live.py count it.
CHART_RULES = {
    "keys": "key and scale of live tracks analysed at the current analyzer version (insights.keys)",
    "files": "live tracks by LOWER(COALESCE(codec, container, '?')); lossless is FLAC, ALAC, WAV, AIFF and the like; "
             "hi-res is more than 16-bit or more than 48 kHz; lossy bitrates in five half-open buckets "
             "(insights.file_buckets)",
    "time": "length in minutes; decade of the album's first release (MusicBrainz, else Plex's date or year); year "
            "added; hour and weekday last played in jimbo-dj's time zone (insights.time_buckets)",
    "place": "an artist's country (Plex, else MusicBrainz), hometown, type and decade formed, and an album's label "
             "(MusicBrainz, else Plex's studio); countries, cities and labels count live tracks, types and "
             "decades formed count artists (insights.place)",
    "sound": "BPM, Camelot key, loudness and moods of live tracks analysed at the current analyzer version "
             "(live.distributions)",
}

# A chart's bars → jimbo-dj's filter for the tracks behind one bar (facets.members), so every bar opens its rows.
FACETS = {
    "files.formats": "format", "files.tiers": "quality", "files.bit_depth": "bits", "files.sample_rate": "rate",
    "files.lossy_bitrate": "bitrate", "files.channels": "channels",
    "time.lengths": "length", "time.decades": "decade", "time.decade_plays": "decade", "time.added": "added",
    "time.hours": "hour", "time.weekdays": "weekday",
    "place.countries": "country", "place.cities": "city", "place.formed": "formed",
    "place.artist_types": "artist_type", "place.labels": "label",
}
# A library.stats field → the key of library.stats' ``rows`` map that lists its tracks.
STATS_ROWS = {
    "tracks": "tracks", "albums": "albums", "artists": "artists", "hours": "hours", "size_gb": "size_gb",
    "codecs": "codecs", "containers": "containers", "bitrate_kbps": "bitrate_kbps",
    "play_history.played_tracks": "played_tracks", "play_history.played_pct": "played_tracks",
    "play_history.total_plays": "total_plays", "play_history.rated_tracks": "rated_tracks",
    "play_history.rated_pct": "rated_tracks", "play_history.top_artists": "top_artists_by_name",
    "sonic_analysis.tracks": "sonic_analysis", "sonic_analysis.pct": "sonic_analysis",
    "paths.mapped": "mapped", "paths.mapped_pct": "mapped", "paths.unmapped_examples": "unmapped",
    "paths.multi_part_tracks": "multi_part_tracks", "paths.removed_since_first_sync": "removed_since_first_sync",
}
ROW_FACETS = jf.FILE + jf.TIME + jf.PLACE + ("label",)  # the facets library.tracks accepts


def _meta(conn: sqlite3.Connection, tables: set[str]) -> dict:
    if "meta" not in tables:
        return {}
    return {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM meta WHERE key IN ('last_sync', 'history_version')")}


def _row(conn: sqlite3.Connection, name: str, tables: set[str]):
    if "stats" not in tables:
        return None
    return conn.execute("SELECT value, version, stamp, built_at FROM stats WHERE name = ? AND params = ''",
                        (name,)).fetchone()


def zone(conn: sqlite3.Connection, default_tz: str | None = None) -> ZoneInfo:
    """jimbo-dj's time zone for the Time charts (schedule.tz(): its TZ, else America/Denver): the one its stored
    library.charts says it used, else traqfreq's TZ, else America/Denver."""
    tables = legacy.table_names(conn)
    row = _row(conn, "library.charts", tables)
    name = None
    if row:
        try:
            name = (json.loads(row["value"]).get("time") or {}).get("timezone")
        except (TypeError, ValueError, AttributeError):
            name = None
    for z in (name, default_tz, ji.DEFAULT_TZ):
        if z:
            try:
                return ZoneInfo(z)
            except Exception:  # noqa: BLE001 - an unknown name: try the next
                continue
    return ZoneInfo("UTC")


def charts(conn: sqlite3.Connection, tz: ZoneInfo) -> dict:
    """jimbo-dj's library.charts for this data (statcache._library_charts: ``{**insights._all_views(con),
    "sound": live.distributions(con)}``), with the vendored copies; genres are TAGS and left out."""
    tables = legacy.table_names(conn)
    missing = [t for t in CHART_TABLES if t not in tables]
    if "tracks" in missing:
        raise library.NoLibrary("tracks")
    if missing:
        raise ValueError(f"jimbo-dj's database has no {', '.join(missing)} table")
    with ji.in_tz(tz):
        return {**ji._all_views(conn), "sound": ji.distributions(conn)}


def charts_stamp(conn: sqlite3.Connection, tables: set[str] | None = None) -> list:
    """The parts of statcache._library_stamp traqfreq can work out: [cache.data_stamp, MusicBrainz, None,
    history_version] (None: genres.version(), jimbo-dj's in-memory counter)."""
    tables = legacy.table_names(conn) if tables is None else tables
    meta = _meta(conn, tables)
    n, last = conn.execute("SELECT COUNT(*), MAX(analyzed_at) FROM analysis").fetchone() if "analysis" in tables \
        else (0, None)
    mb = [list(conn.execute(f"SELECT COUNT(*), MAX(fetched_at) FROM {t}").fetchone()) if t in tables else [0, None]
          for t in ("mb_artists", "mb_releases")]
    return _norm([[n, last, meta.get("last_sync")], mb, None, meta.get("history_version")])


def cache_key(conn: sqlite3.Connection, tz: ZoneInfo) -> str:
    """What the comparison is built from: the library's data (library.cache_key: sync, history, analysis),
    MusicBrainz's cache, the time zone and jimbo-dj's stored rows (rebuilt or added)."""
    tables = legacy.table_names(conn)
    stored = conn.execute("SELECT COUNT(*), MAX(built_at) FROM stats WHERE name IN ('library.stats', "
                          "'library.charts')").fetchone() if "stats" in tables else (0, None)
    mb = json.dumps(charts_stamp(conn, tables)[1])
    return "|".join([f"g{GATE_VERSION}", library.cache_key(conn), mb, str(tz), f"{stored[0]}:{stored[1]}"])


def _q(**params) -> str:
    return urlencode(params)


def _fields(theirs: dict, ours: dict, name: str, stats_rows: dict) -> list[dict]:
    """Every stored field (dicts one level down: ``paths.mapped``, ``files.formats``) next to traqfreq's."""
    out = []
    for k, v in theirs.items():
        if k in SKIP:
            continue
        if name == "library.charts" and k not in SECTIONS:
            out.append({"field": k, "matches": None, "skipped": NOT_IN_P2.get(k, "not a library number"),
                        "jimbodj": v if k != "genres" else None})
            continue
        nested = name == "library.charts" or k in ("play_history", "sonic_analysis", "paths")
        if nested and isinstance(v, dict):
            mine = ours.get(k) if isinstance(ours.get(k), dict) else {}
            for k2, v2 in v.items():
                f = f"{k}.{k2}"
                if f in NOT_IN_P2:
                    out.append({"field": f, "matches": None, "skipped": NOT_IN_P2[f], "jimbodj": v2})
                    continue
                out.append({**_field(f, v2, mine.get(k2)), **_rows(f, k2, v2, stats_rows)})
            continue
        out.append({**_field(k, v, ours.get(k)), **_rows(k, k, v, stats_rows)})
    return out


def _rows(field: str, key: str, value, stats_rows: dict) -> dict:
    """The query for library.tracks that lists a field's rows: one for a count, one per bar for a chart."""
    if field in FACETS and isinstance(value, list):
        facet = FACETS[field]
        return {"rows": {str(b["label"]): _q(facet=facet, value=b["label"]) for b in value
                         if isinstance(b, dict) and b.get("label") is not None}}
    if field in ("files.tracks", "files.size_gb", "time.average_minutes"):
        return {"rows": ""}
    r = stats_rows.get(STATS_ROWS.get(field, ""))
    return {"rows": r} if r is not None else {}


def compare(conn: sqlite3.Connection, tz: ZoneInfo, stats_of=None, charts_of=None) -> dict:
    """The P2 gate. ``stats_of`` / ``charts_of`` give traqfreq's builds (cached by the app; built here when not
    given)."""
    tables = legacy.table_names(conn)
    if "tracks" not in tables:
        raise library.NoLibrary("tracks")
    stats_of = stats_of or (lambda: library.stats(conn))
    charts_of = charts_of or (lambda: charts(conn, tz))
    meta = _meta(conn, tables)
    stats_now = json.dumps([meta.get("last_sync"), meta.get("history_version")])
    charts_now = charts_stamp(conn, tables)
    ours_stats = None
    rows = []
    for name, version in (("library.stats", STATS_VERSION), ("library.charts", CHARTS_VERSION)):
        s = _row(conn, name, tables)
        if s is None:
            continue
        base = {"name": name, "params": "", "built_at": legacy._iso(s["built_at"]), "version": s["version"],
                "stamp": s["stamp"]}
        try:
            theirs = json.loads(s["value"])
        except (TypeError, ValueError):
            rows.append({**base, "matches": False, "fresh": None, "error": "not JSON", "fields": [],
                         "compared": 0, "matching": 0})
            continue
        if name == "library.stats":
            fresh = s["stamp"] == stats_now and s["version"] == version
            current = stats_now
            ours_stats = ours = stats_of() if ours_stats is None else ours_stats
            stats_rows = dict(ours.get("rows") or {})
            by_key = stats_rows.get("top_artists") or {}
            stats_rows["top_artists_by_name"] = {a["artist"]: by_key[str(a["artist_key"])]
                                                 for a in ours.get("top_artist_keys") or []
                                                 if str(a["artist_key"]) in by_key}
        else:
            try:
                st = _norm(json.loads(s["stamp"])) if s["stamp"] else None
            except (TypeError, ValueError):
                st = None
            fresh = (isinstance(st, list) and len(st) == 4 and s["version"] == version
                     and [st[0], st[1], st[3]] == [charts_now[0], charts_now[1], charts_now[3]])
            current = json.dumps(charts_now)
            ours = charts_of()
            stats_rows = {}
        fields = _fields(theirs, ours, name, stats_rows)
        compared = [f for f in fields if f["matches"] is not None]
        rows.append({**base, "fresh": fresh, "current_stamp": current, "matches": all(f["matches"] for f in compared),
                     "fields": fields, "compared": len(compared),
                     "matching": sum(1 for f in compared if f["matches"])})
    differ = [r for r in rows if not r["matches"]]
    explained = [r for r in differ if r.get("fresh") is False]
    return {
        "rows": rows,
        "stored": len(rows),
        "fields": sum(r.get("compared", 0) for r in rows),
        "matching_fields": sum(r.get("matching", 0) for r in rows),
        "matching": len(rows) - len(differ),
        "differ": len(differ),
        "stale": sum(1 for r in rows if r.get("fresh") is False),
        "explained": len(explained),
        "passed": bool(rows) and len(differ) == len(explained),
        "timezone": str(tz),
        "not_in_p2": NOT_IN_P2,
        "chart_rules": CHART_RULES,
        "rules": {
            "stored": "jimbo-dj's stats rows library.stats and library.charts (statcache.py)",
            "fresh": "library.stats: its stamp is jimbo-dj's current [last_sync, history_version]; library.charts: "
                     "its stamp's analysis, MusicBrainz and history parts are jimbo-dj's current ones (the styles' "
                     "version lives only in jimbo-dj's memory); and the builder version is the current one",
            "passed": "every stored row matches, or each one that differs is stale (older than jimbo-dj's data)",
        },
    }


def facet_keys(conn: sqlite3.Connection, facet: str, value: str, tz: ZoneInfo) -> list[int]:
    """The live tracks behind one chart bar, by jimbo-dj's facets.members (same rule as the bar)."""
    if facet not in ROW_FACETS:
        raise ValueError(f"facet is one of {', '.join(ROW_FACETS)}")
    tables = legacy.table_names(conn)
    need = {"albums", "mb_releases"} if facet in jf.TIME or facet == "label" else \
        {"artists", "mb_artists"} if facet in jf.PLACE else set()
    if not need <= tables:
        raise ValueError(f"facet {facet} needs jimbo-dj's {', '.join(sorted(need - tables))} table")
    with ji.in_tz(tz):
        return sorted(jf.members(conn, facet, value))
