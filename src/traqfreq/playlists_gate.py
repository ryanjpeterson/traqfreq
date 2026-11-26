"""The P5 gate, "Same tracks as jimbo-dj" (docs/specs/t24-playlists.md): the comparisons, pure.

Check 1 (lines, T25) and check 2 (tracks: the set from T25, the order from T27, flow.order). ``theirs`` is
jimbo-dj's ``POST /api/rules/preview`` answer for a tree (``branches``: id, count, share, got, available; ``total``;
``tracks`` in play order, each with its ``rating_key`` and ``branch``); ``ours`` is junction.build's ``preview``, the
same shape. Check 3, the saved list, comes with ``scripts/p5_gate.py`` and its trees (T28).
"""
from __future__ import annotations

LINE_FIELDS = ("count", "share", "got", "available")
RULES = {
    "lines": "every line's count, share, got and available, and the union's total, equal jimbo-dj's preview",
    "track_set": "the same picked tracks, each brought in by the same line",
    "order": "the same tracks in the same play order (flow.order); the first place they differ is named",
    "tracks": "check 2: the same tracks in the same order, each brought in by the same line",
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
