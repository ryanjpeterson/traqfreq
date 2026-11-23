"""Matching Plex copies to server items, on snapshots (T14, spec docs/specs/t13-servers.md).

``match(left, right)`` is the one rule, used for every pair: Plex ↔ Jellyfin, Plex ↔ Navidrome, and
Jellyfin ↔ Navidrome for the items Plex doesn't join. The tiers, in order, each said on the match (W3):

1. ``file``: the same file key; then the same loose key (case-folded), when only one item has it.
2. ``mbid``: the same MusicBrainz recording and release. Plex has no per-track MusicBrainz ID, so a Plex copy
   borrows the IDs of the item its file matched on the *other* server ("inherits Plex's file match").
3. ``tags``: the same match key (history.py), album (``norm_title``), disc and track number, durations within
   2 s; only when exactly one candidate is left.

One to one, per server: an item matched at one tier is not offered at the next. Two Plex copies of one file
(``shared_file``) both match its item, and say so. A tier that finds more than one candidate for a copy, or
one candidate that two copies want, stops there: ``ambiguous``. Every unmatched copy and item gets exactly one
reason, so the reasons add up to the unmatched counts.

Read-only: copies come from identity.py, items from stored snapshots; nothing is sent to any server.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict

from . import identity as identity_mod
from . import store
from .snapshots import FOLDER_SOURCES, folder_of
from .vendor.jimbodj_history import match_key, norm_title

MATCH_VERSION = 1
TIERS = ("file", "mbid", "tags")
TOLERANCE_MS = 2000
OTHERS = ("jellyfin", "navidrome")
PAIRS = {"jellyfin": ("plex", "jellyfin"), "navidrome": ("plex", "navidrome"),
         "jellyfin-navidrome": ("jellyfin", "navidrome")}

TIER_RULES = {
    "file": "The same file key (the path below each server's music folder); then the same loose key "
            "(case-folded), only when exactly one item has it.",
    "mbid": "The same MusicBrainz recording and release, from the server's tags. A Plex copy has none of its "
            "own: it uses the IDs of the item its file matched on the other server.",
    "tags": "The same match key (artist|title, normalised as listens are), album, disc and track number, and "
            "durations within 2 s; only when exactly one candidate is left.",
    "plex": "Jellyfin ↔ Navidrome: both items are matched to the same Plex copy.",
}

REASONS = ("no_path", "outside_roots", "not_on_server", "ambiguous", "hidden_path", "not_in_plex", "multi_part")
REASON_RULES = {
    "no_path": "No file to match by: Plex gives no path for the copy, or the server none for the item; "
               "the MusicBrainz and tag tiers found nothing either.",
    "outside_roots": "The file is outside the known music folders, so it has no file key; the MusicBrainz and "
                     "tag tiers found nothing either.",
    "not_on_server": "No item on the other server has this file, MusicBrainz IDs or tags.",
    "ambiguous": "More than one candidate at the first tier that had any (or one candidate two copies want): "
                 "traqfreq doesn't guess.",
    "hidden_path": "The server gives no real path (Navidrome without Report Real Path), so the file tier can't "
                   "be used, and the MusicBrainz and tag tiers found nothing.",
    "not_in_plex": "An item no Plex copy matched: a file Plex doesn't list.",
    "multi_part": "Another part of a multi-part Plex copy (same folder, disc and track): Plex keeps only the "
                  "first part's file, which is matched; this part is not.",
}
NOTE_RULES = {
    "loose": "Matched by the loose key: the file key with other capitals.",
    "shared_file": "Two or more Plex copies point at one file; they all match its one item.",
    "multi_part": "A multi-part Plex copy, matched by its first part's file.",
}


# --- records: what the rule looks at ------------------------------------------------------------------

def _copy_rec(t: dict, mb: tuple | None = None) -> dict:
    path = "none" if not t["plex_path"] else ("outside" if not t["file"] else "ok")
    return {"id": t["rating_key"], "file": t["file"], "loose": t["loose"],
            "rec": mb[0] if mb else None, "rel": mb[1] if mb else None,
            "match_key": t["match_key"], "album": norm_title(t["album"]), "disc": t["disc"] or 1,
            "track": t["track_no"], "duration_ms": t["duration_ms"], "path": path}


def _item_rec(i: dict) -> dict:
    path = "hidden" if i["hidden"] else "none" if not i["path"] else "outside" if not i["file"] else "ok"
    return {"id": i["id"], "file": i["file"], "loose": i["loose"], "rec": i["mb_recording"],
            "rel": i["mb_release"], "match_key": match_key(i["artist"] or i["album_artist"], i["title"]),
            "album": norm_title(i["album"]), "disc": i["disc"] or 1, "track": i["track"],
            "duration_ms": i["duration_ms"], "path": path}


def _tag_key(r: dict) -> tuple | None:
    if r["track"] is None or not r["duration_ms"]:
        return None
    return (r["match_key"], r["album"], r["disc"], r["track"])


def match(left: list[dict], right: list[dict], tiers: tuple[str, ...] = TIERS,
          unmatched_left: str = "not_on_server", unmatched_right: str = "not_in_plex") -> dict:
    """Match records (``_copy_rec`` / ``_item_rec``) one to one. Returns {pairs: [{left, right, tier, how,
    shared}], left: {id: reason}, right: {id: reason}} with every unmatched record's one reason."""
    by_file, by_loose, by_mbid, by_tags = (defaultdict(list) for _ in range(4))
    for r in right:
        if r["file"]:
            by_file[r["file"]].append(r["id"])
            by_loose[r["loose"]].append(r["id"])
        if r["rec"] and r["rel"]:
            by_mbid[(r["rec"], r["rel"])].append(r["id"])
        k = _tag_key(r)
        if k:
            by_tags[k].append(r)

    def candidates(tier, how, l):
        if tier == "file":
            k = l["file"] if how == "exact" else l["loose"]
            return (by_file if how == "exact" else by_loose).get(k, []) if k else []
        if tier == "mbid":
            return by_mbid.get((l["rec"], l["rel"]), []) if l["rec"] and l["rel"] else []
        k = _tag_key(l)
        return [r["id"] for r in by_tags.get(k, []) if abs(r["duration_ms"] - l["duration_ms"]) <= TOLERANCE_MS] if k else []

    steps = [(t, h) for t in tiers for h in (("exact", "loose") if t == "file" else (None,))]
    claimed: set = set()
    pairs: dict = {}
    amb_left: set = set()
    amb_right: set = set()
    pending = list(left)
    for tier, how in steps:
        cands = {}
        for l in pending:
            c = [rid for rid in candidates(tier, how, l) if rid not in claimed]
            if c:
                cands[l["id"]] = c
        wanted = Counter(c[0] for c in cands.values() if len(c) == 1)
        for lid, c in cands.items():
            if len(c) > 1 or (wanted[c[0]] > 1 and how != "exact"):
                amb_left.add(lid)
                amb_right.update(c)
            else:
                pairs[lid] = {"left": lid, "right": c[0], "tier": tier, "how": how,
                              "shared": wanted[c[0]] > 1}
        claimed.update(p["right"] for p in pairs.values())
        pending = [l for l in pending if l["id"] not in pairs and l["id"] not in amb_left]
    hides = any(r["path"] == "hidden" for r in right)
    lreason = {}
    for l in left:
        if l["id"] in pairs:
            continue
        lreason[l["id"]] = ("ambiguous" if l["id"] in amb_left else "no_path" if l["path"] == "none"
                            else "outside_roots" if l["path"] == "outside" else "hidden_path" if hides
                            else unmatched_left)
    rreason = {}
    for r in right:
        if r["id"] in claimed:
            continue
        rreason[r["id"]] = ("ambiguous" if r["id"] in amb_right else "hidden_path" if r["path"] == "hidden"
                            else "no_path" if r["path"] == "none" else "outside_roots" if r["path"] == "outside"
                            else unmatched_right)
    return {"pairs": list(pairs.values()), "left": lreason, "right": rreason}


# --- the three pairs ------------------------------------------------------------------------------------

COPY_VIEW = ("rating_key", "title", "artist", "track_artist", "album", "disc", "track_no", "duration_ms",
             "plex_path", "parts", "file", "issues")
ITEM_VIEW = ("id", "path", "hidden", "file", "title", "artist", "album_artist", "album", "disc", "track",
             "duration_ms", "mb_recording", "mb_release", "size", "play_count")


def _view(x: dict, fields) -> dict:
    return {k: x.get(k) for k in fields}


class Matches:
    """Every pair's matches and unmatched rows, built from the library's identity and the stored snapshots."""

    def __init__(self, idn: identity_mod.Identity, snaps: dict[str, dict]):
        self.idn = idn
        self.snaps = snaps
        copies = idn.copies
        self.items = {s: {i["id"]: i for i in snaps[s]["items"]} for s in OTHERS if s in snaps}
        irecs = {s: [_item_rec(i) for i in snaps[s]["items"]] for s in self.items}
        # Phase 1: file tier only, so each copy can borrow MusicBrainz IDs from its file match elsewhere.
        file_only = {s: {p["left"]: p["right"] for p in match([_copy_rec(t) for t in copies], irecs[s],
                                                               tiers=("file",))["pairs"]} for s in self.items}

        def borrowed(s, rk):
            for o in self.items:
                if o != s and rk in file_only[o]:
                    it = self.items[o][file_only[o][rk]]
                    if it["mb_recording"] and it["mb_release"]:
                        return it["mb_recording"], it["mb_release"], o
            return None

        parts = {(folder_of(t["file"]), t["disc"] or 1, t["track_no"]) for t in copies
                 if (t["parts"] or 0) > 1 and t["file"]}
        self.result: dict[str, dict] = {}
        for s in self.items:
            mb = {t["rating_key"]: borrowed(s, t["rating_key"]) for t in copies}
            m = match([_copy_rec(t, mb[t["rating_key"]]) for t in copies], irecs[s])
            for p in m["pairs"]:
                b = mb[p["left"]]
                p["mbid_from"] = b[2] if p["tier"] == "mbid" and b else None
                p["multi_part"] = (self.idn.by_key[p["left"]]["parts"] or 0) > 1
            for rid in list(m["right"]):
                it = self.items[s][rid]
                if it["file"] and (folder_of(it["file"]), it["disc"] or 1, it["track"]) in parts:
                    m["right"][rid] = "multi_part"
            self.result[s] = m
        if len(self.items) == 2:
            self.result["jellyfin-navidrome"] = self._between()

    def _between(self) -> dict:
        """Jellyfin ↔ Navidrome: through Plex where both match one copy, then the rule on what's left."""
        jm = {p["left"]: p["right"] for p in self.result["jellyfin"]["pairs"]}
        nm = {p["left"]: p["right"] for p in self.result["navidrome"]["pairs"]}
        pairs, seen = [], set()
        for t in self.idn.copies:
            rk = t["rating_key"]
            if rk in jm and rk in nm and (jm[rk], nm[rk]) not in seen:
                seen.add((jm[rk], nm[rk]))
                pairs.append({"left": jm[rk], "right": nm[rk], "tier": "plex", "how": None, "shared": False,
                              "via": rk})
        jdone = {p["left"] for p in pairs}
        ndone = {p["right"] for p in pairs}
        left = [_item_rec(i) for i in self.snaps["jellyfin"]["items"] if i["id"] not in jdone]
        right = [_item_rec(i) for i in self.snaps["navidrome"]["items"] if i["id"] not in ndone]
        m = match(left, right, unmatched_right="not_on_server")
        for p in m["pairs"]:
            p["via"] = None
        return {"pairs": pairs + m["pairs"], "left": m["left"], "right": m["right"]}

    # --- counts and rows -------------------------------------------------------------------------------

    def _sides(self, pair: str):
        ls, rs = PAIRS[pair]
        lview = (lambda k: _view(self.idn.by_key[k], COPY_VIEW)) if ls == "plex" else \
            (lambda k: _view(self.items[ls][k], ITEM_VIEW))
        return ls, rs, lview, lambda k: _view(self.items[rs][k], ITEM_VIEW)

    def summary(self, pair: str) -> dict:
        ls, rs = PAIRS[pair]
        m = self.result[pair]
        nleft = len(self.idn.copies) if ls == "plex" else len(self.items[ls])
        tiers = ("plex", *TIERS) if ls != "plex" else TIERS
        by_tier = Counter(p["tier"] for p in m["pairs"])
        lname = "copies" if ls == "plex" else "left"
        counts = {
            lname: nleft,
            "items": len(self.items[rs]),
            "matched": len(m["pairs"]),
            "items_matched": len({p["right"] for p in m["pairs"]}),
            f"{lname}_unmatched": len(m["left"]),
            "items_unmatched": len(m["right"]),
        }
        notes = {"loose": sum(1 for p in m["pairs"] if p["how"] == "loose"),
                 "shared_file": sum(1 for p in m["pairs"] if p["shared"])}
        if ls == "plex":
            notes["multi_part"] = sum(1 for p in m["pairs"] if p.get("multi_part"))
        lr = Counter(m["left"].values())
        rr = Counter(m["right"].values())
        return {
            "pair": pair, "left": ls, "right": rs,
            "counts": counts,
            "tiers": {t: by_tier.get(t, 0) for t in tiers},
            "notes": notes,
            "unmatched_left": {r: lr.get(r, 0) for r in REASONS if r in lr},
            "unmatched_items": {r: rr.get(r, 0) for r in REASONS if r in rr},
            "rules": {
                lname: ("Live Plex copies (identity)." if ls == "plex" else f"Items in the {ls} snapshot."),
                "items": f"Items in the {rs} snapshot.",
                "matched": f"{'Copies' if ls == 'plex' else 'Items'} matched to one {rs} item, at the tier said.",
                "items_matched": f"Distinct {rs} items matched (a shared file counts once).",
                f"{lname}_unmatched": "Not matched; each with one reason, so the reasons add up to this.",
                "items_unmatched": f"{rs} items nothing matched; each with one reason.",
                **{t: TIER_RULES[t] for t in tiers},
                **{k: NOTE_RULES[k] for k in notes},
            },
            "rows": {
                "all": f"server={pair}",
                **{t: f"server={pair}&tier={t}" for t in tiers},
                **{r: f"server={pair}&reason={r}" for r in set(lr) | set(rr)},
            },
        }

    def rows(self, pair: str, tier: str | None = None, reason: str | None = None) -> list[dict]:
        ls, rs, lview, rview = self._sides(pair)
        m = self.result[pair]
        out = []
        if reason is None:
            for p in m["pairs"]:
                if tier and p["tier"] != tier:
                    continue
                out.append({"pair": pair, "side": "both", "tier": p["tier"], "how": p["how"],
                            "shared": p["shared"], "multi_part": p.get("multi_part", False),
                            "mbid_from": p.get("mbid_from"), "via": p.get("via"), "reason": None,
                            "left": lview(p["left"]), "right": rview(p["right"])})
        if tier is None:
            for k, r in m["left"].items():
                if reason is None or r == reason:
                    out.append({"pair": pair, "side": "left", "tier": None, "reason": r, "left": lview(k), "right": None})
            for k, r in m["right"].items():
                if reason is None or r == reason:
                    out.append({"pair": pair, "side": "right", "tier": None, "reason": r, "left": None, "right": rview(k)})
        return out


_built: dict[tuple, Matches] = {}
_lock = threading.Lock()


def matches(conn, data_dir, env_roots: tuple[str, ...] = ()) -> Matches:
    """The Matches for this library state and these snapshots (built once, then kept in memory)."""
    key = (MATCH_VERSION, identity_mod.stamp(conn, env_roots), str(data_dir), store.snapshot_stamps(data_dir))
    with _lock:
        m = _built.get(key)
        if m is None:
            _built.clear()
            m = _built[key] = Matches(identity_mod.identity(conn, env_roots), store.snapshots(data_dir))
        return m


def _snapshot_info(s: str, snap: dict | None, now: float) -> dict:
    if snap is None:
        return {"server": s, "snapshot": False,
                "note": "No snapshot yet: press Refresh on the server's column to read it (GET requests only)."}
    return {"server": s, "snapshot": True, "read_at": snap["read_at"], "age_s": round(now - snap["read_at"]),
            "stamp": snap["stamp"], "folders": snap["folders"], "folder_source": snap["folder_source"],
            "folder_rule": FOLDER_SOURCES[snap["folder_source"]], "items": len(snap["items"]),
            "hidden_paths": sum(1 for i in snap["items"] if i["hidden"])}


def _of_copy(row: dict, rating_key: int) -> bool:
    """A row about this Plex copy: its match or miss on a Plex pair, or a Jellyfin ↔ Navidrome match made
    through it (tier ``plex``)."""
    left = row["left"] or {}
    return left.get("rating_key") == rating_key or row.get("via") == rating_key


def report(conn, data_dir, env_roots: tuple[str, ...] = (), server: str | None = None, tier: str | None = None,
           reason: str | None = None, limit: int = 50, offset: int = 0, rating_key: int | None = None) -> dict:
    """``GET /api/servers/matches``: the snapshots, each pair's counts with their rules and rows queries, and
    the rows asked for (``server`` = jellyfin, navidrome or jellyfin-navidrome; ``tier``; ``reason``;
    ``rating_key``: one Plex copy's rows, for the track page's "On servers")."""
    if server is not None and server not in PAIRS:
        raise ValueError(f"server must be one of {', '.join(PAIRS)}")
    if tier is not None and tier not in (*TIERS, "plex"):
        raise ValueError(f"tier must be one of {', '.join((*TIERS, 'plex'))}")
    if reason is not None and reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    if tier and reason:
        raise ValueError("ask for a tier (matched rows) or a reason (unmatched rows), not both")
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    m = matches(conn, data_dir, env_roots)
    now = time.time()
    pairs = [p for p in PAIRS if p in m.result]
    out = {
        "snapshots": [_snapshot_info(s, m.snaps.get(s), now) for s in OTHERS],
        "pairs": [m.summary(p) for p in pairs],
        "missing": [p for p in PAIRS if p not in m.result],
        "tiers": [{"tier": t, "rule": TIER_RULES[t]} for t in (*TIERS, "plex")],
        "reasons": REASON_RULES,
        "tolerance_ms": TOLERANCE_MS,
        "read_only": "Matched from stored snapshots; nothing is sent to any server.",
        "version": MATCH_VERSION,
    }
    if server or tier or reason or rating_key is not None:
        sel = [server] if server else pairs
        if server and server not in m.result:
            sel = []
        rows = [r for p in sel for r in m.rows(p, tier, reason)]
        rule = [f"pair {server}" if server else "every pair"]
        if tier:
            rule.append(f"matched at tier {tier}")
        if reason:
            rule.append(f"unmatched because {reason}")
        if rating_key is not None:
            rows = [r for r in rows if _of_copy(r, rating_key)]
            rule.append(f"Plex copy {rating_key} (its match or reason; Jellyfin ↔ Navidrome matched through it)")
            out["copy"] = {"rating_key": rating_key, "live": rating_key in m.idn.by_key}
        out["rows"] = {"total": len(rows), "offset": offset, "limit": limit, "rule": ", ".join(rule),
                       "rows": rows[offset:offset + limit]}
    return out
