"""P3 gate: one song, three servers. Read-only.

Asks a deployed traqfreq for ``GET /api/servers/compare`` and prints its three checks:

1. one to one, per server: every Plex copy whose file the server can see is matched to exactly one item, and no
   item is matched twice;
2. every unmatched copy and item has a reason, and the reasons add up to the unmatched count;
3. a spot check: every case plus 20 copies at random, each asked of Jellyfin and Navidrome by ID (GET only):
   the file and the duration (within 2 s) agree with Plex's.

    python scripts/p3_gate.py --url http://macmini:4492            # today's random sample
    python scripts/p3_gate.py --url http://macmini:4492 --seed 7   # another sample

traqfreq matches from its stored snapshots (press Refresh on SERVERS first for fresh ones) and its spot check
sends GET requests only; this script sends one GET to traqfreq. ``--json`` prints the whole answer. Exit
status 0 = passed, 1 = not passed, 2 = couldn't run.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

ROWS = 10  # failing spot rows printed


def from_url(url: str, seed: int | None) -> dict:
    q = f"?{urllib.parse.urlencode({'seed': seed})}" if seed is not None else ""
    with urllib.request.urlopen(url.rstrip("/") + "/api/servers/compare" + q, timeout=900) as r:
        return json.load(r)


def _n(v) -> str:
    return f"{v:,}" if isinstance(v, int) else str(v)


def _counts(d: dict) -> str:
    return ", ".join(f"{k} {_n(v)}" for k, v in d.items() if v) or "none"


def report(c: dict) -> str:
    one, why, spot = c["checks"]
    out = [f"P3 gate: {_n(c['copies'])} live Plex copies"]
    for s in c["snapshots"]:
        if s["snapshot"]:
            out.append(f"  {s['server']} snapshot: {_n(s['items'])} items, read {round(s['age_s'] / 60)} min ago, "
                       f"{_n(s['hidden_paths'])} hidden paths")
        else:
            out.append(f"  {s['server']}: no snapshot")
    out.append(f"1. one to one: {'passed' if one['passed'] else 'NOT PASSED'}")
    for p in one["pairs"]:
        state = "passed" if p["passed"] else "NOT PASSED"
        if p.get("missing"):
            out.append(f"   plex-{p['pair']:18} {state}: no snapshot")
        elif p["server"]:
            out.append(f"   plex-{p['pair']:18} {state}: {_n(p['visible_matched'])} of {_n(p['visible'])} copies with a "
                       f"file the server has matched; {_n(p['matched'])} matched in all; hidden paths "
                       f"{_n(p['hidden_paths'])}; failures: {_counts(p['failures'])}"
                       + (f" (unmatched: {_counts(p['visible_unmatched'])})" if p["visible_unmatched"] else ""))
        else:
            out.append(f"   {p['pair']:23} {state}: {_n(p['matched'])} matched; items twice {p['failures']['item_twice']}")
    out.append(f"2. reasons: {'passed' if why['passed'] else 'NOT PASSED'}")
    for p in why["pairs"]:
        if p.get("missing"):
            out.append(f"   {p['pair']:23} NOT PASSED: no snapshot")
            continue
        for side in ("left", "right"):
            x = p["sides"][side]
            out.append(f"   {p['pair']:23} {p[side]:9} {'ok' if x['passed'] else 'NOT OK'}: {_n(x['unmatched'])} "
                       f"unmatched = {_counts(x['reasons'])} (sum {_n(x['reasons_sum'])}); "
                       f"{_n(x['matched'])} + {_n(x['unmatched'])} of {_n(x['total'])}")
    out.append(f"3. spot check: {'passed' if spot['passed'] else 'NOT PASSED'}: {spot['sample']} in the sample "
               f"({spot['cases']} cases, {spot['random']} random, seed {spot['seed']}); asked "
               f"{_counts(spot['asked'])}; {_counts(spot['status'])}"
               + (f"; problems: {_counts(spot['problems'])}" if spot["problems"] else ""))
    bad = [r for r in spot["rows"] if not r["passed"]]
    for r in bad[:ROWS]:
        what = (f"copy {r['rating_key']} {r.get('artist')} – {r.get('title')}" if r["kind"] == "copy"
                else f"{r.get('server') or r.get('pair')} item {r['id']}")
        detail = "; ".join(f"{s}: {v['status']}" + (f" ({', '.join(v['problems'])})" if v.get("problems") else "")
                           + (f" ({v['message']})" if v.get("message") else "") for s, v in r["servers"].items())
        out.append(f"     {what} [{', '.join(r['why'])}]: {detail}")
    if len(bad) > ROWS:
        out.append(f"     … {len(bad) - ROWS} more (--json)")
    for n in c.get("notes") or []:
        out.append(f"  note: {n}")
    out.append("PASSED" if c["passed"] else "NOT PASSED")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="a deployed traqfreq, e.g. http://macmini:4492")
    ap.add_argument("--seed", type=int, help="the random sample's seed (default: today's date)")
    ap.add_argument("--json", action="store_true", help="print the whole answer as JSON")
    a = ap.parse_args(argv)
    try:
        c = from_url(a.url, a.seed)
    except Exception as e:  # noqa: BLE001 - say what failed, don't trace
        print(f"couldn't run the gate: {e}", file=sys.stderr)
        return 2
    print(json.dumps(c, indent=1, ensure_ascii=False) if a.json else report(c))
    return 0 if c["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
