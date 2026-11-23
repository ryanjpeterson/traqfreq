"""Stand-in for jimbo-dj's genres module (styles from Plex, MusicBrainz and Discogs), not vendored.

Styles and genre families are TAGS (P4). The vendored ``live.distributions`` imports this module inside its
body (``from . import genres``) for the Discogs genres of each analysed track; here there are none, so its
``genres`` bars are empty and the gate marks them not compared.
"""
from __future__ import annotations


class _Styles:
    sound_genres: dict[int, tuple] = {}
    scores: dict[int, dict] = {}


def get(con) -> _Styles:  # noqa: ARG001
    return _Styles()
