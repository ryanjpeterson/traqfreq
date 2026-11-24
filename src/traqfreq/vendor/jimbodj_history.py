"""Pure functions vendored from jimbo-dj (ryanjpeterson/jimbo-dj, private), src/jimbodj/history.py at 1d8a7cb.

Copied as is (constants, band_of, norm_artist, norm_title, match_key, Names, window_sql; T8: DAY, _range,
_minutes, TOP_PERIODS, top_range; T21: _genre_tags, with ``log``), never edited here: traqfreq must count and match listens exactly the way jimbo-dj does
until HISTORY's cut-over (P6). To update: copy the same names again from jimbo-dj, bump VENDORED_FROM,
and run tests/test_vendor.py (it checks these against the match keys jimbo-dj stored in the fixture).
Why vendored, not a git dependency: jimbo-dj's repo is private (HANDOFF, open question 3).
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import functools
import json
import logging
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/history.py"

log = logging.getLogger(__name__)

MIN_PLAY_MS = 30_000
# How far apart a listen and a Last.fm scrobble of the same song can be and still be one play. Spotify's
# start times are exact; Plex records a play around when it starts, give or take a track's length.
DEDUPE_SECONDS = {"lastfm": 300, "plex": 900, "spotify": 300, "applemusic": 300}
PRIORITY = ("lastfm", "plex", "spotify", "applemusic")  # who wins when two sources have the same play
REPEAT_SECONDS = 30  # one source logging the same song twice this close together is one play

SOURCES = {"lastfm": "Last.fm", "plex": "Plex", "spotify": "Spotify", "applemusic": "Apple Music"}

# Times of day, in TZ: (first hour, last hour + 1). Night wraps past midnight.
BANDS = {"morning": (5, 12), "afternoon": (12, 17), "evening": (17, 22), "night": (22, 5)}


def band_of(hour: int) -> str:
    for name, (a, b) in BANDS.items():
        if (a <= hour < b) if a < b else (hour >= a or hour < b):
            return name
    return "night"


# Latin letters NFKD can't take apart, written the way an ASCII spelling of the name would be.
_PLAIN = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "þ": "th", "ð": "d", "ı": "i"})


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().translate(_PLAIN)


def _squash(s: str, raw: str | None) -> str:
    """Letters and digits in any script (so 細野晴臣 and ТПСБ keep a key of their own). A name of only
    punctuation ("!!!", "(sic)", "~") keeps its folded self without spaces instead of becoming empty."""
    out = re.sub(r"[\W_]+", "", s)
    return out or re.sub(r"[\s|]+", "", _fold(raw or ""))  # never "|": it splits a match key


@functools.lru_cache(maxsize=262_144)  # pure, and called for every play by every summary
def norm_artist(s: str | None) -> str:
    raw = s
    s = _fold(s or "").replace("&", " and ")
    s = re.sub(r"^the\s+", "", s.strip())
    s = re.sub(r"\s+(feat\.?|ft\.?|featuring)\s.*$", "", s)
    return _squash(s, raw)


@functools.lru_cache(maxsize=262_144)
def norm_title(s: str | None) -> str:
    raw = s
    s = _fold(s or "")
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)  # (Remastered 2011), [Live], (feat. X)
    s = re.sub(r"\s+-\s+.*(remaster|live|mono|stereo|demo|edit|version|mix|single|bonus|acoustic|session).*$", "", s)
    s = re.sub(r"\s+(feat\.?|ft\.?)\s.*$", "", s)
    return _squash(s, raw)


def match_key(artist: str | None, title: str | None) -> str:
    return f"{norm_artist(artist)}|{norm_title(title)}"


def window_sql(source: str) -> str:
    """How far apart (s) a listen from `source` and the same play from another source can be. Apple Music's
    day-by-hour summary (uri daily:…) only knows the hour."""
    if source == "applemusic":
        return f"(CASE WHEN listens.uri LIKE 'daily:%' THEN 3600 ELSE {DEDUPE_SECONDS['applemusic']} END)"
    return str(DEDUPE_SECONDS.get(source, 300))


class Names:
    """One name for everything heard under one normalised key, whichever source spelled it how: an artist
    (norm_artist) is the library's spelling when it's in Plex, otherwise the most played one; a song
    (match_key) is the library title of its default copy, otherwise the most played; an album (norm artist
    + norm title) the library's, otherwise the most played. So "Death from Above 1979" (Apple Music, Last.fm)
    and "Death From Above 1979" (Spotify) are one artist everywhere history is counted."""

    def __init__(self, con: sqlite3.Connection):
        lib: dict[str, Counter] = defaultdict(Counter)
        lib_albums: dict[tuple, str] = {}
        for a, al, n in con.execute("SELECT artist, album, COUNT(*) FROM tracks WHERE removed_at IS NULL GROUP BY artist, album"):
            if a:
                lib[norm_artist(a)][a] += n
                if al:
                    lib_albums.setdefault((norm_artist(a), norm_title(al)), al)
        for ta, n in con.execute("SELECT track_artist, COUNT(*) FROM tracks WHERE removed_at IS NULL AND track_artist IS NOT NULL "
                                 "AND track_artist != artist GROUP BY track_artist"):
            k = norm_artist(ta)
            if k not in lib and not re.search(r"(?i)\s(feat\.?|ft\.?|featuring)\s", ta):
                lib[k][ta] += n
        heard: dict[str, Counter] = defaultdict(Counter)
        albums: dict[tuple, Counter] = defaultdict(Counter)
        for a, al, n in con.execute("SELECT artist, album, COUNT(*) FROM listens WHERE counted=1 GROUP BY artist, album"):
            k = norm_artist(a)
            heard[k][a] += n
            if al:
                albums[(k, norm_title(al))][al] += n
        self.artists = {k: lib[k].most_common(1)[0][0] if k in lib else c.most_common(1)[0][0] for k, c in heard.items()}
        self.albums = {k: lib_albums.get(k) or c.most_common(1)[0][0] for k, c in albums.items()}
        titles: dict[str, Counter] = defaultdict(Counter)
        lib_titles: dict[str, str] = {}
        for mk, t, n, lt in con.execute(
                "SELECT l.match_key, l.title, COUNT(*), t.title FROM listens l LEFT JOIN listen_matches m ON m.match_key = l.match_key "
                "LEFT JOIN tracks t ON t.rating_key = m.rating_key WHERE l.counted=1 GROUP BY l.match_key, l.title"):
            titles[mk][t] += n
            if lt:
                lib_titles[mk] = lt
        self.titles = {k: lib_titles.get(k) or c.most_common(1)[0][0] for k, c in titles.items()}

    def artist(self, raw: str | None) -> str | None:
        return self.artists.get(norm_artist(raw), raw)

    def title(self, mk: str, raw: str | None) -> str | None:
        return self.titles.get(mk, raw)

    def album(self, artist: str | None, raw: str | None) -> str | None:
        return self.albums.get((norm_artist(artist), norm_title(raw)), raw) if raw else raw


# --- T8: periods and minutes (copied unchanged) ----------------------------------------------------------

DAY = 86400


def _range(con: sqlite3.Connection, year: int, month: int | None, day: int | None = None) -> tuple[float, float]:
    tz = listen_tz(con)
    if month and day:
        a = dt.datetime(year, month, day, tzinfo=tz)
        b = dt.datetime.combine(a.date() + dt.timedelta(days=1), dt.time(), tzinfo=tz)
        return a.timestamp(), b.timestamp()
    a = dt.datetime(year, month or 1, 1, tzinfo=tz)
    b = dt.datetime(year + (month or 12) // 12, (month or 12) % 12 + 1, 1, tzinfo=tz)
    return a.timestamp(), b.timestamp()


def _minutes(r) -> float:
    """How long a play lasted. Last.fm doesn't say (the track's length is used); Apple Music's daily summary
    gives a day's total over its plays, which can run past the track, so it's capped at the track's length."""
    ms = r["ms_played"] if r["source"] != "lastfm" else None
    if ms and r["duration_ms"] and r["source"] == "applemusic" and (r.get("uri") or "").startswith("daily:"):
        ms = min(ms, r["duration_ms"])
    return (ms or r["duration_ms"] or 225_000) / 60000


TOP_PERIODS = {"all": "All time", "30d": "Last 30 days", "12m": "Last 12 months"}


def top_range(con: sqlite3.Connection, period: str) -> tuple[float | None, float | None]:
    """A Top period: "all", "30d", "12m" (both ending today), a year ("2025") or a month ("2025-06")."""
    tz = listen_tz(con)
    if period in ("all", ""):
        return None, None
    if period in ("30d", "12m"):
        today = dt.datetime.now(tz).date()
        start = today - dt.timedelta(days=29 if period == "30d" else 364)
        a = dt.datetime.combine(start, dt.time(), tzinfo=tz)
        b = dt.datetime.combine(today + dt.timedelta(days=1), dt.time(), tzinfo=tz)
        return a.timestamp(), b.timestamp()
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?", period)
    if not m or (m[2] and not 1 <= int(m[2]) <= 12):
        raise ValueError("period is all, 30d, 12m, a year (2025) or a month (2025-06)")
    return _range(con, int(m[1]), int(m[2]) if m[2] else None)


# --- traqfreq's stand-in, not vendored --------------------------------------------------------------------
# jimbo-dj's _range and top_range call its listen_tz(con) (meta history_tz, else TZ). traqfreq works the zone
# out the same way (history.listen_tz, with Settings.tz for TZ) and hands it in here, so the copies above stay
# unchanged.
_TZ: contextvars.ContextVar = contextvars.ContextVar("listen_tz")


def listen_tz(con: sqlite3.Connection):
    """The zone set by ``in_zone``: the vendored functions above read it through this name."""
    return _TZ.get()


@contextlib.contextmanager
def in_zone(tz):
    """Run vendored period code in ``tz`` (traqfreq's history.listen_tz for the connection)."""
    token = _TZ.set(tz)
    try:
        yield
    finally:
        _TZ.reset(token)


# --- T21: the per-track genre tags (Top's genres; TAGS' gate check 2). ``tags`` is vendor/tags.py: its ``get`` is
# traqfreq's one Library per data stamp (jimbo-dj's background cache isn't copied). --------------------------------
def _genre_tags(con: sqlite3.Connection) -> tuple[dict[int, list[str]], dict[str, str]]:
    """rating_key → the canonical genre tags of the track (its own Plex genres and its album's, through
    Library → Tags' rules, junk left out), and tag key → its name. The same keys /library/tags/<key> uses."""
    from . import tags
    try:
        lib = tags.get(con)
    except Exception:  # noqa: BLE001 - no tags yet: no genres, said so on the page
        log.exception("genre tags unavailable for Top")
        return {}, {}
    R = lib.rules
    parsed: dict[str, list[str]] = {}

    def keys(raws) -> list[str]:
        out = []
        for raw in raws:
            if raw not in parsed:
                parsed[raw] = [p["key"] for p in R.parse(raw) if not p["junk"] and p["key"]]
            out += parsed[raw]
        return out

    album_tags = {k: keys(json.loads(g or "[]")) for k, g in con.execute("SELECT album_key, genres FROM albums")}
    by_track: dict[int, list[str]] = {}
    for rk, ak, g in con.execute("SELECT rating_key, album_key, plex_genres FROM tracks WHERE removed_at IS NULL"):
        ks = list(dict.fromkeys(album_tags.get(ak, []) + keys(json.loads(g or "[]"))))
        if ks:
            by_track[rk] = ks
    names = {k: e["name"] for k, e in lib.index.items()}
    return by_track, names
