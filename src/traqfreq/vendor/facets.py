"""The name jimbo-dj's rules.py imports (``from . import facets``): vendor/jimbodj_facets.py's ``members`` and
constants, plus a stand-in ``scope`` (not vendored) for the ``in:`` condition.

jimbo-dj's ``facets.scope`` imports its clusters, mixes, songs and store modules. Here they are the read-only
copies in vendor/ (clusters.py, store.py, songs.py, and from T27 mixes.py's ``latest``). The body below is
jimbo-dj's ``scope`` as written at 1d8a7cb; only where its modules come from differs.
"""
from __future__ import annotations

import sqlite3

from .jimbodj_facets import FILE, KEYS, OTHER, PLACE, TIME, VENDORED_FROM, _by, members  # noqa: F401


# --- stand-in: jimbo-dj's facets.scope over the read-only copies ----------------------------------------
def scope(con: sqlite3.Connection, ref: str, index=None) -> tuple[list[int], str]:
    """'cluster:heavy-grindcore' → (its tracks, 'Cluster: Heavy Grindcore'). A cluster is every member of it
    in the current run; a saved playlist (saved:more-like-afi) or a mix is its tracks; an artist or album
    (artist:afi, album:afi-sing-the-sorrow) is its library tracks. Old numeric ids still work."""
    from . import clusters, mixes, songs, store

    kind, _, ident = ref.partition(":")
    if kind == "cluster":
        rid = clusters.current_run_id(con)
        cid = clusters.resolve(con, ident)
        c = con.execute("SELECT name FROM clusters WHERE run_id=? AND id=?", (rid, cid)).fetchone() if cid is not None else None
        if not c:
            raise ValueError("that cluster isn't in the current run")
        keys = [r[0] for r in con.execute("SELECT rating_key FROM cluster_members WHERE run_id=? AND cluster_id=?", (rid, cid))]
        return keys, f"Cluster: {c['name']}"
    if kind == "saved":
        pid = store.resolve(con, ident)
        p = store.get(con, pid) if pid is not None else None
        if not p:
            raise ValueError("no such saved playlist")
        return p["keys"], p["title"]
    if kind == "mix":
        if index is None:
            from . import vectors
            index = vectors.get(con)
        m = mixes.latest(con, index, ident)
        if not m:
            raise ValueError("that mix isn't built yet")
        return [t["rating_key"] for t in m["tracks"]], m["title"]
    if kind in ("artist", "album"):  # an artist's or album's page
        col = f"{kind}_key"
        idx = songs.index(con)
        key = (idx.artist if kind == "artist" else idx.album)(ident) or (int(ident) if ident.isdigit() else None)
        rows = con.execute(f"SELECT rating_key, artist, album FROM tracks WHERE {col}=? AND removed_at IS NULL", (key,)).fetchall() if key else []
        if not rows:
            raise ValueError(f"no such {kind}")
        return [r[0] for r in rows], rows[0]["artist"] if kind == "artist" else f"{rows[0]['album']} ({rows[0]['artist']})"
    raise ValueError(f"no scope {ref!r}")
