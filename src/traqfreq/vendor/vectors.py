"""Stand-in for jimbo-dj's vectors.py (not vendored as a whole): the index's ``meta``, which ``make.details``
reads, without the embeddings. ``META_COLS`` and ``_META_Q`` are copied unchanged at 1d8a7cb, so ``meta`` holds the
same rows jimbo-dj's does: every track the analyzer read at the current version (status ok), with its features.
jimbo-dj's Index also loads the CLAP and EffNet vectors for Radio and clusters. T28's Ask box needs the CLAP half
(``Clap``): ``_norm``, ``_EMB_Q``, ``_stamp`` and ``_vectors`` are copied unchanged, and ``Clap`` keeps the tracks
with both vectors, as Index does, centred on their mean and L2-normalised. Read-only."""
from __future__ import annotations

import sqlite3
import threading

import numpy as np

from . import cache
from .analyzer_version import ANALYZER_VERSION

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/vectors.py (META_COLS, _META_Q, _norm, _EMB_Q, _stamp, _vectors)"

# --- src/jimbodj/vectors.py -------------------------------------------------------------------------------
META_COLS = ("rating_key", "artist", "artist_key", "track_artist", "title", "album", "album_key", "year",
             "duration_ms", "view_count", "last_viewed_at", "user_rating", "added_at",
             "bpm", "bpm_confidence", "camelot", "key", "scale", "loudness_lufs", "danceability", "aggressive", "relaxed",
             "happy", "sad", "voice", "moods", "genres")

_META_Q = (f"SELECT {', '.join('t.' + c if c in ('rating_key',) else c for c in META_COLS)} FROM tracks t "
           "JOIN features f USING (rating_key) WHERE t.rating_key IN (SELECT rating_key FROM analysis WHERE status='ok' AND version>=?) {extra}")




def _norm(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)


_EMB_Q = ("SELECT e.rating_key, e.kind, e.dtype, e.vec FROM embeddings e "
          "JOIN analysis a USING (rating_key) JOIN tracks t USING (rating_key) "
          "WHERE a.status='ok' AND a.version>=? AND t.removed_at IS NULL AND e.kind IN ('clap','effnet') {extra} "
          "ORDER BY e.rating_key")


def _stamp(con: sqlite3.Connection) -> tuple:
    """Changes when a track is analysed or re-analysed, and on every library sync (tracks removed)."""
    n, last = con.execute("SELECT COUNT(*), MAX(analyzed_at) FROM analysis WHERE status='ok' AND version>=?",
                          (ANALYZER_VERSION,)).fetchone()
    sync = con.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
    return n, last or 0, sync[0] if sync else None


def _vectors(rows) -> tuple[dict, dict]:
    clap, eff = {}, {}
    for key, kind, dtype, blob in rows:
        v = np.frombuffer(blob, dtype="<f4" if dtype == "float32" else "<f2")
        (clap if kind == "clap" else eff)[key] = v
    return clap, eff


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
class Index:
    """jimbo-dj's Index without the vectors: ``meta`` (rating_key → its META_COLS), read with jimbo-dj's query."""

    def __init__(self, con: sqlite3.Connection):
        self.meta = {r[0]: dict(zip(META_COLS, r)) for r in con.execute(_META_Q.format(extra=""), (ANALYZER_VERSION,))}

    def __len__(self) -> int:
        return len(self.meta)


_built: dict[tuple, Index] = {}
_lock = threading.Lock()


def get(con: sqlite3.Connection) -> Index:
    """The index for this data (cache.data_stamp: the database, the analysed tracks, the last sync)."""
    key = cache.data_stamp(con)
    with _lock:
        idx = _built.get(key)
        if idx is None:
            _built.clear()
            idx = _built[key] = Index(con)
        return idx


class Clap:
    """The CLAP half of jimbo-dj's Index (``__init__``'s lines for ``keys``, ``pos`` and ``clap``): the live tracks
    analysed at the current version with both vectors, CLAP centred on their mean and L2-normalised. No EffNet:
    the Ask box compares words, and EffNet has no text side. jimbo-dj grows its index between full loads; this one
    is built again when ``_stamp`` moves, which gives the full load's vectors."""

    def __init__(self, con: sqlite3.Connection):
        self.stamp = _stamp(con)
        try:
            rows = con.execute(_EMB_Q.format(extra=""), (ANALYZER_VERSION,)).fetchall()
        except sqlite3.OperationalError:  # no embeddings table: nothing analysed for sound yet
            rows = []
        clap, eff = _vectors(rows)
        keys = sorted(set(clap) & set(eff))
        self.keys = np.array(keys, dtype=np.int64)
        self.pos = {k: i for i, k in enumerate(keys)}
        if keys:
            c = np.stack([clap[k] for k in keys]).astype(np.float32)
            self.clap = _norm(c - c.mean(0))
        else:
            self.clap = np.zeros((0, 512), np.float32)

    def __len__(self) -> int:
        return len(self.keys)


_clap: dict[tuple, Clap] = {}


def clap(con: sqlite3.Connection) -> Clap:
    """The CLAP vectors for this data (``_stamp``, with the database in front, as cache.data_stamp does)."""
    db = con.execute("PRAGMA database_list").fetchone()
    key = (db[2] if db else "", *_stamp(con))
    with _lock:
        got = _clap.get(key)
        if got is None:
            _clap.clear()
            got = _clap[key] = Clap(con)
        return got
