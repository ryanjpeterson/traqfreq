"""Stand-in for jimbo-dj's vectors.py (not vendored as a whole): the index's ``meta``, which ``make.details``
reads, without the embeddings. ``META_COLS`` and ``_META_Q`` are copied unchanged at 1d8a7cb, so ``meta`` holds the
same rows jimbo-dj's does: every track the analyzer read at the current version (status ok), with its features.
jimbo-dj's Index also loads the CLAP and EffNet vectors for Radio and clusters; P5 needs neither. Read-only."""
from __future__ import annotations

import sqlite3
import threading

from . import cache
from .analyzer_version import ANALYZER_VERSION

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/vectors.py (META_COLS, _META_Q)"

# --- src/jimbodj/vectors.py -------------------------------------------------------------------------------
META_COLS = ("rating_key", "artist", "artist_key", "track_artist", "title", "album", "album_key", "year",
             "duration_ms", "view_count", "last_viewed_at", "user_rating", "added_at",
             "bpm", "bpm_confidence", "camelot", "key", "scale", "loudness_lufs", "danceability", "aggressive", "relaxed",
             "happy", "sad", "voice", "moods", "genres")

_META_Q = (f"SELECT {', '.join('t.' + c if c in ('rating_key',) else c for c in META_COLS)} FROM tracks t "
           "JOIN features f USING (rating_key) WHERE t.rating_key IN (SELECT rating_key FROM analysis WHERE status='ok' AND version>=?) {extra}")


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
