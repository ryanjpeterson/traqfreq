"""The P5 gate, "Same tracks as jimbo-dj" (docs/specs/t24-playlists.md): the comparisons, pure.

Check 1 (lines, T25) and check 2 (tracks: the set from T25, the order from T27, flow.order). ``theirs`` is
jimbo-dj's ``POST /api/rules/preview`` answer for a tree (``branches``: id, count, share, got, available; ``total``;
``tracks`` in play order, each with its ``rating_key`` and ``branch``); ``ours`` is junction.build's ``preview``, the
same shape. Check 3 (T28): the saved list, traqfreq's ``GET /api/playlists/compare`` ``saved`` rows against
jimbo-dj's ``GET /api/saved``. ``coverage`` says which kinds of condition the ten trees use, and ``gate`` puts it
together. It imports nothing from traqfreq, so ``scripts/p5_gate.py`` uses it on the answers it fetches.
"""
from __future__ import annotations

GATE_VERSION = 1
TREES = 10
ROWS = 20  # differences kept per tree
SAVED_FIELDS = ("kind", "title", "tracks", "in_plex", "stale")
# The kinds of condition the ten trees must use between them (the spec's list).
CHART = ("quality", "format", "bits", "rate", "bitrate", "channels", "length", "decade", "added", "hour", "weekday",
         "country", "city", "formed", "artist_type", "label", "artist")  # facets.KEYS less family, style, listened
FEATURES = ("and", "or", "not", "nested", "in", "chart", "sound", "genre", "style", "family", "listened")
ENDPOINTS = {"compare": "/api/playlists/compare", "tree": "/api/playlists/compare/trees/{i}",
             "stamp": "/api/playlists/compare/stamp", "saved": "/api/playlists/compare",
             "jimbodj_preview": "POST /api/rules/preview", "jimbodj_saved": "GET /api/saved"}
READ_ONLY = ("Read-only. traqfreq reads jimbo-dj's database opened read-only. Only scripts/p5_gate.py asks "
             "jimbo-dj, with GET /api/saved and POST /api/rules/preview, which builds a preview and writes nothing.")

LINE_FIELDS = ("count", "share", "got", "available")
RULES = {
    "lines": "every line's count, share, got and available, and the union's total, equal jimbo-dj's preview",
    "track_set": "the same picked tracks, each brought in by the same line",
    "order": "the same tracks in the same play order (flow.order); the first place they differ is named",
    "tracks": "check 2: the same tracks in the same order, each brought in by the same line",
    "saved": "check 3: the same saved playlists as jimbo-dj's GET /api/saved, each with the same kind, title, track "
             "count, Plex switch and stale flag",
    "trees": "every saved playlist with a tree (make.spec_of), then p5_trees.json's fixed trees until there are ten; "
             "between them they use AND, OR, NOT, a nested group, an in: scope, a chart bar, a sound filter, genre, "
             "style, family and listened",
    "stamp": "both sides are asked within seconds; if the data stamp moves in between, the tree is asked again once",
    "passed": "passed when the ten trees cover every kind of condition and checks 1, 2 and 3 pass for all of them",
}


def check_lines(ours: dict, theirs: dict) -> dict:
    """Check 1: per line (by id, in jimbo-dj's order) each field, and the total. Every difference is named."""
    mine = {b["id"]: b for b in ours["branches"]}
    lines, ok = [], True
    for b in theirs["branches"]:
        m = mine.get(b["id"])
        fields = {f: {"ours": m.get(f) if m else None, "theirs": b.get(f), "ok": bool(m) and m.get(f) == b.get(f)}
                  for f in LINE_FIELDS}
        good = all(x["ok"] for x in fields.values())
        ok &= good
        lines.append({"id": b["id"], "ok": good, "fields": fields})
    extra = [i for i in mine if i not in {b["id"] for b in theirs["branches"]}]
    total = {"ours": ours["total"], "theirs": theirs["total"], "ok": ours["total"] == theirs["total"]}
    ok = ok and not extra and total["ok"]
    return {"ok": ok, "lines": lines, "extra_lines": extra, "total": total, "rule": RULES["lines"]}


def check_track_set(ours: dict, theirs: dict) -> dict:
    """Check 2's set: the tracks each side picked, and the line that brought each one in."""
    mine = {t["rating_key"]: t["branch"] for t in ours["tracks"]}
    their = {t["rating_key"]: t["branch"] for t in theirs["tracks"]}
    missing = sorted(set(their) - set(mine))
    extra = sorted(set(mine) - set(their))
    other_line = sorted(({"rating_key": k, "ours": mine[k], "theirs": their[k]} for k in set(mine) & set(their)
                         if mine[k] != their[k]), key=lambda x: x["rating_key"])
    return {"ok": not (missing or extra or other_line), "count": {"ours": len(mine), "theirs": len(their)},
            "missing": missing, "extra": extra, "other_line": other_line, "rule": RULES["track_set"]}


def check_order(ours: dict, theirs: dict) -> dict:
    """Check 2's order: the picked tracks' play order, place by place. The first place they differ is named."""
    mine = [t["rating_key"] for t in ours["tracks"]]
    their = [t["rating_key"] for t in theirs["tracks"]]
    first = next((i for i, (a, b) in enumerate(zip(mine, their)) if a != b), None)
    if first is None and len(mine) != len(their):
        first = min(len(mine), len(their))
    at = None if first is None else {"position": first + 1, "ours": mine[first] if first < len(mine) else None,
                                     "theirs": their[first] if first < len(their) else None}
    return {"ok": first is None, "first_difference": at, "rule": RULES["order"]}


def check_tracks(ours: dict, theirs: dict) -> dict:
    """Check 2 in full: the set (each track by the same line) and the order."""
    got_set, got_order = check_track_set(ours, theirs), check_order(ours, theirs)
    return {"ok": got_set["ok"] and got_order["ok"], "set": got_set, "order": got_order, "rule": RULES["tracks"]}


# --- T28: the trees, check 3 and the gate ------------------------------------------------------------------

def features(match: dict) -> set[str]:
    """The kinds of condition a line's group uses (FEATURES)."""
    if "f" in match:
        f = match["f"]
        return {"chart" if f in CHART else "sound" if f in ("bpm", "key", "mood") else f}
    out: set[str] = set()
    if match.get("all"):
        out.add("and")
    if match.get("any"):
        out.add("or")
    if match.get("not"):
        out.add("not")
    for part in ("all", "any", "not"):
        for x in match.get(part, []):
            if "f" not in x:
                out.add("nested")
            out |= features(x)
    return out


def tree_features(tree: dict) -> list[str]:
    got = set().union(*(features(b["match"]) for b in tree["branches"])) if tree["branches"] else set()
    return [f for f in FEATURES if f in got]


def coverage(trees: list[dict]) -> dict:
    """Which of the trees use each kind of condition, and whether every kind is used."""
    by = {f: [i for i, t in enumerate(trees) if f in tree_features(t)] for f in FEATURES}
    return {"ok": all(by.values()) and len(trees) == TREES, "trees": len(trees), "by": by,
            "missing": [f for f, v in by.items() if not v], "rule": RULES["trees"]}


def saved_rows(listing: dict) -> list[dict]:
    """traqfreq's list of jimbo-dj's saved playlists (GET /api/playlists), as check 3 compares it."""
    out = []
    for k in listing["kinds"]:
        for r in k["rows"]:
            plex = next((s for s in r["switches"] if s["server"] == "plex"), {})
            out.append({"id": r["id"], "kind": r["kind"], "title": r["title"], "tracks": r["tracks"],
                        "in_plex": bool(plex.get("on")), "stale": bool(r["stale"])})
    return sorted(out, key=lambda r: r["id"])


def check_saved(ours: list[dict], theirs: list[dict]) -> dict:
    """Check 3: the same rows (by id), each with the same SAVED_FIELDS. ``theirs`` is GET /api/saved's playlists."""
    mine = {r["id"]: r for r in ours}
    their = {r["id"]: r for r in theirs}
    differ = []
    for i in sorted(set(mine) & set(their)):
        f = {k: {"ours": mine[i].get(k), "theirs": _saved(their[i], k)} for k in SAVED_FIELDS
             if mine[i].get(k) != _saved(their[i], k)}
        if f:
            differ.append({"id": i, "title": their[i].get("title"), "fields": f})
    missing, extra = sorted(set(their) - set(mine)), sorted(set(mine) - set(their))
    return {"ok": not (differ or missing or extra), "count": {"ours": len(mine), "theirs": len(their)},
            "same": len(set(mine) & set(their)) - len(differ), "differ": differ[:ROWS], "differ_count": len(differ),
            "missing": missing, "extra": extra, "rule": RULES["saved"]}


def _saved(row: dict, k: str):
    v = row.get(k)
    return bool(v) if k in ("in_plex", "stale") else v


def check_tree(ours: dict, theirs: dict) -> dict:
    """Checks 1 and 2 for one tree: ``ours`` and ``theirs`` in the preview shape (branches, total, tracks)."""
    lines, tracks = check_lines(ours, theirs), check_tracks(ours, theirs)
    s = tracks["set"]
    for k in ("missing", "extra", "other_line"):
        s[k] = s[k][:ROWS]
    return {"ok": lines["ok"] and tracks["ok"], "lines": lines, "tracks": tracks}


def gate(trees: list[dict], results: list[dict], saved: dict) -> dict:
    """The gate from each tree's result (``check_tree`` plus its source and ``asked``), check 3 and the trees'
    coverage. Passed when every kind of condition is used and all three checks pass."""
    cov = coverage(trees)
    one = all(r["lines"]["ok"] for r in results)
    two = all(r["tracks"]["ok"] for r in results)
    checks = [{"check": "lines", "passed": one and len(results) == len(trees), "rule": RULES["lines"],
               "ok": sum(r["lines"]["ok"] for r in results), "trees": len(results)},
              {"check": "tracks", "passed": two and len(results) == len(trees), "rule": RULES["tracks"],
               "ok": sum(r["tracks"]["ok"] for r in results), "trees": len(results)},
              {"check": "saved", "passed": saved["ok"], "rule": RULES["saved"]}]
    return {"gate": "P5", "version": GATE_VERSION, "passed": cov["ok"] and all(c["passed"] for c in checks),
            "coverage": cov, "checks": checks, "trees": results, "saved": saved, "rules": RULES,
            "endpoints": ENDPOINTS, "read_only": READ_ONLY}
