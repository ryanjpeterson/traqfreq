"""P5 gate: same tracks as jimbo-dj. Writes nothing.

For ten playlist trees (every saved playlist with a tree, then src/traqfreq/p5_trees.json's fixed ones until there
are ten), asks a deployed traqfreq and a running jimbo-dj for the same tree, within seconds of each other:

1. lines: every line's count, share, got and available, and the union's total, equal jimbo-dj's;
2. tracks: the same tracks in the same order, each brought in by the same line;
3. saved playlists: traqfreq's list equals jimbo-dj's ``GET /api/saved`` (rows, kinds, titles, track counts, Plex
   switches, stale flags).

traqfreq's side is GET only (``/api/playlists/compare``, ``/api/playlists/compare/trees/{i}``,
``/api/playlists/compare/stamp``). jimbo-dj's side is ``GET /api/saved`` and ``POST /api/rules/preview``, which builds
the playlist and writes nothing; this script is the only thing in traqfreq that calls it. If the data stamp moves
between traqfreq's answer and jimbo-dj's, that tree is asked again once.

    python scripts/p5_gate.py --url http://macmini:4492 --jimbodj http://macmini:4490
    python scripts/p5_gate.py --url http://macmini:4492 --json

``--jimbodj`` defaults to the same host on port 4490. Exit status 0 = passed, 1 = not passed, 2 = couldn't run.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from traqfreq import playlists_gate  # noqa: E402 - pure: reads answers, imports nothing else of traqfreq

ROWS = 5  # differences printed per tree
TIMEOUT = 900


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=TIMEOUT) as r:
        return json.load(r)


def post(base: str, path: str, body: dict) -> dict:
    """The one non-GET call: jimbo-dj's POST /api/rules/preview (a preview; jimbo-dj writes nothing)."""
    assert path == "/api/rules/preview", "the gate only POSTs to jimbo-dj's preview"
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def jimbodj_default(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((u.scheme, f"{u.hostname}:4490", "", "", ""))


def ask_tree(url: str, jd: str, i: int, get=get, post=post) -> tuple[dict, dict, dict]:
    """Tree i from both sides; asked again once if the stamp moved in between."""
    for attempt in (1, 2):
        ours = get(url, f"/api/playlists/compare/trees/{i}")
        theirs = post(jd, "/api/rules/preview", {"rules": ours["rules"]})
        after = get(url, "/api/playlists/compare/stamp")["stamp"]
        steady = after == ours["stamp"]
        if steady:
            break
    return ours, theirs, {"attempts": attempt, "steady": steady}


def from_url(url: str, jd: str, get=get, post=post) -> dict:
    c = get(url, "/api/playlists/compare")
    results = []
    for t in c["trees"]:
        try:
            ours, theirs, asked = ask_tree(url, jd, t["i"], get, post)
            r = playlists_gate.check_tree(ours["preview"], theirs)
        except Exception as e:  # noqa: BLE001 - a tree either side can't build fails, and says why
            r, asked = {"ok": False, "error": f"{e.__class__.__name__}: {e}",
                        "lines": {"ok": False}, "tracks": {"ok": False}}, {"attempts": 1, "steady": None}
        results.append(r | {"i": t["i"], "source": t["source"], "query": t["query"], "asked": asked})
    saved = playlists_gate.check_saved(c["saved"]["rows"], get(jd, "/api/saved")["playlists"])
    return playlists_gate.gate([t["rules"] for t in c["trees"]], results, saved)


def _state(ok: bool) -> str:
    return "passed" if ok else "NOT PASSED"


def _name(r: dict) -> str:
    s = r["source"]
    return f"{s['name']} ({'saved ' + str(s['id']) if s['kind'] == 'saved' else 'fixed'})"


def report(g: dict) -> str:
    cov = g["coverage"]
    out = ["P5 gate: same tracks as jimbo-dj",
           f"trees: {cov['trees']} of {playlists_gate.TREES}; every kind of condition used: "
           + ("yes" if not cov["missing"] else f"no (missing: {', '.join(cov['missing'])})")]
    one, two, three = g["checks"]
    out.append(f"1. lines: {_state(one['passed'])} ({one['ok']} of {one['trees']} trees)")
    out.append(f"2. tracks: {_state(two['passed'])} ({two['ok']} of {two['trees']} trees)")
    for r in g["trees"]:
        again = "" if r["asked"]["attempts"] == 1 else (" (asked again: the stamp moved)" if r["asked"]["steady"]
                                                         else " (the stamp moved twice)")
        if r.get("error"):
            out.append(f"   {r['i'] + 1}. {_name(r)}: couldn't compare: {r['error']}")
            continue
        t, s = r["lines"]["total"], r["tracks"]["set"]
        out.append(f"   {r['i'] + 1}. {_name(r)}: lines {_state(r['lines']['ok'])}, total {t['ours']:,} here, "
                   f"{t['theirs']:,} jimbo-dj; tracks {_state(r['tracks']['ok'])}, {s['count']['ours']} here, "
                   f"{s['count']['theirs']} jimbo-dj{again}")
        for line in [x for x in r["lines"]["lines"] if not x["ok"]][:ROWS]:
            fields = "; ".join(f"{f} {v['ours']} here, {v['theirs']} jimbo-dj" for f, v in line["fields"].items() if not v["ok"])
            out.append(f"      line {line['id']}: {fields}")
        if s["missing"] or s["extra"] or s["other_line"]:
            out.append(f"      only jimbo-dj: {s['missing'][:ROWS]}; only here: {s['extra'][:ROWS]}; "
                       f"other line: {len(s['other_line'])}")
        o = r["tracks"]["order"]
        if not o["ok"] and o["first_difference"]:
            d = o["first_difference"]
            out.append(f"      order differs first at {d['position']}: {d['ours']} here, {d['theirs']} jimbo-dj")
    sv = g["saved"]
    out.append(f"3. saved playlists: {_state(three['passed'])} ({sv['same']} of {sv['count']['theirs']} the same; "
               f"{sv['count']['ours']} here)")
    for d in sv["differ"][:ROWS]:
        out.append(f"   {d['id']} {d['title']}: " + "; ".join(f"{k} {v['ours']} here, {v['theirs']} jimbo-dj"
                                                         for k, v in d["fields"].items()))
    if sv["missing"] or sv["extra"]:
        out.append(f"   only jimbo-dj: {sv['missing'][:ROWS]}; only here: {sv['extra'][:ROWS]}")
    out.append("PASSED" if g["passed"] else "NOT PASSED")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="a deployed traqfreq, e.g. http://macmini:4492")
    ap.add_argument("--jimbodj", help="jimbo-dj, e.g. http://macmini:4490 (default: the same host, port 4490)")
    ap.add_argument("--json", action="store_true", help="print the whole answer as JSON")
    a = ap.parse_args(argv)
    try:
        g = from_url(a.url, a.jimbodj or jimbodj_default(a.url))
    except Exception as e:  # noqa: BLE001 - say what failed, don't trace
        print(f"couldn't run the gate: {e}", file=sys.stderr)
        return 2
    print(json.dumps(g, indent=1, ensure_ascii=False) if a.json else report(g))
    return 0 if g["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
