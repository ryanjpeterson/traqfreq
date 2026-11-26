"""jimbo-dj's ``mixes.latest`` and ``POOL_LABEL``, copied unchanged at 1d8a7cb, for the ``in:mix:daily`` condition
(facets.scope). It reads the newest ``mixes`` row of the kind and keeps the tracks the vectors index knows
(``index.meta``: analysed at the current version, status ok, with features), each with its flow details and its
transition (flow.describe). Building, saving and pushing mixes are not copied: P5 only reads.

Until T27 a stand-in kept every live track with an ok analysis at any version; jimbo-dj's keeps only what its index
knows, so a track analysed at an old version no longer counts toward ``in:mix:``. ``ensure_schema`` is a stand-in:
the legacy DB is read-only, so a database without the table reads as no mix built yet. Read-only."""
from __future__ import annotations

import json
import sqlite3

from . import flow
from .similar import _public
from .vectors import Index

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/mixes.py (POOL_LABEL, latest)"

# --- src/jimbodj/mixes.py ---------------------------------------------------------------------------------
POOL_LABEL = {"favourite": "a favourite", "overlooked": "overlooked", "new": "recently added", "rediscover": "an old love",
              "unplayed": "never played"}


# --- traqfreq's stand-in, not vendored ---------------------------------------------------------------------
class NoTable(ValueError):
    pass


def ensure_schema(con: sqlite3.Connection) -> None:
    """jimbo-dj creates the table; the legacy DB is read-only, so a missing one means no mix is built yet
    (facets.scope's answer for a mix that isn't there)."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mixes'").fetchone():
        raise NoTable("that mix isn't built yet")


# --- src/jimbodj/mixes.py ---------------------------------------------------------------------------------
def latest(con: sqlite3.Connection, index: Index, kind: str) -> dict | None:
    ensure_schema(con)
    r = con.execute("SELECT * FROM mixes WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    if not r:
        return None
    tracks = []
    for key, pool in json.loads(r["tracks"]):
        m = index.meta.get(key)
        if m:
            tracks.append({**_public(m), "pool": pool, "similarity": 0.0, "score": 0.0, "transition": {}})
    prev = None
    for t in tracks:
        t["transition"] = flow.describe(prev, t)
        prev = t
    return {"id": r["id"], "kind": kind, "period": r["period"], "title": r["title"], "created_at": r["created_at"],
            "summary": r["summary"], "pushed_at": r["pushed_at"],
            "push_result": json.loads(r["push_result"]) if r["push_result"] else None, "tracks": tracks,
            "minutes": round(sum((t["duration_ms"] or 0) for t in tracks) / 60000),
            "counts": {p: sum(1 for t in tracks if t["pool"] == p) for p in POOL_LABEL}}
