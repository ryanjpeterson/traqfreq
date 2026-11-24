"""jimbo-dj's file tags (filetags.py): the read-only parts copied unchanged at 1d8a7cb.

jimbo-dj reads every genre value in the audio files into its ``file_tags`` table (its "file_tags" job) and writes a
file's genre tag only for Fix in Plex with "the files too" on. traqfreq copies only what reads that table:
``by_album`` (a source of vendor/jimbodj_tags.py ``Library``), ``stamp`` and ``status``. Not copied: ``scan``,
``read_genres``, ``write_genres``, ``remember`` and ``ensure`` (they open audio files or write). Audio files are
read-only to traqfreq; it never opens them.
"""
from __future__ import annotations

import json

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/filetags.py (by_album, stamp, status)"

# --- src/jimbodj/filetags.py -----------------------------------------------------------------------------
def by_album(con) -> dict[int, dict]:
    """album_key → {"tracks": tracks read, "tags": Counter-like {genre: tracks carrying it}}."""
    from collections import Counter, defaultdict

    out: dict[int, dict] = defaultdict(lambda: {"tracks": 0, "tags": Counter()})
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='file_tags'").fetchone():
        return {}
    for a, g in con.execute("SELECT t.album_key, f.genres FROM file_tags f JOIN tracks t ON t.rating_key=f.rating_key "
                            "WHERE t.removed_at IS NULL AND f.genres IS NOT NULL"):
        out[a]["tracks"] += 1
        try:
            out[a]["tags"].update(set(json.loads(g)))
        except ValueError:
            pass
    return dict(out)


def stamp(con):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='file_tags'").fetchone():
        return None
    return con.execute("SELECT MAX(read_at) FROM file_tags").fetchone()[0]


def status(con) -> dict:
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='file_tags'").fetchone():
        return {"read": 0, "failed": 0, "last": None}
    r = con.execute("SELECT SUM(error IS NULL), SUM(error IS NOT NULL), MAX(read_at) FROM file_tags").fetchone()
    return {"read": r[0] or 0, "failed": r[1] or 0, "last": r[2]}
