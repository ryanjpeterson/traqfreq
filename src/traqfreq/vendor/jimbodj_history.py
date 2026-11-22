"""Pure functions vendored from jimbo-dj (ryanjpeterson/jimbo-dj, private), src/jimbodj/history.py at 1d8a7cb.

Copied as is, never edited here: traqfreq must count and match listens exactly the way jimbo-dj does
until HISTORY's cut-over (P6). To update: copy the same names again from jimbo-dj, bump VENDORED_FROM,
and run tests/test_vendor.py (it checks these against the match keys jimbo-dj stored in the fixture).
Why vendored, not a git dependency: jimbo-dj's repo is private (HANDOFF, open question 3).
"""
from __future__ import annotations

import functools
import re
import unicodedata

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
