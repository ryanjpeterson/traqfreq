"""The P4 gate: ladders and per-track tags right (T23, spec docs/specs/t20-tags.md). Read-only.

The gate is three checks traqfreq already answers; this module only reads their answers and says whether each
passed, with the numbers behind it. It imports nothing from traqfreq, so ``scripts/p4_gate.py`` can use it on
the three answers it GETs from a deployed traqfreq, and ``GET /api/tags/compare`` on the same answers built here.

1. **Ladders** (``GET /api/tags/ladder`` ``check``): every broad tag's numbers and children equal jimbo-dj's
   families, run here and as stored (a stored row that differs passes only when it is stale), and every ladder
   ends at jimbo-dj's broad tag.
2. **Per-track tags** (``GET /api/tags/tracks/check``): every live track's tags equal jimbo-dj's
   ``history._genre_tags``, and its kept styles ``genres.Styles.sound_genres``.
3. **The audit** (``GET /api/tags/proposals`` ``check``): every tag's numbers, the album issue counts, the fixes
   and the suggestions equal jimbo-dj's stored ``library.tags`` (same stale rule).
"""

from __future__ import annotations

GATE_VERSION = 1
ROWS = 20  # differing rows kept per check (the counts are whole)

ENDPOINTS = {"ladder": "/api/tags/ladder", "tracks": "/api/tags/tracks/check", "audit": "/api/tags/proposals"}
RULES = {
    "ladder": "Every broad tag with albums under it has the same albums, albums carrying it, albums missing it and "
              "children (with their albums) as jimbo-dj's families: its rules run here and its stored library.tags "
              "(a stored row that differs passes only when it is stale); every ladder ends at jimbo-dj's broad tag.",
    "tracks": "Every live track's tags equal jimbo-dj's per-track rule (history._genre_tags), and the analyzer "
              "styles it keeps equal jimbo-dj's strict test (genres.Styles.sound_genres).",
    "audit": "Every tag's numbers (albums, artists, tracks, MusicBrainz, sound, issues), the album issue counts, the "
             "fixes and the suggestions equal jimbo-dj's stored library.tags (a stored row that differs passes "
             "only when it is stale).",
    "passed": "Passed when all three checks pass.",
}
READ_ONLY = ("Read-only: the gate reads traqfreq's own answers, built from jimbo-dj's database opened read-only. "
             "Nothing is written to jimbo-dj, Plex or the files.")


def _ok(rows: list[dict]) -> int:
    return sum(1 for r in rows if r.get("matches"))


def ladder(c: dict) -> dict:
    """Check 1 from ``/api/tags/ladder``'s ``check``."""
    st = c.get("stored")
    bad = [r for r in c["rules"]["rows"] if not r["matches"]]
    sbad = [r for r in (st["rows"] if st else []) if not r["matches"]]
    return {
        "check": "ladder", "passed": bool(c["passed"]), "rule": RULES["ladder"], "page": "/tags",
        "rules": {"broad": len(c["rules"]["rows"]), "ok": _ok(c["rules"]["rows"]), "matches": c["rules"]["matches"],
                  "differing": [r["key"] for r in bad][:ROWS]},
        "ends": {"tags": c["ends"]["tags"], "ok": c["ends"]["ok"], "matches": c["ends"]["matches"],
                 "failing": c["ends"]["failing"][:ROWS]},
        "stored": None if not st else {"broad": len(st["rows"]), "ok": _ok(st["rows"]), "matches": st["matches"],
                                       "fresh": st["fresh"], "built_at": st.get("built_at"),
                                       "differing": [r["key"] for r in sbad][:ROWS]},
    }


def tracks(c: dict) -> dict:
    """Check 2 from ``/api/tags/tracks/check``."""
    t, s = c["tags"], c["styles"]
    return {
        "check": "tracks", "passed": bool(c["passed"]), "rule": RULES["tracks"], "page": "/tags",
        "tags": {"tracks": t["tracks"], "ok": t["ok"], "differ": t["differ"], "with_tags": t["with_tags"],
                 "matches": t["matches"], "differing": [x["rating_key"] for x in t["items"]][:ROWS]},
        "styles": {"tracks": s["tracks"], "ok": s["ok"], "differ": s["differ"], "analysed": s["analysed"],
                   "kept": s["kept"], "matches": s["matches"], "differing": [x["rating_key"] for x in s["items"]][:ROWS]},
    }


def _fields(row: dict) -> dict:
    a, b = row.get("traqfreq") or {}, row.get("jimbodj") or {}
    return {f: [a.get(f), b.get(f)] for f in dict.fromkeys([*a, *b]) if f not in ("key", "name") and a.get(f) != b.get(f)}


def audit(c: dict) -> dict:
    """Check 3 from ``/api/tags/proposals``'s ``check``."""
    if not c.get("stored"):
        return {"check": "audit", "passed": False, "rule": RULES["audit"], "page": "/tags/proposals", "stored": False,
                "fresh": None}
    t = c["tags"]
    part = lambda p: {"items": c[p]["items"], "ok": c[p]["ok"], "matches": c[p]["matches"]}  # noqa: E731
    return {
        "check": "audit", "passed": bool(c["passed"]), "rule": RULES["audit"], "page": "/tags/proposals",
        "stored": True, "fresh": c["fresh"], "built_at": c.get("built_at"),
        "tags": {"tags": t["tags"], "ok": t["ok"], "differ": t["differ"], "matches": t["matches"],
                 "only_here": t.get("only_here", 0), "only_stored": t.get("only_stored", 0),
                 "differing": [{"key": r["key"], "name": r["name"], "fields": _fields(r)} for r in t["differing"]][:ROWS]},
        "issues": {"kinds": c["issues"]["kinds"], "ok": c["issues"]["ok"], "matches": c["issues"]["matches"]},
        "fixes": part("fixes"), "suggestions": part("suggestions"),
    }


def compare(ladder_check: dict, tracks_check: dict, audit_check: dict) -> dict:
    """The gate from the three answers: each check, and whether all three passed."""
    checks = [ladder(ladder_check), tracks(tracks_check), audit(audit_check)]
    return {"gate": "P4", "version": GATE_VERSION, "checks": checks, "passed": all(c["passed"] for c in checks),
            "endpoints": ENDPOINTS, "rules": RULES, "read_only": READ_ONLY}
