"""jimbo-dj's clusters.py, the lookups only: the current run and a cluster by its slug, copied unchanged at
1d8a7cb (``in:cluster:…``). Making clusters (UMAP and HDBSCAN) stays in jimbo-dj. ``ensure_schema`` is a stand-in."""
from __future__ import annotations

import sqlite3

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/clusters.py (current_run_id, slugs, resolve)"

# --- src/jimbodj/clusters.py -----------------------------------------------------------------------------
def current_run_id(con: sqlite3.Connection) -> int | None:
    ensure_schema(con)
    r = con.execute("SELECT value FROM meta WHERE key='cluster_run'").fetchone()
    return int(r[0]) if r else None


def slugs(con: sqlite3.Connection, rid: int | None = None) -> dict[int, str]:
    """The current run's clusters by readable slug (/playlists/new/clusters/heavy-grindcore), unique within the run."""
    from .store import unique_slugs
    rid = rid if rid is not None else current_run_id(con)
    return unique_slugs([(r[0], r[1]) for r in con.execute("SELECT id, name FROM clusters WHERE run_id=?", (rid,))]) if rid else {}


def resolve(con: sqlite3.Connection, ref: str | int) -> int | None:
    """A current cluster's id from its slug (or an old numeric id)."""
    from .songs import squash
    ref = str(ref)
    want = squash(ref.lower())
    found = next((i for i, sl in slugs(con).items() if squash(sl) == want), None)
    return found if found is not None else (int(ref) if ref.isdigit() else None)


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
def ensure_schema(con: sqlite3.Connection) -> None:  # noqa: ARG001 - read-only
    return None
