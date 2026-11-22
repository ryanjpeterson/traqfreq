"""Strictly read-only access to jimbo-dj's SQLite database.

traqfreq never writes to the legacy DB. The connection is opened with the
SQLite URI ``mode=ro`` and ``PRAGMA query_only`` as a second guard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

# Tables whose row counts the summary reports (skipped if absent).
KEY_TABLES = ("tracks", "albums", "artists", "listens", "track_analysis", "track_tags")

# meta keys that look like timestamps of the last sync / import.
META_TIME_HINTS = ("sync", "import", "scan")


class LegacyDBMissing(FileNotFoundError):
    pass


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the legacy DB read-only. Raises LegacyDBMissing if the file is absent."""
    p = Path(path).resolve()
    if not p.is_file():
        raise LegacyDBMissing(str(p))
    uri = f"file:{quote(str(p))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


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
    return {"counts": counts, "missing_tables": [t for t in KEY_TABLES if t not in tables], "times": times}
