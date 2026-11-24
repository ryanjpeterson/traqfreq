"""jimbo-dj's genres module (genres.py), copied unchanged at 1d8a7cb: the constants, the families ``family`` sorts a
style into, ``_votes``, ``_support`` (T20) and ``Styles`` (T21). Not copied: jimbo-dj's background cache (``_cache``,
``get``, ``version``, ``invalidate``, from its cache.py); stand-ins for ``get`` and ``version`` are at the bottom.

``family`` gives a genre's broad family ("black metal" → Metal), which tag_rules.json's ``broad.families`` turns
into the broad tag (vendor/jimbodj_tags.py ``Rules.broad``). ``_support`` is how many MusicBrainz votes speak for
an album or artist. ``Styles`` merges every live track's styles from the analyzer's Discogs scores
(``features.genres``), MusicBrainz and Plex (noisy-or) under the strict test; ``sound_genres`` is the Discogs styles
each analysed track keeps (Explore's genre filter in jimbo-dj): the vendored ``live.distributions`` (the P2 gate's
``sound.genres`` bars, still not compared), ``tags._sound_by_album`` (the "sound" source) and TAGS' per-track tags
(T21) read it. Nothing here writes anything.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/genres.py (constants, family, _loads, _votes, _support, Styles)"

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


class Styles:
    """Every live track's style scores, and the catalogue of styles.

    Strict boundaries: a style counts for a track only when its metadata (MusicBrainz genres for its album
    or artist, Plex tags on the track, album or artist) names that style or another of its family, or when
    the sound alone is very sure (SOUND_ALONE) and no metadata contradicts it: metadata naming families but
    not this one. So Rush (progressive, hard rock) is never punk however a song sounds. The same test
    decides which of the analyzer's Discogs genres a track keeps (`sound_genres`, Explore's genre filter)."""

    def __init__(self, con):
        t0 = time.time()
        rel, art, support_alb, support_art = {}, {}, defaultdict(set), defaultdict(set)
        for r in con.execute("SELECT a.album_key, m.genres FROM albums a JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok'"):
            d = _loads(r["genres"], {})
            rel[r["album_key"]] = _votes(d, 0.5, 0.45)
            support_alb[r["album_key"]] |= _support(d)
        for r in con.execute("SELECT a.artist_key, m.genres FROM artists a JOIN mb_artists m ON m.mbid = a.mbid AND m.status='ok'"):
            d = _loads(r["genres"], {})
            art[r["artist_key"]] = _votes(d, 0.3, 0.35)
            support_art[r["artist_key"]] |= _support(d)
        alb_tags = {}
        for r in con.execute("SELECT album_key, genres FROM albums"):
            alb_tags[r[0]] = [t.lower() for t in _loads(r[1], [])]
            support_alb[r[0]] |= set(alb_tags[r[0]])
        for r in con.execute("SELECT artist_key, genres FROM artists"):
            support_art[r[0]] |= {t.lower() for t in _loads(r[1], [])}
        self.parent: dict[str, str] = {}
        self.sources: dict[str, set] = defaultdict(set)
        self.scores: dict[int, dict[str, float]] = {}
        self.sound_genres: dict[int, list[str]] = {}   # Discogs "Rock---Punk" keys the track keeps, strongest first
        self.dropped = Counter()                        # style → tracks it was taken from
        ctx_cache: dict[tuple, tuple[frozenset, frozenset]] = {}
        for r in con.execute(
                "SELECT t.rating_key, t.album_key, t.artist_key, t.plex_genres, f.genres FROM tracks t "
                "LEFT JOIN features f USING (rating_key) WHERE t.removed_at IS NULL"):
            track_tags = tuple(sorted(t.lower() for t in _loads(r["plex_genres"], [])))
            ck = (r["album_key"], r["artist_key"], track_tags)
            if ck not in ctx_cache:
                names = frozenset(support_alb.get(r["album_key"], set()) | support_art.get(r["artist_key"], set()) | set(track_tags))
                fams = frozenset(f for n in names if (f := family(n, self.parent.get(n))) != "Other")
                ctx_cache[ck] = (names, fams)
            names, fams = ctx_cache[ck]

            def allowed(name: str, sound: float) -> bool:
                if name in names:
                    return True
                fam = family(name, self.parent.get(name))
                if fam != "Other" and fam in fams:
                    return True
                return sound >= SOUND_ALONE and (fam == "Other" or not fams)

            parts: list[tuple[str, dict[str, float]]] = []
            disc = {}
            raw = _loads(r["genres"], {})
            kept = []
            for g, sc in sorted(raw.items(), key=lambda kv: -kv[1]):
                p, _, st = g.partition("---")
                name = (st or p).lower()
                self.parent.setdefault(name, p)
                v = min(1.0, sc * 1.6)
                disc[name] = max(disc.get(name, 0.0), v)
                if sc >= GENRE_MIN and allowed(name, v):
                    kept.append(g)
            if raw:
                self.sound_genres[r["rating_key"]] = kept
            parts.append(("sound", disc))
            parts.append(("musicbrainz", rel.get(r["album_key"], {})))
            parts.append(("musicbrainz", art.get(r["artist_key"], {})))
            parts.append(("plex", {t: 0.55 for t in track_tags}))
            parts.append(("plex", {t: 0.45 for t in alb_tags.get(r["album_key"], [])}))
            miss: dict[str, float] = {}
            for src, d in parts:
                for name, v in d.items():
                    miss[name] = miss.get(name, 1.0) * (1.0 - min(v, 0.99))
                    if v >= 0.3:
                        self.sources[name].add(src)
            if miss:
                sc = {}
                for k, m in miss.items():
                    v = round(1 - m, 3)
                    if v >= MATCH and not allowed(k, disc.get(k, 0.0)):
                        self.dropped[k] += 1
                        continue
                    sc[k] = v
                self.scores[r["rating_key"]] = sc
        self.count = Counter(name for sc in self.scores.values() for name, v in sc.items() if v >= MATCH)
        self._genre_members: dict[str, set[int]] = {}
        self.loaded_at = time.time()
        self.seconds = round(time.time() - t0, 2)

    def genre_members(self, genre: str) -> set[int]:
        """Tracks with a Discogs genre ("Rock---Punk", or "Rock" for every style under it) the strict test keeps."""
        if genre not in self._genre_members:
            whole = "---" not in genre
            self._genre_members[genre] = {k for k, gs in self.sound_genres.items()
                                          if any(g == genre or (whole and g.partition("---")[0] == genre) for g in gs)}
        return self._genre_members[genre]

    def catalogue(self, min_tracks: int = 5) -> list[dict]:
        return [{"name": name, "family": family(name, self.parent.get(name)), "tracks": n,
                 "sources": sorted(self.sources.get(name, ()))}
                for name, n in self.count.most_common() if n >= min_tracks]

    def top_for(self, keys, limit: int = 3) -> dict[int, list[str]]:
        return {k: [n for n, _ in sorted(self.scores.get(k, {}).items(), key=lambda kv: -kv[1])[:limit]] for k in keys}


# --- stand-ins (not vendored) ----------------------------------------------------------------------------
# jimbo-dj builds Styles in the background (cache.Background, keyed by cache.data_stamp and rebuilt after a sync or
# a MusicBrainz batch). traqfreq builds it on first use and keeps one per database and stamp: jimbo-dj's
# cache.data_stamp (analysed tracks, their newest analysis, the last sync) plus MusicBrainz's newest fetches.
_STAMP = ("SELECT (SELECT COUNT(*) FROM analysis), (SELECT MAX(analyzed_at) FROM analysis), "
          "(SELECT value FROM meta WHERE key='last_sync'), (SELECT MAX(fetched_at) FROM mb_releases), "
          "(SELECT MAX(fetched_at) FROM mb_artists)")
_built: dict[tuple, Styles] = {}


def stamp(con) -> tuple:
    db = con.execute("PRAGMA database_list").fetchone()
    return (db[2] if db else "", *con.execute(_STAMP).fetchone())


def get(con) -> Styles:
    key = stamp(con)
    st = _built.get(key)
    if st is None:
        _built.clear()
        st = _built[key] = Styles(con)
    return st


def version() -> int:
    """jimbo-dj bumps this on every rebuild of its styles (in its process memory); traqfreq has none."""
    return 0
