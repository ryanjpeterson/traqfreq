"""jimbo-dj's songs.py, copied unchanged: one song, however many copies of it the library has.

A song is an artist and a title with the version stripped off ("Westkreuz (Live)" is "Westkreuz"); each copy
is a version (the original, a live take, a compilation, a single). jimbo-dj's artist page groups its top
tracks by song (pages._top_songs) and its album and song pages count a track's other copies with this index.

Copied: everything in songs.py except ``_stamp`` and ``index`` (jimbo-dj builds the index in its background
cache, cache.Background). traqfreq's stand-in ``index`` is at the bottom: it builds the same Index on the
read-only connection, once per library state (the same stamp jimbo-dj uses). Never edit the copies; re-copy
them from jimbo-dj when it changes.
"""
from __future__ import annotations

import functools
import json
import re
import threading
import unicodedata
from collections import defaultdict

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/songs.py"

# --- src/jimbodj/songs.py --------------------------------------------------------------------------------
_BRACKETS = re.compile(r"\s*[\(\[].*?[\)\]]")
_SUFFIX = re.compile(r"\s+-\s+.*(remaster|live|mono|stereo|demo|edit|version|mix|single|bonus|acoustic|session).*$", re.I)
_FEAT = re.compile(r"\s+(feat\.?|ft\.?|featuring)\s.*$", re.I)
VERSION_WORDS = re.compile(r"\b(live|demo|remix|mix|acoustic|instrumental|rehearsal|session|karaoke|edit|version|bbc|unplugged)\b", re.I)
LIVE_WORDS = ("live", "unplugged", "bbc", "session", "rehearsal")


@functools.lru_cache(maxsize=1 << 17)
def slugify(s: str | None) -> str:
    """"Sing the Sorrow" → "sing-the-sorrow"; "Mötley Crüe" → "motley-crue". A name with no Latin letters
    or digits keeps its own, lower-cased, spaces as hyphens."""
    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("&", " and ")
    out = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not out and (s or "").strip():
        out = re.sub(r"\s+", "-", (s or "").strip().lower())
    return out


def base_title(s: str | None) -> str:
    """The song's title without its version: brackets, " - Live at …", "feat. …"."""
    t = _FEAT.sub("", _SUFFIX.sub("", _BRACKETS.sub("", s or ""))).strip()
    return t or (s or "").strip()


def base_artist(s: str | None) -> str:
    return _FEAT.sub("", s or "").strip() or (s or "").strip()


def squash(slug: str) -> str:
    """The loose form a slug is looked up by: no leading "the-", no hyphens."""
    return re.sub(r"^the-", "", slug).replace("-", "")


def song_artist(t: dict) -> str:
    return t.get("track_artist") or t.get("artist") or ""


def song_slug(artist: str | None, title: str | None) -> str:
    return f"{slugify(base_artist(artist))}-{slugify(base_title(title))}"


def album_slug(artist: str | None, album: str | None) -> str:
    return f"{slugify(artist)}-{slugify(album)}"


def is_live(*texts: str | None) -> bool:
    for t in texts:
        m = VERSION_WORDS.search(t or "")
        if m and m.group(1).lower() in LIVE_WORDS:
            return True
    return False


def version(title: str | None, album: str | None, secondary: list[str] | None = None, primary: str | None = None) -> tuple[int, str | None]:
    """How regular a copy is (0 the original, 1 a compilation, single or EP, 3 live or another take) and
    what it is, for the UI ("live", "compilation", "demo", …; None for the original)."""
    sec = [x.lower() for x in secondary or []]
    words = VERSION_WORDS.search(f"{title or ''} {album or ''}")
    if "live" in sec or (words and words.group(1).lower() in LIVE_WORDS):
        return 3, "live"
    if words and words.group(1).lower() in ("demo", "remix", "mix", "acoustic", "instrumental", "karaoke", "edit", "version"):
        return 3, words.group(1).lower()
    if "compilation" in sec:
        return 1, "compilation"
    if primary in ("Single", "EP"):
        return 1, primary.lower()
    return 0, None


_LIB_Q = ("SELECT t.rating_key, t.title, t.artist, t.track_artist, t.artist_key, t.album, t.album_key, t.year, t.view_count, "
          "t.duration_ms, m.primary_type, m.secondary_types FROM tracks t LEFT JOIN albums a ON a.album_key = t.album_key "
          "LEFT JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok' WHERE t.removed_at IS NULL")


class Index:
    """Every library copy by song, and albums and artists by slug. Built once per library sync."""

    def __init__(self, con):
        self.tracks: dict[int, dict] = {}
        self.songs: dict[str, list[int]] = defaultdict(list)       # squash(song slug) → rating keys
        self.by_album_artist: dict[str, list[int]] = defaultdict(list)  # the same, by album artist, for compilations
        self.albums: dict[str, list[tuple[int, int]]] = defaultdict(list)  # squash(album slug) → (tracks, album_key)
        self.artists: dict[str, int] = {}                          # squash(artist slug) → artist_key
        album_tracks: dict[int, int] = defaultdict(int)
        album_name: dict[int, tuple[str, str]] = {}
        for r in con.execute(_LIB_Q):
            t = dict(r)
            t["secondary"] = json.loads(t.pop("secondary_types") or "[]")
            t["rank"], t["kind"] = version(t["title"], t["album"], t["secondary"], t["primary_type"])
            if t["kind"] is None and t["track_artist"] and squash(slugify(base_artist(t["track_artist"]))) != squash(slugify(t["artist"])):
                t["rank"], t["kind"] = 1, "compilation"  # on someone else's album: Various Artists, a soundtrack
            rk = t["rating_key"]
            self.tracks[rk] = t
            self.songs[self.song_key(t)].append(rk)
            if t["track_artist"]:
                self.by_album_artist[squash(song_slug(t["artist"], t["title"]))].append(rk)
            album_tracks[t["album_key"]] += 1
            album_name.setdefault(t["album_key"], (t["artist"], t["album"]))
            if t["artist_key"]:
                self.artists.setdefault(squash(slugify(t["artist"])), t["artist_key"])
        for ak, (artist, album) in album_name.items():
            self.albums[squash(album_slug(artist, album))].append((album_tracks[ak], ak))
        for v in self.albums.values():
            v.sort(reverse=True)
        with_tracks = set(self.artists.values())
        for r in con.execute("SELECT artist_key, title FROM artists"):  # Plex's artist name, if it differs
            if r["artist_key"] in with_tracks:
                self.artists.setdefault(squash(slugify(r["title"])), r["artist_key"])

    @staticmethod
    def song_key(t: dict) -> str:
        return squash(song_slug(song_artist(t), t["title"]))

    def song(self, slug: str) -> list[int]:
        """Every copy of the song a slug names: by its artist, or by a compilation's album artist."""
        k = squash(slug)
        if k in self.songs:
            return list(self.songs[k])
        keys: set[int] = set()
        for rk in self.by_album_artist.get(k, []):
            keys.update(self.songs[self.song_key(self.tracks[rk])])
        return sorted(keys)

    def versions_of(self, rk: int) -> list[int]:
        t = self.tracks.get(rk)
        return list(self.songs[self.song_key(t)]) if t else []

    def album(self, slug: str) -> int | None:
        v = self.albums.get(squash(slug))
        return v[0][1] if v else None

    def artist(self, slug: str) -> int | None:
        return self.artists.get(squash(slug))

    def best(self, keys: list[int], plays: dict[int, int]) -> int:
        """The copy a song page opens on: the original over a compilation or live take, then the most played."""
        return min(keys, key=lambda k: (self.tracks[k]["rank"], -plays.get(k, 0), self.tracks[k]["year"] or 9999, k))


# --- traqfreq's stand-in, not vendored -------------------------------------------------------------------
# jimbo-dj's index(con) keeps one Index in its background cache, rebuilt when _stamp changes (meta last_sync,
# and the count and newest rating_key of live tracks). Here: the same stamp, plus which database file it is
# (tests open many fixtures), and the Index built in the foreground on traqfreq's read-only connection.
_built: dict[tuple, Index] = {}
_lock = threading.Lock()


def index(con) -> Index:
    """The Index for this database and library state (built once, then kept in memory)."""
    row = con.execute("SELECT value FROM meta WHERE key = 'last_sync'").fetchone()
    file = con.execute("PRAGMA database_list").fetchone()[2]
    stamp = (file, row[0] if row else None,
             *con.execute("SELECT COUNT(*), MAX(rating_key) FROM tracks WHERE removed_at IS NULL").fetchone())
    with _lock:
        idx = _built.get(stamp)
        if idx is None:
            _built.clear()
            idx = _built[stamp] = Index(con)
        return idx
