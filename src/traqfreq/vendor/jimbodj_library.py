"""Functions vendored from jimbo-dj (ryanjpeterson/jimbo-dj, private) at 1d8a7cb, copied as is:

- src/jimbodj/library.py: ``_pct``, ``stats`` (the library's counts, statcache's ``library.stats``);
- src/jimbodj/history.py: ``_track_stats`` (a track's plays from every source), ``plays_of``, ``last_of``;
- src/jimbodj/analyzer_version.py: ``ANALYZER_VERSION``.

Never edited here: traqfreq must count the library exactly the way jimbo-dj does until LIBRARY's cut-over (P6).
The copies call jimbo-dj's ``db.connect``, ``db.get_meta``, ``Settings`` and ``listen_tz``; the stand-ins at the
bottom (marked, not vendored) give them the read-only connection traqfreq hands in (``using``) and an empty
``path_map``, so ``stats`` never looks at a disk: its ``paths.folders`` depend on jimbo-dj's config and mounts.
To update: copy the same names again from jimbo-dj, bump VENDORED_FROM, run tests/test_library.py.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import os  # noqa: F401 - stats reads os.path.isdir, only for folders (none here)
import sqlite3
from collections import Counter

from .jimbodj_history import band_of, listen_tz  # noqa: F401 - _track_stats calls them (listen_tz: T8's stand-in)

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/library.py, history.py, analyzer_version.py"

# --- src/jimbodj/analyzer_version.py ----------------------------------------------------------------------
ANALYZER_VERSION = 2  # 2: loudness measured at 44.1 kHz (v1 was wrong for 96 kHz files)


# --- src/jimbodj/library.py -------------------------------------------------------------------------------
def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def stats(s: Settings, check_files: bool = False) -> dict:
    con = db.connect(s.db_path)
    live = "removed_at IS NULL"
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]  # noqa: E731
    total = q(f"SELECT COUNT(*) FROM tracks WHERE {live}")
    server = json.loads(db.get_meta(con, "server") or "{}")
    last_sync = db.get_meta(con, "last_sync")

    def counts(col: str, limit: int = 10) -> dict:
        rows = con.execute(
            f"SELECT COALESCE({col}, '?') v, COUNT(*) n FROM tracks WHERE {live} GROUP BY v ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return {str(r["v"]): r["n"] for r in rows}

    bitrate_buckets = {}
    for label, lo, hi in [("<192k", 0, 192), ("192-255k", 192, 256), ("256-319k", 256, 320),
                          ("320k", 320, 321), (">320k (lossless)", 321, 10**9)]:
        bitrate_buckets[label] = q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND bitrate>=? AND bitrate<?", lo, hi)

    played = q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND view_count>0")
    rated = q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND user_rating IS NOT NULL")
    sonic = q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND sonic_version IS NOT NULL")
    mapped = q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND local_path IS NOT NULL")
    top_artists = con.execute(
        f"SELECT artist, SUM(view_count) plays FROM tracks WHERE {live} GROUP BY artist_key "
        "HAVING plays>0 ORDER BY plays DESC LIMIT 10"
    ).fetchall()
    unmapped_examples = [r[0] for r in con.execute(
        f"SELECT plex_path FROM tracks WHERE {live} AND local_path IS NULL LIMIT 5")]

    out = {
        "server": server,
        "last_sync": int(last_sync) if last_sync else None,
        "tracks": total,
        "artists": q(f"SELECT COUNT(DISTINCT artist_key) FROM tracks WHERE {live}"),
        "albums": q(f"SELECT COUNT(DISTINCT album_key) FROM tracks WHERE {live}"),
        "hours": round((q(f"SELECT COALESCE(SUM(duration_ms),0) FROM tracks WHERE {live}")) / 3_600_000, 1),
        "size_gb": round((q(f"SELECT COALESCE(SUM(file_size),0) FROM tracks WHERE {live}")) / 1e9, 1),
        "codecs": counts("codec"),
        "containers": counts("container"),
        "bitrate_kbps": bitrate_buckets,
        "play_history": {
            "played_tracks": played, "played_pct": _pct(played, total),
            "total_plays": q(f"SELECT COALESCE(SUM(view_count),0) FROM tracks WHERE {live}"),
            "rated_tracks": rated, "rated_pct": _pct(rated, total),
            "top_artists": {r["artist"]: r["plays"] for r in top_artists},
        },
        "sonic_analysis": {"tracks": sonic, "pct": _pct(sonic, total)},
        "paths": {
            "folders": {plex_dir: {"read_from": local_dir, "readable_here": os.path.isdir(local_dir), "tracks": q(
                f"SELECT COUNT(*) FROM tracks WHERE {live} AND (plex_path=? OR substr(plex_path, 1, ?)=?)",
                plex_dir, len(plex_dir) + 1, plex_dir + "/")} for plex_dir, local_dir in s.path_map},
            "mapped": mapped, "mapped_pct": _pct(mapped, total),
            "unmapped_examples": unmapped_examples,
            "multi_part_tracks": q(f"SELECT COUNT(*) FROM tracks WHERE {live} AND parts>1"),
            "removed_since_first_sync": q("SELECT COUNT(*) FROM tracks WHERE removed_at IS NOT NULL"),
        },
    }
    if check_files:
        out["paths"]["on_disk"] = _check_files(con, s)
    con.close()
    return out



# --- src/jimbodj/history.py -------------------------------------------------------------------------------
def _track_stats(con: sqlite3.Connection) -> dict[int, dict]:
    tz = listen_tz(con)
    out: dict[int, dict] = {}
    for rk, started, source in con.execute(
            "SELECT COALESCE(l.rating_key, m.rating_key), l.started_at, l.source FROM listens l "
            "LEFT JOIN listen_matches m ON m.match_key = l.match_key "
            "WHERE COALESCE(l.rating_key, m.rating_key) IS NOT NULL AND l.counted=1"):
        s = out.get(rk)
        if s is None:
            s = out[rk] = {"plays": 0, "first": started, "last": started, "bands": Counter(), "sources": Counter()}
        s["plays"] += 1
        s["first"] = min(s["first"], started)
        s["last"] = max(s["last"], started)
        s["bands"][band_of(dt.datetime.fromtimestamp(started, tz).hour)] += 1
        s["sources"][source] += 1
    return out


def plays_of(m: dict, hist: dict[int, dict]) -> int:
    """A track's plays: Plex's count or the history's, whichever is larger (Plexamp may scrobble to
    Last.fm too, so adding them would count those twice)."""
    h = hist.get(m["rating_key"])
    return max(m.get("view_count") or 0, h["plays"] if h else 0)


def last_of(m: dict, hist: dict[int, dict]) -> float | None:
    h = hist.get(m["rating_key"])
    return max(filter(None, [m.get("last_viewed_at"), h["last"] if h else None]), default=None)



# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
# stats(s) opens jimbo-dj's database with db.connect(s.db_path) and closes it; here db.connect returns the
# read-only connection set by ``using`` (its close does nothing), and s.path_map is empty, so the folder
# checks (os.path.isdir on jimbo-dj's mounts) never run. check_files stays False: _check_files is not copied.
#
# The bitrate buckets as written inside stats, for the rows behind each one (tests check that counting rows
# with these gives stats' bitrate_kbps).
BITRATE_BUCKETS = [("<192k", 0, 192), ("192-255k", 192, 256), ("256-319k", 256, 320),
                   ("320k", 320, 321), (">320k (lossless)", 321, 10**9)]

_CONN: contextvars.ContextVar = contextvars.ContextVar("library_conn")


class _Borrowed:
    """The connection handed in, with close() left to its owner."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, *a):
        return self._conn.execute(*a)

    def close(self) -> None:
        pass


class _Db:
    @staticmethod
    def connect(_path):
        return _Borrowed(_CONN.get())

    @staticmethod
    def get_meta(con, key: str) -> str | None:
        row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


db = _Db()


class Settings:
    """What stats reads from jimbo-dj's Settings: db_path (unused here) and path_map (none: not compared)."""
    db_path = None
    path_map: list[tuple[str, str]] = []


def _check_files(con, s):  # noqa: ARG001 - never called: stats(s) runs with check_files=False
    raise NotImplementedError("traqfreq never checks jimbo-dj's files")


@contextlib.contextmanager
def using(conn: sqlite3.Connection):
    """Run the vendored stats on ``conn`` (traqfreq's read-only connection to jimbo-dj's database)."""
    token = _CONN.set(conn)
    try:
        yield
    finally:
        _CONN.reset(token)
