"""The P3 gate: one song, three servers (T19, spec docs/specs/t13-servers.md). Read-only.

``compare`` runs the gate's three checks on the matches T14 builds from the stored snapshots:

1. **One to one** (``one_to_one``), per server: every Plex copy whose file the server can see (its file key, or
   its loose key, is an item's in the snapshot) is matched to exactly one item; no item is matched by two
   copies unless they are one file (``shared_file``); a match where both sides have a file names the same file.
   A server that hides paths (Navidrome without Report Real Path) gives no file to check, so its check can't
   pass: what the server sees can't be checked. Jellyfin ↔ Navidrome: no item is matched twice on either side.
2. **Reasons** (``reasons``), per pair and side: every record is matched or unmatched, never both; every
   unmatched one has one known reason; the reasons add up to the unmatched count, and matched plus unmatched to
   the total.
3. **Spot check** (``spot``): every case (the first copy or item of each tier, note and reason, on each pair)
   plus ``RANDOM`` copies at random (``seed``), each asked of Jellyfin and Navidrome by ID (GET only, live,
   not from the snapshot): the item is there, its file is the Plex copy's, and its duration is within 2 s of
   Plex's. Plex is read through jimbo-dj's database, so Plex's side is its last sync. An unmatched copy on a
   server is not asked there (it has no ID there); its reason is shown. An unmatched item is asked, and its
   reason checked where it can be (``not_in_plex``: no live copy has its file; ``hidden_path``: still hidden).
   A Jellyfin ↔ Navidrome match not made through Plex is asked of both: the durations within 2 s, and the same
   file only at the file tier (the MusicBrainz and tag tiers pair two files of one recording by design).

The gate passes when all three pass. Nothing is written anywhere: only GET requests leave traqfreq, and the
matches are read from the snapshots already stored.
"""

from __future__ import annotations

import random
import time
from collections import Counter
from datetime import date

import httpx

from . import matching, reading
from .identity import loose_key
from .servers import NAMES
from .settings import Settings

GATE_VERSION = 1
RANDOM = 20
TOLERANCE_MS = matching.TOLERANCE_MS
FAIL_ROWS = 20  # failing rows shown per check and server (the counts are whole)

RULES = {
    "one_to_one": "Every Plex copy whose file the server can see is matched to exactly one item on that server, "
                  "and no item is matched twice (two Plex copies of one file share its item, and say so). A match "
                  "where both sides have a file names the same file. A server that hides its paths gives no file "
                  "to check, so this check can't pass for it. Jellyfin ↔ Navidrome: no item matched twice.",
    "reasons": "Every copy and item is matched or unmatched, never both; every unmatched one has one known reason; "
               "the reasons add up to the unmatched count.",
    "spot": f"Every case (the first copy or item of each tier, note and reason on each pair) plus {RANDOM} copies "
            f"at random, each asked of the server by ID now (GET only): the item is there, its file is the Plex "
            f"copy's and its duration within {TOLERANCE_MS // 1000} s of Plex's (jimbo-dj's last Plex sync).",
    "passed": "Passed when all three checks pass.",
}


def _row(m: matching.Matches, rk: int) -> dict:
    t = m.idn.by_key[rk]
    return {"rating_key": rk, "title": t["title"], "artist": t["track_artist"] or t["artist"], "album": t["album"],
            "file": t["file"], "duration_ms": t["duration_ms"]}


# --- 1. one to one ------------------------------------------------------------------------------------------

def _plex_pair(m: matching.Matches, s: str) -> dict:
    items = m.items[s]
    r = m.result[s]
    files = {i["file"] for i in items.values() if i["file"]}
    looses = {i["loose"] for i in items.values() if i["loose"]}
    visible = [t for t in m.idn.copies if (t["file"] and t["file"] in files) or (t["loose"] and t["loose"] in looses)]
    pairs = {p["left"]: p for p in r["pairs"]}
    fails: dict[str, list] = {"visible_unmatched": [], "item_twice": [], "file_differs": []}
    unmatched_why: Counter = Counter()
    for t in visible:
        if t["rating_key"] not in pairs:
            why = r["left"].get(t["rating_key"])
            unmatched_why[why] += 1
            fails["visible_unmatched"].append({**_row(m, t["rating_key"]), "reason": why})
    by_item: dict[str, list] = {}
    for p in r["pairs"]:
        by_item.setdefault(p["right"], []).append(p)
    for iid, ps in by_item.items():
        if len(ps) > 1 and not (all(p["shared"] for p in ps)
                                and len({m.idn.by_key[p["left"]]["file"] for p in ps}) == 1):
            fails["item_twice"].append({"id": iid, "rating_keys": sorted(p["left"] for p in ps)})
    for p in r["pairs"]:
        cf, it = m.idn.by_key[p["left"]]["file"], items[p["right"]]
        if cf and it["file"] and loose_key(cf) != it["loose"]:
            fails["file_differs"].append({**_row(m, p["left"]), "id": p["right"], "tier": p["tier"],
                                          "item_file": it["file"]})
    hidden = sum(1 for i in items.values() if i["hidden"])
    passed = not hidden and not any(fails.values())
    return {
        "pair": s, "server": s, "passed": passed, "copies": len(m.idn.copies), "items": len(items),
        "visible": len(visible), "visible_matched": len(visible) - len(fails["visible_unmatched"]),
        "matched": len(r["pairs"]), "hidden_paths": hidden,
        "failures": {k: len(v) for k, v in fails.items()},
        "visible_unmatched": dict(unmatched_why),
        "rows": {k: v[:FAIL_ROWS] for k, v in fails.items() if v},
    }


def _between(m: matching.Matches) -> dict:
    r = m.result["jellyfin-navidrome"]
    lc = Counter(p["left"] for p in r["pairs"])
    rc = Counter(p["right"] for p in r["pairs"])
    twice = [{"side": "jellyfin", "id": k, "times": n} for k, n in lc.items() if n > 1] + \
            [{"side": "navidrome", "id": k, "times": n} for k, n in rc.items() if n > 1]
    return {"pair": "jellyfin-navidrome", "server": None, "passed": not twice, "matched": len(r["pairs"]),
            "failures": {"item_twice": len(twice)}, "rows": {"item_twice": twice[:FAIL_ROWS]} if twice else {}}


def one_to_one(m: matching.Matches) -> dict:
    out = []
    for s in matching.OTHERS:
        if s in m.result:
            out.append(_plex_pair(m, s))
        else:
            out.append({"pair": s, "server": s, "passed": False, "missing": "no_snapshot"})
    if "jellyfin-navidrome" in m.result:
        out.append(_between(m))
    return {"check": "one_to_one", "passed": all(p["passed"] for p in out), "rule": RULES["one_to_one"],
            "pairs": out}


# --- 2. reasons ---------------------------------------------------------------------------------------------

def _side(total_ids: list, matched: set, unmatched: dict) -> dict:
    ids = set(total_ids)
    both = matched & set(unmatched)
    neither = ids - matched - set(unmatched)
    unknown = Counter(r for r in unmatched.values() if r not in matching.REASONS)
    by = Counter(unmatched.values())
    adds_up = sum(by.values()) == len(unmatched) == len(ids) - len(matched & ids)
    passed = not both and not neither and not unknown and adds_up and matched <= ids and set(unmatched) <= ids
    return {"total": len(ids), "matched": len(matched), "unmatched": len(unmatched),
            "reasons": {r: by[r] for r in matching.REASONS if by.get(r)}, "reasons_sum": sum(by.values()),
            "both": len(both), "neither": len(neither), "unknown": dict(unknown), "adds_up": adds_up,
            "passed": passed}


def reasons(m: matching.Matches) -> dict:
    out = []
    for pair, (ls, rs) in matching.PAIRS.items():
        if pair not in m.result:
            if pair in matching.OTHERS:
                out.append({"pair": pair, "passed": False, "missing": "no_snapshot"})
            continue
        r = m.result[pair]
        left_ids = [t["rating_key"] for t in m.idn.copies] if ls == "plex" else list(m.items[ls])
        left = _side(left_ids, {p["left"] for p in r["pairs"]}, r["left"])
        right = _side(list(m.items[rs]), {p["right"] for p in r["pairs"]}, r["right"])
        out.append({"pair": pair, "left": ls, "right": rs, "passed": left["passed"] and right["passed"],
                    "sides": {"left": left, "right": right}})
    return {"check": "reasons", "passed": all(p["passed"] for p in out), "rule": RULES["reasons"], "pairs": out}


# --- 3. spot check ------------------------------------------------------------------------------------------

def cases(m: matching.Matches) -> list[dict]:
    """The first copy or item (by ID) of every tier, note and reason on every pair: what each case is."""
    picked: dict[tuple, dict] = {}

    def add(key, entry, why):
        k = (entry["kind"], entry.get("rating_key"), entry.get("server"), entry.get("id"), entry.get("pair"))
        picked.setdefault(k, {**entry, "why": []})["why"].append(why)

    for pair, r in m.result.items():
        ls, rs = matching.PAIRS[pair]
        first: dict[str, dict] = {}
        for p in sorted(r["pairs"], key=lambda p: str(p["left"])):
            notes = [p["tier"]] + (["loose"] if p["how"] == "loose" else []) + \
                    (["shared_file"] if p["shared"] else []) + (["multi_part"] if p.get("multi_part") else [])
            for n in notes:
                first.setdefault(n, p)
        for n, p in first.items():
            if ls == "plex":
                add(n, {"kind": "copy", "rating_key": p["left"]}, f"{pair}: {n}")
            else:
                add(n, {"kind": "pair", "pair": pair, "left_id": p["left"], "id": p["right"], "tier": p["tier"]},
                    f"{pair}: {n}")
        seen: set = set()
        for k, why in sorted(r["left"].items(), key=lambda kv: str(kv[0])):
            if why in seen:
                continue
            seen.add(why)
            if ls == "plex":
                add(why, {"kind": "copy", "rating_key": k}, f"{pair}: {ls} copy unmatched, {why}")
            else:
                add(why, {"kind": "item", "server": ls, "id": k, "reason": why, "other": rs},
                    f"{pair}: {ls} item unmatched, {why}")
        seen = set()
        for k, why in sorted(r["right"].items(), key=lambda kv: str(kv[0])):
            if why in seen:
                continue
            seen.add(why)
            add(why, {"kind": "item", "server": rs, "id": k, "reason": why, "other": ls},
                f"{pair}: {rs} item unmatched, {why}")
    return list(picked.values())


def sample(m: matching.Matches, seed: int, n: int = RANDOM) -> list[dict]:
    """Every case, then ``n`` more Plex copies at random (``random.Random(seed)``) among those matched on at
    least one server and not already in the sample."""
    out = cases(m)
    taken = {e["rating_key"] for e in out if e["kind"] == "copy"}
    matched = set()
    for s in matching.OTHERS:
        if s in m.result:
            matched |= {p["left"] for p in m.result[s]["pairs"]}
    pool = sorted(matched - taken)
    for rk in random.Random(seed).sample(pool, min(n, len(pool))):
        out.append({"kind": "copy", "rating_key": rk, "why": ["random"]})
    return out


class _Asker:
    """Asks each server for items by ID through the read-only client; after a server can't be reached (no
    answer at all), the rest of its items are not asked."""

    def __init__(self, settings: Settings, m: matching.Matches, transport: httpx.BaseTransport | None):
        self.settings, self.m, self.transport = settings, m, transport
        self.clients: dict[str, reading.Client] = {}
        self.down: dict[str, str] = {}

    def ask(self, server: str, item_id: str) -> tuple[dict | None, str | None]:
        if server in self.down:
            return None, f"Not asked: {self.down[server]}"
        if reading.missing_settings(server, self.settings):
            return None, f"{NAMES[server]} is not set up."
        c = self.clients.get(server)
        if c is None:
            c = self.clients[server] = reading.client_for(server, self.settings, self.transport)
        roots = (self.m.snaps.get(server) or {}).get("folders") or []
        try:
            return reading.ITEM_BY_ID[server](c, item_id, roots), None
        except reading.ServerError as e:
            if e.status is None and not isinstance(e, reading.NotFound):
                self.down[server] = e.message
            return None, e.message

    def requests(self) -> dict:
        return {s: self.clients[s].requests if s in self.clients else 0 for s in matching.OTHERS}

    def close(self) -> None:
        for c in self.clients.values():
            c.close()


def _item_view(it: dict | None) -> dict | None:
    if it is None:
        return None
    return {k: it.get(k) for k in ("id", "path", "hidden", "file", "title", "artist", "album", "duration_ms")}


def _same(a: dict, b: dict | None, loose: bool) -> tuple[bool | None, bool | None, int | None, list[str]]:
    """File and duration of ``b`` (asked now) against ``a`` (Plex's copy, or the other server's item)."""
    why = []
    if b is None:
        return None, None, None, why
    if b["hidden"]:
        file_ok = False
        why.append("hidden_path")
    elif not a.get("file") or not b.get("file"):
        file_ok = False
        why.append("no_file")
    else:
        file_ok = (loose_key(a["file"]) == b["loose"]) if loose else a["file"] == b["file"]
        if not file_ok:
            why.append("file_differs")
    da, db = a.get("duration_ms"), b.get("duration_ms")
    diff = abs(da - db) if da and db else None
    dur_ok = diff is not None and diff <= TOLERANCE_MS
    if not dur_ok:
        why.append("no_duration" if diff is None else "duration_differs")
    return file_ok, dur_ok, diff, why


def _check_copy(m: matching.Matches, e: dict, ask: _Asker) -> dict:
    rk = e["rating_key"]
    t = m.idn.by_key[rk]
    out = {**e, **_row(m, rk), "servers": {}}
    for s in matching.OTHERS:
        if s not in m.result:
            out["servers"][s] = {"status": "error", "message": f"No {NAMES[s]} snapshot: press Refresh on SERVERS."}
            continue
        p = next((p for p in m.result[s]["pairs"] if p["left"] == rk), None)
        if p is None:
            out["servers"][s] = {"status": "unmatched", "reason": m.result[s]["left"].get(rk)}
            continue
        it, err = ask.ask(s, p["right"])
        if err:
            out["servers"][s] = {"status": "error", "id": p["right"], "tier": p["tier"], "message": err}
            continue
        file_ok, dur_ok, diff, why = _same(t, it, p["how"] == "loose")
        out["servers"][s] = {"status": "ok" if file_ok and dur_ok else "differs", "id": p["right"], "tier": p["tier"],
                             "file_ok": file_ok, "duration_ok": dur_ok, "diff_ms": diff, "problems": why,
                             "item": _item_view(it)}
    return out


def _check_item(m: matching.Matches, e: dict, ask: _Asker) -> dict:
    s, iid, why = e["server"], e["id"], e["reason"]
    it, err = ask.ask(s, iid)
    out = {**e, "servers": {}}
    if err:
        out["servers"][s] = {"status": "error", "id": iid, "message": err}
        return out
    holds = True
    if why == "not_in_plex":
        holds = not it["loose"] or it["loose"] not in {t["loose"] for t in m.idn.copies if t["loose"]}
    elif why == "hidden_path":  # this item gives no real path, or the server it was matched against doesn't
        other = (m.snaps.get(e["other"]) or {}).get("items") or []
        holds = bool(it["hidden"]) or any(i["hidden"] for i in other)
    elif why == "no_path":
        holds = not it["path"]
    elif why == "outside_roots":
        holds = bool(it["path"]) and not it["hidden"] and not it["file"]
    out["servers"][s] = {"status": "ok" if holds else "differs", "id": iid, "reason": why, "reason_holds": holds,
                         "problems": [] if holds else ["reason_does_not_hold"], "item": _item_view(it)}
    return out


def _check_pair(m: matching.Matches, e: dict, ask: _Asker) -> dict:
    ls, rs = matching.PAIRS[e["pair"]]
    a, aerr = ask.ask(ls, e["left_id"])
    b, berr = ask.ask(rs, e["id"])
    out = {**e, "servers": {}}
    if aerr or berr:
        out["servers"][ls] = {"status": "error" if aerr else "ok", "id": e["left_id"], "message": aerr,
                              "item": _item_view(a)}
        out["servers"][rs] = {"status": "error" if berr else "ok", "id": e["id"], "message": berr, "item": _item_view(b)}
        return out
    file_ok, dur_ok, diff, why = _same(a, b, True)
    if a["hidden"] and "hidden_path" not in why:
        file_ok = False
        why.insert(0, "hidden_path")
    if e["tier"] not in ("file", "plex"):  # MusicBrainz IDs or tags: two files of one recording, by design
        file_ok, why = None, [w for w in why if w not in ("hidden_path", "no_file", "file_differs")]
    out["servers"][ls] = {"status": "ok", "id": e["left_id"], "item": _item_view(a)}
    out["servers"][rs] = {"status": "ok" if file_ok is not False and dur_ok else "differs", "id": e["id"],
                          "tier": e["tier"], "file_ok": file_ok,
                          "duration_ok": dur_ok, "diff_ms": diff, "problems": why, "item": _item_view(b)}
    return out


def spot(m: matching.Matches, settings: Settings, seed: int, transport: httpx.BaseTransport | None = None) -> dict:
    entries = sample(m, seed)
    ask = _Asker(settings, m, transport)
    t0 = time.perf_counter()
    try:
        rows = [(_check_copy if e["kind"] == "copy" else _check_item if e["kind"] == "item" else _check_pair)(m, e, ask)
                for e in entries]
    finally:
        ask.close()
    status = Counter(v["status"] for r in rows for v in r["servers"].values())
    problems = Counter(p for r in rows for v in r["servers"].values() for p in v.get("problems") or [])
    for r in rows:
        r["passed"] = all(v["status"] in ("ok", "unmatched") for v in r["servers"].values())
    missing = [s for s in matching.OTHERS if s not in m.result]
    return {"check": "spot", "passed": not missing and all(r["passed"] for r in rows), "rule": RULES["spot"],
            "seed": seed, "sample": len(rows), "cases": sum(1 for r in rows if r["why"] != ["random"]),
            "random": sum(1 for r in rows if r["why"] == ["random"]), "asked": ask.requests(),
            "status": dict(status), "problems": dict(problems), "failed": sum(1 for r in rows if not r["passed"]),
            "seconds": round(time.perf_counter() - t0, 3), "missing": missing, "tolerance_ms": TOLERANCE_MS,
            "rows": rows}


# --- the gate -----------------------------------------------------------------------------------------------

def notes(m: matching.Matches) -> list[str]:
    out = []
    for s in matching.OTHERS:
        snap = m.snaps.get(s)
        if snap is None:
            out.append(f"{NAMES[s]} has no snapshot: press Refresh on SERVERS (GET requests only).")
            continue
        hidden = sum(1 for i in snap["items"] if i["hidden"])
        if hidden:
            out.append(f"{NAMES[s]} gives no real path for {hidden:,} of {len(snap['items']):,} items"
                       f"{' (Report Real Path is off for the player traqfreq logs in as)' if s == 'navidrome' else ''}: "
                       f"there is no file to check there, so checks 1 and 3 can't pass for {NAMES[s]}.")
    return out


def compare(conn, settings: Settings, seed: int | None = None, transport: httpx.BaseTransport | None = None) -> dict:
    """``GET /api/servers/compare``: the three checks and whether the gate passed."""
    m = matching.matches(conn, settings.data_dir, settings.plex_roots)
    seed = int(date.today().strftime("%Y%m%d")) if seed is None else int(seed)
    now = time.time()
    checks = [one_to_one(m), reasons(m), spot(m, settings, seed, transport)]
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "notes": notes(m),
        "snapshots": [matching._snapshot_info(s, m.snaps.get(s), now) for s in matching.OTHERS],
        "copies": len(m.idn.copies),
        "rules": RULES,
        "read_only": "Matched from the stored snapshots; the spot check sends GET requests only. Nothing is "
                     "written to any server, to jimbo-dj's database or to traqfreq's.",
        "version": GATE_VERSION,
    }
