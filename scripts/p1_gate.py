"""P1 gate: every HISTORY number jimbo-dj stored, next to traqfreq's for the same period. Read-only.

jimbo-dj keeps its HISTORY numbers in its ``stats`` table (``history.overview`` and one ``history.wrapped``
row per year, month or day). This script puts each stored field next to the one traqfreq works out
(``traqfreq.periods.compare``) and says whether they match. A stored row older than jimbo-dj's data (its stamp
isn't the current one) may differ; that's shown as stale. The gate passes when every row matches, or each
row that differs is stale.

Two ways to run it:

    python scripts/p1_gate.py --url http://macmini:4492        # ask the deployed traqfreq (/api/history/compare)
    python scripts/p1_gate.py --db path/to/jimbodj.sqlite      # read jimbo-dj's DB here (read-only, mode=ro)

``--db`` defaults to TRAQFREQ_LEGACY_DB; TZ is jimbo-dj's TZ when its meta history_tz isn't set. ``--json``
prints the whole comparison. Exit status 0 = passed, 1 = not passed, 2 = couldn't run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def from_db(db: str, tz_env: str | None) -> dict:
    from traqfreq import history, legacy, periods

    conn = legacy.connect(db)  # mode=ro + query_only: jimbo-dj's DB is never written
    try:
        tz = history.listen_tz(conn, tz_env)
        nm = periods.Names(conn)
        today_jd = dt.datetime.now(ZoneInfo(tz_env or history.DEFAULT_TZ)).date().isoformat()
        return periods.compare(conn, tz, nm, today_jd)
    finally:
        conn.close()


def from_url(url: str) -> dict:
    with urllib.request.urlopen(url.rstrip("/") + "/api/history/compare", timeout=600) as r:
        return json.load(r)


def short(v) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 160 else s[:157] + "..."


def report(c: dict) -> str:
    out = [f"P1 gate: {c['stored']} stored rows, {c['matching']} match, {c['differ']} differ "
           f"({c['explained']} of them stale), {c['matching_fields']} of {c['fields']} fields match"]
    for r in c["rows"]:
        name = r["name"] + (f" {r['params']}" if r["params"] else "")
        state = "match" if r["matches"] else ("differs, stale" if r.get("fresh") is False else "DIFFERS")
        out.append(f"  {name:28} {state:15} {r.get('matching', 0)}/{r.get('compared', 0)} fields"
                   f"{'' if r.get('fresh') else '  (stored row is older than the data)'}")
        for f in r.get("fields", []):
            if f["matches"] is False:
                detail = f.get("first_diff") if "first_diff" in f else {"jimbodj": f.get("jimbodj"), "traqfreq": f.get("traqfreq")}
                out.append(f"      {f['field']}: {short(detail)}")
    skipped = c.get("not_in_p1") or {}
    if skipped:
        out.append("  not compared in P1: " + "; ".join(f"{k} ({v})" for k, v in skipped.items()))
    out.append("PASSED" if c["passed"] else "NOT PASSED")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--url", help="a deployed traqfreq, e.g. http://macmini:4492")
    g.add_argument("--db", help="jimbo-dj's jimbodj.sqlite (default: TRAQFREQ_LEGACY_DB)")
    ap.add_argument("--json", action="store_true", help="print the whole comparison as JSON")
    a = ap.parse_args(argv)
    try:
        if a.url:
            c = from_url(a.url)
        else:
            db = a.db or os.environ.get("TRAQFREQ_LEGACY_DB")
            if not db:
                print("give --url or --db (or set TRAQFREQ_LEGACY_DB)", file=sys.stderr)
                return 2
            c = from_db(db, os.environ.get("TZ") or None)
    except Exception as e:  # noqa: BLE001 - say what failed, don't trace
        print(f"couldn't run the gate: {e}", file=sys.stderr)
        return 2
    print(json.dumps(c, indent=1, ensure_ascii=False) if a.json else report(c))
    return 0 if c["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
