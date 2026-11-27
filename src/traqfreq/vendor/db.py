"""A stand-in for jimbo-dj's db.py, for its vendored Plex sync and watcher. ``COLUMNS``, ``upsert_tracks``,
``set_meta`` and ``get_meta`` are copied unchanged at 1d8a7cb. ``connect`` is traqfreq's: it opens only traqfreq's
library.sqlite (the path must be ``own.path``), the way jimbo-dj's opens its file (WAL, synchronous NORMAL, no
memory-mapped reads, a transaction per ``with con:``), and it **refuses unless the ``plex`` cut-over is owned**, so
nothing vendored can write before the copy. It never creates or alters a table: the copy made them with jimbo-dj's
schema. jimbo-dj's database is never opened here."""
from __future__ import annotations

import sqlite3
from pathlib import Path

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/db.py (COLUMNS, upsert_tracks, set_meta, get_meta)"

# --- src/jimbodj/db.py -----------------------------------------------------------------------------------
COLUMNS = [
    "rating_key", "guid", "title", "artist", "track_artist", "album", "album_key", "artist_key",
    "disc", "track_no", "year", "duration_ms", "plex_path", "local_path", "parts", "file_size",
    "container", "codec", "bitrate", "channels", "view_count", "last_viewed_at",
    "user_rating", "added_at", "updated_at", "sonic_version", "seen_at",
]


def upsert_tracks(con: sqlite3.Connection, rows: list[dict]) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join(f":{c}" for c in COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "rating_key")
    con.executemany(
        f"INSERT INTO tracks ({cols}) VALUES ({marks}) "
        f"ON CONFLICT(rating_key) DO UPDATE SET {updates}, removed_at=NULL",
        rows,
    )


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT INTO meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_meta(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


# --- traqfreq's stand-in, not vendored --------------------------------------------------------------------
CUTOVER = "plex"


class NotOwned(RuntimeError):
    """The write was refused: the cut-over isn't traqfreq's (jimbo-dj still writes these tables)."""


def connect(path: Path) -> sqlite3.Connection:
    from .. import own

    path = Path(path)
    if path.name != own.FILE:
        raise NotOwned(f"only traqfreq's {own.FILE} is written, not {path.name}")
    state = own.record(path.parent, CUTOVER)["state"]
    if state != own.OWNED:
        raise NotOwned(f"the {CUTOVER} cut-over isn't owned by traqfreq ({state.replace('_', ' ')}): jimbo-dj still "
                       f"writes its tables, so traqfreq doesn't")
    con = sqlite3.connect(path, timeout=60, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA mmap_size=0")
    return con
