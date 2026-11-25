"""Stand-in for jimbo-dj's ``mixes.latest`` (not vendored), for the ``in:mix:daily`` condition.

jimbo-dj's reads the newest ``mixes`` row of the kind and keeps the tracks its vectors index knows (``index.meta``:
analysed tracks), each with flow details. Here: the same row and the live tracks the analyzer read (status ok),
without the details, which T27 adds with the index. Read-only."""
from __future__ import annotations

import json
import sqlite3


def latest(con: sqlite3.Connection, index, kind: str) -> dict | None:  # noqa: ARG001 - no index before T27
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mixes'").fetchone():
        return None
    r = con.execute("SELECT * FROM mixes WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    if not r:
        return None
    ok = {k for (k,) in con.execute("SELECT t.rating_key FROM tracks t JOIN analysis a ON a.rating_key = t.rating_key "
                                    "WHERE t.removed_at IS NULL AND a.status = 'ok'")}
    tracks = [{"rating_key": key, "pool": pool} for key, pool in json.loads(r["tracks"]) if key in ok]
    return {"id": r["id"], "kind": kind, "period": r["period"], "title": r["title"], "tracks": tracks}
