"""Stand-in for jimbo-dj's cache.py (not vendored): ``data_stamp``, which keys ``rules.leaf_keys``' cache.

jimbo-dj's is the analysed tracks' count, their newest analysis and the last sync, for its one database. traqfreq
puts the database file in front (tests open many fixtures, and two with the same rows would share a stamp)."""
from __future__ import annotations


def data_stamp(con) -> tuple:
    n, last = con.execute("SELECT COUNT(*), MAX(analyzed_at) FROM analysis").fetchone()
    sync = con.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
    db = con.execute("PRAGMA database_list").fetchone()
    return db[2] if db else "", n, last, sync[0] if sync else None
