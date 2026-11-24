"""TAGS (P4), read-only: a page per tag, the genre map and movements (T23).

- **A tag's page** (``tag``): where it sits (its ladders up to the broad tag, every path; its children; the
  names inside it under another broad tag), how it got its name (each spelling in Plex with its albums, artists
  and tracks and the tag rules that made it this tag; the broad-tag rule), and its numbers, each opening its rows:
  albums carrying it, albums under it, a broad tag's albums missing it, artists carrying it, the live tracks
  carrying it (jimbo-dj's per-track rule, ``history._genre_tags``), their plays (HISTORY's counted plays of those
  tracks: jimbo-dj's Top genres rule, all time), and its sound (albums whose analyzer styles name it, jimbo-dj's
  ``sound`` count; and what its plays sounded like, jimbo-dj's ``history.sound_of``).
- **The genre map** (``genre_map``): the whole ladder as lines, one per broad tag, its tags as stations on
  their rungs (a tag with two parents is a station on each branch, said so), and the tags with no broad tag.
- **Movements** (``movements``), read from ``movements.json`` in traqfreq's repo: a named set of tags across
  broad tags (Blackgaze with Shoegaze). Shown on the map and on each tag's page; a movement changes no ladder and
  no count: each tag keeps its own broad tag and its own numbers.

Nothing here writes anything.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import Counter
from pathlib import Path

from . import history, legacy, tags
from .vendor import genres
from .vendor import jimbodj_history as jh
from .vendor import jimbodj_tags as jd

MOVEMENTS_PATH = Path(__file__).with_name("movements.json")
MAP_VERSION = 1  # bump when the map's or a tag page's answers change
PATHS_MAX = 24   # ladders listed on a tag's page (a tag with many shared parents could have more)

RULES = {
    "ladders": "every path from the tag up to its broad tag, through its parents (the nearest heads in use under "
               "the same broad tag)",
    "children": "the tags whose nearest head is this one",
    "spellings": "each way Plex spells the tag (album, artist and track genres) and the tag rules that turned it "
                 "into this tag (jimbo-dj's tag_rules.json)",
    "tracks": "live tracks carrying the tag by jimbo-dj's per-track rule (history._genre_tags: the album's Plex "
              "genres, then the track's own, through the tag rules, junk left out)",
    "plays": "HISTORY's counted plays (counted = 1) of those tracks, all time: jimbo-dj's Top genres rule (a play "
             "counts for every tag its library track carries; a play with no library track has no genre)",
    "sound": "albums whose analyzer styles name the tag (a style counts for an album when at least "
             f"{round(jd.SOUND_SHARE * 100)}% of its analysed tracks keep it: jimbo-dj's sound count)",
    "profile": "what the tag's plays sounded like: the analysis of its tracks, each weighted by its plays "
               "(jimbo-dj's history.sound_of; at least 20 analysed plays)",
    "line": "one line per broad tag: its tags as stations, each on its rung (a tag under two parents is a station "
            "on both branches)",
    "movement": "a named set of tags across broad tags, from traqfreq's movements.json; it changes no ladder and "
                "no count",
}


# --- movements ----------------------------------------------------------------------------------------------

def load_movements(path: Path = MOVEMENTS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def movements_stamp(path: Path = MOVEMENTS_PATH) -> str:
    raw = path.read_bytes()
    return f"m{json.loads(raw).get('version', 0)}:{hashlib.sha1(raw).hexdigest()[:8]}"


def movements(lib: jd.Library, lad: dict, data: dict | None = None) -> list[dict]:
    """Each movement with its tags through jimbo-dj's rules: in use or not, on which line and rung, their numbers."""
    data = data or load_movements()
    R, nodes = lib.rules, lad["nodes"]
    out = []
    for m in data["movements"]:
        members, seen = [], set()
        for raw in m["tags"]:
            for p in R.parse(raw):
                k = p["key"]
                if not k or k in seen or p["junk"]:
                    continue
                seen.add(k)
                n = nodes.get(k)
                members.append({"key": k, "name": n["name"] if n else p["name"], "in_use": bool(n and n["in_use"]),
                                "broad": n["broad"] if n else R.broad(k), "rung": n["rung"] if n else None,
                                "albums": n["albums"] if n else 0, "artists": n["artists"] if n else 0})
        broads = list(dict.fromkeys(x["broad"] for x in members if x["broad"]))
        out.append({"id": m["id"], "name": m["name"], "about": m.get("about", ""), "tags": members,
                    "broads": broads, "in_use": sum(1 for x in members if x["in_use"])})
    return out


def movements_of(mvs: list[dict]) -> dict[str, list[dict]]:
    """tag key → the movements naming it."""
    out: dict[str, list[dict]] = {}
    for m in mvs:
        for x in m["tags"]:
            out.setdefault(x["key"], []).append({"id": m["id"], "name": m["name"]})
    return out


# --- plays --------------------------------------------------------------------------------------------------

_plays: dict[str, Counter] = {}
_plays_lock = threading.Lock()


def plays_by_track(conn: sqlite3.Connection, default_tz: str | None = None) -> Counter | None:
    """HISTORY's counted plays per library track (``COALESCE(listens.rating_key, listen_matches.rating_key)``, the
    track jimbo-dj's ``_plays`` gives each play), once per history state. None without HISTORY's tables."""
    if not {"listens", "listen_matches"} <= legacy.table_names(conn):
        return None
    key = f"{tags.legacy_id(conn)}|{history.cache_key(conn, default_tz)}"
    with _plays_lock:
        hit = _plays.get(key)
        if hit is None:
            _plays.clear()
            hit = _plays[key] = Counter({rk: n for rk, n in conn.execute(
                "SELECT COALESCE(l.rating_key, m.rating_key) rk, COUNT(*) FROM listens l "
                "LEFT JOIN listen_matches m ON m.match_key = l.match_key "
                "WHERE l.counted = 1 AND COALESCE(l.rating_key, m.rating_key) IS NOT NULL GROUP BY rk")})
        return hit


def _tracks_of(conn: sqlite3.Connection, key: str) -> list[int]:
    """Live tracks carrying a tag by jimbo-dj's per-track rule."""
    return [rk for rk, ks in tags.jimbodj_track_tags(conn).items() if key in ks]


def _sound_albums(conn: sqlite3.Connection, lib: jd.Library, key: str) -> set[int]:
    """Albums whose analyzer styles name the tag at SOUND_SHARE (what jimbo-dj's index counts as ``sound``)."""
    if not {"features", "analysis"} <= legacy.table_names(conn):
        return set()
    try:
        by_album = jd._sound_by_album(conn)
    except Exception:  # noqa: BLE001 - no analysis yet, as jimbo-dj's Library has it
        return set()
    R = lib.rules
    return {a for a, s in by_album.items() if key in {p["key"] for g, v in s.items() if v >= jd.SOUND_SHARE for p in R.parse(g)}}


# --- a tag's page -------------------------------------------------------------------------------------------

def _paths(lad: dict, key: str) -> list[list[str]]:
    """Every path up from a tag to its broad tag, broad tag first."""
    nodes = lad["nodes"]

    def up(k: str, seen: frozenset) -> list[list[str]]:
        ps = [p for p in nodes[k]["parents"] if p not in seen]
        if not ps:
            return [[k]]
        return [path + [k] for p in ps for path in up(p, seen | {k})]

    out = up(key, frozenset())
    return sorted(out, key=lambda p: (len(p), [nodes[k]["name"] for k in p]))[:PATHS_MAX]


def _broad_rule(R: jd.Rules, key: str) -> dict | None:
    """Which rule gives a tag its broad tag: an override in tag_rules.json, or a family genres.family finds."""
    for rx, tag in R.overrides:
        m = rx.search(key)
        if m:
            return {"how": "override", "pattern": rx.pattern, "match": m.group(0), "broad": tag}
    fam = genres.family(key)
    if fam and R.families.get(fam):
        m = next((rx.search(key) for f, rx in genres._FAMILIES if f == fam and rx.search(key)), None)
        return {"how": "family", "family": fam, "match": m.group(0) if m else None, "broad": R.families[fam]}
    return None


def _rule_names(R: jd.Rules) -> dict[str, dict]:
    return {r["id"]: r for r in R.rule_index()}


def tag(conn: sqlite3.Connection, key: str, default_tz: str | None = None, mvs: list[dict] | None = None) -> dict:
    """One tag's page: its place on the ladder, its spellings and rules, its numbers (each with its rows'
    query), its plays and its sound, and the movements naming it."""
    lib, lad = tags._ready(conn)
    R = lib.rules
    k = jd.norm(key)
    n = lad["nodes"].get(k)
    e = lib.index.get(k)
    if n is None and e is None:
        raise tags.NotFound(f"no tag {key!r} in use")
    rules = _rule_names(R)
    spellings = []
    for raw, uses in sorted((e["variants"] if e else {}).items(),
                            key=lambda kv: (-(kv[1]["albums"] + kv[1]["artists"] + kv[1]["tracks"]), kv[0])):
        part = next((p for p in R.parse(raw) if p["key"] == k), None)
        fired = [*(part["rules"] if part else []), *([part["junk"]] if part and part["junk"] else [])]
        spellings.append({"raw": raw, "albums": uses["albums"], "artists": uses["artists"], "tracks": uses["tracks"],
                          "same": raw == (n or e)["name"], "split": len(R.parse(raw)) > 1,
                          "rules": [{"id": r, "label": rules[r]["label"] if r in rules else r} for r in fired]})
    junk = e["junk"] if e else None
    nodes = lad["nodes"]

    def brief(c: str) -> dict:
        x = nodes[c]
        return {"key": c, "name": x["name"], "albums": x["albums"], "under": x["under"], "rung": x["rung"],
                "children": len(x["children"]), "parents": len(x["parents"])}

    tracks = _tracks_of(conn, k)
    played = plays_by_track(conn, default_tz)
    weights = Counter({rk: played[rk] for rk in tracks if played and played[rk]}) if played is not None else Counter()
    profile = None
    if weights and "features" in legacy.table_names(conn):
        profile = jh.sound_of(conn, weights)
    sound = _sound_albums(conn, lib, k)
    row = next((r for r in lib.tag_rows() if r["key"] == k), None)
    mv = [m for m in (mvs or []) if any(x["key"] == k for x in m["tags"])]
    return {
        "key": k, "name": (n or e)["name"], "in_use": bool(n and n["in_use"]) or bool(e),
        "junk": {"id": junk, "label": rules[junk]["label"] if junk in rules else junk,
                 "why": rules[junk]["why"] if junk in rules else None} if junk else None,
        "broad": n["broad"] if n else None, "root": bool(n and n["root"]), "rung": n["rung"] if n else None,
        "broad_rule": _broad_rule(R, k) if n and n["broad"] and not junk else None,
        "ladders": [[{"key": p, "name": nodes[p]["name"], "rung": nodes[p]["rung"]} for p in path]
                    for path in _paths(lad, k)] if n and n["broad"] else [],
        "parents": [brief(p) for p in n["parents"]] if n else [],
        "children": [brief(c) for c in n["children"]] if n else [],
        "below": n["below"] if n else 0,
        "other_heads": n["other_heads"] if n else [],
        "spellings": spellings,
        "issues": row["issues"] if row else [],
        "numbers": {
            "albums": len(e["albums"]) if e else 0,
            "under": n["under"] if n else 0,
            "missing": n["missing"] if n and n["root"] else None,
            "artists": len(e["artists"]) if e else 0,
            "tracks": len(tracks),
            "plays": sum(weights.values()) if played is not None else None,
            "sound": len(sound),
            "musicbrainz": e["mb"] if e else 0,
        },
        "history": played is not None,
        "profile": profile,
        "movements": mv,
        "rules": RULES,
    }


def tag_tracks(conn: sqlite3.Connection, key: str, sort: str = "plays", limit: int = 50, offset: int = 0,
               default_tz: str | None = None) -> dict:
    """The live tracks carrying a tag (jimbo-dj's per-track rule), each with its counted plays."""
    if sort not in ("plays", "album"):
        raise ValueError("sort is plays or album")
    lib, lad = tags._ready(conn)
    k = jd.norm(key)
    n = lad["nodes"].get(k)
    if n is None and k not in lib.index:
        raise tags.NotFound(f"no tag {key!r} in use")
    keys = _tracks_of(conn, k)
    played = plays_by_track(conn, default_tz) or Counter()
    rows = []
    for i in range(0, len(keys), 900):
        part = keys[i:i + 900]
        rows += [dict(r) for r in conn.execute(
            "SELECT rating_key, title, artist, album, album_key, disc, track_no FROM tracks "
            f"WHERE rating_key IN ({','.join('?' * len(part))})", part)]
    for r in rows:
        r["plays"] = played.get(r["rating_key"], 0)
    by_album = lambda r: ((r["artist"] or "").lower(), (r["album"] or "").lower(), r["disc"] or 0, r["track_no"] or 0,  # noqa: E731
                          (r["title"] or "").lower())
    rows.sort(key=(lambda r: (-r["plays"], *by_album(r))) if sort == "plays" else by_album)
    page, limit, offset = tags._page(rows, limit, offset)
    name = n["name"] if n else lib.index[k]["name"]
    return {"tag": {"key": k, "name": name, "root": bool(n and n["root"])}, "sort": sort, "rule": RULES["tracks"],
            "plays_rule": RULES["plays"], "total": len(rows), "plays": sum(r["plays"] for r in rows),
            "limit": limit, "offset": offset, "items": page}


# --- the genre map -------------------------------------------------------------------------------------------

def genre_map(lib: jd.Library, lad: dict, mvs: list[dict]) -> dict:
    """The whole ladder as lines: one per broad tag, its tags as stations on their rungs."""
    nodes = lad["nodes"]
    mof = movements_of(mvs)

    def station(k: str, parent: str | None, seen: frozenset) -> dict:
        x = nodes[k]
        also = [nodes[p]["name"] for p in x["parents"] if p != parent]
        kids = [c for c in x["children"] if c not in seen]
        return {"key": k, "name": x["name"], "albums": x["albums"], "under": x["under"], "rung": x["rung"],
                "in_use": x["in_use"], "also": also, "movements": [m["id"] for m in mof.get(k, [])],
                "stations": [station(c, k, seen | {k}) for c in kids]}

    def count(st: list[dict]) -> int:
        return sum(1 + count(s["stations"]) for s in st)

    lines = []
    for r in lad["roots"]:
        x = nodes[r]
        st = [station(c, r, frozenset({r})) for c in x["children"]]
        lines.append({"key": r, "name": x["name"], "albums": x["albums"], "under": x["under"], "missing": x["missing"],
                      "in_use": x["in_use"], "tags": x["below"], "stations": st, "stops": count(st),
                      "movements": [m["id"] for m in mof.get(r, [])]})
    alone = [{"key": k, "name": nodes[k]["name"], "albums": nodes[k]["albums"], "under": nodes[k]["under"],
              "movements": [m["id"] for m in mof.get(k, [])]} for k in lad["alone"]]
    return {"lines": lines, "alone": alone, "movements": mvs,
            "summary": {"lines": len(lines), "tags": lad["summary"]["tags"], "alone": len(alone),
                        "shared": lad["summary"]["shared"], "deepest": lad["summary"]["deepest"],
                        "movements": len(mvs)},
            "rules": RULES}


def map_key(conn: sqlite3.Connection) -> str:
    return f"g{MAP_VERSION}|{movements_stamp()}|{tags.cache_key(conn)}"


def overview(conn: sqlite3.Connection) -> dict:
    lib, lad = tags._ready(conn)
    return genre_map(lib, lad, movements(lib, lad))
