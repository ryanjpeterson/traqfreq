"""The two functions of jimbo-dj's history.py the ``listened`` condition needs (``facets.members`` imports
``history``): ``_range`` and ``listened_keys``, copied unchanged at 1d8a7cb. ``listen_tz`` is T8's stand-in
(vendor/jimbodj_history.py: the zone set by ``in_zone``); ``ensure_schema`` is a stand-in that does nothing,
because the legacy database is read-only and jimbo-dj made the tables."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

from .jimbodj_history import listen_tz  # noqa: F401 - stand-in (T8)

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/history.py (_range, listened_keys)"


# --- src/jimbodj/history.py -------------------------------------------------------------------------------
def _range(con: sqlite3.Connection, year: int, month: int | None, day: int | None = None) -> tuple[float, float]:
    tz = listen_tz(con)
    if month and day:
        a = dt.datetime(year, month, day, tzinfo=tz)
        b = dt.datetime.combine(a.date() + dt.timedelta(days=1), dt.time(), tzinfo=tz)
        return a.timestamp(), b.timestamp()
    a = dt.datetime(year, month or 1, 1, tzinfo=tz)
    b = dt.datetime(year + (month or 12) // 12, (month or 12) % 12 + 1, 1, tzinfo=tz)
    return a.timestamp(), b.timestamp()


def listened_keys(con: sqlite3.Connection, period: str) -> set[int]:
    """Library tracks played in a year ("2018"), a month ("2018-06") or a day ("2018-06-21") — Explore's `listened` filter."""
    ensure_schema(con)
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", period.strip())
    if not m:
        raise ValueError("listened is a year (2018), a month (2018-06) or a day (2018-06-21)")
    a, b = _range(con, int(m[1]), int(m[2]) if m[2] else None, int(m[3]) if m[3] else None)
    return {r[0] for r in con.execute(
        "SELECT DISTINCT COALESCE(l.rating_key, m.rating_key) FROM listens l LEFT JOIN listen_matches m ON m.match_key=l.match_key "
        "WHERE l.counted=1 AND l.started_at >= ? AND l.started_at < ? AND COALESCE(l.rating_key, m.rating_key) IS NOT NULL",
        (int(a), int(b)))}


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
def ensure_schema(con) -> None:  # noqa: ARG001 - jimbo-dj creates its tables; traqfreq only reads
    return None
