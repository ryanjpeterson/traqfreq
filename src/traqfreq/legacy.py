"""Strictly read-only access to jimbo-dj's SQLite database.

traqfreq never writes to the legacy DB. The connection is opened with the
SQLite URI ``mode=ro`` and ``PRAGMA query_only`` as a second guard.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

# Tables whose raw row counts the summary reports (skipped if absent). Names from jimbo-dj's db.py and
# history.py (checked at jimbo-dj 1d8a7cb).
KEY_TABLES = ("tracks", "albums", "artists", "analysis", "features", "listens", "listen_matches", "history_imports")

LIVE = "removed_at IS NULL"  # a track the last Plex sync still saw (library.py stats)
PLAYS = "counted = 1"  # a listen that is a play: 30 s or more and not a duplicate (history.py dedupe)

# The numbers jimbo-dj shows, counted its way. Each: id, the table it needs, the SQL, and where jimbo-dj
# stores its own copy (stats table name, JSON field) so the two can be compared.
MEASURES = (
    ("tracks", "tracks", f"SELECT COUNT(*) FROM tracks WHERE {LIVE}", ("library.stats", "tracks")),
    ("albums", "tracks", f"SELECT COUNT(DISTINCT album_key) FROM tracks WHERE {LIVE}", ("library.stats", "albums")),
    ("artists", "tracks", f"SELECT COUNT(DISTINCT artist_key) FROM tracks WHERE {LIVE}", ("library.stats", "artists")),
    ("plays", "listens", f"SELECT COUNT(*) FROM listens WHERE {PLAYS}", ("history.overview", "plays")),
)

# meta keys that look like timestamps of the last sync / import.
META_TIME_HINTS = ("sync", "import", "scan")


class LegacyDBMissing(FileNotFoundError):
    pass


def _ro_uri(p: Path) -> str:
    return f"file:{quote(str(p))}?mode=ro"


def connect(path: str | Path, own: tuple[Path, tuple[str, ...], tuple[str, ...]] | None = None) -> sqlite3.Connection:
    """Open the legacy DB read-only. Raises LegacyDBMissing if the file is absent.

    ``own`` (P6, ``own.reader``): (traqfreq's ``library.sqlite``, the tables its cut-overs own, their meta keys).
    That file is attached read-only as ``own`` and each owned table gets a TEMP VIEW of its name over
    ``own.<table>``; SQLite resolves an unqualified name in ``temp`` first, so every reader sees traqfreq's copy
    unchanged. ``meta`` becomes traqfreq's owned keys first, then jimbo-dj's for the rest. The views are made
    before ``query_only`` goes on (SQLite refuses a TEMP VIEW under it); both files stay ``mode=ro``."""
    p = Path(path).resolve()
    if not p.is_file():
        raise LegacyDBMissing(str(p))
    conn = sqlite3.connect(_ro_uri(p), uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if own is not None:
        lib, tables, meta_keys = own
        conn.execute("ATTACH DATABASE ? AS own", (_ro_uri(Path(lib).resolve()),))
        for t in tables:
            conn.execute(f'CREATE TEMP VIEW "{t}" AS SELECT * FROM own."{t}"')
        if meta_keys:
            has_legacy_meta = conn.execute(
                "SELECT 1 FROM main.sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            rest = (" UNION ALL SELECT key, value FROM main.meta WHERE key NOT IN (SELECT key FROM own.meta)"
                    if has_legacy_meta else "")
            conn.execute(f"CREATE TEMP VIEW meta AS SELECT key, value FROM own.meta{rest}")
    conn.execute("PRAGMA query_only = ON")
    return conn


def attach(conn: sqlite3.Connection, path: str | Path, alias: str = "legacy") -> None:
    """Attach the legacy DB read-only (``mode=ro``) to one of traqfreq's own connections, for the P6 one-time
    copy (``own.copy``). Raises LegacyDBMissing if the file is absent. The connection must be opened with
    ``uri=True``; the attached file can't be written through it."""
    p = Path(path).resolve()
    if not p.is_file():
        raise LegacyDBMissing(str(p))
    conn.execute(f"ATTACH DATABASE ? AS {alias}", (_ro_uri(p),))


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def summary(conn: sqlite3.Connection) -> dict:
    tables = table_names(conn)
    counts = {
        t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        for t in KEY_TABLES
        if t in tables
    }
    times: dict[str, str] = {}
    if "meta" in tables:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(meta)")}
        if {"key", "value"} <= cols:
            for r in conn.execute("SELECT key, value FROM meta ORDER BY key"):
                if any(h in r["key"].lower() for h in META_TIME_HINTS):
                    times[r["key"]] = r["value"]
    return {
        "measures": measures(conn, tables),
        "counts": counts,
        "missing_tables": [t for t in KEY_TABLES if t not in tables],
        "times": times,
    }


def stored_stat(conn: sqlite3.Connection, name: str, tables: set[str] | None = None) -> tuple[dict, float] | None:
    """One of jimbo-dj's stored summaries (its ``stats`` table, statcache.py): (value, built_at), or None."""
    if "stats" not in (tables if tables is not None else table_names(conn)):
        return None
    row = conn.execute("SELECT value, built_at FROM stats WHERE name = ? AND params = ''", (name,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"]), row["built_at"]
    except (TypeError, ValueError):
        return None


def measures(conn: sqlite3.Connection, tables: set[str] | None = None) -> list[dict]:
    """jimbo-dj's headline numbers, counted the way jimbo-dj counts them (W3: each carries its rule), next to
    the copy jimbo-dj last stored (``jimbodj``: None if it has none) and whether the two agree."""
    tables = table_names(conn) if tables is None else tables
    stored: dict[str, tuple[dict, float] | None] = {}
    out = []
    for mid, table, sql, (stat, field) in MEASURES:
        if table not in tables:
            continue
        value = conn.execute(sql).fetchone()[0]
        if stat not in stored:
            stored[stat] = stored_stat(conn, stat, tables)
        theirs = stored[stat]
        jd = None
        if theirs and isinstance(theirs[0].get(field), int):
            jd = {"value": theirs[0][field], "built_at": _iso(theirs[1]), "source": f"stats.{stat}"}
        out.append({"id": mid, "value": value, "rule": sql, "jimbodj": jd,
                    "matches": None if jd is None else jd["value"] == value})
    return out


def _iso(epoch: object) -> str | None:
    """jimbo-dj stores times as Unix seconds (int or float, sometimes as text)."""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def last_scan(conn: sqlite3.Connection) -> dict | None:
    """The last Plex library sync: jimbo-dj's ``meta.last_sync`` (library.py sets it after each sync)."""
    if "meta" not in table_names(conn):
        return None
    row = conn.execute("SELECT value FROM meta WHERE key = 'last_sync'").fetchone()
    at = _iso(row["value"]) if row else None
    return {"at": at, "source": "meta.last_sync"} if at else None


def recent_jobs(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Finished jobs jimbo-dj keeps in its DB: history imports (``history_imports``), newest first.

    jimbo-dj's running jobs (sync, analyzer, pushes) live in its process memory (jobs.py), not in the DB.
    """
    if "history_imports" not in table_names(conn):
        return []
    rows = conn.execute(
        "SELECT id, source, at, rows, added, note FROM history_imports ORDER BY at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"id": r["id"], "kind": "history_import", "source": r["source"], "at": _iso(r["at"]),
         "rows": r["rows"], "added": r["added"], "note": r["note"]}
        for r in rows
    ]


def activity(conn: sqlite3.Connection, limit: int = 10) -> dict:
    tables = table_names(conn)
    return {
        "last_scan": last_scan(conn),
        "jobs": recent_jobs(conn, limit),
        "jobs_source": "history_imports" if "history_imports" in tables else None,
    }
