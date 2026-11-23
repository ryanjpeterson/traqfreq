"""Pure functions vendored from jimbo-dj (ryanjpeterson/jimbo-dj, private), src/jimbodj/history.py at 1d8a7cb.

Copied as is (constants, band_of, norm_artist, norm_title, match_key, Names, window_sql), never edited here: traqfreq must count and match listens exactly the way jimbo-dj does
until HISTORY's cut-over (P6). To update: copy the same names again from jimbo-dj, bump VENDORED_FROM,
and run tests/test_vendor.py (it checks these against the match keys jimbo-dj stored in the fixture).
Why vendored, not a git dependency: jimbo-dj's repo is private (HANDOFF, open question 3).
"""
from __future__ import annotations

import functools
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/history.py"

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
