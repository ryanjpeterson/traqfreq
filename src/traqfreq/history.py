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

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import counted, legacy
from .vendor.jimbodj_history import PRIORITY, SOURCES, Names, norm_artist, norm_title

# Bump when the shape of what ``summary`` builds changes, so cached summaries are rebuilt (store.py).
SUMMARY_VERSION = 1
TOP_ARTISTS = 15  # as many as jimbo-dj's overview keeps

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


def cache_key(conn: sqlite3.Connection, default_tz: str | None = None) -> str:
    """What a summary is built from: jimbo-dj's history, match and library versions and the time zone. Any
    change (an import, a rematch, a Plex sync, a new time zone) gives a new key, so the summary is rebuilt."""
    meta = {}
    if "meta" in legacy.table_names(conn):
        meta = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM meta WHERE key IN ('history_version', 'match_version', 'last_sync')")}
    parts = [f"v{SUMMARY_VERSION}", *(meta.get(k) or "-" for k in ("history_version", "match_version", "last_sync")),
             str(listen_tz(conn, default_tz))]
    return "|".join(parts)


def overview(conn: sqlite3.Connection, default_tz: str | None = None) -> dict:
    """Plays and every listen that isn't one, by source and by year, with the rule each number uses (uncached)."""
    return summary(conn, default_tz)["overview"]


def summary(conn: sqlite3.Connection, default_tz: str | None = None) -> dict:
    """Everything the HISTORY overview shows, in one pass over the plays: ``overview`` (counts, sources, years,
    top artists) and ``days`` (plays per day in the listening time zone, for the heatmap). Built once per
    ``cache_key`` and kept in traqfreq's own database (store.py)."""
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
    per_day: Counter = Counter()
    artists: Counter = Counter()
    # One name per artist however each source spelled it (jimbo-dj's Names, vendored), counted the way
    # jimbo-dj's overview counts its top artists. Names needs the library's tracks for its spellings.
    name_of = Names(conn).artist if "tracks" in tables else (lambda a: a)
    matched = 0
    for started, source, artist, rk in conn.execute(
            f"SELECT l.started_at, l.source, l.artist, {track} rk {frm} WHERE {STATUS['play']}"):
        when = datetime.fromtimestamp(started, tz)
        y = years[when.year]
        y["plays"] += 1
        y["by_source"][source] += 1
        per_day[when.date().isoformat()] += 1
        artists[name_of(artist)] += 1
        matched += rk is not None
    songs = matched_songs = None
    if has_matches:
        songs, matched_songs = conn.execute("SELECT COUNT(*), COUNT(rating_key) FROM listen_matches").fetchone()

    top = [{"name": a, "key": norm_artist(a), "plays": n} for a, n in artists.most_common(TOP_ARTISTS)]
    matched_pct = round(100 * matched / max(totals["play"], 1), 1)

    stored = legacy.stored_stat(conn, "history.overview", tables)
    jd = None
    if stored and isinstance(stored[0].get("plays"), int):
        theirs = stored[0]
        jd = {"plays": theirs["plays"], "built_at": legacy._iso(stored[1]), "source": "stats.history.overview",
              "matches": theirs["plays"] == totals["play"]}
        if isinstance(theirs.get("matched_pct"), (int, float)):
            jd["matched_pct"] = theirs["matched_pct"]
            jd["matched_pct_matches"] = theirs["matched_pct"] == matched_pct
        if isinstance(theirs.get("top_artists"), list):
            jd["top_artists"] = [{"name": a.get("name"), "plays": a.get("plays")} for a in theirs["top_artists"]]
            jd["top_artists_match"] = jd["top_artists"] == [{"name": a["name"], "plays": a["plays"]} for a in top]
    over = {
        "plays": totals["play"],
        "listens": totals["listens"],
        "not_plays": {k: totals[k] for k in STATUS if k != "play"},
        "adds_up": sum(totals[k] for k in STATUS) == totals["listens"],
        "matched": {"plays": matched, "pct": matched_pct},
        "songs": {"heard": songs, "matched": matched_songs},
        "sources": sources,
        "years": [{"year": y, "plays": v["plays"], "by_source": dict(v["by_source"])} for y, v in sorted(years.items())],
        "top_artists": top,
        "artists_heard": len(artists),
        "timezone": str(tz),
        "rules": {"listens": "SELECT COUNT(*) FROM listens", **{k: f"listens WHERE {v.replace('l.', '')}" for k, v in STATUS.items()},
                  "matched": f"plays WHERE {track.replace('l.', 'listens.').replace('m.', 'listen_matches.')} IS NOT NULL",
                  "top_artists": "plays grouped by artist under one name per artist (jimbo-dj's Names)",
                  "days": "plays grouped by day in the listening time zone"},
        "jimbodj": jd,
    }
    return {"overview": over, "days": dict(sorted(per_day.items()))}


def _levels(counts: list[int]) -> tuple[list[int], list[dict]]:
    """Five heatmap levels: 0 = no plays; 1-4 = the quarters of the days with plays, by plays that day.
    Returns the three cut points and each level's range of plays a day (min > max: no day has that level)."""
    lit = sorted(n for n in counts if n > 0)
    if not lit:
        cuts = [0, 0, 0]
    else:
        cuts = [lit[min(len(lit) - 1, max(0, -(-len(lit) * q // 4) - 1))] for q in (1, 2, 3)]  # nearest rank
    bounds = [(0, 0), (1, cuts[0]), (cuts[0] + 1, cuts[1]), (cuts[1] + 1, cuts[2]), (cuts[2] + 1, lit[-1] if lit else 0)]
    return cuts, [{"level": i, "min": a, "max": b} for i, (a, b) in enumerate(bounds)]


def level_of(n: int, cuts: list[int]) -> int:
    return 0 if n <= 0 else 1 + sum(n > c for c in cuts)


def heatmap(days: dict[str, int], tz, year: int | None = None, today: date | None = None) -> dict:
    """A year of days with each day's plays and level. Without ``year``: 53 whole weeks, Monday first, ending
    this week (jimbo-dj's Home heatmap). With one: that calendar year, up to today."""
    today = today or datetime.now(tz).date()
    if year is None:
        first = today - timedelta(days=today.weekday() + 52 * 7)
        last = today
    else:
        first, last = date(year, 1, 1), min(date(year, 12, 31), today)
    span = [first + timedelta(days=i) for i in range(max(0, (last - first).days + 1))]
    counts = [days.get(d.isoformat(), 0) for d in span]
    cuts, levels = _levels(counts)
    months: dict[str, dict] = {}
    for d, n in zip(span, counts):
        m = months.setdefault(d.strftime("%Y-%m"), {"month": d.strftime("%Y-%m"), "plays": 0, "days": 0, "days_played": 0,
                                                     "busiest": None})
        m["plays"] += n
        m["days"] += 1
        if n:
            m["days_played"] += 1
            if m["busiest"] is None or n > m["busiest"]["plays"]:
                m["busiest"] = {"date": d.isoformat(), "plays": n}
    lit = [(d, n) for d, n in zip(span, counts) if n]
    busiest = max(lit, key=lambda x: x[1]) if lit else None
    years = sorted({int(k[:4]) for k in days})
    return {
        "year": year, "first": first.isoformat() if span else None, "last": last.isoformat() if span else None,
        "timezone": str(tz), "plays": sum(counts), "days": len(span), "days_played": len(lit),
        "busiest": {"date": busiest[0].isoformat(), "plays": busiest[1]} if busiest else None,
        "levels": levels, "cuts": cuts,
        "cells": [{"date": d.isoformat(), "plays": n, "level": level_of(n, cuts)} for d, n in zip(span, counts)],
        "months": list(months.values()),
        "years": years,
        "rules": {"plays": "plays (listens WHERE counted = 1) grouped by day in the listening time zone",
                  "levels": "level 0: no plays; levels 1-4: the quarters of this view's days with plays, by plays that day"},
    }


def year_range(year: int, tz) -> tuple[int, int]:
    a = datetime(year, 1, 1, tzinfo=tz)
    b = datetime(year + 1, 1, 1, tzinfo=tz)
    return int(a.timestamp()), int(b.timestamp())


PERIOD = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


def period_range(period: str, tz) -> tuple[int, int]:
    """[start, end) in UTC epoch seconds of a year (YYYY), month (YYYY-MM) or day (YYYY-MM-DD) in ``tz``."""
    m = PERIOD.match(period or "")
    if not m:
        raise ValueError("period is YYYY, YYYY-MM or YYYY-MM-DD")
    y, mo, d = int(m[1]), int(m[2] or 1), int(m[3] or 1)
    try:
        a = date(y, mo, d)
    except ValueError:
        raise ValueError(f"no such date: {period}")
    if m[3]:
        b = a + timedelta(days=1)
    elif m[2]:
        b = date(y + (mo == 12), mo % 12 + 1, 1)
    else:
        b = date(y + 1, 1, 1)
    start = datetime(a.year, a.month, a.day, tzinfo=tz)
    end = datetime(b.year, b.month, b.day, tzinfo=tz)
    return int(start.timestamp()), int(end.timestamp())


def listens(conn: sqlite3.Connection, status: str = "play", source: str | None = None, year: int | None = None,
            limit: int = 50, offset: int = 0, default_tz: str | None = None, period: str | None = None,
            artist: str | None = None, matched: bool | None = None, of: str | None = None, gap: str | None = None,
            start: int | None = None, end: int | None = None, song: str | None = None, album: str | None = None,
            hour: int | None = None, weekday: int | None = None) -> dict:
    """The rows behind a number: listens with one status, optionally one source, one year or period (YYYY,
    YYYY-MM, YYYY-MM-DD), one artist (its normalised key, as in ``top_artists``), matched or not, the source a
    repeat or duplicate is of (``of``), its gap to that listen (``gap`` "a-b" seconds or "none", counted.py) and
    a span of UTC epoch seconds (``start``/``end``, inclusive), one song (its match_key), one album (T8: the key
    Top and Wrapped use, norm_artist|norm_title of the album, or of its library track's album when the listen
    names none), an hour of the day (0-23) or a weekday (0 = Monday) in the listening zone, newest first. Repeats and duplicates carry
    ``of``: the listen they repeat or duplicate, the gap and the window (or None when none is in it)."""
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
    if period:
        where.append("l.started_at >= ? AND l.started_at < ?")
        args += period_range(period, tz)
    if artist:
        # jimbo-dj's norm_artist (vendored) as an SQL function on this read-only connection.
        conn.create_function("norm_artist", 1, norm_artist, deterministic=True)
        where.append("norm_artist(l.artist) = ?")
        args.append(artist)
    if matched is not None:
        where.append(f"{track} IS {'NOT ' if matched else ''}NULL")
    if song:
        where.append("l.match_key = ?")
        args.append(song)
    if album:
        if not has_matches or "tracks" not in tables:
            raise ValueError("album needs jimbo-dj's listen_matches and tracks")
        conn.create_function("norm_artist", 1, norm_artist, deterministic=True)
        conn.create_function("norm_title", 1, norm_title, deterministic=True)
        frm = f"{frm} LEFT JOIN tracks t ON t.rating_key = {track}"
        where.append("(norm_artist(l.artist) || '|' || norm_title(COALESCE(NULLIF(l.album, ''), t.album))) = ?")
        args.append(album)
    if hour is not None or weekday is not None:
        if hour is not None and not 0 <= hour <= 23:
            raise ValueError("hour is 0 to 23")
        if weekday is not None and not 0 <= weekday <= 6:
            raise ValueError("weekday is 0 (Monday) to 6 (Sunday)")
        conn.create_function("local_hour", 1, lambda s: datetime.fromtimestamp(s, tz).hour, deterministic=True)
        conn.create_function("local_weekday", 1, lambda s: datetime.fromtimestamp(s, tz).weekday(), deterministic=True)
        if hour is not None:
            where.append("local_hour(l.started_at) = ?")
            args.append(hour)
        if weekday is not None:
            where.append("local_weekday(l.started_at) = ?")
            args.append(weekday)
    if of:
        where.append("l.dup_of = ?")
        args.append(of)
    if gap:
        if status not in ("repeat", "duplicate"):
            raise ValueError("gap needs status repeat or duplicate")
        where.append(counted.gap_where(gap))
    if start is not None:
        where.append("l.started_at >= ?")
        args.append(start)
    if end is not None:
        where.append("l.started_at <= ?")
        args.append(end)
    w = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) {frm} WHERE {w}", args).fetchone()[0]
    limit = max(1, min(limit, 500))
    rows = conn.execute(
        f"SELECT l.id, l.source, l.started_at, l.ms_played, l.artist, l.title, l.album, l.dup_of, {track} rating_key "
        f"{frm} WHERE {w} ORDER BY l.started_at DESC, l.id DESC LIMIT ? OFFSET ?", [*args, limit, max(0, offset)]
    ).fetchall()
    ofs = counted.of_rows(conn, [r["id"] for r in rows]) if status in ("repeat", "duplicate") else {}
    rule = w if not gap else w.replace(counted.GAP, "gap")  # the gap's subquery is in rules.gap
    return {
        "status": status, "source": source, "year": year, "period": period, "artist": artist, "matched": matched,
        "of": of, "gap": gap, "start": start, "end": end, "song": song, "album": album, "hour": hour, "weekday": weekday,
        "timezone": str(tz), "total": total,
        "limit": limit, "offset": max(0, offset), "rule": f"listens WHERE {rule.replace('l.', '')}", "params": args,
        "rows": [{**dict(r), "started_at": legacy._iso(r["started_at"]),
                  **({"of": ofs.get(r["id"])} if status in ("repeat", "duplicate") else {})} for r in rows],
    }
