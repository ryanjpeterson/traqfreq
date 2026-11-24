"""TAGS (P4), read-only: the ladder (T20) and tracks tagged one by one (T21), built on jimbo-dj's tag rules
(vendor/jimbodj_tags.py), its per-track rule (vendor/jimbodj_history.py ``_genre_tags``) and its styles
(vendor/genres.py ``Styles``).

jimbo-dj sorts every canonical genre tag under one broad tag ("Black Metal" → Metal: ``Rules.broad``, from
tag_rules.json and ``genres.family``) and lists those families flat (``Library.families``). The ladder keeps that
and adds the rungs in between, any depth, with shared parents:

- **Nodes**: every canonical tag in use (``Library.index``, junk left out: a tag the rules call not a genre is no
  rung), plus each broad tag the rules name for them, in use or not.
- **Roots**: the broad tags (a broad tag's broad is itself). A tag whose rules give no broad tag (Soundtrack,
  Experimental) stands alone: no ladder, said so.
- **Parents**: a tag's parents are the tags in use whose name is its head: what is left when leading words are
  dropped ("Atmospheric Black Metal" → "Black Metal") or one part of a hyphenated word is kept ("Death-Doom Metal"
  → "Death Metal" and "Doom Metal"), any number of times, and only under the **same broad tag** (Post-Punk is
  Rock, so Punk is not its parent: listed as a name under another broad tag instead). Of those, only the nearest
  (one that is not itself the head of another). With none, the parent is the broad tag. So every ladder ends at
  jimbo-dj's broad tag, and a tag can sit on several ladders.
- **Numbers**: albums and artists carrying a tag (Plex's album and artist genres, as jimbo-dj counts them), and
  the albums under it (carrying it or any tag below it). For a broad tag those are jimbo-dj's family numbers:
  albums under it, tagged, missing (under it without carrying it: jimbo-dj's "Missing its broad tag").

``check`` is the agreement: each broad tag's numbers and children against the vendored ``Library.families`` (the
rules run here) and against jimbo-dj's stored ``library.tags`` (its own run), with whether that row is fresh.
Nothing here writes anything: Fix in Plex stays in jimbo-dj until P6.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict

from . import legacy
from .vendor import jimbodj_tags as jd

LADDER_VERSION = 1  # bump when the ladder's shape changes (it is in the cache key)
NEEDS = ("tracks", "albums", "artists", "mb_releases", "mb_artists", "meta")
SETS = ("carries", "under", "missing")

RULES = {
    "node": "a canonical tag in use (jimbo-dj's tag rules: split, aliases, rewrites, case), junk left out",
    "root": "a broad tag (tag_rules.json broad.families from genres.family, or an override)",
    "parent": "the nearest tags in use whose name is its head (leading words dropped, or one part of a "
              "hyphenated word kept), under the same broad tag; else the broad tag",
    "alone": "a tag in use whose rules give no broad tag",
    "carries": "albums whose Plex album genres name the tag (any spelling the rules make it)",
    "under": "albums carrying the tag or any tag below it",
    "missing": "albums under a broad tag that don't carry it (jimbo-dj's Missing its broad tag)",
    "artists": "artists whose Plex artist genres name the tag",
}


class NoTags(LookupError):
    """jimbo-dj's database has no tag tables."""


class NotFound(LookupError):
    pass


def _tables(conn: sqlite3.Connection) -> None:
    missing = [t for t in NEEDS if t not in legacy.table_names(conn)]
    if missing:
        raise NoTags(", ".join(missing))


def data_stamp(conn: sqlite3.Connection) -> list:
    """What jimbo-dj's tags are built from (its ``tags.stamp``) without the two parts traqfreq can't share: the
    styles' rebuild counter and the rules file's mtime (traqfreq's copy is fixed). MusicBrainz releases' and
    artists' newest fetch, the last Plex sync, the file tags' newest read, Fix in Plex's newest batch."""
    s = jd.stamp(conn)
    return [s[0], s[1], s[2], s[5], s[6]]


def cache_key(conn: sqlite3.Connection) -> str:
    _tables(conn)
    return f"v{LADDER_VERSION}|" + json.dumps(data_stamp(conn), separators=(",", ":"))


_libs: dict[str, jd.Library] = {}
_libs_lock = threading.Lock()


def library(conn: sqlite3.Connection) -> jd.Library:
    """jimbo-dj's tag Library, built once per data stamp and kept in memory (album rows need it)."""
    key = f"{legacy_id(conn)}|{cache_key(conn)}"
    with _libs_lock:
        lib = _libs.get(key)
        if lib is None:
            _libs.clear()
            lib = _libs[key] = jd.Library(conn)
        return lib


def legacy_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA database_list").fetchone()
    return row[2] if row else ""


# --- the ladder ---------------------------------------------------------------------------------------------

def _heads_once(key: str) -> set[str]:
    words = key.split(" ")
    out = {" ".join(words[i:]) for i in range(1, len(words))}
    for i, w in enumerate(words):
        parts = [p for p in w.split("-") if p]
        if len(parts) > 1:
            out |= {" ".join([*words[:i], p, *words[i + 1:]]) for p in parts}
    return {h for h in out if h and h != key}


def heads(key: str) -> set[str]:
    """Every shorter name inside a tag's name as its head, any number of steps ("atmospheric black metal" →
    "black metal", "metal"; "death-doom metal" → "death metal", "doom metal", "metal")."""
    seen: set[str] = set()
    todo = list(_heads_once(key))
    while todo:
        h = todo.pop()
        if h not in seen:
            seen.add(h)
            todo += _heads_once(h)
    return seen


def ladder(lib: jd.Library) -> dict:
    """Every tag in use on its rungs: nodes by key, roots, the tags that stand alone, and the summary."""
    R = lib.rules
    idx = lib.index
    live = {k: e for k, e in idx.items() if not e["junk"]}
    nodes: dict[str, dict] = {}

    def node(key: str, name: str) -> dict:
        n = nodes.get(key)
        if n is None:
            e = live.get(key)
            n = nodes[key] = {
                "key": key, "name": e["name"] if e else name, "in_use": e is not None,
                "broad": None, "root": False, "parents": [], "children": [], "rung": None,
                "albums": len(e["albums"]) if e else 0, "artists": len(e["artists"]) if e else 0,
                "variants": [v for v in sorted(e["variants"], key=lambda v: -sum(e["variants"][v].values()))] if e else [],
                "niche": bool(e and e["niche"]), "other_heads": [],
            }
        return n

    broads = {jd.norm(e["broad"]): e["broad"] for e in live.values() if e["broad"]}
    for k, e in live.items():
        n = node(k, e["name"])
        if k in broads:  # a broad tag is a root, whatever else it is called
            n["root"], n["broad"] = True, broads[k]
            continue
        b = e["broad"]
        if not b:
            continue
        n["broad"] = b
        bk = jd.norm(b)
        root = node(bk, b)
        root["root"], root["broad"] = True, b
        same, other = [], []
        for h in heads(k):
            if h in live and h != bk:
                (same if live[h]["broad"] == b else other).append(h)
        n["other_heads"] = sorted({live[h]["name"] for h in other})
        near = [h for h in same if not any(h in heads(o) for o in same if o != h)]
        n["parents"] = sorted(near) or [bk]

    for k, n in nodes.items():
        for p in n["parents"]:
            nodes[p]["children"].append(k)
    for n in nodes.values():
        n["children"].sort(key=lambda c: (-nodes[c]["albums"], nodes[c]["name"]))

    def rung(k: str) -> int | None:
        n = nodes[k]
        if n["rung"] is None and n["broad"]:
            n["rung"] = 0 if n["root"] else 1 + max(rung(p) for p in n["parents"])
        return n["rung"]

    below: dict[str, set[str]] = {}

    def descendants(k: str) -> set[str]:
        if k not in below:
            out: set[str] = set()
            for c in nodes[k]["children"]:
                out |= {c} | descendants(c)
            below[k] = out
        return below[k]

    for k, n in nodes.items():
        rung(k)
        have = idx[k]["albums"] if k in live else set()
        under = set(have)
        for d in descendants(k):
            under |= idx[d]["albums"]
        n["under"] = len(under)
        n["missing"] = len(under - have) if n["root"] else None
        n["below"] = len(descendants(k))

    roots = sorted((k for k, n in nodes.items() if n["root"]), key=lambda k: (-nodes[k]["under"], nodes[k]["name"]))
    alone = sorted((k for k, n in nodes.items() if not n["broad"]), key=lambda k: (-nodes[k]["albums"], nodes[k]["name"]))
    in_use = [n for n in nodes.values() if n["in_use"]]
    return {
        "nodes": nodes, "roots": roots, "alone": alone,
        "summary": {
            "tags": len(in_use), "roots": len(roots),
            "deepest": max((n["rung"] or 0 for n in nodes.values()), default=0),
            "shared": sum(1 for n in nodes.values() if len(n["parents"]) > 1),
            "alone": len(alone), "junk": sum(1 for e in idx.values() if e["junk"]),
            "albums": len(lib.albums), "artists": len(lib.artist_rows),
        },
        "rules": RULES,
    }


def descendants_of(lad: dict, key: str) -> set[str]:
    nodes = lad["nodes"]
    out, todo = set(), list(nodes[key]["children"])
    while todo:
        c = todo.pop()
        if c not in out:
            out.add(c)
            todo += nodes[c]["children"]
    return out


# --- agreement with jimbo-dj ----------------------------------------------------------------------------------

def _family_of_ladder(lad: dict, key: str) -> dict:
    n = lad["nodes"][key]
    kids = [lad["nodes"][d] for d in descendants_of(lad, key)]
    kids = sorted((c for c in kids if c["albums"]), key=lambda c: (-c["albums"], c["name"]))
    return {"tag": n["name"], "key": key, "albums": n["under"], "tagged": n["albums"], "missing": n["missing"],
            "children": [{"tag": c["name"], "key": c["key"], "albums": c["albums"]} for c in kids]}


def _same(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return False
    keys = ("tag", "albums", "tagged", "missing")
    kids = lambda f: sorted((c["key"], c["albums"]) for c in f["children"])  # noqa: E731
    return all(a[k] == b[k] for k in keys) and kids(a) == kids(b)


def _compare(ours: dict[str, dict], theirs: dict[str, dict]) -> list[dict]:
    rows = []
    for k in list(dict.fromkeys([*ours, *theirs])):
        rows.append({"key": k, "tag": (ours.get(k) or theirs.get(k))["tag"], "ladder": ours.get(k),
                     "jimbodj": theirs.get(k), "matches": _same(ours.get(k), theirs.get(k))})
    return rows


def stored(conn: sqlite3.Connection) -> dict | None:
    """jimbo-dj's stored ``library.tags`` row (its own run of the rules), with its stamp and whether it's fresh."""
    if "stats" not in legacy.table_names(conn):
        return None
    row = conn.execute("SELECT value, stamp, built_at FROM stats WHERE name = 'library.tags' AND params = ''").fetchone()
    if row is None:
        return None
    try:
        value, stamp = json.loads(row["value"]), json.loads(row["stamp"]) if row["stamp"] else None
    except ValueError:
        return None
    now = data_stamp(conn)
    theirs = [stamp[i] for i in (0, 1, 2, 5, 6)] if isinstance(stamp, list) and len(stamp) >= 7 else None
    return {"value": value, "stamp": stamp, "built_at": row["built_at"], "fresh": theirs == now}


def check(lib: jd.Library, lad: dict, saved: dict | None) -> dict:
    """Each broad tag with albums under it, from the ladder, next to jimbo-dj's families: as the vendored rules
    count them here, and as jimbo-dj stored them. And whether every ladder ends at jimbo-dj's broad tag."""
    ours = {k: _family_of_ladder(lad, k) for k in lad["roots"] if lad["nodes"][k]["under"]}
    here = {f["key"]: f for f in lib.families()}
    rules_rows = _compare(ours, here)
    out = {"rules": {"rows": rules_rows, "matches": all(r["matches"] for r in rules_rows),
                     "source": "jimbo-dj's tags.py families(), vendored, run here"}}
    ends = [k for k, n in lad["nodes"].items() if n["broad"] and not n["root"]]
    bad = [k for k in ends if not _ends_at_broad(lad, k)]
    out["ends"] = {"tags": len(ends), "ok": len(ends) - len(bad), "failing": sorted(bad), "matches": not bad,
                   "rule": "every ladder from a tag ends at the broad tag jimbo-dj's rules give it"}
    if saved is None or not isinstance(saved.get("value"), dict) or "families" not in saved["value"]:
        out["stored"] = None
    else:
        theirs = {f["key"]: f for f in saved["value"]["families"]}
        rows = _compare(ours, theirs)
        out["stored"] = {"rows": rows, "matches": all(r["matches"] for r in rows), "fresh": saved["fresh"],
                         "built_at": saved["built_at"], "source": "jimbo-dj's stats table, library.tags"}
    out["passed"] = (out["rules"]["matches"] and out["ends"]["matches"]
                     and (out["stored"] is None or out["stored"]["matches"] or not out["stored"]["fresh"]))
    return out


def _ends_at_broad(lad: dict, key: str) -> bool:
    nodes, want = lad["nodes"], jd.norm(lad["nodes"][key]["broad"])
    todo, seen = [key], set()
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        n = nodes[k]
        if not n["parents"]:
            if k != want or not n["root"]:
                return False
        todo += n["parents"]
    return True


def overview(conn: sqlite3.Connection) -> dict:
    """The TAGS page in one go: the ladder and its agreement with jimbo-dj (cached by the caller)."""
    lib = library(conn)
    lad = ladder(lib)
    return {**lad, "check": check(lib, lad, stored(conn)), "seconds": lib.seconds}


# --- rows -----------------------------------------------------------------------------------------------------

def _page(rows: list, limit: int, offset: int) -> tuple[list, int, int]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    return rows[offset:offset + limit], limit, offset


def albums(conn: sqlite3.Connection, tag: str, which: str = "carries", limit: int = 50, offset: int = 0) -> dict:
    """The albums behind a tag's number: carrying it, under it, or (a broad tag) missing it. Each with its Plex
    album tags as they are and the tags below this one it carries."""
    if which not in SETS:
        raise ValueError(f"set is one of {', '.join(SETS)}")
    lib = library(conn)
    lad = ladder(lib)
    k = jd.norm(tag)
    if k not in lad["nodes"]:
        raise NotFound(f"no tag {tag!r} in use")
    n = lad["nodes"][k]
    if which == "missing" and not n["root"]:
        raise ValueError("only a broad tag has albums missing it")
    have = lib.index[k]["albums"] if k in lib.index else set()
    below = descendants_of(lad, k)
    via: dict[int, list[str]] = defaultdict(list)
    for d in below:
        for a in lib.index[d]["albums"]:
            via[a].append(lad["nodes"][d]["name"])
    keys = set(have) if which == "carries" else (set(have) | set(via)) - (set(have) if which == "missing" else set())
    rows = [lib.albums[a] for a in keys if a in lib.albums]
    rows.sort(key=lambda a: ((a["artist"] or "").lower(), a["year"] or 0, (a["title"] or "").lower()))
    page, limit, offset = _page(rows, limit, offset)
    items = [{"album_key": a["album_key"], "title": a["title"], "artist": a["artist"], "artist_key": a["artist_key"],
              "year": a["year"], "tags": [t["name"] for t in a["tags"]], "carries": a["album_key"] in have,
              "via": sorted(via.get(a["album_key"], []))} for a in page]
    return {"tag": {"key": k, "name": n["name"], "root": n["root"]}, "set": which, "rule": RULES[which],
            "total": len(rows), "limit": limit, "offset": offset, "items": items}


def artists(conn: sqlite3.Connection, tag: str, limit: int = 50, offset: int = 0) -> dict:
    """The artists whose Plex artist genres name a tag."""
    lib = library(conn)
    lad = ladder(lib)
    k = jd.norm(tag)
    if k not in lad["nodes"]:
        raise NotFound(f"no tag {tag!r} in use")
    have = lib.index[k]["artists"] if k in lib.index else set()
    rows = sorted((lib.artist_rows[a] for a in have if a in lib.artist_rows), key=lambda a: (a["name"] or "").lower())
    page, limit, offset = _page(rows, limit, offset)
    items = [{"artist_key": a["artist_key"], "name": a["name"], "albums": a["albums"],
              "tags": [t["name"] for t in a["tags"]]} for a in page]
    return {"tag": {"key": k, "name": lad["nodes"][k]["name"], "root": lad["nodes"][k]["root"]},
            "rule": RULES["artists"], "total": len(rows), "limit": limit, "offset": offset, "items": items}



# --- T21: tracks tagged one by one ----------------------------------------------------------------------------
# A track's tags by source, each on its rung, and its tags by jimbo-dj's per-track rule (``history._genre_tags``:
# the track's own Plex genres and its album's, through the rules, junk left out). An album lists its tracks so a
# track that differs from its album shows, and the tags its tracks carry that speak for it (TRACK_SHARE, as
# jimbo-dj's ``_recs`` reads them).

TRACK_VERSION = 2  # bump when the per-track answers change (in the check's cache key); 2: each kept style once
SOURCES = ("track", "file", "album", "artist", "mb-release", "mb-artist", "sound")
TRACK_RULES = {
    "track": "the track's own Plex genres (tracks.plex_genres: what Plex read from the file, its first few values)",
    "file": "every genre value in the track's file, as jimbo-dj read it (file_tags)",
    "album": "the album's Plex genres (albums.genres)",
    "artist": "the artist's Plex genres (artists.genres)",
    "mb-release": "MusicBrainz genres of the album's release and release group, with votes (mb_releases)",
    "mb-artist": "MusicBrainz genres of the artist, with votes (mb_artists)",
    "sound": "the analyzer's Discogs styles with their scores (features.genres); kept: jimbo-dj's strict test "
             "(genres.Styles: the metadata names the style or its family, or the sound alone is at least 0.8 "
             "with no metadata against it; scores from 0.15)",
    "tags": "jimbo-dj's per-track rule (history._genre_tags): the album's Plex genres, then the track's own, "
            "through the tag rules, junk left out, each once",
    "differs": "tags the track carries that its album doesn't (its own Plex genres beyond the album's)",
    "speaks": f"a tag on at least {round(jd.TRACK_SHARE * 100)}% of the album's tracks (their Plex genres) or "
              "files speaks for the album (jimbo-dj's TRACK_SHARE, as its suggestions read it)",
    "check": "for every live track: the tags built here from its sources equal jimbo-dj's _genre_tags (vendored, "
             "run here), and the styles shown as kept equal genres.Styles.sound_genres (vendored), same order",
}

_per_track: dict[str, dict] = {}
_per_track_lock = threading.Lock()


def jimbodj_track_tags(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """jimbo-dj's ``history._genre_tags`` (vendored, unchanged), once per data stamp."""
    from .vendor import jimbodj_history as jh
    key = f"{legacy_id(conn)}|{cache_key(conn)}"
    with _per_track_lock:
        hit = _per_track.get(key)
        if hit is None:
            _per_track.clear()
            hit = _per_track[key] = jh._genre_tags(conn)[0]
        return hit


def styles(conn: sqlite3.Connection):
    """jimbo-dj's ``genres.Styles`` (vendored), once per stamp; None without the analyzer's tables."""
    from .vendor import genres
    if not {"features", "analysis"} <= legacy.table_names(conn):
        return None
    return genres.get(conn)


def _l(v, default):
    return jd._loads(v, default) if isinstance(v, (str, bytes)) or v is None else v


def _tag(lad: dict, R, raw: str, **extra) -> list[dict]:
    """One raw tag through the rules: each canonical tag it makes, with its rung on the ladder."""
    out = []
    for p in R.parse(raw):
        n = lad["nodes"].get(p["key"]) if not p["junk"] else None
        out.append({"raw": raw, "key": p["key"], "name": n["name"] if n else p["name"], "junk": p["junk"] or None,
                    "broad": n["broad"] if n else (None if p["junk"] else R.broad(p["key"])),
                    "rung": n["rung"] if n else None, "on_ladder": n is not None, **extra})
    return out


def _track_rows(conn: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT t.rating_key, t.title, t.artist, t.album, t.album_key, t.artist_key, t.disc, t.track_no, t.removed_at, "
        f"t.plex_genres FROM tracks t WHERE {where} ORDER BY t.disc IS NULL, t.disc, t.track_no IS NULL, t.track_no, "
        "t.title", args)]


class _Context:
    """The rows every source of a track reads, for one album or the whole library."""

    def __init__(self, conn: sqlite3.Connection, tracks: list[dict]):
        tables = legacy.table_names(conn)
        keys = [t["rating_key"] for t in tracks]
        albums = {t["album_key"] for t in tracks}
        artists = {t["artist_key"] for t in tracks}

        def rows(sql: str, ids) -> list:
            ids = list(ids)
            out = []
            for i in range(0, len(ids), 900):
                part = ids[i:i + 900]
                out += conn.execute(sql.format(",".join("?" * len(part))), part).fetchall()
            return out

        self.albums = {r[0]: (r[1], r[2]) for r in rows("SELECT album_key, genres, mbid FROM albums WHERE album_key IN ({})", albums)}
        self.artists = {r[0]: (r[1], r[2]) for r in rows("SELECT artist_key, genres, mbid FROM artists WHERE artist_key IN ({})", artists)}
        self.mb_rel = {r[0]: _l(r[1], {}) for r in conn.execute("SELECT mbid, genres FROM mb_releases WHERE status='ok'")}
        self.mb_art = {r[0]: _l(r[1], {}) for r in conn.execute("SELECT mbid, genres FROM mb_artists WHERE status='ok'")}
        self.files = ({r[0]: (r[1], r[2]) for r in rows("SELECT rating_key, genres, error FROM file_tags WHERE rating_key IN ({})", keys)}
                      if "file_tags" in tables else None)
        self.sound = ({r[0]: _l(r[1], {}) for r in rows("SELECT rating_key, genres FROM features WHERE rating_key IN ({}) "
                                                        "AND genres IS NOT NULL", keys)}
                      if "features" in tables else {})
        st = styles(conn)
        self.kept = st.sound_genres if st is not None else {}


def _sources(t: dict, ctx: _Context, lad: dict, R) -> dict[str, dict]:
    """Every source's genres for one track, each raw value through the rules and on its rung."""
    alb_g, alb_mb = ctx.albums.get(t["album_key"], (None, None))
    art_g, art_mb = ctx.artists.get(t["artist_key"], (None, None))

    def plain(raws) -> list[dict]:
        return [x for raw in raws for x in _tag(lad, R, raw)]

    def votes(d: dict) -> list[dict]:
        return [x for raw, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0])) for x in _tag(lad, R, raw, score=v)]

    out = {"track": {"tags": plain(_l(t["plex_genres"], []))}}
    if ctx.files is None:
        out["file"] = {"tags": [], "read": False, "note": "no file_tags table (jimbo-dj's file tags job never ran)"}
    else:
        g, err = ctx.files.get(t["rating_key"], (None, None))
        out["file"] = {"tags": plain(_l(g, [])), "read": t["rating_key"] in ctx.files and err is None, "error": err}
    out["album"] = {"tags": plain(_l(alb_g, []))}
    out["artist"] = {"tags": plain(_l(art_g, []))}
    out["mb-release"] = {"tags": votes(ctx.mb_rel.get(alb_mb) or {}), "found": alb_mb in ctx.mb_rel}
    out["mb-artist"] = {"tags": votes(ctx.mb_art.get(art_mb) or {}), "found": art_mb in ctx.mb_art}
    raw = ctx.sound.get(t["rating_key"]) or {}
    kept = set(ctx.kept.get(t["rating_key"], ()))
    snd = []
    for g, sc in sorted(raw.items(), key=lambda kv: -kv[1]):  # ties keep their order, as Styles does
        style = g.partition("---")[2] or g
        snd += _tag(lad, R, style, score=sc, discogs=g, kept=g in kept)
    out["sound"] = {"tags": snd, "analysed": bool(raw)}
    return out


def _own_tags(src: dict[str, dict]) -> list[str]:
    """The track's tags built here from its sources: the album's Plex genres, then its own, junk out, each once
    (what jimbo-dj's _genre_tags gives, worked out separately so the check means something)."""
    return list(dict.fromkeys(x["key"] for s in ("album", "track") for x in src[s]["tags"] if not x["junk"] and x["key"]))


def _kept(src: dict[str, dict]) -> list[str]:
    """The Discogs styles kept, each once: the rules split a style like "Cut-up/DJ" into two tags, one style still."""
    return list(dict.fromkeys(x["discogs"] for x in src["sound"]["tags"] if x.get("kept")))


def _track(t: dict, ctx: _Context, lad: dict, lib: jd.Library, theirs: dict[int, list[str]]) -> dict:
    R = lib.rules
    src = _sources(t, ctx, lad, R)
    mine = _own_tags(src)
    album_keys = {x["key"] for x in src["album"]["tags"] if not x["junk"]}
    by_source = defaultdict(list)
    for s in SOURCES:
        for x in src[s]["tags"]:
            if not x["junk"] and (s != "sound" or x.get("kept")):
                by_source[x["key"]].append(s)

    def node(k: str) -> dict:
        n = lad["nodes"].get(k)
        e = lib.index.get(k)
        return {"key": k, "name": n["name"] if n else (e["name"] if e else k), "broad": n["broad"] if n else R.broad(k),
                "rung": n["rung"] if n else None, "on_ladder": n is not None,
                "sources": list(dict.fromkeys(by_source.get(k, []))), "album": k in album_keys}

    jim = theirs.get(t["rating_key"], [])
    st_theirs = list(ctx.kept.get(t["rating_key"], ()))
    return {
        "rating_key": t["rating_key"], "title": t["title"], "artist": t["artist"], "album": t["album"],
        "album_key": t["album_key"], "artist_key": t["artist_key"], "disc": t["disc"], "track_no": t["track_no"],
        "live": t["removed_at"] is None,
        "tags": [node(k) for k in mine],
        "differs": [node(k) for k in mine if k not in album_keys],
        "styles": [x for x in src["sound"]["tags"] if x.get("kept")],
        "sources": src,
        "check": {"tags": mine == jim, "styles": _kept(src) == st_theirs, "jimbodj_tags": jim, "jimbodj_styles": st_theirs},
    }


def _ready(conn: sqlite3.Connection) -> tuple[jd.Library, dict]:
    lib = library(conn)
    return lib, ladder(lib)


def track(conn: sqlite3.Connection, key: int) -> dict:
    """One track's tags by source, each on its rung, and its tags by jimbo-dj's per-track rule."""
    lib, lad = _ready(conn)
    rows = _track_rows(conn, "t.rating_key = ?", (int(key),))
    if not rows:
        raise NotFound(f"no track {key}")
    if rows[0]["removed_at"] is not None:
        raise NotFound(f"track {key} is removed (jimbo-dj's tags read live tracks only)")
    ctx = _Context(conn, rows)
    out = _track(rows[0], ctx, lad, lib, jimbodj_track_tags(conn))
    return {**out, "album_tags": _album_tags(lib, rows[0]["album_key"]), "rules": TRACK_RULES}


def _album_tags(lib: jd.Library, album_key) -> list[dict]:
    a = lib.albums.get(album_key)
    return list(a["tags"]) if a else []


def album(conn: sqlite3.Connection, key: int) -> dict:
    """An album's tracks with their tags, the ones that differ from the album marked, and the tags its tracks and
    files carry that speak for it."""
    lib, lad = _ready(conn)
    a = lib.albums.get(int(key))
    if a is None:
        raise NotFound(f"no album {key}")
    rows = _track_rows(conn, "t.album_key = ? AND t.removed_at IS NULL", (int(key),))
    ctx = _Context(conn, rows)
    theirs = jimbodj_track_tags(conn)
    tracks = [_track(t, ctx, lad, lib, theirs) for t in rows]
    for t in tracks:
        del t["sources"]
    speaks = []
    for g in a["genres"]:
        s = g["sources"]
        share = max(s.get("plex-track", 0), s.get("file", 0))
        if g["status"] == "junk" or share <= 0:
            continue
        n = lad["nodes"].get(g["key"])
        speaks.append({"key": g["key"], "name": g["tag"], "rung": n["rung"] if n else None, "on_ladder": n is not None,
                       "broad": n["broad"] if n else lib.rules.broad(g["key"]),
                       "tracks": s.get("plex-track", 0), "files": s.get("file", 0),
                       "speaks": share >= jd.TRACK_SHARE, "album": g["status"] in ("keep", "niche"), "status": g["status"]})
    speaks.sort(key=lambda x: (not x["speaks"], -max(x["tracks"], x["files"]), x["name"]))
    return {
        "album_key": a["album_key"], "title": a["title"], "artist": a["artist"], "artist_key": a["artist_key"],
        "year": a["year"], "tags": a["tags"], "tracks": tracks,
        "differ": sum(1 for t in tracks if t["differs"]), "from_tracks": speaks, "track_share": jd.TRACK_SHARE,
        "check": {"tags": sum(1 for t in tracks if t["check"]["tags"]), "styles": sum(1 for t in tracks if t["check"]["styles"]),
                  "tracks": len(tracks)},
        "rules": TRACK_RULES,
    }


def track_check_key(conn: sqlite3.Connection) -> str:
    from .vendor import genres
    st = genres.stamp(conn) if {"features", "analysis"} <= legacy.table_names(conn) else None
    return f"t{TRACK_VERSION}|{cache_key(conn)}|" + json.dumps(st[1:] if st else None, separators=(",", ":"), default=str)


def track_check(conn: sqlite3.Connection, limit: int = 50) -> dict:
    """Gate check 2: for every live track, the tags built here from its sources against jimbo-dj's _genre_tags,
    and the styles shown as kept against genres.Styles.sound_genres. Lists the first tracks that differ."""
    lib, lad = _ready(conn)
    rows = _track_rows(conn, "t.removed_at IS NULL", ())
    ctx = _Context(conn, rows)
    theirs = jimbodj_track_tags(conn)
    tag_bad, style_bad, analysed, with_tags = [], [], 0, 0
    for t in rows:
        src = _sources(t, ctx, lad, lib.rules)
        mine = _own_tags(src)
        with_tags += bool(mine)
        if mine != theirs.get(t["rating_key"], []):
            tag_bad.append({"rating_key": t["rating_key"], "title": t["title"], "artist": t["artist"],
                            "traqfreq": mine, "jimbodj": theirs.get(t["rating_key"], [])})
        analysed += src["sound"]["analysed"]
        if _kept(src) != list(ctx.kept.get(t["rating_key"], ())):
            style_bad.append({"rating_key": t["rating_key"], "title": t["title"], "artist": t["artist"],
                              "traqfreq": _kept(src), "jimbodj": list(ctx.kept.get(t["rating_key"], ()))})
    extra = sorted(set(theirs) - {t["rating_key"] for t in rows})
    n = len(rows)
    tags_part = {"tracks": n, "with_tags": with_tags, "ok": n - len(tag_bad), "differ": len(tag_bad),
                 "items": tag_bad[:limit], "unknown": extra[:limit], "matches": not tag_bad and not extra,
                 "source": "jimbo-dj's history._genre_tags, vendored, run here"}
    styles_part = {"tracks": n, "analysed": analysed, "kept": sum(1 for v in ctx.kept.values() if v),
                   "ok": n - len(style_bad), "differ": len(style_bad), "items": style_bad[:limit],
                   "matches": not style_bad and analysed == len(ctx.kept),
                   "source": "jimbo-dj's genres.Styles.sound_genres, vendored, run here"}
    return {"tags": tags_part, "styles": styles_part, "passed": tags_part["matches"] and styles_part["matches"],
            "rule": TRACK_RULES["check"]}
