"""TAGS (P4), read-only: the ladder (T20), built on jimbo-dj's tag rules (vendor/jimbodj_tags.py).

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

