"""The Junction (P5, T25): what a tree picks now, read-only. traqfreq's name for jimbo-dj's branch builder.

``build`` runs jimbo-dj's ``rules.build`` (vendor/rules.py, Picking, copied unchanged at 1d8a7cb) the way jimbo-dj's
``POST /api/rules/preview`` does: Never in mixes as ``exclude=bans.get(con) or None``, the index's ``meta``
(vendor/vectors.py) for ``make.details``, every source's plays for ``rank`` (library.track_plays). Each line gets
its ``count``, ``share``, ``got`` and ``available``, the union its ``total``: gate check 1's fields. The picked
tracks each carry the line that took them (``branch``): gate check 2's set. Their order is pick order until T27
copies ``flow.order`` (vendor/flow.py is a stand-in and the answer says so).

Every number has its rows (``rows``): a line's matches, the tracks it got, the pool it chose from, the tracks
Never in mixes left out. Nothing is saved, pushed or written anywhere.
"""
from __future__ import annotations

import sqlite3

from . import legacy, library, playlists
from .vendor import bans, flow, make, rules, vectors
from .vendor import history as vh

WHICH = ("count", "got", "available", "banned", "picked", "total")
TRACK_FIELDS = ("rating_key", "title", "artist", "album", "year", "duration_ms")
RULES = {
    "count": "the live tracks a line's conditions match (rules.branch_sets)",
    "share": "the line's whole number of the playlist's n tracks (rules.quotas, largest remainder)",
    "got": "the tracks the line took: lines take turns toward their shares in order, a track two lines share goes "
           "to the first, a song (artist and title) goes in once, at most per_artist each (rules.pick)",
    "available": "the line's pool: its tracks most played first, up to max(6n, 400), less Never in mixes "
                 "(rules.rank, make.details)",
    "banned": "the line's tracks Never in mixes leaves out: a song, an artist or a style (bans.get), for tracks "
              "jimbo-dj's index knows, as make.details tests them",
    "total": "the live tracks any line matches, each once",
    "picked": "every track picked, each with the line that took it",
    "minutes": "the picked tracks' length, rounded to minutes",
    "order": "pick order: jimbo-dj orders the picked tracks for flow (flow.order), which traqfreq copies in T27",
}


def _bans(conn: sqlite3.Connection) -> bans.Bans:
    """jimbo-dj's Never in mixes, or none when the table isn't there (an old database)."""
    return bans.get(conn) if "bans" in legacy.table_names(conn) else bans.Bans()


class _Run:
    """The vendored rules inside both zones, with every source's plays for ``rank`` (browse._with_plays)."""

    def __init__(self, conn, default_tz):
        self.zones = playlists._In(conn, default_tz)
        self.plays = vh.using(library.track_plays(conn, default_tz))

    def __enter__(self):
        self.zones.__enter__()
        self.plays.__enter__()

    def __exit__(self, *exc):
        self.plays.__exit__(*exc)
        self.zones.__exit__(*exc)


def _track(t: dict) -> dict:
    return {k: t.get(k) for k in TRACK_FIELDS} | {"line": t.get("branch"), "live": True}  # rank keeps live tracks only


def _pick(conn: sqlite3.Connection, tree: dict, default_tz: str | None):
    """jimbo-dj's preview for a cleaned tree, plus each line's banned tracks and the bans' sizes."""
    with _Run(conn, default_tz):
        ban = _bans(conn)
        idx = vectors.get(conn)
        sets = rules.branch_sets(conn, tree, idx)
        r = rules.build(conn, idx, tree, exclude=ban or None, sets=sets)
        banned = [{k for k in s if (m := idx.meta.get(k)) is not None and ban(m)} if ban else set() for s in sets]
    return r, sets, banned, ban


def build(conn: sqlite3.Connection, tree: dict, default_tz: str | None = None) -> dict:
    """The playlist the tree makes now, as jimbo-dj's preview answers it, with each line's conditions and counts
    (playlists.lines) and the rows behind every number. Raises ValueError when the tree can't be read."""
    tree = rules.clean(tree)
    out = playlists.lines(conn, tree, default_tz)
    r, _sets, banned, ban = _pick(conn, tree, default_tz)
    by_id = {b["id"]: b for b in r["branches"]}
    for line, gone in zip(out["lines"], banned):
        b = by_id[line["id"]]
        assert b["count"] == line["count"]  # the same sets, counted twice
        line |= {"got": b["got"], "available": b["available"], "banned": len(gone)}
    labels = {b["id"]: b.get("label") or rules.describe(b["match"]) for b in tree["branches"]}
    tracks = [_track(t) | {"line_name": labels.get(t.get("branch"))} for t in r["tracks"]]
    out |= {
        "summary": rules.summary(tree, len(tracks)),
        "picked": {"count": len(tracks), "minutes": r["minutes"], "tracks": tracks,
                   "order": "pick" if getattr(flow, "STAND_IN", False) else "flow", "seconds": r["seconds"]},
        "bans": {"songs": len(ban.songs), "artists": len(ban.artists), "styles": len(ban.styles)},
        "preview": {"branches": r["branches"], "total": r["total"],
                    "tracks": [{"rating_key": t["rating_key"], "branch": t["line"]} for t in tracks]},
        "rules": out["rules"] | RULES,
        "read_only": "A preview: nothing is saved, and nothing is pushed to Plex, Jellyfin or Navidrome.",
    }
    return out


def build_from_query(conn: sqlite3.Connection, query: str, default_tz: str | None = None) -> dict:
    """Any tree in jimbo-dj's URL form (``b=…&n=…&per=…&shuffle=…``). Nothing is saved."""
    return build(conn, rules.from_query(query), default_tz)


def _pool(conn: sqlite3.Connection, tree: dict, i: int, keys: set[int], ban) -> list[int]:
    """Line i's pool as rules.build makes it before Shuffle's jitter: most played first, up to max(6n, 400),
    less what make.details drops (Never in mixes, tracks it can't describe)."""
    ranked = rules.rank(conn, keys, max(6 * tree["n"], 400))
    details = make.details(conn, vectors.get(conn), ranked, ban or None)
    return [k for k in ranked if k in details]


def rows(conn: sqlite3.Connection, tree: dict, line: str = "", which: str = "count", path: str = "",
         limit: int = 50, offset: int = 0, default_tz: str | None = None) -> dict:
    """The tracks behind one number: a line's ``count`` (or one condition's, ``path``), what it ``got``, its pool
    (``available``), what Never in mixes left out (``banned``), every track ``picked`` or every track any line
    matches (``total``; neither needs a line)."""
    if which not in WHICH:
        raise ValueError(f"which must be one of {', '.join(WHICH)}")
    tree = rules.clean(tree)
    if which == "count":
        return playlists.line_rows(conn, tree, line, path, limit, offset, default_tz) | {"which": "count"}
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    ids = [b["id"] for b in tree["branches"]]
    if which not in ("picked", "total") and line not in ids:
        raise playlists.NotFound(f"no line {line!r}")
    if which == "total":
        with playlists._In(conn, default_tz):
            keys = set().union(*rules.branch_sets(conn, tree))
        total, page = playlists._rows(conn, keys, limit, offset)
        rule = RULES["total"] + ", in album order"
    elif which in ("got", "picked"):
        r, *_ = _pick(conn, tree, default_tz)
        keys = [t["rating_key"] for t in r["tracks"] if which == "picked" or t["branch"] == line]
        total, page = playlists._rows(conn, keys, limit, offset, order=keys)
        lines = {t["rating_key"]: t["branch"] for t in r["tracks"]}
        page = [p | {"line": lines.get(p["rating_key"])} for p in page]
        rule = RULES[which] + ", in " + RULES["order"]
    else:
        i = ids.index(line)
        r, sets, banned, ban = _pick(conn, tree, default_tz)
        if which == "banned":
            total, page = playlists._rows(conn, banned[i], limit, offset)
            rule = RULES["banned"] + ", in album order"
        else:
            with _Run(conn, default_tz):
                keys = _pool(conn, tree, i, sets[i], ban)
            total, page = playlists._rows(conn, keys, limit, offset, order=keys)
            rule = RULES["available"] + ", in that order (before Shuffle's jitter)"
    return {"line": line or None, "which": which, "path": "", "count": total, "rows": page, "limit": limit,
            "offset": offset, "rule": rule}
