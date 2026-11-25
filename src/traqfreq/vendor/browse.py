"""jimbo-dj's browse.py (Explore), the parts the branch builder uses, copied unchanged at 1d8a7cb: ``SOUND`` and
``_where`` (the sound conditions, ``rules.leaf_keys``), ``ORDER``, ``SORTS`` and ``_with_plays`` (most played first,
``rules.rank``; T25). ``_with_plays`` registers an SQL function on the connection, which writes nothing; its
``history`` is vendor/history.py, where ``track_stats`` is traqfreq's stand-in. Nothing here writes."""
from __future__ import annotations

import json
import re
import sqlite3

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/browse.py (ORDER, SORTS, SOUND, _where, _with_plays)"

# --- src/jimbodj/browse.py -------------------------------------------------------------------------------
# plays(): every source's plays, not just Plex's (_with_plays). Ties fall back to album order, so a
# sort that has nothing to go on still reads like the record.
ORDER = "t.artist_key, t.year, t.album_key, t.disc, t.track_no"
SORTS = {
    "plays": f"plays(t.rating_key, t.view_count) DESC, t.last_viewed_at DESC, {ORDER}",
    "bpm": f"f.bpm IS NULL, f.bpm ASC, {ORDER}",
    "added": f"t.added_at DESC, {ORDER}",
    "random": "RANDOM()",
}


SOUND = ("bpm", "key", "mood", "genre")


def _where(f: dict, version: int, keys: set[int] | None = None) -> tuple[str, list]:
    sql, args = ["t.removed_at IS NULL"], []
    if any(f.get(k) for k in SOUND):
        sql += ["a.status='ok'", "a.version>=?"]
        args.append(version)
    if keys is not None:
        sql.append("t.rating_key IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(keys)))
    if bpm := f.get("bpm"):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)?-(\d+(?:\.\d+)?)?", bpm)
        if not m:
            raise ValueError("bpm is lo-hi, like 120-130")
        if m[1]:
            sql.append("f.bpm >= ?")
            args.append(float(m[1]))
        if m[2]:
            sql.append("f.bpm < ?")
            args.append(float(m[2]))
    if key := f.get("key"):
        camelots = [k.strip().upper() for k in key.split(",") if k.strip()]
        sql.append(f"f.camelot IN ({','.join('?' * len(camelots))})")
        args += camelots
    if mood := f.get("mood"):
        sql.append("EXISTS (SELECT 1 FROM json_each(f.moods) j WHERE j.key=?)")
        args.append(mood)
    return " AND ".join(sql), args


def _with_plays(con: sqlite3.Connection) -> sqlite3.Connection:
    """Gives the SQL a plays(rating_key, view_count): Plex's count or the listening history's (Spotify,
    Last.fm…), whichever is larger (history.plays_of). Plex's alone is 0 for most of what you play elsewhere."""
    from . import history
    hist = history.track_stats(con)
    con.create_function("plays", 2, lambda rk, vc: history.plays_of({"rating_key": rk, "view_count": vc}, hist),
                        deterministic=True)
    return con
