"""Movements, rooted to roaming (P5, T26): how far a line could reach if it followed its tag. New in traqfreq.

jimbo-dj has nothing like it: a line matches its conditions and no more. This is a preview only, read-only, and not
part of the P5 gate. jimbo-dj's picking (vendor/rules.py, junction.py) is not touched, and the Junction's answers
don't move: this module only reads them.

A line **follows** the tag of each ``style`` condition it needs: in its ``all`` or ``any`` parts, not under a
``not`` (widening what a line leaves out would shrink it). The tag is the condition's value through jimbo-dj's tag
rules (vendor/jimbodj_tags.py), as TAGS has it (T20's ladder, T23's movements). Four stops, each taking in the one
before:

1. **rooted**: the tag alone. The line as it is: its count is the Junction's.
2. **ladder**: and every tag under it on its ladder (TAGS, ``tags.descendants_of``).
3. **movement**: and every tag of each movement (``movements.json``) that names one of those.
4. **roaming**: and their neighbours on the genre map: the tags one rung up or down from each (parents and
   children), broad tags left out (a broad tag would take its whole line).

At each stop the followed condition matches any of its tags, each counted the way jimbo-dj counts a ``style``
condition (``rules.leaf_keys``: the track's style score at ``genres.MATCH`` or more); everything else in the line
stays as it is. Every count opens its rows (``rows``). Nothing is saved, picked or written anywhere.
"""
from __future__ import annotations

import sqlite3

from . import playlists, tagpages, tags
from .vendor import jimbodj_tags as jd
from .vendor import rules

STOPS = ("rooted", "ladder", "movement", "roaming")
WHICH = ("count", "added")
FOLLOWS = ("style",)

RULES = {
    "follows": "a line follows the tag of each style condition it needs (in its all or any parts, not under a not), "
               "the condition's value through jimbo-dj's tag rules",
    "rooted": "the tag alone: the line as it is, its count the Junction's",
    "ladder": "and every tag under it on its ladder (TAGS)",
    "movement": "and every tag of each movement (traqfreq's movements.json) naming one of those",
    "roaming": "and their neighbours on the genre map: the tags one rung up or down from each, broad tags left out",
    "count": "the live tracks the line matches at this stop, its followed conditions matching any of the stop's "
             "tags, each counted as jimbo-dj counts a style condition (a style score of at least 0.45)",
    "added": "the live tracks this stop matches that the rooted line doesn't",
    "preview": "A preview only: jimbo-dj's lines don't follow tags, nothing here is picked or saved, and the Junction's "
               "numbers stay as they are. Not part of the P5 gate.",
}


class _Map:
    """TAGS' ladder and movements, read once per answer. Empty when the database has no tags yet."""

    def __init__(self, conn: sqlite3.Connection):
        try:
            self.lib, self.lad = tags._ready(conn)
        except tags.NoTags:
            self.lib, self.lad = None, {"nodes": {}}
        self.nodes = self.lad["nodes"]
        self.movements = tagpages.movements(self.lib, self.lad) if self.lib else []

    def key(self, value: str) -> str | None:
        """The tag a style value names, through jimbo-dj's tag rules (its first part, junk left out)."""
        if self.lib is None:
            return jd.norm(value) or None
        part = next((p for p in self.lib.rules.parse(value) if p["key"] and not p["junk"]), None)
        return part["key"] if part else None

    def name(self, k: str) -> str:
        n = self.nodes.get(k)
        if n:
            return n["name"]
        for m in self.movements:
            for x in m["tags"]:
                if x["key"] == k:
                    return x["name"]
        return k

    def known(self, k: str) -> bool:
        return k in self.nodes or any(x["key"] == k for m in self.movements for x in m["tags"])

    def stops(self, k: str) -> list[list[dict]]:
        """Each stop's new tags, in order: [{key, via, movement?}], every tag once at its first stop."""
        seen = {k}
        out = [[{"key": k, "via": "tag"}]]
        ladder = sorted(tags.descendants_of(self.lad, k), key=self._order) if k in self.nodes else []
        out.append([{"key": d, "via": "ladder"} for d in ladder])
        seen |= set(ladder)
        moved = []
        for m in self.movements:
            if any(x["key"] in seen for x in m["tags"]):
                for x in m["tags"]:
                    if x["key"] not in seen and all(y["key"] != x["key"] for y in moved):
                        moved.append({"key": x["key"], "via": "movement", "movement": m["id"]})
        out.append(moved)
        seen |= {x["key"] for x in moved}
        near = []
        for x in sorted(seen, key=self._order):
            n = self.nodes.get(x)
            if not n:
                continue
            for y in [*n["parents"], *n["children"]]:
                if y not in seen and not self.nodes[y]["root"] and all(z["key"] != y for z in near):
                    near.append({"key": y, "via": "neighbour", "of": x})
        out.append(sorted(near, key=lambda z: self._order(z["key"])))
        return out

    def _order(self, k: str):
        n = self.nodes.get(k)
        return (n["rung"] if n and n["rung"] is not None else 99, -(n["albums"] if n else 0), self.name(k))


def _followed(node: dict, path: str = "", under_not: bool = False) -> list[tuple[str, dict]]:
    """The style conditions a line needs, with their paths (as playlists' rows read them)."""
    if "f" in node:
        return [(path, node)] if node["f"] in FOLLOWS and not under_not else []
    out = []
    for part in ("all", "any", "not"):
        for i, x in enumerate(node.get(part, [])):
            out += _followed(x, f"{path}.{part}.{i}" if path else f"{part}.{i}", under_not or part == "not")
    return out


def _sets(conn: sqlite3.Connection, match: dict, widen: dict[str, set[str]], lib: frozenset) -> set[int]:
    """The line's live tracks with each followed condition (by value) matching any of its tags. With nothing to
    widen it is rules.evaluate itself, so the rooted count is the Junction's."""
    def leaf(f, v):
        if f in FOLLOWS and v in widen:
            return set().union(*(rules.leaf_keys(conn, f, y) for y in widen[v]))
        return rules.leaf_keys(conn, f, v)
    return rules.evaluate(match, leaf, lambda: lib) & lib


def _line(conn: sqlite3.Connection, b: dict, mp: _Map, lib: frozenset) -> tuple[dict, list[set[int]]]:
    follows = []
    for path, c in _followed(b["match"]):
        k = mp.key(c["v"])
        if k and mp.known(k) and all(f["v"] != c["v"] for f in follows):
            follows.append({"path": path, "v": c["v"], "key": k, "text": rules._leaf_text(c["f"], c["v"]),
                            "stops": mp.stops(k)})
    base = {"id": b["id"], "label": b.get("label"), "words": rules.describe(b["match"]),
            "follows": [{"path": f["path"], "value": f["v"], "key": f["key"], "name": mp.name(f["key"]), "text": f["text"],
                         "movements": [{"id": m["id"], "name": m["name"]} for m in mp.movements
                                       if any(x["key"] == f["key"] for x in m["tags"])]} for f in follows]}
    if not follows:
        return base | {"stops": []}, []
    stops, sets = [], []
    widen = {f["v"]: {f["v"]} for f in follows}
    reached = {f["v"]: {f["key"]} for f in follows}
    for i, stop in enumerate(STOPS):
        new = []
        for f in follows:
            if i:
                widen[f["v"]] |= {f["key"]} | {x["key"] for x in f["stops"][i]}
                reached[f["v"]] |= {x["key"] for x in f["stops"][i]}
            new += [{"key": x["key"], "name": mp.name(x["key"]), "via": x["via"], "follows": f["key"],
                     "in_use": bool(mp.nodes.get(x["key"], {}).get("in_use")),
                     **({"movement": x["movement"]} if "movement" in x else {}),
                     **({"of": mp.name(x["of"])} if "of" in x else {})}
                    for x in f["stops"][i]]
        got = _sets(conn, b["match"], widen if i else {}, lib)
        sets.append(got)
        stops.append({"stop": stop, "count": len(got), "added": len(got - sets[0]),
                      "tags": len(set().union(*reached.values())), "new_tags": new})
    return base | {"stops": stops}, sets


def reach(conn: sqlite3.Connection, tree: dict, default_tz: str | None = None) -> dict:
    """Each line of a tree with the tags it follows and its four stops, rooted to roaming. Raises ValueError when
    the tree can't be read."""
    tree = rules.clean(tree)
    mp = _Map(conn)
    with playlists._In(conn, default_tz):
        lib = rules.library(conn)
        lines = [_line(conn, b, mp, lib)[0] for b in tree["branches"]]
    return {"query": rules.to_query(tree), "name": rules.name(tree), "stops": list(STOPS), "lines": lines,
            "following": sum(1 for x in lines if x["stops"]), "movements": len(mp.movements), "rules": RULES}


def reach_from_query(conn: sqlite3.Connection, query: str, default_tz: str | None = None) -> dict:
    return reach(conn, rules.from_query(query), default_tz)


def rows(conn: sqlite3.Connection, tree: dict, line: str, stop: str, which: str = "count", limit: int = 50,
         offset: int = 0, default_tz: str | None = None) -> dict:
    """The live tracks behind a stop's number: all it matches (``count``) or only those the rooted line doesn't
    (``added``), in album order."""
    if stop not in STOPS:
        raise ValueError(f"stop must be one of {', '.join(STOPS)}")
    if which not in WHICH:
        raise ValueError(f"which must be one of {', '.join(WHICH)}")
    tree = rules.clean(tree)
    b = next((x for x in tree["branches"] if x["id"] == line), None)
    if b is None:
        raise playlists.NotFound(f"no line {line!r}")
    mp = _Map(conn)
    with playlists._In(conn, default_tz):
        lib = rules.library(conn)
        out, sets = _line(conn, b, mp, lib)
    if not sets:
        raise playlists.NotFound(f"line {line!r} follows no tag")
    i = STOPS.index(stop)
    keys = sets[i] - sets[0] if which == "added" else sets[i]
    total, page = playlists._rows(conn, keys, max(1, min(limit, 200)), max(0, offset))
    return {"line": line, "stop": stop, "which": which, "words": out["words"], "count": total, "rows": page,
            "limit": limit, "offset": offset, "rule": f"{RULES[stop]}; {RULES[which]}, in album order"}
