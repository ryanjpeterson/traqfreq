"""P4 gate: ladders and per-track tags right. Read-only.

Asks a deployed traqfreq for the three checks, each from the endpoint that answers it (GET only):

1. ladders: ``GET /api/tags/ladder`` ``check``: every broad tag's numbers and children equal jimbo-dj's families,
   run here and as stored (a stored row that differs passes only when it is stale); every ladder ends at
   jimbo-dj's broad tag;
2. per-track tags: ``GET /api/tags/tracks/check``: every live track's tags equal jimbo-dj's
   ``history._genre_tags``, and its kept styles ``genres.Styles.sound_genres``;
3. the audit: ``GET /api/tags/proposals`` ``check``: every tag's numbers, the album issue counts, the fixes and the
   suggestions equal jimbo-dj's stored ``library.tags`` (same stale rule).

    python scripts/p4_gate.py --url http://macmini:4492
    python scripts/p4_gate.py --url http://macmini:4492 --json

``GET /api/tags/compare`` gives the same in one answer (the gate card on SETUP and TAGS); this script reads the
three endpoints, so it also runs against a traqfreq from before T23. Exit status 0 = passed, 1 = not passed,
2 = couldn't run.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from traqfreq import tags_gate  # noqa: E402 - pure: reads answers, imports nothing else of traqfreq

ROWS = 10  # differing rows printed


def get(url: str, path: str) -> dict:
    with urllib.request.urlopen(url.rstrip("/") + path, timeout=900) as r:
        return json.load(r)


def from_url(url: str) -> dict:
    lad = get(url, tags_gate.ENDPOINTS["ladder"])
    trk = get(url, tags_gate.ENDPOINTS["tracks"])
    prop = get(url, tags_gate.ENDPOINTS["audit"])
    return tags_gate.compare(lad["check"], trk, prop["check"])


def _n(v) -> str:
    return f"{v:,}" if isinstance(v, int) else str(v)


def _state(ok: bool) -> str:
    return "passed" if ok else "NOT PASSED"


def report(g: dict) -> str:
    lad, trk, aud = g["checks"]
    out = ["P4 gate: ladders and per-track tags right"]
    out.append(f"1. ladders: {_state(lad['passed'])}")
    r, e, s = lad["rules"], lad["ends"], lad["stored"]
    out.append(f"   jimbo-dj's rules run here: {_n(r['ok'])} of {_n(r['broad'])} broad tags match"
               + (f" (differ: {', '.join(r['differing'][:ROWS])})" if r["differing"] else ""))
    out.append(f"   ladders end at the broad tag: {_n(e['ok'])} of {_n(e['tags'])}"
               + (f" (failing: {', '.join(e['failing'][:ROWS])})" if e["failing"] else ""))
    if s:
        out.append(f"   jimbo-dj's stored library.tags ({'fresh' if s['fresh'] else 'stale'}): {_n(s['ok'])} of "
                   f"{_n(s['broad'])} broad tags match" + (f" (differ: {', '.join(s['differing'][:ROWS])})" if s["differing"] else ""))
    else:
        out.append("   jimbo-dj's stored library.tags: none")
    out.append(f"2. per-track tags: {_state(trk['passed'])}")
    t, st = trk["tags"], trk["styles"]
    out.append(f"   tags: {_n(t['ok'])} of {_n(t['tracks'])} live tracks match ({_n(t['with_tags'])} with a tag)"
               + (f"; differ: {', '.join(map(str, t['differing'][:ROWS]))}" if t["differing"] else ""))
    out.append(f"   styles: {_n(st['ok'])} of {_n(st['tracks'])} match ({_n(st['analysed'])} analysed, {_n(st['kept'])} "
               f"keeping a style)" + (f"; differ: {', '.join(map(str, st['differing'][:ROWS]))}" if st["differing"] else ""))
    out.append(f"3. the audit: {_state(aud['passed'])}")
    if not aud["stored"]:
        out.append("   no stored library.tags in jimbo-dj's database: nothing to compare")
    else:
        a = aud["tags"]
        out.append(f"   stored library.tags is {'fresh' if aud['fresh'] else 'stale'}")
        out.append(f"   tags: {_n(a['ok'])} of {_n(a['tags'])} match (only here {_n(a['only_here'])}, only stored "
                   f"{_n(a['only_stored'])})")
        for d in a["differing"][:ROWS]:
            fields = "; ".join(f"{f} {_n(v[0])} here, {_n(v[1])} stored" for f, v in d["fields"].items()
                               if not isinstance(v[0], (list, dict)))
            out.append(f"     {d['name']}: {fields or 'issues differ'}")
        if a["differ"] > ROWS:
            out.append(f"     … {a['differ'] - ROWS} more (--json)")
        for k, label in (("issues", "album issue kinds"), ("fixes", "fixes"), ("suggestions", "suggestions")):
            p = aud[k]
            out.append(f"   {label}: {_n(p['ok'])} of {_n(p['kinds'] if k == 'issues' else p['items'])} match")
    out.append("PASSED" if g["passed"] else "NOT PASSED")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="a deployed traqfreq, e.g. http://macmini:4492")
    ap.add_argument("--json", action="store_true", help="print the whole answer as JSON")
    a = ap.parse_args(argv)
    try:
        g = from_url(a.url)
    except Exception as e:  # noqa: BLE001 - say what failed, don't trace
        print(f"couldn't run the gate: {e}", file=sys.stderr)
        return 2
    print(json.dumps(g, indent=1, ensure_ascii=False) if a.json else report(g))
    return 0 if g["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
