"""The P5 gate's traqfreq side (T28): the ten trees, what traqfreq picks for each, and its saved list. Read-only.

``GET /api/playlists/compare`` answers this for the gate card: the ten trees (every saved playlist with a tree, as
``make.spec_of`` reads it, by id; then ``p5_trees.json``'s fixed trees until there are ten), each with its lines'
numbers and what it picks now (junction.build), which kinds of condition they use between them, and the saved list
check 3 compares. jimbo-dj's side is asked only by ``scripts/p5_gate.py``: ``POST /api/rules/preview`` for each tree
(``GET /api/playlists/compare/trees/{i}`` is traqfreq's answer for the same tree) and ``GET /api/saved``. The
comparisons are in playlists_gate.py. Nothing is written anywhere.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import junction, playlists, playlists_gate
from .vendor import rules, store

TREES_FILE = Path(__file__).with_name("p5_trees.json")


def fixed_trees() -> list[dict]:
    return json.loads(TREES_FILE.read_text())["trees"]


def gate_trees(conn: sqlite3.Connection) -> list[dict]:
    """The ten trees: each with where it came from, its cleaned tree and its URL form."""
    playlists._check(conn)
    out = []
    for row in sorted(store.listing(conn), key=lambda r: r["id"]):
        tree = playlists.tree_of(row)
        if tree:
            out.append({"source": {"kind": "saved", "id": row["id"], "slug": row.get("slug"), "title": row["title"],
                                   "name": playlists.playlists.base_name(row["title"])}, "rules": tree})
    for t in fixed_trees():
        if len(out) >= playlists_gate.TREES:
            break
        out.append({"source": {"kind": "fixed", "id": t["id"], "name": t["name"]}, "rules": rules.clean(t["rules"])})
    return [t | {"i": i, "query": rules.to_query(t["rules"]), "features": playlists_gate.tree_features(t["rules"])}
            for i, t in enumerate(out[:playlists_gate.TREES])]


def stamp(conn: sqlite3.Connection) -> str:
    """What both sides' answers depend on: jimbo-dj's data stamp (rules._stamp: the analysed tracks, the last sync,
    the genre rules), the counted listens (plays rank a line's pool; ``listened``) and the saved playlists
    (``in:saved:``, check 3). If it moves between traqfreq's answer and jimbo-dj's, the tree is asked again once."""
    listens = conn.execute("SELECT COUNT(*), MAX(started_at) FROM listens WHERE counted=1").fetchone()
    saved = conn.execute("SELECT COUNT(*), MAX(updated_at) FROM saved_playlists").fetchone()
    return json.dumps([rules._stamp(conn), list(listens), list(saved)], default=str)


def _summary(conn, t: dict, default_tz) -> dict:
    try:
        b = junction.build(conn, t["rules"], default_tz)
    except ValueError as e:
        return {"error": str(e)}
    return {"lines": [{k: x[k] for k in ("id", "label", "words", "share", "count", "got", "available")}
                      for x in b["lines"]],
            "total": b["total"], "picked": b["picked"]["count"], "minutes": b["picked"]["minutes"]}


def compare(conn: sqlite3.Connection, default_tz: str | None = None) -> dict:
    """traqfreq's answers for the gate card: the ten trees with their numbers, their coverage and the saved list."""
    trees = gate_trees(conn)
    saved = playlists_gate.saved_rows(playlists.listing(conn))
    cov = playlists_gate.coverage([t["rules"] for t in trees])
    return {
        "gate": "P5", "version": playlists_gate.GATE_VERSION, "stamp": stamp(conn),
        "trees": [t | _summary(conn, t, default_tz) for t in trees],
        "coverage": cov,
        "saved": {"count": len(saved), "rows": saved},
        "checks": [{"check": c, "rule": playlists_gate.RULES[c], "asked_by": "scripts/p5_gate.py"}
                   for c in ("lines", "tracks", "saved")],
        "script": "python scripts/p5_gate.py --url http://macmini:4492 --jimbodj http://macmini:4490",
        "rules": playlists_gate.RULES, "endpoints": playlists_gate.ENDPOINTS, "read_only": playlists_gate.READ_ONLY,
    }


def tree(conn: sqlite3.Connection, i: int, default_tz: str | None = None) -> dict:
    """traqfreq's answer for tree i, in the shape of jimbo-dj's preview (``preview``), with the stamp it was built on."""
    trees = gate_trees(conn)
    if not 0 <= i < len(trees):
        raise playlists.NotFound(f"no tree {i}")
    t = trees[i]
    before = stamp(conn)
    b = junction.build(conn, t["rules"], default_tz)
    return t | {"stamp": before, "preview": b["preview"], "total": b["total"], "picked": b["picked"]["count"]}
