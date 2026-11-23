"""traqfreq's own database (``TRAQFREQ_DATA_DIR/traqfreq.sqlite``): never jimbo-dj's.

For now it holds one table, ``stats``: built summaries of jimbo-dj's data, so pages don't loop over every
listen on each request. A summary is keyed by what it was built from (jimbo-dj's meta ``history_version``,
``match_version`` and ``last_sync``, and the listening time zone); when any of them changes the key changes
and the summary is rebuilt on the next read. Old keys for the same name are deleted then, so the table holds
one row per name.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

FILE = "traqfreq.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS stats (
    name TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, built_at REAL NOT NULL, seconds REAL NOT NULL,
    PRIMARY KEY (name, key)
);
"""

_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def path(data_dir: Path) -> Path:
    return Path(data_dir) / FILE


def connect(data_dir: Path) -> sqlite3.Connection:
    """Open (and create) traqfreq's database. Writable: this is traqfreq's own file."""
    p = path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def _lock(data_dir: Path, name: str) -> threading.Lock:
    k = (str(path(data_dir).resolve()), name)
    with _locks_guard:
        return _locks.setdefault(k, threading.Lock())


def cached(data_dir: Path, name: str, key: str, build: Callable[[], dict]) -> tuple[dict, dict]:
    """The summary ``name`` built for ``key``: read from the stats table, or built now (one build at a time
    per name) and stored. Returns (value, info), info = {name, key, built_at, seconds, hit}."""
    def read(conn):
        return conn.execute("SELECT value, built_at, seconds FROM stats WHERE name = ? AND key = ?",
                            (name, key)).fetchone()

    conn = connect(data_dir)
    try:
        row = read(conn)
        hit = row is not None
        if not hit:
            with _lock(data_dir, name):
                row = read(conn)  # another request may have built it while this one waited
                hit = row is not None
                if not hit:
                    t0 = time.perf_counter()
                    value = build()
                    seconds = round(time.perf_counter() - t0, 3)
                    built_at = time.time()
                    text = json.dumps(value, separators=(",", ":"))
                    with conn:
                        conn.execute("DELETE FROM stats WHERE name = ?", (name,))
                        conn.execute("INSERT INTO stats VALUES (?, ?, ?, ?, ?)", (name, key, text, built_at, seconds))
                    row = (text, built_at, seconds)
        return json.loads(row[0]), {"name": name, "key": key, "built_at": row[1], "seconds": row[2], "hit": hit}
    finally:
        conn.close()
