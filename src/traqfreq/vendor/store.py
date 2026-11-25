"""jimbo-dj's saved playlists (store.py): how a row reads and how a slug finds it, copied unchanged at 1d8a7cb.
Not copied: save, sync, rename, set_in_plex, mark_stale, revive, delete, adopt (they write). ``ensure_schema``
is a stand-in that does nothing (the legacy database is read-only; jimbo-dj made the table)."""
from __future__ import annotations

import json
import sqlite3

from . import playlists, songs

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/store.py (SCHEMA, KINDS, _row, unique_slugs, slugs, resolve, get, by_title, listing)"

# --- src/jimbodj/store.py --------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_playlists (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,        -- mix | cluster | like | explore | blend | setlist | plex | history
    title       TEXT NOT NULL UNIQUE, -- the full Plex title, emoji included
    summary     TEXT,
    keys        TEXT NOT NULL,        -- JSON [rating_key] in play order
    source      TEXT,                 -- JSON: what made it (seed, blend parts, setlist, cluster id…)
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    in_plex     INTEGER NOT NULL DEFAULT 0,
    plex_key    INTEGER,              -- the Plex playlist's ratingKey while it's there
    pushed_at   INTEGER,
    plex_error  TEXT,
    stale       INTEGER NOT NULL DEFAULT 0,  -- a cluster that no longer exists, an old mix kind…
    stale_in_plex INTEGER                    -- it was in Plex when it went stale (so going back to an older run restores it)
);
"""

KINDS = {
    "mix": "Mix", "cluster": "Cluster", "like": "More like this", "explore": "Explore",
    "blend": "Genre blend", "setlist": "Setlist", "plex": "From Plex", "history": "From your history",
}

def _row(r: sqlite3.Row | None, tracks: bool = False) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    keys = json.loads(d.pop("keys") or "[]")
    d["source"] = json.loads(d["source"] or "{}")
    d["in_plex"], d["stale"] = bool(d["in_plex"]), bool(d["stale"])
    d["tracks"] = len(keys)
    if tracks:
        d["keys"] = keys
    return d


def unique_slugs(items: list[tuple[int, str]], reserved: tuple[str, ...] = ()) -> dict[int, str]:
    """(id, name) → id → a readable slug, unique: the oldest keeps "late-night-jazz", later ones get "-2"…
    A reserved slug (a path of its own) starts at "-2"."""
    out, seen = {}, dict.fromkeys(reserved, 1)
    for i, name in sorted(items):
        base = songs.slugify(name) or "playlist"
        n = seen.get(base, 0) + 1
        seen[base] = n
        out[i] = base if n == 1 else f"{base}-{n}"
    return out


def slugs(con) -> dict[int, str]:
    """Every saved playlist's slug, from its name without the emoji: /playlists/more-like-afi."""
    ensure_schema(con)
    return unique_slugs([(r[0], playlists.base_name(r[1])) for r in con.execute("SELECT id, title FROM saved_playlists")],
                        reserved=("new", "mixes", "blend", "setlist"))  # /playlists/new, and old /playlists/… paths that redirect


def resolve(con, ref: str | int) -> int | None:
    """A saved playlist's id from its slug (or an old numeric id)."""
    ref = str(ref)
    want = songs.squash(ref.lower())
    found = next((i for i, sl in slugs(con).items() if songs.squash(sl) == want), None)
    return found if found is not None else (int(ref) if ref.isdigit() else None)


def get(con, pid: int, tracks: bool = True) -> dict | None:
    ensure_schema(con)
    d = _row(con.execute("SELECT * FROM saved_playlists WHERE id=?", (pid,)).fetchone(), tracks)
    if d:
        d["slug"] = slugs(con).get(pid)
    return d


def by_title(con, title: str) -> dict | None:
    ensure_schema(con)
    return _row(con.execute("SELECT * FROM saved_playlists WHERE title=?", (title,)).fetchone(), True)


def listing(con, kind: str | None = None) -> list[dict]:
    ensure_schema(con)
    q = "SELECT * FROM saved_playlists" + (" WHERE kind=?" if kind else "") + " ORDER BY in_plex DESC, updated_at DESC"
    out, sl = [], slugs(con)
    for r in con.execute(q, (kind,) if kind else ()):
        d = _row(r, True)
        d["slug"] = sl.get(d["id"])
        d["preview"] = d.pop("keys")[:4]
        out.append(d)
    return out


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
def ensure_schema(con: sqlite3.Connection) -> None:  # noqa: ARG001 - jimbo-dj creates the table; traqfreq only reads
    return None
