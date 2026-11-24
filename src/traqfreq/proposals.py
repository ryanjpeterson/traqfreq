"""TAGS (P4), read-only: the proposals inbox (T22) and gate check 3.

Every album's proposed change, as jimbo-dj's audit has it (vendor/jimbodj_tags.py ``Library.albums``: its issues,
each with the fix it would make, its suggestions with their sources and votes, and ``proposed``), before and after
the way Fix in Plex's preview shows it (vendor/tagwrite.py ``proposal`` and ``plan``, copied unchanged). Grouped as
jimbo-dj groups them: by kind of issue (``summary.issues``), by fix (``Library.fixes``) and by suggestion
(``Library.suggestions``), each count opening its albums.

Beside them, traqfreq's own proposals, labelled as such:

- **Ladder** (``ladder``): an album carrying a tag but not the tags above it on the ladder, below the broad tag (an
  album with Atmospheric Black Metal and no Black Metal). The broad tag itself is jimbo-dj's own fix ("Missing its
  broad tag"), so it isn't repeated here.
- **Rule questions** (``rules``): a tag whose broad tag comes from ``genres.family`` matching a word before the
  tag's last one, while no shorter name inside the tag has a broad tag at all ("Drill and Bass" is Hip Hop by its
  "drill"; "Bass" has none). Not a fix: the rules are jimbo-dj's until P6. Each opens the albums carrying the tag.

Nothing is applied, kept or sent: Fix in Plex stays in jimbo-dj until P6.

``check`` is gate check 3: every tag's numbers (albums, artists, tracks, MusicBrainz, sound, issues), the album
issue counts, the fixes and the suggestions, against jimbo-dj's stored ``library.tags``. A stored row that differs
passes only when it is stale (built from an older data stamp), as in check 1.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict

from . import tags
from .vendor import genres
from .vendor import jimbodj_tags as jd
from .vendor import tagwrite

PROPOSALS_VERSION = 1  # bump when the inbox's or the check's answers change (in the cache key)
GROUPS = ("all", "kind", "fix", "suggest", "ladder", "rule")
ALL = 10**9  # jimbo-dj's fixes() and suggestions() take a limit; the inbox lists them all
TAG_FIELDS = ("albums", "artists", "tracks", "musicbrainz", "sound", "issues")

RULES = {
    "all": "every album with a proposed change: an issue jimbo-dj's audit finds, a genre it suggests, or a "
           "ladder proposal of traqfreq's",
    "kind": "albums whose Plex album tags have this kind of issue (jimbo-dj's audit, summary.issues)",
    "fix": "albums this one fix would change (jimbo-dj's fixes(): the same change on every album)",
    "suggest": "albums jimbo-dj's audit suggests this genre for (its sources back it and the album lacks it)",
    "ladder": "traqfreq's proposal: albums carrying a tag below this one on the ladder but not this one (the "
              "broad tag itself is jimbo-dj's Missing its broad tag)",
    "rule": "traqfreq's question: the albums carrying a tag whose broad tag comes from genres.family matching a "
            "word before its last one, while no shorter name inside it has a broad tag",
    "before": "the album's Plex genres now",
    "after": "the album's Plex genres after Fix in Plex's fixes of these kinds (jimbo-dj's tagwrite.proposal); "
             "nothing here applies them",
    "proposed": "jimbo-dj's proposed list: the tags it keeps, the broad tags it adds and the genres it suggests",
    "check": "every tag's numbers (albums, artists, tracks, MusicBrainz, sound, issues), the album issue counts, "
             "the fixes and the suggestions equal jimbo-dj's stored library.tags; a stored row that differs passes "
             "only when it is stale",
}


def cache_key(conn: sqlite3.Connection) -> str:
    return f"p{PROPOSALS_VERSION}|" + tags.cache_key(conn)


def fix_id(f: dict) -> str:
    """A short, stable name for one of jimbo-dj's fixes (op, kind, tag, to): the same change on every album."""
    raw = json.dumps([f["op"], f["kind"], f["tag"], list(f.get("to") or [])], separators=(",", ":"))
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def _issue_fix(i: dict) -> dict:
    return {"op": i["op"], "kind": i["kind"], "tag": i["tag"], "to": list(i.get("to") or [])}


# --- traqfreq's own: the ladder and the rules ------------------------------------------------------------

def _album_keys(lib: jd.Library) -> dict[int, set[str]]:
    by_album: dict[int, set[str]] = defaultdict(set)
    for k, e in lib.index.items():
        if not e["junk"]:
            for a in e["albums"]:
                by_album[a].add(k)
    return by_album


def _above(lad: dict, key: str) -> set[str]:
    """Every tag above one on the ladder, the broad tag left out."""
    nodes, out, todo = lad["nodes"], set(), list(lad["nodes"][key]["parents"])
    while todo:
        p = todo.pop()
        if p in out or nodes[p]["root"]:
            continue
        out.add(p)
        todo += nodes[p]["parents"]
    return out


def ladder_proposals(lib: jd.Library, lad: dict) -> dict[int, list[dict]]:
    """album_key → the tags above its tags on the ladder (below the broad tag) it doesn't carry, each with the
    tags it carries that call for it."""
    nodes = lad["nodes"]
    out: dict[int, list[dict]] = {}
    for a, keys in _album_keys(lib).items():
        need: dict[str, set[str]] = defaultdict(set)
        for k in keys:
            if k in nodes and not nodes[k]["root"] and nodes[k]["broad"]:
                for p in _above(lad, k) - keys:
                    need[p].add(nodes[k]["name"])
        if need:
            out[a] = sorted(({"key": p, "tag": nodes[p]["name"], "because": sorted(b), "rung": nodes[p]["rung"]}
                             for p, b in need.items()), key=lambda x: (x["rung"], x["tag"]))
    return out


def _family_match(key: str) -> tuple[str, re.Match] | None:
    for fam, rx in genres._FAMILIES:
        m = rx.search(key)
        if m:
            return fam, m
    return None


def rule_questions(lib: jd.Library, lad: dict) -> list[dict]:
    """Tags whose broad tag rests on a word before their last one: the rules give it from ``genres.family`` (no
    override names it), the family's match ends before the tag's last word, and no shorter name inside the tag
    has a broad tag of its own."""
    R = lib.rules
    out = []
    for k, n in lad["nodes"].items():
        if not n["in_use"] or n["root"] or not n["broad"] or " " not in k:
            continue
        if any(rx.search(k) for rx, _ in R.overrides):
            continue
        hs = tags.heads(k)
        if not hs or any(R.broad(h) for h in hs):
            continue
        fm = _family_match(k)
        if fm is None or fm[1].end() > k.rfind(" "):
            continue
        last = k.rsplit(" ", 1)[1]
        out.append({"key": k, "tag": n["name"], "broad": n["broad"], "family": fm[0], "match": fm[1].group(0),
                    "last": R.case(last), "albums": n["albums"], "artists": n["artists"]})
    out.sort(key=lambda q: (-q["albums"], q["tag"]))
    return out


# --- the inbox ---------------------------------------------------------------------------------------------

def _context(conn: sqlite3.Connection) -> tuple[jd.Library, dict, dict[int, list[dict]], list[dict]]:
    lib = tags.library(conn)
    lad = tags.ladder(lib)
    return lib, lad, ladder_proposals(lib, lad), rule_questions(lib, lad)


def _has_any(row: dict, lp: dict[int, list[dict]]) -> bool:
    return bool(row["issues"] or row["recs"] or row["album_key"] in lp)


def inbox(conn: sqlite3.Connection) -> dict:
    """The inbox in one go: jimbo-dj's proposals grouped as it groups them, traqfreq's own, Fix in Plex's preview
    counts, and gate check 3 (cached by the caller)."""
    lib, lad, lp, rq = _context(conn)
    s = lib.summary()
    plan = tagwrite.plan(lib, tagwrite.FIXABLE)
    rows = list(lib.albums.values())
    fixes = [{**f, "id": fix_id(f), "label": jd.KINDS[f["kind"]]} for f in lib.fixes(ALL)]
    groups: dict[str, dict] = {}
    for a, props in lp.items():
        for p in props:
            g = groups.setdefault(p["key"], {"key": p["key"], "tag": p["tag"], "rung": p["rung"], "albums": 0,
                                             "because": defaultdict(int)})
            g["albums"] += 1
            for b in p["because"]:
                g["because"][b] += 1
    ladder = sorted(({**g, "because": [b for b, _ in sorted(g["because"].items(), key=lambda kv: (-kv[1], kv[0]))]}
                     for g in groups.values()), key=lambda g: (-g["albums"], g["tag"]))
    return {
        "summary": {
            "albums": len(rows), "proposed": sum(1 for r in rows if _has_any(r, lp)),
            "issues": sum(1 for r in rows if r["issues"]), "clean": s["clean"], "with_recs": s["with_recs"],
            "fixable": plan["albums"], "ladder": len(lp), "rules": len(rq),
        },
        "kinds": [{"kind": k, "label": label, "albums": s["issues"][k], "fixable": k in tagwrite.FIXABLE}
                  for k, label in jd.KINDS.items()],
        "fixable": plan["fixable"], "default": tagwrite.DEFAULT,
        "fixes": fixes,
        "suggestions": lib.suggestions(ALL),
        "ladder": ladder,
        "rules": rq,
        "check": check(lib, tags.stored(conn)),
        "fix_in_plex": {"where": "jimbo-dj", "path": "/library/tags", "port": 4490, "until": "P6"},
        "rule": RULES,
    }


def _picked(row: dict, group: str, value: str | None, fixes: dict[str, dict], lp: dict, rq: dict) -> bool:
    if group == "all":
        return _has_any(row, lp)
    if group == "kind":
        return any(i["kind"] == value for i in row["issues"])
    if group == "fix":
        f = fixes[value]
        return any(_issue_fix(i) == f for i in row["issues"])
    if group == "suggest":
        return any(r["key"] == value for r in row["recs"])
    if group == "ladder":
        return any(p["key"] == value for p in lp.get(row["album_key"], []))
    return False


def _kinds_for(group: str, value: str | None, fixes: dict[str, dict]) -> list[str]:
    """Which of Fix in Plex's kinds the preview uses: the group's own kind when it has one, else all of them."""
    if group == "kind" and value in tagwrite.FIXABLE:
        return [value]
    if group == "kind":
        return []
    if group == "fix":
        return [fixes[value]["kind"]] if fixes[value]["kind"] in tagwrite.FIXABLE else []
    return list(tagwrite.FIXABLE)


def albums(conn: sqlite3.Connection, group: str = "all", value: str | None = None, limit: int = 50,
           offset: int = 0) -> dict:
    """The albums behind one of the inbox's numbers, each with its Plex tags before and after Fix in Plex's
    preview (nothing applied), its issues with their fixes, its suggestions with their sources and votes,
    jimbo-dj's proposed list, and traqfreq's ladder proposals."""
    if group not in GROUPS:
        raise ValueError(f"group is one of {', '.join(GROUPS)}")
    if group != "all" and not value:
        raise ValueError(f"group {group} needs a value")
    lib, lad, lp, rq_list = _context(conn)
    rq = {q["key"]: q for q in rq_list}
    fixes = {fix_id(f): {k: f[k] for k in ("op", "kind", "tag", "to")} for f in lib.fixes(ALL)}
    title: dict = {"group": group, "value": value}
    if group == "kind":
        if value not in jd.KINDS:
            raise tags.NotFound(f"no kind of issue {value!r}")
        title["label"] = jd.KINDS[value]
    elif group == "fix":
        if value not in fixes:
            raise tags.NotFound(f"no fix {value!r} (the tags may have changed since)")
        title["fix"] = {**fixes[value], "label": jd.KINDS[fixes[value]["kind"]]}
    elif group in ("suggest", "ladder", "rule"):
        value = jd.norm(value or "")
        title["value"] = value
        node = lad["nodes"].get(value)
        e = lib.index.get(value)
        title["tag"] = node["name"] if node else e["name"] if e else value
        if group == "rule":
            if value not in rq:
                raise tags.NotFound(f"no rule question for {value!r}")
            title["question"] = rq[value]
        elif group == "ladder" and not any(p["key"] == value for ps in lp.values() for p in ps):
            raise tags.NotFound(f"no ladder proposal adds {value!r}")
    if group == "rule":
        have = lib.index[value]["albums"]
        rows = [r for k, r in lib.albums.items() if k in have]
    else:
        rows = [r for r in lib.albums.values() if _picked(r, group, value, fixes, lp, rq)]
    rows.sort(key=lambda x: ((x["artist"] or "").lower(), x["year"] or 0, (x["title"] or "").lower()))
    kinds = _kinds_for(group, value, fixes)
    page, limit, offset = tags._page(rows, limit, offset)
    items = []
    for r in page:
        after, changes = tagwrite.proposal(r, kinds)
        items.append({
            "album_key": r["album_key"], "title": r["title"], "artist": r["artist"], "artist_key": r["artist_key"],
            "year": r["year"], "before": [t["name"] for t in r["tags"]], "after": after, "changes": changes,
            "issues": r["issues"], "recs": r["recs"], "proposed": r["proposed"], "score": r["score"],
            "ladder": lp.get(r["album_key"], []),
        })
    return {**title, "kinds": kinds, "rule": RULES[group], "total": len(rows), "limit": limit, "offset": offset,
            "items": items, "rules": RULES}


# --- gate check 3 -------------------------------------------------------------------------------------------

def _tag_row(r: dict) -> dict:
    return {"key": r["key"], "name": r["name"], **{f: r[f] for f in TAG_FIELDS}}


def _list_part(ours: list[dict], theirs, fields: tuple[str, ...], limit: int) -> dict:
    """Two ordered lists, item by item on these fields."""
    if not isinstance(theirs, list):
        return {"items": len(ours), "ok": 0, "differ": len(ours), "rows": [], "matches": False, "stored": False}
    pick = lambda x: {f: x.get(f) for f in fields}  # noqa: E731
    a, b = [pick(x) for x in ours], [pick(x) for x in theirs]
    rows = []
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        rows.append({"at": i + 1, "traqfreq": x, "jimbodj": y, "matches": x == y})
    bad = [r for r in rows if not r["matches"]]
    return {"items": len(rows), "ok": len(rows) - len(bad), "differ": len(bad), "rows": rows[:limit],
            "differing": bad[:limit], "matches": not bad, "stored": True}


def check(lib: jd.Library, saved: dict | None, limit: int = 50) -> dict:
    """Gate check 3: the audit's numbers here (jimbo-dj's rules, vendored) against jimbo-dj's stored run."""
    out: dict = {"rule": RULES["check"], "source": "jimbo-dj's stats table, library.tags"}
    value = saved.get("value") if saved else None
    if not isinstance(value, dict):
        return {**out, "stored": None, "passed": False}
    out.update(fresh=saved["fresh"], built_at=saved["built_at"], stored=True)

    ours = {r["key"]: _tag_row(r) for r in lib.tag_rows()}
    stored_tags = value.get("tags")
    if isinstance(stored_tags, list):
        theirs = {r["key"]: {"key": r["key"], "name": r.get("name"), **{f: r.get(f) for f in TAG_FIELDS}}
                  for r in stored_tags}
        keys = list(dict.fromkeys([*ours, *theirs]))
        bad = [{"key": k, "name": (ours.get(k) or theirs.get(k))["name"], "traqfreq": ours.get(k),
                "jimbodj": theirs.get(k)} for k in keys if ours.get(k) != theirs.get(k)]
        out["tags"] = {"tags": len(keys), "ok": len(keys) - len(bad), "differ": len(bad), "differing": bad[:limit],
                       "only_here": sum(1 for k in keys if k not in theirs), "only_stored": sum(1 for k in keys if k not in ours),
                       "fields": list(TAG_FIELDS), "matches": not bad, "stored": True}
    else:
        out["tags"] = {"tags": len(ours), "ok": 0, "differ": len(ours), "differing": [], "fields": list(TAG_FIELDS),
                       "matches": False, "stored": False}

    here = lib.summary()["issues"]
    there = (value.get("summary") or {}).get("issues") if isinstance(value.get("summary"), dict) else None
    rows = [{"kind": k, "label": jd.KINDS[k], "traqfreq": here.get(k, 0),
             "jimbodj": there.get(k) if isinstance(there, dict) else None} for k in jd.KINDS]
    for r in rows:
        r["matches"] = r["traqfreq"] == r["jimbodj"]
    out["issues"] = {"rows": rows, "ok": sum(r["matches"] for r in rows), "kinds": len(rows),
                     "matches": all(r["matches"] for r in rows), "stored": isinstance(there, dict)}
    out["fixes"] = _list_part(lib.fixes(), value.get("fixes"), ("op", "kind", "tag", "to", "albums"), limit)
    out["suggestions"] = _list_part(lib.suggestions(), value.get("suggestions"), ("tag", "key", "albums", "in_use"), limit)
    parts = ("tags", "issues", "fixes", "suggestions")
    out["matches"] = all(out[p]["matches"] for p in parts)
    out["passed"] = out["matches"] or not out["fresh"]
    return out
