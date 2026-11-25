"""The functions of jimbo-dj's history.py the branch builder needs, under jimbo-dj's module name: ``_range`` and
``listened_keys`` (the ``listened`` condition), copied unchanged at 1d8a7cb; ``match_key``, ``norm_artist`` and
``plays_of`` (Never in mixes and most played first, T25), the copies already in vendor/jimbodj_history.py and
vendor/jimbodj_library.py; and ``track_stats``, a stand-in (below). ``listen_tz`` is T8's stand-in
(vendor/jimbodj_history.py: the zone set by ``in_zone``); ``ensure_schema`` is a stand-in that does nothing,
because the legacy database is read-only and jimbo-dj made the tables."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

import contextlib
import contextvars

from .jimbodj_history import listen_tz  # noqa: F401 - stand-in (T8)
from .jimbodj_history import match_key, norm_artist  # noqa: F401 - copies (T5), bans.Bans calls them
from .jimbodj_library import plays_of  # noqa: F401 - copy (T9), browse._with_plays calls it

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


# T25: browse._with_plays calls history.track_stats(con), jimbo-dj's _track_stats behind its background cache.
# traqfreq builds it once per data version (library.track_plays, in the right zone) and hands it in with ``using``.
_HIST: contextvars.ContextVar = contextvars.ContextVar("track_stats")


def track_stats(con) -> dict:  # noqa: ARG001 - built by library.track_plays, handed in with using()
    return _HIST.get()


@contextlib.contextmanager
def using(hist: dict):
    token = _HIST.set(hist)
    try:
        yield
    finally:
        _HIST.reset(token)
