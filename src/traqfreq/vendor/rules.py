"""The branch builder (Library → Tracks): a playlist made of branches, each a set of conditions, merged into
one list with each branch's share of the length.

    {"n": 60, "per_artist": 3, "shuffle": 0,
     "branches": [{"id": "a", "label": "Atmo BM, 2000s", "share": 40,
                   "match": {"all": [{"f": "style", "v": "atmospheric black metal"}, {"f": "decade", "v": "2000s"}]}},
                  {"id": "b", "share": 20,
                   "match": {"all": [{"f": "style", "v": "progressive metal"},
                                     {"any": [{"f": "style", "v": "black metal"}, {"f": "label", "v": "Profound Lore"}]}],
                             "not": [{"f": "style", "v": "depressive black metal"}]}}]}

A condition (a leaf) is any filter Library already has: a chart bar (facets.KEYS), a sound filter (bpm, key,
mood, genre) or a playlist scope (in: cluster:12, saved:4, mix:daily, artist:afi). Each one's tracks come
from the same code the charts count with (facets.members, browse._where), so a branch made from a bar
starts with the bar's number. A group keeps the tracks in every `all`, in any of `any`, and in none of
`not`; groups nest three deep at most.

Shares are track counts adding up to n. Each branch ranks its tracks by plays (Shuffle mixes in a seeded
jitter), then the branches take turns toward their shares, so a track that fits two branches is counted
once, for the first that takes it. A branch that runs short leaves its rest to the others. The picked
tracks are then ordered for flow, as every jimbo-dj playlist is.

The tree also has a URL form (to_query / from_query, mirrored in web/src/lib/rules.ts): one `b` per branch,
`style:progressive metal,(style:black metal|label:Profound Lore),!style:depressive black metal~20`.
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import threading
import time
from collections import Counter, OrderedDict
from urllib.parse import parse_qsl, urlencode

from . import facets, flow  # vendor/facets.py, vendor/flow.py

SOUND = ("bpm", "key", "mood", "genre")
FIELDS = facets.KEYS + SOUND + ("in",)
MAX_DEPTH, MAX_BRANCHES, MAX_LEAVES = 3, 8, 12
DEFAULT_N, MIN_N, MAX_N = 60, 5, 200
_ID = re.compile(r"^[a-z0-9-]{1,12}$")
_BPM = re.compile(r"^(\d+(?:\.\d+)?)?-(\d+(?:\.\d+)?)?$")


# --- Shape ------------------------------------------------------------------------------------------

def quotas(weights: list[float], n: int) -> list[int]:
    """Weights → whole track counts adding up to n (largest remainder)."""
    total = sum(weights)
    if total <= 0:
        weights, total = [1.0] * len(weights), float(len(weights) or 1)
    raw = [n * w / total for w in weights]
    q = [math.floor(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - q[i]))[: n - sum(q)]:
        q[i] += 1
    return q


def _letters(i: int) -> str:
    return chr(ord("a") + i) if i < 26 else f"b{i}"


def _leaf(node: dict) -> dict:
    f, v = node.get("f"), node.get("v")
    if f not in FIELDS:
        raise ValueError(f"no condition {f!r}")
    v = str(v if v is not None else "").strip()[:200]
    if not v:
        raise ValueError(f"{f} needs a value")
    if f in ("style", "mood"):
        v = v.lower()
    if f == "bpm" and not _BPM.match(v):
        raise ValueError("bpm is lo-hi, like 120-130")
    return {"f": f, "v": v}


def _group(node, depth: int, count: list[int]) -> dict:
    if not isinstance(node, dict):
        raise ValueError("a condition is {f, v} or a group of all / any / not")
    if "f" in node:
        count[0] += 1
        if count[0] > MAX_LEAVES:
            raise ValueError(f"a branch has at most {MAX_LEAVES} conditions")
        return _leaf(node)
    if depth > MAX_DEPTH:
        raise ValueError(f"groups nest at most {MAX_DEPTH} deep")
    out = {}
    for part in ("all", "any", "not"):
        xs = node.get(part) or []
        if not isinstance(xs, list):
            raise ValueError(f"{part} is a list")
        xs = [_group(x, depth + 1, count) for x in xs]
        if xs:
            out[part] = xs
    if not out:
        raise ValueError("a group needs at least one condition")
    return out


def clean(tree, n: int | None = None) -> dict:
    """The tree, checked and normalised: ids, shares adding up to n, conditions known. ValueError says what's wrong."""
    if not isinstance(tree, dict):
        raise ValueError("a playlist's rules are {n, branches: [...]}")
    n = max(MIN_N, min(int(n or tree.get("n") or DEFAULT_N), MAX_N))
    branches = tree.get("branches") or []
    if not isinstance(branches, list) or not branches:
        raise ValueError("add at least one branch")
    if len(branches) > MAX_BRANCHES:
        raise ValueError(f"at most {MAX_BRANCHES} branches")
    out, seen = [], set()
    for i, b in enumerate(branches):
        if not isinstance(b, dict):
            raise ValueError("a branch is {share, match}")
        bid = str(b.get("id") or "").lower()
        if not _ID.match(bid) or bid in seen:
            bid = next(_letters(j) for j in range(i, i + 64) if _letters(j) not in seen)
        seen.add(bid)
        item = {"id": bid, "share": max(0.0, float(b.get("share") or 0)), "match": _group(b.get("match"), 1, [0])}
        if label := str(b.get("label") or "").strip()[:80]:
            item["label"] = label
        out.append(item)
    for b, q in zip(out, quotas([b["share"] for b in out], n)):
        b["share"] = q
    return {"n": n, "per_artist": max(1, min(int(tree.get("per_artist") or 3), 20)),
            "shuffle": max(0, int(tree.get("shuffle") or 0)), "branches": out}


def from_filters(filters: dict, n: int = DEFAULT_N) -> dict:
    """An old Library → Tracks filter ({style: grindcore, decade: 1990s}) as a one-branch tree."""
    leaves = [{"f": k, "v": v} for k, v in filters.items() if k in FIELDS and v not in (None, "")]
    if not leaves:
        raise ValueError("pick at least one filter")
    return clean({"n": n, "branches": [{"id": "a", "share": n, "match": {"all": leaves}}]})


def from_blend(parts: list[dict], n: int = DEFAULT_N, per_artist: int = 3, shuffle: int = 0) -> dict:
    """An old genre blend ([{style, weight}]) as one branch per style, with its share."""
    parts = [p for p in parts if str(p.get("style") or "").strip() and float(p.get("weight", 1)) > 0]
    if not parts:
        raise ValueError("pick at least one style with a weight above 0")
    return clean({"n": n, "per_artist": per_artist, "shuffle": shuffle,
                  "branches": [{"share": float(p.get("weight", 1)), "match": {"all": [{"f": "style", "v": p["style"]}]}}
                               for p in parts]})


# --- Words ------------------------------------------------------------------------------------------

def _leaf_text(f: str, v: str) -> str:
    return {"bpm": f"{v} BPM", "listened": f"played in {v}", "in": f"in {v}", "formed": f"formed {v}",
            "added": f"added {v}", "length": f"{v} min"}.get(f, v)


def describe(node: dict, top: bool = True) -> str:
    """A group in words: "progressive metal · (black metal or Profound Lore) · not depressive black metal"."""
    if "f" in node:
        return _leaf_text(node["f"], node["v"])
    parts = [describe(x, False) for x in node.get("all", [])]
    if node.get("any"):
        anys = " or ".join(describe(x, False) for x in node["any"])
        parts.append(anys if top and not parts and not node.get("not") else f"({anys})")
    parts += [f"not {describe(x, False)}" for x in node.get("not", [])]
    text = " · ".join(parts)
    return text if top or len(parts) == 1 else f"({text})"


def name(tree: dict) -> str:
    """What the playlist is called unless you name it."""
    return " + ".join(b.get("label") or describe(b["match"]) for b in tree["branches"])[:120] or "Every track"


def summary(tree: dict, count: int) -> str:
    if len(tree["branches"]) == 1:
        what = f"the tracks in your library that are {describe(tree['branches'][0]['match'])}"
    else:
        what = ", ".join(f"{b['share']} {b.get('label') or describe(b['match'])}" for b in tree["branches"])
    return f"{count} tracks: {what}. Ordered so key and tempo flow. Made by jimbo-dj."


# --- URL form (mirrors web/src/lib/rules.ts) --------------------------------------------------------

_SPECIAL = ",|()!~%"


def _esc(v: str) -> str:
    return "".join(f"%{ord(c):02X}" if c in _SPECIAL else c for c in v)


def _unesc(v: str) -> str:
    return re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m[1], 16)), v)


def _item(node: dict) -> str:
    """One item of a comma list: a condition, (a|b) for any, or a bracketed list."""
    if "f" in node:
        return f"{node['f']}:{_esc(node['v'])}"
    if set(node) == {"any"}:
        return "(" + "|".join(_list(x) for x in node["any"]) + ")"
    return "(" + _list(node) + ")"


def _list(node: dict) -> str:
    """A group as a comma list: its all, its any as one (a|b) item, then !x for each not."""
    if "f" in node:
        return _item(node)
    items = [_item(x) for x in node.get("all", [])]
    if node.get("any"):
        items.append(_item({"any": node["any"]}))
    items += ["!" + _item(x) for x in node.get("not", [])]
    return ",".join(items)


def encode_branch(b: dict) -> str:
    share = int(b["share"]) if float(b["share"]).is_integer() else b["share"]
    out = f"{_list(b['match'])}~{share}"
    return out + (f"~{_esc(b['label'])}" if b.get("label") else "")


class _Parser:
    def __init__(self, s: str):
        self.s, self.i = s, 0

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def list(self, stop: str) -> dict:
        all_, not_ = [], []
        while True:
            neg = self.peek() == "!"
            if neg:
                self.i += 1
            (not_ if neg else all_).append(self.prim())
            if self.peek() != ",":
                break
            self.i += 1
        if self.peek() not in stop:
            raise ValueError(f"can't read the rules at {self.s[self.i:self.i + 12]!r}")
        if len(all_) == 1 and not not_:
            return all_[0]
        g = {}
        if all_:
            g["all"] = all_
        if not_:
            g["not"] = not_
        return g

    def prim(self) -> dict:
        if self.peek() == "(":
            self.i += 1
            alts = [self.list("|)")]
            while self.peek() == "|":
                self.i += 1
                alts.append(self.list("|)"))
            if self.peek() != ")":
                raise ValueError("a ( without its )")
            self.i += 1
            return {"any": alts} if len(alts) > 1 else alts[0]
        j = self.i
        while self.i < len(self.s) and self.s[self.i] not in _SPECIAL.replace("%", ""):
            self.i += 1
        f, _, v = self.s[j:self.i].partition(":")
        return {"f": f.strip(), "v": _unesc(v)}


def decode_branch(raw: str) -> dict:
    p = _Parser(raw)
    m = p.list("~")
    if "f" in m or "any" in m and len(m) == 1:
        m = {"all": [m]}
    rest = raw[p.i + 1:].split("~", 1) if p.peek() == "~" else []
    b = {"match": m, "share": float(rest[0]) if rest and rest[0] else 0}
    if len(rest) > 1 and rest[1]:
        b["label"] = _unesc(rest[1])
    return b


def to_query(tree: dict) -> str:
    pairs = [("b", encode_branch(b)) for b in tree["branches"]]
    pairs += [(k, str(tree[k])) for k, d in (("n", DEFAULT_N), ("per_artist", 3), ("shuffle", 0)) if tree.get(k, d) != d]
    return urlencode([("per" if k == "per_artist" else k, v) for k, v in pairs], safe=":,|()!~")


def from_query(query: str) -> dict:
    """A builder URL's query (b=…, or the old flat ?style=…&decade=…) as a clean tree."""
    q = parse_qsl(query.lstrip("?"), keep_blank_values=False)
    n = next((int(v) for k, v in q if k == "n" and v.isdigit()), DEFAULT_N)
    branches = [decode_branch(v) for k, v in q if k == "b"]
    if not branches:
        return from_filters({k: v for k, v in q if k in FIELDS}, n)
    per = next((int(v) for k, v in q if k == "per" and v.isdigit()), 3)
    shuffle = next((int(v) for k, v in q if k == "shuffle" and v.isdigit()), 0)
    return clean({"n": n, "per_artist": per, "shuffle": shuffle, "branches": branches})


def path(tree: dict) -> str:
    return f"/library/tracks?{to_query(tree)}"


# --- Matching --------------------------------------------------------------------------------------

_leaf_cache: OrderedDict[tuple, frozenset] = OrderedDict()
_leaf_lock = threading.Lock()
_VOLATILE = ("in", "listened")  # saved playlists and your plays change without the data stamp moving


def _stamp(con) -> tuple:
    from . import cache, genres
    return cache.data_stamp(con), genres.version()


def leaf_keys(con: sqlite3.Connection, f: str, v: str, index=None) -> frozenset:
    """The library tracks one condition matches, as the chart that shows it counts them."""
    key = (f, v, _stamp(con)) if f not in _VOLATILE else None
    if key:
        with _leaf_lock:
            if key in _leaf_cache:
                _leaf_cache.move_to_end(key)
                return _leaf_cache[key]
    if f in facets.KEYS:
        got = facets.members(con, f, v)
    elif f == "in":
        got = set(facets.scope(con, v, index)[0])
    elif f == "genre":
        from . import genres
        got = genres.get(con).genre_members(v)
    elif f in SOUND:
        from . import browse
        from .analyzer_version import ANALYZER_VERSION
        where, args = browse._where({f: v}, ANALYZER_VERSION)
        got = {r[0] for r in con.execute("SELECT t.rating_key FROM tracks t LEFT JOIN features f ON f.rating_key = t.rating_key "
                                         f"LEFT JOIN analysis a ON a.rating_key = t.rating_key WHERE {where}", args)}
    else:
        raise ValueError(f"no condition {f!r}")
    got = frozenset(got)
    if key:
        with _leaf_lock:
            _leaf_cache[key] = got
            while len(_leaf_cache) > 512:
                _leaf_cache.popitem(last=False)
    return got


def library(con: sqlite3.Connection) -> frozenset:
    return frozenset(r[0] for r in con.execute("SELECT rating_key FROM tracks WHERE removed_at IS NULL"))


def evaluate(node: dict, leaf, everything) -> set[int]:
    """A group's tracks. leaf(f, v) gives one condition's; everything() the library (for a group of only `not`)."""
    if "f" in node:
        return set(leaf(node["f"], node["v"]))
    out = None
    for x in node.get("all", []):
        s = evaluate(x, leaf, everything)
        out = s if out is None else out & s
    if node.get("any"):
        u = set().union(*(evaluate(x, leaf, everything) for x in node["any"]))
        out = u if out is None else out & u
    if out is None:
        out = set(everything())
    for x in node.get("not", []):
        out -= evaluate(x, leaf, everything)
    return out


def branch_sets(con: sqlite3.Connection, tree: dict, index=None) -> list[set[int]]:
    """Each branch's library tracks."""
    lib = library(con)
    return [evaluate(b["match"], lambda f, v: leaf_keys(con, f, v, index), lambda: lib) & lib for b in tree["branches"]]


# --- Picking ----------------------------------------------------------------------------------------

def pick(pools: list[list[int]], shares: list[int], n: int, per_artist: int, meta: dict[int, dict]) -> tuple[list[tuple[int, int]], list[int]]:
    """Branches take turns toward their shares, each from its pool (best first). A track two branches share
    goes to the first that takes it; a song (artist and title) goes in once; at most per_artist each. A branch
    that runs short leaves the rest to the others, the ones furthest under their share first.
    Returns [(branch, key)] in pick order and how many each branch got."""
    from .similar import _norm_title
    got, cursor = [0] * len(pools), [0] * len(pools)
    picked: list[tuple[int, int]] = []
    used, titles, per = set(), set(), Counter()

    def take(i: int) -> bool:
        pool = pools[i]
        while cursor[i] < len(pool):
            k = pool[cursor[i]]
            cursor[i] += 1
            m = meta[k]
            t = ((m.get("artist") or "").lower(), _norm_title(m.get("title")))
            if k in used or t in titles or per[m.get("artist_key")] >= per_artist:
                continue
            used.add(k)
            titles.add(t)
            per[m.get("artist_key")] += 1
            picked.append((i, k))
            got[i] += 1
            return True
        return False

    active = True
    while active:
        active = False
        for i in range(len(pools)):
            if got[i] < shares[i] and take(i):
                active = True
    short = n - len(picked)
    while short > 0:
        progressed = False
        for i in sorted(range(len(pools)), key=lambda i: got[i] / max(shares[i], 1e-9)):
            if short and take(i):
                short -= 1
                progressed = True
        if not progressed:
            break
    return picked, got


def rank(con: sqlite3.Connection, keys: set[int], limit: int) -> list[int]:
    """The keys, most played first (every source's plays, as Library sorts)."""
    from . import browse
    if not keys:
        return []
    return [r[0] for r in browse._with_plays(con).execute(
        "SELECT t.rating_key FROM tracks t WHERE t.removed_at IS NULL AND t.rating_key IN (SELECT value FROM json_each(?)) "
        f"ORDER BY {browse.SORTS['plays']} LIMIT ?", (json.dumps(sorted(keys)), limit))]


def _jitter(pool: list[int], rng: random.Random) -> list[int]:
    scored = [(1 - i / max(len(pool), 1) + 0.5 * rng.random(), k) for i, k in enumerate(pool)]
    return [k for _, k in sorted(scored, reverse=True)]


def build(con: sqlite3.Connection, index, tree: dict, exclude=None, rest=None, sets: list[set[int]] | None = None) -> dict:
    """The playlist a tree makes now. rest(track) → True leaves a track out when its branch can spare it
    (Keep fresh: played in the last week). Returns the tracks in flow order, each with its branch, and per
    branch how many it matches (count), its share, how many it got and how many it could choose from."""
    from . import make
    t0 = time.time()
    n = tree["n"]
    sets = sets if sets is not None else branch_sets(con, tree, index)
    limit = max(6 * n, 400)
    ranked = [rank(con, s, limit) for s in sets]
    details = make.details(con, index, list(dict.fromkeys(k for pool in ranked for k in pool)), exclude)
    rng = random.Random(f"{tree['shuffle']}:" + json.dumps(tree["branches"], sort_keys=True))
    shares = [b["share"] for b in tree["branches"]]
    pools = []
    for pool, share in zip(ranked, shares):
        pool = [k for k in pool if k in details]
        if rest:
            fresh = [k for k in pool if not rest(details[k])]
            pool = fresh if len(fresh) >= share else pool
        pools.append(_jitter(pool, rng) if tree["shuffle"] else pool)
    picked, got = pick(pools, shares, n, tree["per_artist"], details)
    tracks = []
    for i, k in picked:
        t = dict(details[k])
        t["branch"] = tree["branches"][i]["id"]
        tracks.append(t)
    ordered = flow.order(tracks)
    prev = None
    for c in ordered:
        c["transition"] = flow.describe(prev, c)
        prev = c
    return {
        "branches": [{"id": b["id"], "count": len(s), "share": shares[i], "got": got[i], "available": len(pools[i])}
                     for i, (b, s) in enumerate(zip(tree["branches"], sets))],
        "total": len(set().union(*sets)),
        "tracks": ordered,
        "minutes": round(sum((t.get("duration_ms") or 0) for t in ordered) / 60000),
        "seconds": round(time.time() - t0, 2),
    }


# --- traqfreq: not copied --------------------------------------------------------------------------------
# facet_counts (narrowing a branch) is not copied: P5 has no narrow panel. Every line above is jimbo-dj's,
# unchanged, except the import comment. rank, pick and build call browse, similar, make and flow by jimbo-dj's
# names: vendor/browse.py, vendor/similar.py, vendor/make.py (copies) and vendor/flow.py (stand-in until T27).
VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/rules.py (Shape, Words, URL form, Matching, Picking)"
