"""HISTORY, read-only: listens from jimbo-dj's database, counted the way jimbo-dj counts them.

jimbo-dj keeps every listen it imported (Last.fm, Plex, Spotify, Apple Music) in ``listens`` and decides,
after each import, which listens are plays (history.py ``dedupe``): ``counted = 1`` is a play; ``counted = 0``
is a listen that isn't one, for one of three reasons:

- ``too_short``: under 30 s (``dup_of`` is NULL);
- ``repeat``: the same source logged the play twice (``dup_of`` = its own source);
- ``duplicate``: a source ahead of it in jimbo-dj's PRIORITY has the same play (``dup_of`` = that source).

traqfreq reads those flags and never recomputes them, so nothing counts twice and every number matches
jimbo-dj's. Each listen is in exactly one bucket; ``overview`` checks that plays + the three reasons add up
to every listen. A play's library track is ``COALESCE(listens.rating_key, listen_matches.rating_key)``.
Years are in jimbo-dj's listening time zone (meta ``history_tz``, else TZ, else America/Denver).
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import legacy
from .vendor.jimbodj_history import PRIORITY, SOURCES

DEFAULT_TZ = "America/Denver"  # jimbo-dj's schedule.tz() default

# Each listen is in exactly one of these (see the module doc). SQL over ``listens`` (alias l).
STATUS = {
    "play": "l.counted = 1",
    "too_short": "l.counted = 0 AND l.dup_of IS NULL",
    "repeat": "l.counted = 0 AND l.dup_of = l.source",
    "duplicate": "l.counted = 0 AND l.dup_of IS NOT NULL AND l.dup_of != l.source",
}
TRACK = "COALESCE(l.rating_key, m.rating_key)"  # the library copy a listen was played as, or NULL
FROM = "FROM listens l LEFT JOIN listen_matches m ON m.match_key = l.match_key"


class NoHistory(LookupError):
    """jimbo-dj's database has no listens table."""


def _require(conn: sqlite3.Connection) -> set[str]:
    tables = legacy.table_names(conn)
    if "listens" not in tables:
        raise NoHistory("listens")
    return tables


def listen_tz(conn: sqlite3.Connection, default: str | None = None) -> ZoneInfo | timezone:
    """jimbo-dj's listening time zone: meta history_tz, else ``default`` (TZ), else America/Denver; UTC if
    this system has no zone data for it."""
    name = None
    if "meta" in legacy.table_names(conn):
        row = conn.execute("SELECT value FROM meta WHERE key = 'history_tz'").fetchone()
        name = row["value"] if row and row["value"] else None
    for candidate in (name, default, DEFAULT_TZ):
        if candidate:
            try:
                return ZoneInfo(candidate)
            except Exception:  # noqa: BLE001 - unknown name or no tzdata: try the next one
                continue
    return timezone.utc


def _order(source: str) -> tuple[int, str]:
    return (PRIORITY.index(source) if source in PRIORITY else len(PRIORITY), source)


def overview(conn: sqlite3.Connection, default_tz: str | None = None) -> dict:
    """Plays and every listen that isn't one, by source and by year, with the rule each number uses."""
    tables = _require(conn)
    has_matches = "listen_matches" in tables
    frm = FROM if has_matches else "FROM listens l"
    track = TRACK if has_matches else "l.rating_key"
    tz = listen_tz(conn, default_tz)

    status_case = "CASE " + " ".join(f"WHEN {sql} THEN '{k}'" for k, sql in STATUS.items()) + " END"
    by_source: dict[str, dict] = {}
    for r in conn.execute(
        f"SELECT l.source, {status_case} status, l.dup_of, COUNT(*) n, MIN(l.started_at) a, MAX(l.started_at) b "
        f"FROM listens l GROUP BY l.source, status, l.dup_of"
    ):
        s = by_source.setdefault(r["source"], {
            "source": r["source"], "name": SOURCES.get(r["source"], r["source"]), "listens": 0,
            **{k: 0 for k in STATUS}, "duplicate_of": {}, "first": None, "last": None})
        s["listens"] += r["n"]
        s[r["status"]] += r["n"]
        if r["status"] == "duplicate":
            s["duplicate_of"][r["dup_of"]] = s["duplicate_of"].get(r["dup_of"], 0) + r["n"]
        s["first"] = r["a"] if s["first"] is None else min(s["first"], r["a"])
        s["last"] = r["b"] if s["last"] is None else max(s["last"], r["b"])
    sources = sorted(by_source.values(), key=lambda s: _order(s["source"]))
    for s in sources:
        s["first"], s["last"] = legacy._iso(s["first"]), legacy._iso(s["last"])

    totals = {k: sum(s[k] for s in sources) for k in ("listens", *STATUS)}
    years: dict[int, dict] = defaultdict(lambda: {"plays": 0, "by_source": Counter()})
    matched = 0
    for started, source, rk in conn.execute(f"SELECT l.started_at, l.source, {track} rk {frm} WHERE {STATUS['play']}"):
        y = years[datetime.fromtimestamp(started, tz).year]
        y["plays"] += 1
        y["by_source"][source] += 1
        matched += rk is not None
    songs = matched_songs = None
    if has_matches:
        songs, matched_songs = conn.execute("SELECT COUNT(*), COUNT(rating_key) FROM listen_matches").fetchone()

    stored = legacy.stored_stat(conn, "history.overview", tables)
    jd = None
    if stored and isinstance(stored[0].get("plays"), int):
        jd = {"plays": stored[0]["plays"], "built_at": legacy._iso(stored[1]), "source": "stats.history.overview",
              "matches": stored[0]["plays"] == totals["play"]}
    return {
        "plays": totals["play"],
        "listens": totals["listens"],
        "not_plays": {k: totals[k] for k in STATUS if k != "play"},
        "adds_up": sum(totals[k] for k in STATUS) == totals["listens"],
        "matched": {"plays": matched, "pct": round(100 * matched / max(totals["play"], 1), 1)},
        "songs": {"heard": songs, "matched": matched_songs},
        "sources": sources,
        "years": [{"year": y, "plays": v["plays"], "by_source": dict(v["by_source"])} for y, v in sorted(years.items())],
        "timezone": str(tz),
        "rules": {"listens": "SELECT COUNT(*) FROM listens", **{k: f"listens WHERE {v.replace('l.', '')}" for k, v in STATUS.items()}},
        "jimbodj": jd,
    }


def year_range(year: int, tz) -> tuple[int, int]:
    a = datetime(year, 1, 1, tzinfo=tz)
    b = datetime(year + 1, 1, 1, tzinfo=tz)
    return int(a.timestamp()), int(b.timestamp())


def listens(conn: sqlite3.Connection, status: str = "play", source: str | None = None, year: int | None = None,
            limit: int = 50, offset: int = 0, default_tz: str | None = None) -> dict:
    """The rows behind a number: listens with one status, optionally one source and one year, newest first."""
    if status not in STATUS:
        raise ValueError(f"status is one of {', '.join(STATUS)}")
    tables = _require(conn)
    has_matches = "listen_matches" in tables
    frm = FROM if has_matches else "FROM listens l"
    track = TRACK if has_matches else "l.rating_key"
    where, args = [STATUS[status]], []
    if source:
        where.append("l.source = ?")
        args.append(source)
    tz = listen_tz(conn, default_tz)
    if year is not None:
        where.append("l.started_at >= ? AND l.started_at < ?")
        args += year_range(year, tz)
    w = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM listens l WHERE {w}", args).fetchone()[0]
    limit = max(1, min(limit, 500))
    rows = conn.execute(
        f"SELECT l.id, l.source, l.started_at, l.ms_played, l.artist, l.title, l.album, l.dup_of, {track} rating_key "
        f"{frm} WHERE {w} ORDER BY l.started_at DESC, l.id DESC LIMIT ? OFFSET ?", [*args, limit, max(0, offset)]
    ).fetchall()
    return {
        "status": status, "source": source, "year": year, "timezone": str(tz), "total": total,
        "limit": limit, "offset": max(0, offset), "rule": f"listens WHERE {w.replace('l.', '')}", "params": args,
        "rows": [{**dict(r), "started_at": legacy._iso(r["started_at"])} for r in rows],
    }
