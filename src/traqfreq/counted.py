"""Counted once (T7), read-only: why each listen that isn't a play isn't one, and patterns among the plays
that jimbo-dj doesn't check.

jimbo-dj's ``dedupe`` stores only a flag (``dup_of``), not the play a listen repeats or duplicates. traqfreq
finds that play again with jimbo-dj's own conditions (vendored ``window_sql``, ``REPEAT_SECONDS``):

- a **repeat** (``dup_of`` = its own source) repeats the nearest listen x of the same source and song
  (``match_key``) logged before it (``x.id < id``) within ``REPEAT_SECONDS``;
- a **duplicate** (``dup_of`` = the winning source) duplicates the nearest play w of that source and song
  within ``MAX(window_sql(loser), window_sql(winner))``.

The gap is ``|Δ started_at|`` in seconds; a flag with no listen in its window is "not found", never hidden.

The checks (burst, loop, steady rhythm; rules in docs/specs/t5-history.md, T7) only report. A play in a
finding is still a play: the count stays jimbo-dj's ``counted = 1`` until HISTORY's cut-over (P6).
"""

from __future__ import annotations

import sqlite3
from collections import Counter

from . import legacy
from .vendor.jimbodj_history import DEDUPE_SECONDS, MIN_PLAY_MS, PRIORITY, REPEAT_SECONDS, window_sql

# Whole seconds, inclusive. The widest window jimbo-dj uses is an hour (Apple Music's daily summary).
GAP_BUCKETS = [(0, 10), (11, 30), (31, 60), (61, 120), (121, 300), (301, 900), (901, 3600)]
WIDEST = 3600

BURST_SECONDS = MIN_PLAY_MS // 1000  # a play needs 30 s; the next one starting sooner can't both have been heard
BURST_MIN = 3
LOOP_MIN = 10
LOOP_SECONDS = 3600
RHYTHM_MIN = 10
RHYTHM_SONGS = 3
RHYTHM_GAP = (30, 600)
RHYTHM_SLACK = 2
NEWEST = 25  # findings listed per check


def _window_case(alias: str, source_col: str) -> str:
    """jimbo-dj's window_sql for whichever source the row ``alias`` has, as one SQL CASE."""
    whens = " ".join(f"WHEN '{s}' THEN {window_sql(s).replace('listens.', f'{alias}.')}" for s in DEDUPE_SECONDS)
    return f"(CASE {source_col} {whens} ELSE {window_sql('')} END)"


# The window between a duplicate l and a candidate play w: MAX(window_sql(loser), window_sql(winner)).
WINDOW = f"MAX({_window_case('l', 'l.source')}, {_window_case('w', 'w.source')})"
DUP_MATCH = (f"w.source = l.dup_of AND w.counted = 1 AND w.match_key = l.match_key "
             f"AND w.started_at BETWEEN l.started_at - {WIDEST} AND l.started_at + {WIDEST} "
             f"AND w.started_at BETWEEN l.started_at - {WINDOW} AND l.started_at + {WINDOW}")
REP_MATCH = (f"x.source = l.source AND x.match_key = l.match_key AND x.id < l.id "
             f"AND x.started_at BETWEEN l.started_at - {REPEAT_SECONDS} AND l.started_at + {REPEAT_SECONDS}")
# The gap (s) from a repeat or duplicate l (alias l) to the listen it repeats or duplicates; NULL = not found.
GAP = (f"(CASE WHEN l.dup_of = l.source "
       f"THEN (SELECT MIN(ABS(x.started_at - l.started_at)) FROM listens x WHERE {REP_MATCH}) "
       f"ELSE (SELECT MIN(ABS(w.started_at - l.started_at)) FROM listens w WHERE {DUP_MATCH}) END)")


def gap_where(gap: str) -> str:
    """SQL for the rows filter ``gap``: "a-b" (seconds, inclusive) or "none" (no listen in the window)."""
    if gap == "none":
        return f"{GAP} IS NULL"
    try:
        a, b = (int(x) for x in gap.split("-", 1))
    except ValueError:
        raise ValueError("gap is a-b (seconds) or none")
    return f"{GAP} BETWEEN {a} AND {b}"


def pair_windows(loser: str, winner: str) -> list[int]:
    """The windows (s) jimbo-dj allows between a ``loser`` listen and a ``winner`` play (two for Apple Music)."""
    def vals(s):
        return [DEDUPE_SECONDS["applemusic"], 3600] if s == "applemusic" else [int(window_sql(s))]
    if loser == winner:
        return [REPEAT_SECONDS]
    return sorted({max(a, b) for a in vals(loser) for b in vals(winner)})


def of_rows(conn: sqlite3.Connection, ids: list[int]) -> dict[int, dict | None]:
    """For each repeat or duplicate listen id: the listen it repeats or duplicates (nearest, then lowest id),
    the gap and the window, or None when none is in its window."""
    out: dict[int, dict | None] = {}
    for i in ids:
        l = conn.execute("SELECT id, source, dup_of FROM listens WHERE id = ?", (i,)).fetchone()
        if l is None or l["dup_of"] is None:
            continue
        if l["dup_of"] == l["source"]:
            r = conn.execute(
                f"SELECT x.id, x.source, x.started_at, x.counted, ABS(x.started_at - l.started_at) gap, {REPEAT_SECONDS} win "
                f"FROM listens l JOIN listens x ON {REP_MATCH} WHERE l.id = ? ORDER BY gap, x.id LIMIT 1", (i,)).fetchone()
        else:
            r = conn.execute(
                f"SELECT w.id, w.source, w.started_at, w.counted, ABS(w.started_at - l.started_at) gap, {WINDOW} win "
                f"FROM listens l JOIN listens w ON {DUP_MATCH} WHERE l.id = ? ORDER BY gap, w.id LIMIT 1", (i,)).fetchone()
        out[i] = None if r is None else {
            "id": r["id"], "source": r["source"], "started_at": legacy._iso(r["started_at"]), "play": r["counted"] == 1,
            "gap_s": r["gap"], "window_s": r["win"]}
    return out


def _order(s: str) -> tuple[int, str]:
    return (PRIORITY.index(s) if s in PRIORITY else len(PRIORITY), s)


def gaps(conn: sqlite3.Connection) -> dict:
    """Every repeat and duplicate by (source, dup_of), with how far each was from the listen it repeats or
    duplicates, in GAP_BUCKETS, and how many have none in their window."""
    pairs: dict[tuple[str, str], dict] = {}
    for source, of, gap in conn.execute(
            f"SELECT l.source, l.dup_of, {GAP} gap FROM listens l WHERE l.counted = 0 AND l.dup_of IS NOT NULL"):
        p = pairs.setdefault((source, of), {
            "source": source, "of": of, "kind": "repeat" if source == of else "duplicate", "listens": 0,
            "windows": pair_windows(source, of), "buckets": [{"min": a, "max": b, "listens": 0} for a, b in GAP_BUCKETS],
            "not_found": 0, "beyond": 0})
        p["listens"] += 1
        if gap is None:
            p["not_found"] += 1
            continue
        for b in p["buckets"]:
            if b["min"] <= gap <= b["max"]:
                b["listens"] += 1
                break
        else:
            p["beyond"] += 1  # can't happen with jimbo-dj's windows; shown so nothing is hidden
    out = sorted(pairs.values(), key=lambda p: (p["kind"] != "repeat", _order(p["source"]), _order(p["of"])))
    return {
        "pairs": out,
        "repeats": sum(p["listens"] for p in out if p["kind"] == "repeat"),
        "duplicates": sum(p["listens"] for p in out if p["kind"] == "duplicate"),
        "not_found": sum(p["not_found"] for p in out),
        "rules": {
            "repeat": f"the nearest earlier listen (lower id) of the same source and match_key within {REPEAT_SECONDS} s",
            "duplicate": "the nearest play (counted = 1) of source dup_of with the same match_key within "
                         "MAX(window_sql(source), window_sql(dup_of)) s",
            "gap": "|started_at - that listen's started_at| in whole seconds",
        },
    }


def _finding(run: list[tuple], tz, **extra) -> dict:
    first, last = run[0], run[-1]
    return {
        "start": first[1], "end": last[1], "first": legacy._iso(first[1]), "last": legacy._iso(last[1]),
        "plays": len(run), "songs": len({r[2] for r in run}), "sources": dict(Counter(r[3] for r in run)),
        "artist": first[4], "title": first[5], **extra}


def _report(findings: list[dict], plays_key: str = "plays") -> dict:
    return {"findings": len(findings), "plays": sum(f[plays_key] for f in findings),
            "newest": sorted(findings, key=lambda f: -f["start"])[:NEWEST]}


def checks(conn: sqlite3.Connection, tz=None) -> dict:
    """Bursts, loops and steady rhythms among the plays (report only; see the module doc)."""
    plays = conn.execute("SELECT id, started_at, match_key, source, artist, title FROM listens "
                         "WHERE counted = 1 ORDER BY started_at, id").fetchall()
    plays = [tuple(r) for r in plays]
    bursts, loops, rhythms = [], [], []

    def runs(same):
        """Maximal runs of consecutive plays where same(prev, cur) holds between each pair."""
        run: list[tuple] = []
        for p in plays:
            if run and same(run[-1], p):
                run.append(p)
            else:
                if run:
                    yield run
                run = [p]
        if run:
            yield run

    for run in runs(lambda a, b: b[1] - a[1] < BURST_SECONDS):
        if len(run) >= BURST_MIN:
            bursts.append(_finding(run, tz, held=len(run) - 1))
    for run in runs(lambda a, b: a[2] == b[2] and b[1] - a[1] <= LOOP_SECONDS):
        if len(run) >= LOOP_MIN:
            loops.append(_finding(run, tz))

    lo, hi = RHYTHM_GAP

    def flush(run, g0):
        if len(run) >= RHYTHM_MIN and len({r[2] for r in run}) >= RHYTHM_SONGS:
            rhythms.append(_finding(run, tz, gap_s=g0))

    run, g0 = [], None
    for p in plays:
        if not run:
            run = [p]
            continue
        g = p[1] - run[-1][1]
        if lo <= g <= hi and (g0 is None or abs(g - g0) <= RHYTHM_SLACK):
            run.append(p)
            g0 = g if g0 is None else g0
            continue
        flush(run, g0)
        # The play before this one may start the next run.
        run, g0 = ([run[-1], p], g) if lo <= g <= hi else ([p], None)
    if run:
        flush(run, g0)

    return {
        "plays_checked": len(plays),
        "burst": {**_report(bursts, "held"), "in_bursts": sum(f["plays"] for f in bursts),
                  "rule": f"{BURST_MIN} or more plays in a row, each starting under {BURST_SECONDS} s after the one before; "
                          f"all but the first are held"},
        "loop": {**_report(loops), "rule": f"the same song {LOOP_MIN} or more plays in a row, each within "
                                           f"{LOOP_SECONDS // 60} min of the one before"},
        "rhythm": {**_report(rhythms), "rule": f"{RHYTHM_MIN} or more plays in a row of at least {RHYTHM_SONGS} songs, every gap "
                                               f"{lo} s to {hi // 60} min and within {RHYTHM_SLACK} s of the first gap"},
    }


def counted(conn: sqlite3.Connection, tz=None) -> dict:
    """What the Counted once page shows: gaps of repeats and duplicates, and the read-only checks."""
    return {"gaps": gaps(conn), "checks": checks(conn, tz), "timezone": str(tz) if tz else None}
