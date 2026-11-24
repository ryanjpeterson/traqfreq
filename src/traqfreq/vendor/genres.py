"""jimbo-dj's genres module (genres.py): the parts TAGS uses copied unchanged at 1d8a7cb (the constants, the
families ``family`` sorts a style into, ``_votes`` and ``_support``); the styles (``Styles``, built from the
analyzer's Discogs scores) are a stand-in below, not vendored.

``family`` gives a genre's broad family ("black metal" → Metal), which tag_rules.json's ``broad.families`` turns
into the broad tag (vendor/jimbodj_tags.py ``Rules.broad``). ``_support`` is how many MusicBrainz votes speak for
an album or artist (proposals, T22). The stand-in ``get`` has no styles: the vendored ``live.distributions`` and
``tags._sound_by_album`` import this module for the Discogs genres of each analysed track and find none, so the
P2 gate's ``genres`` bars are empty (not compared) and the tags carry no "sound" source until T21 vendors the
styles. ``version`` stands in for jimbo-dj's in-memory rebuild counter.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/genres.py (constants, family, _loads, _votes, _support)"

# --- src/jimbodj/genres.py -------------------------------------------------------------------------------
MATCH = 0.45      # a track counts as this style from here
CACHE_SECONDS = 120   # the most often the styles are rebuilt while the analyzer is adding tracks
# Strict boundaries: a style needs its artist's or album's metadata behind it (see Styles). A MusicBrainz
# genre backs a style when it has at least SUPPORT_SHARE of the entity's top votes, and two or more (Rush's
# 2 "heavy metal" votes against 25 for "progressive rock" don't, nor one vote on a live album); Plex's tags always do. Without that, only a sound score of
# SOUND_ALONE or more counts, and only when no metadata points to other families.
SUPPORT_SHARE = 0.25
SOUND_ALONE = 0.8
GENRE_MIN = 0.15  # the analyzer's Discogs genres count from here (Explore's genre filter and chart)

# Families, so the UI can group styles the way you'd think of them (Discogs files all of metal under Rock).
_FAMILIES = [
    ("Metal", re.compile(r"metal|grind|djent|deathcore|sludge|doom|thrash|black'n'roll|nwobhm|mathcore|metalcore")),
    ("Punk & hardcore", re.compile(r"(?<!post-)punk|hardcore(?! techno| house)|emo|screamo|crust|powerviolence|\boi\b|crossover|riot grrrl|post-hardcore")),
    ("Hip hop", re.compile(r"hip hop|hip-hop|rap|trap|boom bap|grime|drill")),
    ("Electronic", re.compile(r"techno|house|trance|ambient|electro|idm|drum and bass|drum n bass|dubstep|jungle|breakbeat|edm|synth(?!.*rock)|downtempo|trip hop|uk garage|bass music|electronic|industrial|ebm|chiptune|vaporwave|glitch")),
    ("Jazz", re.compile(r"jazz|bop|swing|fusion")),
    ("Blues & soul", re.compile(r"blues|soul|funk|r&b|rhythm & blues|gospel|motown|disco")),
    ("Folk & country", re.compile(r"folk|country|bluegrass|americana|singer-songwriter|celtic")),
    ("Classical", re.compile(r"classical|baroque|romantic|opera|orchestral|choral|chamber|contemporary classical|modern classical")),
    ("Reggae", re.compile(r"reggae|dub\b|ska|dancehall|rocksteady")),
    ("Pop", re.compile(r"pop")),
    ("Rock", re.compile(r"rock|grunge|shoegaze|new wave|post-punk|indie|psychedelic|garage|britpop|noise")),
]


_PARENTS = {"Hip Hop": "Hip hop", "Folk, World, & Country": "Folk & country", "Funk / Soul": "Blues & soul",
            "Blues": "Blues & soul", "Brass & Military": "Classical", "Children's": "Other"}


def family(name: str, discogs_parent: str | None = None) -> str:
    for fam, rx in _FAMILIES:
        if rx.search(name):
            return fam
    return _PARENTS.get(discogs_parent, discogs_parent) if discogs_parent else "Other"


def _loads(v, default):
    if v is None:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def _votes(d: dict[str, int], floor: float, span: float) -> dict[str, float]:
    if not d:
        return {}
    top = max(d.values()) or 1
    return {k: floor + span * (v / top) for k, v in d.items() if v > 0 or top == 1}


def _support(d: dict[str, int]) -> set[str]:
    """The MusicBrainz genres with enough votes to speak for the artist or album: SUPPORT_SHARE of the top
    genre's votes and at least two, unless no genre has more than one."""
    if not d:
        return set()
    top = max(d.values()) or 1
    return {k for k, v in d.items() if top <= 1 or v >= max(2, SUPPORT_SHARE * top)}


# --- stand-ins (not vendored) ----------------------------------------------------------------------------
class _Styles:
    sound_genres: dict[int, tuple] = {}
    scores: dict[int, dict] = {}


def get(con) -> _Styles:  # noqa: ARG001
    return _Styles()


def version() -> int:
    """jimbo-dj bumps this on every rebuild of its styles (in its process memory); traqfreq has none."""
    return 0
