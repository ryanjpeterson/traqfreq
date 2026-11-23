"""HISTORY by period (T8), read-only: Years, Wrapped, On this day, Top, and the P1 gate's comparison.

Every number here is worked out the way jimbo-dj works it out (history.py at 1d8a7cb: ``_overview``,
``_wrapped``, ``_top``), from jimbo-dj's plays (``counted = 1``) under one name per artist, song and album
(``Names``), with the vendored ``_minutes`` and period ranges (``_range``, ``top_range``). The plays are read
with jimbo-dj's own query (``plays``), so they come in the same order and ties, sums and rounding come out
the same.

Not here, because they come from the library and its tags (P2, P4): Wrapped's styles (``families``), decades
and sound, and Top's genres. The comparison says so instead of comparing them.

``compare`` is the P1 gate: every number jimbo-dj stored for HISTORY (its ``stats`` rows ``history.overview``
and every ``history.wrapped``) next to traqfreq's for the same period, with ``matches``. A stored row older
than jimbo-dj's data (its stamp isn't the current one) can differ; that is said per row (``fresh``).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from typing import Callable

from . import legacy
from .vendor import jimbodj_history as jd
from .vendor.jimbodj_history import SOURCES, Names, norm_artist, norm_title

PERIOD_VERSION = 1  # bump when what wrapped / top / daily build changes shape (store.py rebuilds them)
NOT_IN_P1 = {"families": "styles of the plays' library tracks (TAGS, P4)",
             "decades": "release decades of the plays' library tracks (LIBRARY, P2)",
             "sound": "the analysis of the plays' library tracks (LIBRARY, P2)",
             "genres": "library genre tags (TAGS, P4)"}
TOP_KINDS = ("artists", "songs", "albums")  # jimbo-dj's Top also has genres: TAGS (P4)
TOP_SORTS = ("plays", "minutes")
WRAPPED_VERSION = 2  # jimbo-dj's history.wrapped builder version (statcache.py); a row of another version is older
OVERVIEW_VERSION = 2  # jimbo-dj's history.overview builder version
WRAPPED = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")

# Names takes a second or so on a large history; one copy per jimbo-dj data version is kept in memory.
_names: dict[str, Names] = {}
_names_lock = threading.Lock()


def names(conn: sqlite3.Connection, key: str) -> Names:
    """jimbo-dj's Names for its data as of ``key`` (history.cache_key), built once per key."""
    with _names_lock:
        nm = _names.get(key)
        if nm is None:
            _names.clear()
            nm = _names[key] = Names(conn)
        return nm


# jimbo-dj's _plays query, as is: the same rows in the same order.
_PLAYS_SQL = (
    "SELECT l.source, l.started_at, l.ms_played, l.uri, l.artist, l.title, l.album, l.match_key, COALESCE(l.rating_key, m.rating_key) rk, "
    "t.duration_ms, t.album_key, t.artist_key, t.title lib_title, t.artist lib_artist, t.album lib_album "
    "FROM listens l LEFT JOIN listen_matches m ON m.match_key = l.match_key "
    "LEFT JOIN tracks t ON t.rating_key = COALESCE(l.rating_key, m.rating_key) "
)


def plays(conn: sqlite3.Connection, nm: Names, a: float | None = None, b: float | None = None,
          source: str | None = None) -> list[dict]:
    """Plays in [a, b) (all without a), optionally one source's, named by Names (jimbo-dj's ``_plays``)."""
    where, args = ["l.counted=1"], []
    if a is not None:
        where.append("l.started_at >= ? AND l.started_at < ?")
        args += [int(a), int(b)]
    if source:
        where.append("l.source = ?")
        args.append(source)
    out = []
    for r in conn.execute(_PLAYS_SQL + f"WHERE {' AND '.join(where)}", args).fetchall():
        d = dict(r)
        d["artist"] = nm.artist(r["artist"])
        d["title"] = nm.title(r["match_key"], r["title"])
        d["album"] = nm.album(r["artist"], r["album"]) or (nm.album(r["lib_artist"], r["lib_album"]) if r["lib_album"] else None)
        out.append(d)
    return out


def first_seen(conn: sqlite3.Connection, nm: Names) -> dict[str, float]:
    """When each artist (by its Names name) was first played (jimbo-dj's ``first_seen``). Kept with ``nm``."""
    cached = getattr(nm, "_traqfreq_first_seen", None)
    if cached is not None:
        return cached
    out: dict[str, float] = {}
    for a, t in conn.execute("SELECT artist, MIN(started_at) FROM listens WHERE counted=1 GROUP BY artist"):
        k = nm.artist(a)
        out[k] = min(out.get(k, t), t)
    nm._traqfreq_first_seen = out  # one Names per data version (names()), so this is too
    return out


def parse_wrapped(period: str) -> tuple[int, int | None, int | None]:
    """"2025", "2025-06" or "2025-06-14" → (year, month, day)."""
    m = WRAPPED.match(period or "")
    if not m:
        raise ValueError("period is YYYY, YYYY-MM or YYYY-MM-DD")
    y, mo, d = int(m[1]), int(m[2]) if m[2] else None, int(m[3]) if m[3] else None
    try:
        dt.date(y, mo or 1, d or 1)
    except ValueError:
        raise ValueError(f"no such date: {period}")
    return y, mo, d


def wrapped_key(year: int, month: int | None = None, day: int | None = None) -> str:
    """jimbo-dj's statcache.wrapped_key: the params of a stored Wrapped row."""
    return f"{year}" + (f"-{month:02d}" if month else "") + (f"-{day:02d}" if month and day else "")


# --- Years, On this day and the overview's highlights (jimbo-dj's _overview) ---------------------------

def daily(conn: sqlite3.Connection, tz, nm: Names, today: dt.date | None = None) -> dict:
    """jimbo-dj's history overview, number for number (``_overview``): every year's plays and hours, the
    sources, all-time top artists, on this day in earlier years, and Home's highlights. Depends on today."""
    order = {s: i for i, s in enumerate(jd.PRIORITY)}
    sources = sorted(({"source": s, "name": SOURCES.get(s, s), "listens": n, "plays": p or 0, "first": a, "last": b,
                       "repeats": rep or 0,
                       "duplicates": {d: c for d, c in conn.execute(
                           "SELECT dup_of, COUNT(*) FROM listens WHERE source=? AND dup_of IS NOT NULL AND dup_of != source GROUP BY dup_of", (s,))}}
                      for s, n, p, a, b, rep in conn.execute(
                          "SELECT source, COUNT(*), SUM(counted), MIN(started_at), MAX(started_at), SUM(dup_of = source) "
                          "FROM listens GROUP BY source")), key=lambda x: order.get(x["source"], 99))
    imports = [dict(r) for r in conn.execute("SELECT source, at, rows, added, note FROM history_imports ORDER BY id DESC LIMIT 8")] \
        if "history_imports" in legacy.table_names(conn) else []
    if not sources:
        return {"sources": [], "imports": imports, "years": [], "plays": 0, "timezone": str(tz)}
    rows = plays(conn, nm)
    years: dict[int, dict] = defaultdict(lambda: {"plays": 0, "minutes": 0.0, "by_source": Counter()})
    artists: Counter = Counter()
    artist_keys: dict[str, int] = {}
    today = today or dt.datetime.now(tz).date()
    on_day: dict[int, Counter] = defaultdict(Counter)
    on_day_meta: dict[tuple, dict] = {}
    matched = 0
    per_day: Counter = Counter()
    week_from = today - dt.timedelta(days=6)
    week_artists, week_songs, year_artists = Counter(), Counter(), Counter()
    week_minutes = 0.0
    first = None
    for r in rows:
        when = dt.datetime.fromtimestamp(r["started_at"], tz)
        d = when.date()
        per_day[d] += 1
        if first is None or r["started_at"] < first["started_at"]:
            first = r
        if d >= week_from:
            week_artists[r["artist"]] += 1
            week_songs[(r["artist"], r["title"])] += 1
            week_minutes += jd._minutes(r)
        if d.year == today.year:
            year_artists[r["artist"]] += 1
        y = years[when.year]
        y["plays"] += 1
        y["minutes"] += jd._minutes(r)
        y["by_source"][r["source"]] += 1
        artists[r["artist"]] += 1
        if r["artist_key"]:
            artist_keys.setdefault(r["artist"], r["artist_key"])
        if r["rk"]:
            matched += 1
        if when.month == today.month and when.day == today.day and when.year < today.year:
            k = (r["artist"], r["title"])
            on_day[when.year][k] += 1
            on_day_meta[k] = {"rating_key": r["rk"], "album_key": r["album_key"]}
    songs = conn.execute("SELECT COUNT(*), COUNT(rating_key) FROM listen_matches").fetchone()
    best = run = 0
    best_end = prev = None
    for d in sorted(per_day):
        run = run + 1 if prev and d - prev == dt.timedelta(days=1) else 1
        if run > best:
            best, best_end = run, d
        prev = d
    current = 0
    d = today if per_day.get(today) else today - dt.timedelta(days=1)
    while per_day.get(d):
        current += 1
        d -= dt.timedelta(days=1)
    busiest = max(per_day.items(), key=lambda kv: kv[1])
    peak = max(years.items(), key=lambda kv: kv[1]["plays"])
    days_played = len(per_day)
    span_days = (today - min(per_day)).days + 1
    highlights = {
        "last_30": [{"date": (today - dt.timedelta(days=i)).isoformat(), "plays": per_day.get(today - dt.timedelta(days=i), 0)}
                    for i in range(29, -1, -1)],
        "last_year": [{"date": d.isoformat(), "plays": per_day.get(d, 0)}
                      for d in (today - dt.timedelta(days=today.weekday() + 52 * 7 - i) for i in range(53 * 7))
                      if d <= today],
        "week": {"plays": sum(week_artists.values()), "hours": round(week_minutes / 60, 1),
                 "top_artists": [{"name": a, "plays": n} for a, n in week_artists.most_common(5)],
                 "top_songs": [{"artist": a, "title": t, "plays": n} for (a, t), n in week_songs.most_common(5)]},
        "this_year": {"year": today.year, "plays": years[today.year]["plays"] if today.year in years else 0,
                      "top_artist": year_artists.most_common(1)[0][0] if year_artists else None},
        "streak": {"current": current, "best": best, "best_ended": best_end.isoformat() if best_end else None},
        "busiest_day": {"date": busiest[0].isoformat(), "plays": busiest[1]},
        "peak_year": {"year": peak[0], "plays": peak[1]["plays"], "hours": round(peak[1]["minutes"] / 60)},
        "first_play": {"date": dt.datetime.fromtimestamp(first["started_at"], tz).date().isoformat(), "artist": first["artist"],
                       "title": first["title"]} if first else None,
        "artists_heard": len(artists),
        "days_played_pct": round(100 * days_played / max(span_days, 1)),
        "average_day": round(len(rows) / max(days_played, 1)),
    }
    return {
        "highlights": highlights,
        "sources": sources, "imports": imports, "plays": len(rows),
        "hours": round(sum(y["minutes"] for y in years.values()) / 60),
        "matched_pct": round(100 * matched / max(len(rows), 1), 1),
        "songs": songs[0], "songs_matched": songs[1],
        "years": [{"year": y, "plays": v["plays"], "hours": round(v["minutes"] / 60), "minutes": round(v["minutes"]),
                   "by_source": dict(v["by_source"])}
                  for y, v in sorted(years.items())],
        "top_artists": [{"name": a, "plays": n, "artist_key": artist_keys.get(a)} for a, n in artists.most_common(15)],
        "on_this_day": [{"year": y, "plays": sum(c.values()),
                         "top": [{"artist": a, "title": t, "plays": n, **on_day_meta[(a, t)]} for (a, t), n in c.most_common(3)]}
                        for y, c in sorted(on_day.items(), reverse=True)],
        "today": today.isoformat(),
        "timezone": str(tz),
    }


# --- Wrapped (jimbo-dj's _wrapped, without the library's styles, decades and sound) --------------------

def wrapped(conn: sqlite3.Connection, tz, nm: Names, year: int, month: int | None = None, day: int | None = None) -> dict:
    """A year, a month or a day of listening, number for number as jimbo-dj's Wrapped: totals, top artists /
    songs / albums, when you listened, what you discovered; a day also has every play, in order."""
    day = day if month else None
    with jd.in_zone(tz):
        a, b = jd._range(conn, year, month, day)
    rows = plays(conn, nm, a, b)
    base = {"period": wrapped_key(year, month, day), "start": int(a), "end": int(b), "timezone": str(tz),
            "not_in_p1": {k: NOT_IN_P1[k] for k in ("families", "decades", "sound")}}
    if not rows:
        return {"year": year, "month": month, "day": day, "plays": 0, **base}
    seen = first_seen(conn, nm)
    artists, songs, albums, sources = Counter(), Counter(), Counter(), Counter()
    minutes = 0.0
    by_hour, by_weekday, by_day = Counter(), Counter(), Counter()
    by_part: Counter = Counter()
    song_meta, album_meta, artist_keys = {}, {}, {}
    played_keys: Counter = Counter()
    keys = {"artists": {}, "songs": {}, "albums": {}}  # traqfreq: the row filter behind each top entry
    for r in rows:
        when = dt.datetime.fromtimestamp(r["started_at"], tz)
        m = jd._minutes(r)
        minutes += m
        sources[r["source"]] += 1
        artists[r["artist"]] += 1
        keys["artists"].setdefault(r["artist"], norm_artist(r["artist"]))
        if r["artist_key"]:
            artist_keys.setdefault(r["artist"], r["artist_key"])
        sk = (r["artist"], r["title"])
        songs[sk] += 1
        keys["songs"].setdefault(sk, r["match_key"])
        song_meta.setdefault(sk, {"rating_key": r["rk"], "album_key": r["album_key"]})
        if r["album"]:
            ak = (r["artist"], r["album"])
            albums[ak] += 1
            keys["albums"].setdefault(ak, f"{norm_artist(r['artist'])}|{norm_title(r['album'])}")
            if r["album_key"]:
                album_meta.setdefault(ak, r["album_key"])
        by_hour[when.hour] += 1
        by_weekday[when.strftime("%a")] += 1
        by_day[when.date().isoformat()] += 1
        by_part[when.hour if day else when.day if month else when.month] += 1
        if r["rk"]:
            played_keys[r["rk"]] += 1
    new_artists = [x for x in artists if a <= (seen.get(x) or 0) < b]
    busiest = max(by_day.items(), key=lambda kv: kv[1])
    in_lib = sum(played_keys.values())
    if day:
        parts, label = range(24), (lambda p: f"{p:02d}")
    elif month:
        parts, label = range(1, (dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)).day + 1), (lambda p: str(p))
    else:
        parts, label = range(1, 13), (lambda p: dt.date(2000, p, 1).strftime("%b"))
    every = None
    if day:
        every = [{"time": dt.datetime.fromtimestamp(r["started_at"], tz).strftime("%H:%M"), "artist": r["artist"], "title": r["title"],
                  "album": r["album"], "source": SOURCES.get(r["source"], r["source"]), "rating_key": r["rk"], "album_key": r["album_key"],
                  "minutes": round(jd._minutes(r), 1)}
                 for r in sorted(rows, key=lambda r: r["started_at"])]
    return {
        "year": year, "month": month, "day": day, "plays": len(rows), "every_play": every, "hours": round(minutes / 60, 1),
        "artists": len(artists), "songs": len(songs), "new_artists": len(new_artists),
        "new_artist_names": sorted(new_artists, key=lambda x: -artists[x])[:12],
        "in_library_pct": round(100 * in_lib / len(rows), 1),
        "sources": [{"source": s, "name": SOURCES.get(s, s), "plays": n} for s, n in sources.most_common()],
        "busiest_day": {"date": busiest[0], "plays": busiest[1]},
        "top_artists": [{"name": x, "plays": n, "artist_key": artist_keys.get(x), "key": keys["artists"][x]}
                        for x, n in artists.most_common(15)],
        "top_songs": [{"artist": ar, "title": t, "plays": n, **song_meta[(ar, t)], "key": keys["songs"][(ar, t)]}
                      for (ar, t), n in songs.most_common(25)],
        "top_albums": [{"artist": ar, "album": al, "plays": n, "album_key": album_meta.get((ar, al)), "key": keys["albums"][(ar, al)]}
                       for (ar, al), n in albums.most_common(12)],
        "by_part": [{"label": label(p), "value": by_part.get(p, 0), "part": p} for p in parts],
        "hours_of_day": [{"label": f"{h:02d}", "value": by_hour.get(h, 0)} for h in range(24)],
        "weekdays": [{"label": d, "value": by_weekday.get(d, 0)} for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")],
        "by_date": [{"date": d.isoformat(), "plays": by_day.get(d.isoformat(), 0)}
                    for d in (dt.datetime.fromtimestamp(a, tz).date() + dt.timedelta(days=i)
                              for i in range(round((b - a) / jd.DAY)))] if not day else None,
        "minutes": round(minutes),
        **base,
    }


# --- Top (jimbo-dj's _top, without genres) ---------------------------------------------------------------

def top_range(conn: sqlite3.Connection, tz, period: str) -> tuple[float | None, float | None]:
    with jd.in_zone(tz):
        return jd.top_range(conn, period)


def top(conn: sqlite3.Connection, tz, nm: Names, period: str = "all", source: str | None = None) -> dict:
    """Every artist, song and album played in a period (all, 30d, 12m, YYYY, YYYY-MM), optionally from one
    source, with plays and minutes, grouped by the keys Names uses so each appears once (jimbo-dj's Top)."""
    if source and source not in SOURCES:
        raise ValueError(f"source is one of {', '.join(SOURCES)}")
    a, b = top_range(conn, tz, period)
    rows = plays(conn, nm, a, b, source)
    sources = Counter(r["source"] for r in plays(conn, nm, a, b)) if source else Counter(r["source"] for r in rows)
    groups: dict[str, dict[str, dict]] = {k: {} for k in TOP_KINDS}
    art: dict[tuple[str, str], Counter] = defaultdict(Counter)

    def add(kind: str, key: str, make: Callable[[], dict], mins: float, album_key: int | None):
        g = groups[kind].get(key)
        if g is None:
            g = groups[kind][key] = {**make(), "key": key, "plays": 0, "minutes": 0.0}
        g["plays"] += 1
        g["minutes"] += mins
        if album_key:
            art[(kind, key)][album_key] += 1

    for r in rows:
        mins = jd._minutes(r)
        ak = r["album_key"]
        na = norm_artist(r["artist"])
        add("artists", na, lambda: {"name": r["artist"], "sub": None, "in_library": False}, mins, ak)
        if r["artist_key"]:
            groups["artists"][na]["in_library"] = True
        add("songs", r["match_key"], lambda: {"name": r["title"], "sub": r["artist"], "artist": r["artist"], "in_library": False}, mins, ak)
        if r["rk"]:
            groups["songs"][r["match_key"]]["in_library"] = True
        if r["album"]:
            k = f"{na}|{norm_title(r['album'])}"
            add("albums", k, lambda: {"name": r["album"], "sub": r["artist"], "artist": r["artist"], "in_library": False}, mins, ak)
            if ak:
                groups["albums"][k]["in_library"] = True

    out: dict = {"period": period, "source": source, "plays": len(rows),
                 "start": int(a) if a is not None else None, "end": int(b) if b is not None else None,
                 "sources": [{"source": s, "name": SOURCES.get(s, s), "plays": n} for s, n in sources.most_common()],
                 "timezone": str(tz), "not_in_p1": {"genres": NOT_IN_P1["genres"]}}
    for kind, gs in groups.items():
        items = list(gs.values())
        for it in items:
            it["minutes"] = round(it["minutes"])
            c = art.get((kind, it["key"]))
            it["album_key"] = c.most_common(1)[0][0] if c else None
        by_plays = sorted(items, key=lambda x: (-x["plays"], -x["minutes"], str(x["name"] or "").lower()))
        by_minutes = sorted(items, key=lambda x: (-x["minutes"], -x["plays"], str(x["name"] or "").lower()))
        out[kind] = {"plays": by_plays, "minutes": by_minutes}
    return out


def top_page(t: dict, kind: str, sort: str = "plays", page: int = 1, per: int = 48) -> dict:
    """One page of a built Top (jimbo-dj's top_page): items with their rank in this sort."""
    if kind not in TOP_KINDS:
        raise ValueError(f"kind is one of {', '.join(TOP_KINDS)}")
    if sort not in TOP_SORTS:
        raise ValueError("sort is plays or minutes")
    per = max(12, min(int(per), 96))
    items = t[kind][sort]
    pages = max(1, math.ceil(len(items) / per))
    page = max(1, min(int(page), pages))
    start = (page - 1) * per
    return {"kind": kind, "period": t["period"], "sort": sort, "source": t["source"], "page": page, "per": per,
            "pages": pages, "total": len(items), "plays": t["plays"], "sources": t["sources"], "timezone": t["timezone"],
            "start": t["start"], "end": t["end"], "not_in_p1": t["not_in_p1"],
            "items": [{**it, "rank": start + i + 1} for i, it in enumerate(items[start:start + per])]}


# --- The P1 gate: jimbo-dj's stored numbers next to traqfreq's ------------------------------------------

# Fields traqfreq adds to its builds that jimbo-dj's rows don't have, and fields never compared.
SKIP = {"built_at"}


def _norm(v):
    """JSON round trip, so tuples and lists, int keys and str keys compare the same."""
    return json.loads(json.dumps(v, default=str))


def _strip(theirs, ours):
    """Ours cut down to the keys jimbo-dj's value has (traqfreq adds row-filter keys to list items)."""
    if isinstance(theirs, dict) and isinstance(ours, dict):
        return {k: _strip(theirs[k], ours.get(k)) for k in theirs}
    if isinstance(theirs, list) and isinstance(ours, list):
        return [_strip(t, o) for t, o in zip(theirs, ours)] + ours[len(theirs):]
    return ours


def _first_diff(a, b) -> dict | None:
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return {"index": i, "jimbodj": x, "traqfreq": y}
        return {"index": min(len(a), len(b)), "jimbodj_length": len(a), "traqfreq_length": len(b)}
    return None


def compare_value(theirs: dict, ours: dict) -> list[dict]:
    """Every field of jimbo-dj's stored value next to traqfreq's (highlights field by field)."""
    fields = []
    for k, v in theirs.items():
        if k in SKIP:
            continue
        if k in NOT_IN_P1:
            fields.append({"field": k, "matches": None, "skipped": NOT_IN_P1[k]})
            continue
        if k == "highlights" and isinstance(v, dict):
            for hk, hv in v.items():
                fields.append(_field(f"highlights.{hk}", hv, (ours.get("highlights") or {}).get(hk)))
            continue
        fields.append(_field(k, v, ours.get(k)))
    return fields


def _field(name: str, theirs, ours) -> dict:
    t, o = _norm(theirs), _norm(_strip(theirs, ours))
    f = {"field": name, "matches": t == o}
    if isinstance(t, (list, dict)):
        if not f["matches"]:
            if isinstance(t, list) and isinstance(o, list):
                f["first_diff"] = _first_diff(t, o)
            elif isinstance(t, dict) and isinstance(o, dict):
                f["first_diff"] = {k: {"jimbodj": t[k], "traqfreq": o.get(k)} for k in t if t[k] != o.get(k)}
            else:
                f["first_diff"] = {"jimbodj": t, "traqfreq": o}
        f["size"] = len(t)
    else:
        f["jimbodj"], f["traqfreq"] = t, o
    return f


def jimbodj_stamp(conn: sqlite3.Connection) -> str:
    """The stamp a fresh history row of jimbo-dj's has (statcache._history_stamp, json.dumps(default=str))."""
    meta = {r["key"]: r["value"] for r in conn.execute(
        "SELECT key, value FROM meta WHERE key IN ('history_version', 'last_sync', 'history_tz')")} \
        if "meta" in legacy.table_names(conn) else {}
    return json.dumps([meta.get("history_version"), meta.get("last_sync"), meta.get("history_tz")], default=str)


def stored_rows(conn: sqlite3.Connection) -> list[dict]:
    """jimbo-dj's stored HISTORY rows: history.overview, then every history.wrapped by period."""
    if "stats" not in legacy.table_names(conn):
        return []
    rows = conn.execute("SELECT name, params, value, version, stamp, built_at FROM stats "
                        "WHERE name IN ('history.overview', 'history.wrapped')").fetchall()
    out = [dict(r) for r in rows]
    out.sort(key=lambda r: (r["name"] != "history.overview", r["params"]))
    return out


def gate_key(conn: sqlite3.Connection) -> str:
    """Changes whenever jimbo-dj rebuilds or adds a stored history row."""
    if "stats" not in legacy.table_names(conn):
        return "none"
    n, b = conn.execute("SELECT COUNT(*), MAX(built_at) FROM stats WHERE name IN ('history.overview', 'history.wrapped')").fetchone()
    return f"{n}|{b}"


def compare(conn: sqlite3.Connection, tz, nm: Names, today_jd: str, today: dt.date | None = None,
            overview_of: Callable[[], dict] | None = None, wrapped_of: Callable[[str], dict] | None = None) -> dict:
    """The P1 gate. ``today_jd`` is the day in jimbo-dj's TZ (its daily rows' stamps end with it).
    ``overview_of`` / ``wrapped_of`` give traqfreq's builds (cached by the app; built here when not given)."""
    overview_of = overview_of or (lambda: daily(conn, tz, nm, today))
    wrapped_of = wrapped_of or (lambda p: wrapped(conn, tz, nm, *parse_wrapped(p)))
    stamp = jimbodj_stamp(conn)
    rows = []
    for s in stored_rows(conn):
        try:
            theirs = json.loads(s["value"])
        except (TypeError, ValueError):
            rows.append({"name": s["name"], "params": s["params"], "matches": False, "error": "not JSON"})
            continue
        daily_row = s["name"] == "history.overview"
        version = OVERVIEW_VERSION if daily_row else WRAPPED_VERSION
        want = f"{stamp}|{today_jd}" if daily_row else stamp
        fresh = s["stamp"] == want and s["version"] == version
        ours = overview_of() if daily_row else wrapped_of(s["params"])
        fields = compare_value(theirs, ours)
        compared = [f for f in fields if f["matches"] is not None]
        matches = all(f["matches"] for f in compared)
        rows.append({"name": s["name"], "params": s["params"], "built_at": legacy._iso(s["built_at"]),
                     "version": s["version"], "fresh": fresh, "stamp": s["stamp"],
                     "matches": matches, "fields": fields,
                     "compared": len(compared), "matching": sum(1 for f in compared if f["matches"])})
    differ = [r for r in rows if not r["matches"]]
    explained = [r for r in differ if r.get("fresh") is False]
    return {
        "rows": rows,
        "stored": len(rows),
        "fields": sum(r.get("compared", 0) for r in rows),
        "matching_fields": sum(r.get("matching", 0) for r in rows),
        "matching": len(rows) - len(differ),
        "differ": len(differ),
        "stale": sum(1 for r in rows if r.get("fresh") is False),
        "explained": len(explained),
        "passed": bool(rows) and len(differ) == len(explained),
        "stamp": stamp, "today": today_jd, "timezone": str(tz),
        "not_in_p1": {k: NOT_IN_P1[k] for k in ("families", "decades", "sound")},
        "rules": {"stored": "jimbo-dj's stats rows history.overview and every history.wrapped (statcache.py)",
                  "fresh": "the row's stamp is jimbo-dj's current one ([history_version, last_sync, history_tz], "
                           "and today for the overview) and its builder version is the current one",
                  "passed": "every stored row matches, or each one that differs is stale (older than jimbo-dj's data)"},
    }
