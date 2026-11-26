"""PLAYLISTS (P5, T24): jimbo-dj's saved playlists and the lines of the ones that have a tree, read-only.

Every saved playlist (``saved_playlists``, read through the vendored store.py) with its three server switches:
Plex is jimbo-dj's ``in_plex``; Jellyfin and Navidrome are off until P6, when traqfreq keeps all three and pushes.
A playlist has lines when jimbo-dj's ``make.spec_of`` reads a tree from it (a ``rules`` spec, an old Explore
``filter``, a genre blend's ``parts``). Each line, each group and each condition carries the number of live tracks
it matches, counted with jimbo-dj's rules (vendor/rules.py ``leaf_keys``, ``evaluate``, ``branch_sets``), and the
rows behind it. From T25 each switch also says how many of the playlist's stored tracks have a copy on that server
(P3's matches; a missing copy is named with its reason, never dropped), and junction.py picks. Nothing is written
anywhere.
"""
from __future__ import annotations

import json
import sqlite3
from zoneinfo import ZoneInfo

from . import history, legacy, matching
from .vendor import jimbodj_history as jh
from .vendor import jimbodj_insights as ji
from .vendor import make, playlists, rules, store

SERVERS = ("plex", "jellyfin", "navidrome")
# The kinds in the order the list shows them: trees first, then what jimbo-dj makes another way.
KIND_ORDER = ("explore", "blend", "mix", "cluster", "like", "history", "setlist", "plex")
ROW_COLUMNS = "rating_key, title, artist, album, year, duration_ms, removed_at"
ALBUM_ORDER = "artist_key, year, album_key, disc, track_no"  # browse.ORDER, jimbo-dj's album order


class NoPlaylists(Exception):
    """jimbo-dj's database has no saved_playlists table."""


class NotFound(Exception):
    pass


def _check(conn: sqlite3.Connection) -> None:
    if "saved_playlists" not in legacy.table_names(conn):
        raise NoPlaylists("saved_playlists")


def _zones(conn: sqlite3.Connection, default_tz: str | None):
    """jimbo-dj's two zones: the listening history's (``listened``) and its TZ (the Time charts' buckets)."""
    return history.listen_tz(conn, default_tz), ZoneInfo(default_tz or history.DEFAULT_TZ)


class _In:
    """Run the vendored rules inside both zones."""

    def __init__(self, conn, default_tz):
        self.listen, self.charts = _zones(conn, default_tz)

    def __enter__(self):
        self._a, self._b = jh.in_zone(self.listen), ji.in_tz(self.charts)
        self._a.__enter__()
        self._b.__enter__()

    def __exit__(self, *exc):
        self._b.__exit__(*exc)
        self._a.__exit__(*exc)


# --- the switches -----------------------------------------------------------------------------------------

def switches(row: dict, copies: "Copies | None" = None) -> list[dict]:
    """Ryan's three switches, read-only. Plex is jimbo-dj's; Jellyfin and Navidrome have no home until P6. With
    ``copies``, each says how many of the stored tracks have a copy on that server (T25)."""
    out = [
        {"server": "plex", "on": bool(row["in_plex"]), "set_by": "jimbo-dj", "pushed_at": row.get("pushed_at"),
         "plex_key": row.get("plex_key"), "error": row.get("plex_error"), "rule": "saved_playlists.in_plex"},
        {"server": "jellyfin", "on": False, "set_by": None, "from": "P6",
         "rule": "jimbo-dj has no Jellyfin playlists; traqfreq keeps this switch from P6"},
        {"server": "navidrome", "on": False, "set_by": None, "from": "P6",
         "rule": "jimbo-dj has no Navidrome playlists; traqfreq keeps this switch from P6"},
    ]
    if copies is not None:
        for s in out:
            s["copies"] = copies.count(s["server"], row["keys"])
    return out


# --- copies on each server (T25) ------------------------------------------------------------------------

COPY_RULES = {
    "plex": "a live Plex copy: the stored rating key is in jimbo-dj's tracks and not removed",
    "jellyfin": "the Plex copy is matched to an item in the stored Jellyfin snapshot (P3's matches)",
    "navidrome": "the Plex copy is matched to an item in the stored Navidrome snapshot (P3's matches)",
}
MISSING_RULES = {
    "removed": "the track was removed from Plex (tracks.removed_at), so no server has the copy jimbo-dj stored",
    "not_in_library": "the stored rating key isn't in jimbo-dj's tracks at all",
    "no_snapshot": "no snapshot of this server yet: press Refresh on SERVERS to read it (GET requests only)",
    **matching.REASON_RULES,
}


class Copies:
    """Which tracks have a copy on each server: Plex's live tracks, and the copies P3 matched on the others."""

    def __init__(self, conn: sqlite3.Connection, data_dir=None, env_roots: tuple[str, ...] = ()):
        self.live, self.known = set(), set()
        for rk, removed in conn.execute("SELECT rating_key, removed_at FROM tracks"):
            self.known.add(rk)
            if removed is None:
                self.live.add(rk)
        self.has = {"plex": self.live}
        self.reasons: dict[str, dict[int, str]] = {"plex": {}}
        self.snapshot = {"plex": True}
        m = matching.matches(conn, data_dir, env_roots) if data_dir is not None else None
        for s in matching.OTHERS:
            ok = m is not None and s in m.result
            self.snapshot[s] = ok
            self.has[s] = {p["left"] for p in m.result[s]["pairs"]} if ok else set()
            self.reasons[s] = dict(m.result[s]["left"]) if ok else {}

    def reason(self, server: str, rk: int) -> str | None:
        """None when the track has a copy on the server; else why not."""
        if rk in self.has[server]:
            return None
        if rk not in self.known:
            return "not_in_library"
        if rk not in self.live:
            return "removed"
        if not self.snapshot[server]:
            return "no_snapshot"
        return self.reasons[server].get(rk, "not_on_server")

    def count(self, server: str, keys: list[int]) -> dict:
        keys = list(dict.fromkeys(keys))
        why: dict[str, int] = {}
        for k in keys:
            if (r := self.reason(server, k)) is not None:
                why[r] = why.get(r, 0) + 1
        missing = sum(why.values())
        return {"count": len(keys) - missing, "of": len(keys), "missing": missing, "reasons": why,
                "snapshot": self.snapshot[server], "rule": COPY_RULES[server],
                "rows": f"server={server}", "missing_rows": f"server={server}&missing=true"}


# --- the list ---------------------------------------------------------------------------------------------

def tree_of(row: dict) -> dict | None:
    """The playlist's tree, as jimbo-dj's make.spec_of reads it, or None (made another way, or the whole library)."""
    spec = make.spec_of(row)
    return spec["rules"] if spec and spec.get("type") == "rules" else None


def _public(row: dict, copies: Copies | None = None) -> dict:
    tree = tree_of(row)
    spec = make.spec_of(row)
    src = row.get("source") or {}
    return {
        "id": row["id"], "slug": row.get("slug"), "kind": row["kind"], "kind_name": store.KINDS.get(row["kind"], row["kind"]),
        "title": row["title"], "name": playlists.base_name(row["title"]), "summary": row.get("summary"),
        "tracks": row["tracks"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        "stale": row["stale"], "stale_in_plex": row.get("stale_in_plex"),
        "made_by": spec["type"] if spec else ("mix" if src.get("mix") else "cluster" if src.get("cluster_id") else None),
        "from": src.get("from"), "lines": len(tree["branches"]) if tree else 0,
        "switches": switches(row, copies),
    }


def listing(conn: sqlite3.Connection, data_dir=None, env_roots: tuple[str, ...] = ()) -> dict:
    """Every saved playlist, grouped by kind, with how many have lines, are in Plex and are stale. With
    ``data_dir`` (traqfreq's snapshots), each switch has its copies."""
    _check(conn)
    copies = Copies(conn, data_dir, env_roots) if data_dir is not None else None
    keys = {i: json.loads(k or "[]") for i, k in conn.execute("SELECT id, keys FROM saved_playlists")} if copies else {}
    rows = [_public(r | {"keys": keys.get(r["id"], [])}, copies) for r in store.listing(conn)]
    kinds = [{"kind": k, "name": store.KINDS.get(k, k), "count": sum(1 for r in rows if r["kind"] == k),
              "rows": [r for r in rows if r["kind"] == k]}
             for k in KIND_ORDER + tuple(sorted({r["kind"] for r in rows} - set(KIND_ORDER)))]
    on = {s: sum(1 for r in rows for w in r["switches"] if w["server"] == s and w["on"]) for s in SERVERS}
    return {
        "count": len(rows),
        "with_lines": sum(1 for r in rows if r["lines"]),
        "stale": sum(1 for r in rows if r["stale"]),
        "on": on,
        "rules": {"count": "every row of saved_playlists (jimbo-dj's store.listing)",
                  "with_lines": "make.spec_of reads a tree: a rules spec, an Explore filter, a genre blend",
                  "stale": "saved_playlists.stale = 1 (a cluster no longer in the current run, an old mix kind)",
                  "on": "switches that are on, per server"},
        "kinds": [k for k in kinds if k["count"]],
    }


# --- lines ------------------------------------------------------------------------------------------------

def _node(conn, node: dict, lib: frozenset, path: str) -> tuple[dict, set[int]]:
    """A condition or a group, with its count (live tracks) and its path for the rows."""
    if "f" in node:
        got = set(rules.leaf_keys(conn, node["f"], node["v"])) & lib
        return {"type": "condition", "f": node["f"], "v": node["v"], "text": rules._leaf_text(node["f"], node["v"]),
                "count": len(got), "path": path}, got
    out: dict = {"type": "group", "words": rules.describe(node, False), "path": path}
    # The same sums as rules.evaluate: every `all`, then any of `any`, then none of `not`.
    acc = None
    for part in ("all", "any", "not"):
        kids = [_node(conn, x, lib, f"{path}.{part}.{i}" if path else f"{part}.{i}") for i, x in enumerate(node.get(part, []))]
        if not kids:
            continue
        out[part] = [d for d, _ in kids]
        if part == "all":
            for _, s in kids:
                acc = s if acc is None else acc & s
        elif part == "any":
            u = set().union(*(s for _, s in kids))
            acc = u if acc is None else acc & u
        else:
            acc = set(lib) if acc is None else acc
            for _, s in kids:
                acc -= s
    got = (set(lib) if acc is None else acc) & lib
    out["count"] = len(got)
    return out, got


def _walk(root: dict, path: str) -> dict:
    node = root
    if not path:
        return node
    bits = path.split(".")
    if len(bits) % 2:
        raise ValueError(f"no such condition {path!r}")
    for part, i in zip(bits[::2], bits[1::2]):
        xs = node.get(part) if part in ("all", "any", "not") and isinstance(node, dict) else None
        if not xs or not i.isdigit() or int(i) >= len(xs):
            raise ValueError(f"no such condition {path!r}")
        node = xs[int(i)]
    return node


def lines(conn: sqlite3.Connection, tree: dict, default_tz: str | None = None) -> dict:
    """The tree's lines: each with its words, share and conditions, every count as jimbo-dj counts it
    (``rules.branch_sets``), and the union's total. Raises ValueError when a condition can't be read."""
    tree = rules.clean(tree)
    with _In(conn, default_tz):
        lib = rules.library(conn)
        out, union = [], set()
        for b in tree["branches"]:
            match, got = _node(conn, b["match"], lib, "")
            union |= got
            out.append({"id": b["id"], "label": b.get("label"), "share": b["share"], "words": rules.describe(b["match"]),
                        "count": len(got), "match": match})
    return {"n": tree["n"], "per_artist": tree["per_artist"], "shuffle": tree["shuffle"], "name": rules.name(tree),
            "query": rules.to_query(tree), "lines": out, "total": len(union), "library": len(lib),
            "rules": {"count": "the live tracks a line's conditions match (jimbo-dj's rules.branch_sets)",
                      "total": "the live tracks any line matches, each once",
                      "share": "the line's whole number of the playlist's n tracks (rules.quotas)"}}


def lines_from_query(conn: sqlite3.Connection, query: str, default_tz: str | None = None) -> dict:
    """Any tree in jimbo-dj's URL form (``b=…&n=…``), read the same way. Nothing is saved."""
    return lines(conn, rules.from_query(query), default_tz)


def _rows(conn, keys, limit: int, offset: int, order: list[int] | None = None) -> tuple[int, list[dict]]:
    keys = list(keys)
    if not keys:
        return 0, []
    got = {r["rating_key"]: dict(r) for r in conn.execute(
        f"SELECT {ROW_COLUMNS}, {ALBUM_ORDER} FROM tracks WHERE rating_key IN (SELECT value FROM json_each(?))",
        (json.dumps(sorted(set(keys))),))}
    if order is None:
        ordered = sorted(got.values(), key=lambda r: tuple((v is None, v or 0) for v in (r["artist_key"], r["year"], r["album_key"], r["disc"], r["track_no"])))
    else:
        ordered = [got[k] for k in order if k in got]
    page = ordered[offset:offset + limit]
    return len(ordered), [{k: r[k] for k in ("rating_key", "title", "artist", "album", "year", "duration_ms")} | {"live": r["removed_at"] is None}
                          for r in page]


def line_rows(conn: sqlite3.Connection, tree: dict, line: str, path: str = "", limit: int = 50, offset: int = 0,
              default_tz: str | None = None) -> dict:
    """The live tracks behind one line's count, or one of its conditions' (``path``: ``all.0``, ``all.1.any.0``),
    in jimbo-dj's album order."""
    tree = rules.clean(tree)
    b = next((x for x in tree["branches"] if x["id"] == line), None)
    if b is None:
        raise NotFound(f"no line {line!r}")
    with _In(conn, default_tz):
        lib = rules.library(conn)
        node = _walk(b["match"], path)
        keys = rules.evaluate(node, lambda f, v: rules.leaf_keys(conn, f, v), lambda: lib) & lib
    total, rows = _rows(conn, keys, max(1, min(limit, 200)), max(0, offset))
    return {"line": line, "path": path, "words": rules.describe(node), "count": total, "rows": rows,
            "limit": limit, "offset": offset, "rule": "live tracks the conditions match, in album order"}


# --- one playlist -----------------------------------------------------------------------------------------

def _get(conn: sqlite3.Connection, ref: str) -> dict:
    _check(conn)
    pid = store.resolve(conn, ref)
    row = store.get(conn, pid) if pid is not None else None
    if not row:
        raise NotFound(f"no saved playlist {ref!r}")
    return row


def playlist(conn: sqlite3.Connection, ref: str, limit: int = 50, offset: int = 0, default_tz: str | None = None,
             data_dir=None, env_roots: tuple[str, ...] = ()) -> dict:
    """One saved playlist: its switches (with copies, given ``data_dir``), the tracks jimbo-dj stored (play order)
    and, with a tree, its lines (each with what it picks now: junction.build)."""
    from . import junction
    row = _get(conn, ref)
    total, rows = _rows(conn, row["keys"], max(1, min(limit, 200)), max(0, offset), order=row["keys"])
    tree = tree_of(row)
    copies = Copies(conn, data_dir, env_roots) if data_dir is not None else None
    out = {"playlist": _public(row, copies), "stored": {"count": len(row["keys"]), "live": sum(1 for _ in _live(conn, row["keys"])),
                                                "rows": rows, "limit": limit, "offset": offset,
                                                "rule": "saved_playlists.keys, the tracks jimbo-dj stored, in play order"},
           "tree": tree, "lines": None, "lines_error": None}
    if tree:
        try:
            out["lines"] = junction.build(conn, tree, default_tz)
        except ValueError as e:
            out["lines_error"] = str(e)
    return out


def _live(conn, keys):
    if not keys:
        return []
    return conn.execute("SELECT rating_key FROM tracks WHERE removed_at IS NULL AND rating_key IN (SELECT value FROM json_each(?))",
                        (json.dumps(sorted(set(keys))),)).fetchall()


def playlist_rows(conn: sqlite3.Connection, ref: str, line: str, path: str = "", limit: int = 50, offset: int = 0,
                  default_tz: str | None = None) -> dict:
    row = _get(conn, ref)
    tree = tree_of(row)
    if not tree:
        raise NotFound("this playlist has no lines")
    return line_rows(conn, tree, line, path, limit, offset, default_tz)


def copy_rows(conn: sqlite3.Connection, ref: str, server: str, missing: bool | None = None, limit: int = 50,
              offset: int = 0, data_dir=None, env_roots: tuple[str, ...] = ()) -> dict:
    """The stored tracks behind a switch's copies, in play order: each with whether the server has a copy and, if
    not, why (``missing``: only those without, or only those with)."""
    if server not in SERVERS:
        raise ValueError(f"server must be one of {', '.join(SERVERS)}")
    row = _get(conn, ref)
    copies = Copies(conn, data_dir, env_roots)
    keys = list(dict.fromkeys(row["keys"]))
    why = {k: copies.reason(server, k) for k in keys}
    if missing is not None:
        keys = [k for k in keys if (why[k] is not None) == missing]
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    page = keys[offset:offset + limit]
    got = {}
    if page:
        got = {r["rating_key"]: dict(r) for r in conn.execute(
            f"SELECT {ROW_COLUMNS} FROM tracks WHERE rating_key IN (SELECT value FROM json_each(?))", (json.dumps(page),))}
    rows = []
    for k in page:
        r = got.get(k) or {"rating_key": k, "title": None, "artist": None, "album": None, "year": None,
                           "duration_ms": None, "removed_at": None}
        rows.append({f: r[f] for f in ("rating_key", "title", "artist", "album", "year", "duration_ms")}
                    | {"live": k in copies.live, "copy": why[k] is None, "reason": why[k]})
    rule = COPY_RULES[server] + ("; only the tracks without one" if missing else "; only the tracks with one"
                                 if missing is False else "")
    return {"server": server, "missing": missing, "count": len(keys), "rows": rows, "limit": limit, "offset": offset,
            "rule": rule, "reasons": MISSING_RULES}
