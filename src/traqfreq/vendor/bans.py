"""jimbo-dj's bans.py, the read side of Never in mixes: ``KINDS``, ``Bans`` and ``get``, copied unchanged at
1d8a7cb. ``rules.build`` leaves out every banned track jimbo-dj's index knows (``exclude=bans.get(con) or None``,
as jimbo-dj's preview passes it). Adding and removing bans stays in jimbo-dj (``add``, ``remove``, ``rekey`` are not
copied), and ``ensure_schema`` is a stand-in that does nothing: the legacy database is read-only."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import genres, history

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/bans.py (KINDS, Bans, get)"

# --- src/jimbodj/bans.py ----------------------------------------------------------------------------------
KINDS = ("song", "artist", "style")


@dataclass
class Bans:
    songs: set[str] = field(default_factory=set)
    artists: set[str] = field(default_factory=set)
    styles: set[str] = field(default_factory=set)
    style_scores: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.songs or self.artists or self.styles)

    def __call__(self, m: dict) -> bool:
        """True when a track (an index meta row, or anything with artist / title / rating_key) is banned."""
        if self.songs and history.match_key(m.get("track_artist") or m.get("artist"), m.get("title")) in self.songs:
            return True
        if self.songs and history.match_key(m.get("artist"), m.get("title")) in self.songs:
            return True
        if self.artists and ({history.norm_artist(m.get("artist")), history.norm_artist(m.get("track_artist"))} & self.artists):
            return True
        if self.styles and (sc := self.style_scores.get(m.get("rating_key"))):
            return any(sc.get(s, 0.0) >= genres.MATCH for s in self.styles)
        return False


def get(con: sqlite3.Connection) -> Bans:
    """The current bans, as a test for tracks (cheap to call per track). An empty Bans is falsy."""
    ensure_schema(con)
    b = Bans()
    for kind, ref in con.execute("SELECT kind, ref FROM bans"):
        {"song": b.songs, "artist": b.artists, "style": b.styles}[kind].add(ref)
    if b.styles:
        b.style_scores = genres.get(con).scores
    return b


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
def ensure_schema(con) -> None:  # noqa: ARG001 - jimbo-dj creates its tables; traqfreq only reads
    return None
