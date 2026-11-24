"""jimbo-dj's Library → Tags (tags.py): the genre tag rules, compiled, and every album's and artist's genres from
every source folded into one canonical list and audited. Copied unchanged at 1d8a7cb, with tag_rules.json beside it
(vendor/tag_rules.json, byte for byte, so ``RULES_PATH`` finds it).

TAGS (P4) builds on this: the ladder (``traqfreq.tags``) puts ``Rules.broad`` and the canonical keys in
``Library.index`` into rungs, and checks itself against ``Library.families``. Not copied: ``_lib`` and ``get``
(jimbo-dj's background cache; traqfreq keeps one Library per data stamp in ``traqfreq.tags``). ``genres`` is
vendor/genres.py (``family`` and ``_support`` vendored; styles a stand-in, so ``_sound_by_album`` gives none),
``filetags`` and ``tagwrite`` (imported inside the copies) are vendor/filetags.py and vendor/tagwrite.py, their
read-only parts only. Nothing here writes anything. Never edit the copies; re-copy them when jimbo-dj changes.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from . import genres

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/tags.py, src/jimbodj/tag_rules.json"

# --- src/jimbodj/tags.py ---------------------------------------------------------------------------------
RULES_PATH = Path(__file__).with_name("tag_rules.json")

# What each issue is called, and how bad it is (the order albums are listed in).
KINDS = {
    "junk": "Not a genre",
    "split": "Several genres in one tag",
    "spelling": "Non-standard spelling",
    "case": "Odd casing",
    "broad": "Missing its broad tag",
    "niche": "Too niche",
    "untagged": "No tags at all",
}
WEIGHT = {"junk": 5, "split": 4, "spelling": 4, "broad": 3, "case": 2, "niche": 1, "untagged": 5}


def load_rules(path: Path = RULES_PATH) -> dict:
    return json.loads(Path(path).read_text())


def norm(s: str) -> str:
    """The comparison key: lower case, one space, typographic quotes made plain."""
    s = unicodedata.normalize("NFC", s or "").replace("’", "'").replace("‘", "'").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


class Rules:
    """tag_rules.json, compiled. `artists` (lower-case names in the library) feeds the artist-names rule;
    `known` (genres MusicBrainz uses) keeps a band called after a genre from turning that genre into junk."""

    def __init__(self, d: dict, artists=(), known=()):
        self.d = d
        self.niche_max = int(d.get("niche_max", 1))
        self.split_rx = re.compile(d["split"]["pattern"])
        self.aliases = {norm(k): norm(v) for k, v in d["aliases"]["map"].items()}
        self.rewrites = [(r, re.compile(r["pattern"]), set(map(norm, r.get("keep", [])))) for r in d["rewrites"]]
        self.junk = []
        for j in d["junk"]:
            self.junk.append((j, set(map(norm, j.get("words", []))), re.compile(j["pattern"]) if j.get("pattern") else None))
        self.artists = {norm(a) for a in artists if a}
        self.known = set(known)
        c = d["case"]
        self.upper = {norm(w): w.upper() for w in c["upper"]}
        self.lower = set(map(norm, c["lower"]))
        b = d["broad"]
        self.families = b["families"]
        self.overrides = [(re.compile(o["pattern"]), o["tag"]) for o in b["overrides"]]
        self.broad_tags = {norm(t) for t in [*self.families.values(), *(o["tag"] for o in b["overrides"])] if t}
        self._parsed: dict[str, list[dict]] = {}

    # -- one tag ---------------------------------------------------------------------------------------

    def case(self, key: str) -> str:
        words = key.split(" ")
        out = []
        for i, w in enumerate(words):
            if w in self.upper:
                out.append(self.upper[w])
            elif i and w in self.lower:
                out.append(w)
            else:
                out.append("-".join(p[:1].upper() + p[1:] if not (p in self.upper) else self.upper[p] for p in w.split("-")))
        return " ".join(out)

    def junk_rule(self, key: str) -> dict | None:
        for j, words, rx in self.junk:
            if key in words or (rx and rx.search(key)):
                return j
            if j.get("artists") and key in self.artists and key not in self.known and key not in self.broad_tags:
                return j
        return None

    def _one(self, part: str) -> dict:
        fired: list[str] = []
        k = norm(part)
        if k in self.aliases and self.aliases[k] != k:
            k = self.aliases[k]
            fired.append(self.d["aliases"]["id"])
        for r, rx, keep in self.rewrites:
            if k in keep:
                continue
            new = re.sub(r"\s+", " ", rx.sub(r["replace"], k)).strip()
            if new != k:
                k = new
                fired.append(r["id"])
        if k in self.aliases and self.aliases[k] != k:
            k = self.aliases[k]
            if self.d["aliases"]["id"] not in fired:
                fired.append(self.d["aliases"]["id"])
        j = self.junk_rule(k)
        name = self.case(k)
        if not fired and name != part.strip():
            fired.append(self.d["case"]["id"])
        return {"name": name, "key": k, "junk": j["id"] if j else None, "rules": fired}

    def parse(self, raw: str) -> list[dict]:
        """What a tag becomes: one or more canonical tags (more when it's several genres in one), each with
        the rules that changed it and the junk rule it falls under, if any."""
        if raw not in self._parsed:
            parts = [p for p in self.split_rx.split(raw or "") if p and p.strip()]
            out = [self._one(p) for p in parts] or [self._one(raw or "")]
            if len(parts) > 1:
                for o in out:
                    o["rules"] = [self.d["split"]["id"], *o["rules"]]
            seen, uniq = set(), []
            for o in out:
                if o["key"] and o["key"] not in seen:
                    seen.add(o["key"])
                    uniq.append(o)
            self._parsed[raw] = uniq
        return self._parsed[raw]

    def broad(self, key: str) -> str | None:
        """The broad parent tag for a canonical key ("black metal" → "Metal"), None when it has none. A broad
        tag's parent is itself."""
        for rx, tag in self.overrides:
            if rx.search(key):
                return tag
        return self.families.get(genres.family(key))

    def rule_index(self) -> list[dict]:
        d = self.d
        out = [{**_pick(d["split"]), "kind": "split"}, {**_pick(d["aliases"]), "kind": "alias"}]
        out += [{**_pick(r), "kind": "rewrite"} for r in d["rewrites"]]
        out += [{**_pick(j), "kind": "junk"} for j in d["junk"]]
        out += [{**_pick(d["case"]), "kind": "case"}, {**_pick(d["broad"]), "kind": "broad"},
                {"id": "niche", "label": f"Used {'once' if self.niche_max == 1 else f'{self.niche_max} times or fewer'} and unknown to MusicBrainz",
                 "why": "A tag only one album carries doesn't group anything. Either it's a typo, or it's a genre that "
                        "deserves more albums. MusicBrainz genres used once get a pass.", "kind": "niche"}]
        return out


def _pick(r: dict) -> dict:
    return {"id": r["id"], "label": r["label"], "why": r["why"]}


def _loads(v, default):
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


# -- the whole library -------------------------------------------------------------------------------

# Where a genre can come from. Plex's track genres are what Plex read from the files' own tags; file tags are
# every genre value in the files themselves, read by filetags.py.
SOURCES = {
    "plex": "Plex album", "plex-artist": "Plex artist", "plex-track": "Track tags", "file": "File tags",
    "mb-release": "MusicBrainz release", "mb-artist": "MusicBrainz artist", "sound": "Sound",
    "plex-albums": "Its albums",
}
SOUND_SHARE = 0.4    # an analysed style counts for an album when this share of its analysed tracks has it
TRACK_SHARE = 0.5    # track tags speak for the album when this share of its tracks carries them


def _sound_by_album(con) -> dict[int, dict[str, float]]:
    """The analyzer's styles (genres.py's strict Discogs styles) per album: share of its analysed tracks."""
    st = genres.get(con)
    album_of = dict(con.execute("SELECT rating_key, album_key FROM tracks WHERE removed_at IS NULL").fetchall())
    per: dict[int, Counter] = defaultdict(Counter)
    n: Counter = Counter()
    for k, gs in st.sound_genres.items():
        a = album_of.get(k)
        if a is None:
            continue
        n[a] += 1
        per[a].update({g.partition("---")[2] or g for g in gs})
    return {a: {s: round(c / n[a], 2) for s, c in cnt.items()} for a, cnt in per.items()}


class Library:
    """Every album's and artist's genres from every source folded into one canonical list, audited by the
    rules, with what to add. Worked out once and cached (`get`)."""

    def __init__(self, con, rules: dict | None = None):
        t0 = time.time()
        artists = {r["artist_key"]: dict(r) for r in con.execute("SELECT artist_key, title, genres, mbid FROM artists")}
        albums = [dict(r) for r in con.execute("SELECT album_key, title, artist_key, year, genres, mbid FROM albums")]
        mb_rel = {r["mbid"]: _loads(r["genres"], {}) for r in con.execute("SELECT mbid, genres FROM mb_releases WHERE status='ok'")}
        mb_art = {r["mbid"]: _loads(r["genres"], {}) for r in con.execute("SELECT mbid, genres FROM mb_artists WHERE status='ok'")}
        album_tracks: dict[int, dict] = defaultdict(lambda: {"tracks": 0, "tags": Counter()})
        for a, g in con.execute("SELECT album_key, plex_genres FROM tracks WHERE removed_at IS NULL"):
            album_tracks[a]["tracks"] += 1
            album_tracks[a]["tags"].update(set(_loads(g, [])))
        from . import filetags
        files = filetags.by_album(con)
        try:
            sound = _sound_by_album(con)
        except Exception:  # noqa: BLE001 (no analysis yet: the other sources still work)
            sound = {}
        self.build(rules or load_rules(), artists, albums, mb_rel, mb_art, album_tracks, sound, files)
        self.seconds = round(time.time() - t0, 2)

    @classmethod
    def from_data(cls, rules, artists, albums, mb_rel=None, mb_art=None, album_tracks=None, sound=None, files=None) -> "Library":
        """For tests: the same thing from plain dicts (artists keyed by artist_key; genres as JSON or lists)."""
        lib = cls.__new__(cls)
        lib.build(rules, artists, albums, mb_rel or {}, mb_art or {}, album_tracks or {}, sound or {}, files or {})
        lib.seconds = 0.0
        return lib

    def build(self, rules, artists, albums, mb_rel, mb_art, album_tracks, sound, files=None):
        files = files or {}
        known = set()
        for d in (*mb_rel.values(), *mb_art.values()):
            known.update(norm(g) for g in d)
        R = self.rules = Rules(rules, artists=[a["title"] for a in artists.values()], known=known)
        self.mb_known = {p["key"] for g in known for p in R.parse(g)}

        def tagsof(v):
            return v if isinstance(v, list) else _loads(v, [])

        # Tag index: canonical key → who carries it, under which spellings, from which sources.
        idx: dict[str, dict] = {}

        def entry(p):
            e = idx.get(p["key"])
            if e is None:
                e = idx[p["key"]] = {"key": p["key"], "name": p["name"], "junk": p["junk"], "albums": set(), "artists": set(),
                                     "tracks": 0, "mb": 0, "sound": 0,
                                     "variants": defaultdict(lambda: {"albums": 0, "artists": 0, "tracks": 0})}
            return e

        raw_uses: Counter = Counter()   # raw tag → album + artist uses
        for a in albums:
            a["tags"] = tagsof(a["genres"])
            for raw in a["tags"]:
                raw_uses[raw] += 1
                for p in R.parse(raw):
                    e = entry(p)
                    e["albums"].add(a["album_key"])
                    e["variants"][raw]["albums"] += 1
        for ar in artists.values():
            ar["tags"] = tagsof(ar["genres"])
            for raw in ar["tags"]:
                raw_uses[raw] += 1
                for p in R.parse(raw):
                    e = entry(p)
                    e["artists"].add(ar["artist_key"])
                    e["variants"][raw]["artists"] += 1
        for t in album_tracks.values():
            for raw, n in t["tags"].items():
                for p in R.parse(raw):
                    e = entry(p)
                    e["tracks"] += n
                    e["variants"][raw]["tracks"] += n
        for d in (*mb_rel.values(), *mb_art.values()):
            for k in {p["key"] for g in d for p in R.parse(g)}:
                if k in idx:
                    idx[k]["mb"] += 1
        for s in sound.values():
            for k in {p["key"] for g, v in s.items() if v >= SOUND_SHARE for p in R.parse(g)}:
                if k in idx:
                    idx[k]["sound"] += 1

        for k, e in idx.items():
            e["broad"] = None if e["junk"] else R.broad(k)
            e["is_broad"] = bool(e["broad"]) and norm(e["broad"]) == k
            e["niche"] = (not e["junk"] and not e["is_broad"] and k not in self.mb_known
                          and 0 < len(e["albums"]) + len(e["artists"]) <= R.niche_max)
        self.index = idx
        self.raw_uses = raw_uses
        self.artists = artists

        # Albums: every source folded together, the issues with Plex's tags, and what to add.
        self.albums = {}
        artist_albums: dict[int, list[dict]] = defaultdict(list)
        for a in albums:
            ar = artists.get(a["artist_key"]) or {}
            rel, art = mb_rel.get(a["mbid"]) or {}, mb_art.get(ar.get("mbid")) or {}
            t = album_tracks.get(a["album_key"]) or {"tracks": 0, "tags": Counter()}
            f = files.get(a["album_key"]) or {"tracks": 0, "tags": Counter()}
            srcs = [("plex", {g: 1 for g in a["tags"]}), ("plex-artist", {g: 1 for g in ar.get("tags", [])}),
                    ("plex-track", {g: round(n / t["tracks"], 2) for g, n in t["tags"].items()} if t["tracks"] else {}),
                    ("file", {g: round(n / f["tracks"], 2) for g, n in f["tags"].items()} if f["tracks"] else {}),
                    ("mb-release", rel), ("mb-artist", art), ("sound", sound.get(a["album_key"]) or {})]
            row = {"album_key": a["album_key"], "title": a["title"], "artist": ar.get("title"), "artist_key": a["artist_key"],
                   "year": a["year"], "musicbrainz": bool(rel), "tracks": t["tracks"],
                   **self._audit(a["tags"], srcs, rel, art)}
            self.albums[a["album_key"]] = row
            artist_albums[a["artist_key"]].append(a)

        # Artists: their own tags in Plex and MusicBrainz, and how many of their albums carry each.
        self.artist_rows = {}
        for ak, ar in artists.items():
            als = artist_albums.get(ak, [])
            share = Counter(g for a in als for g in set(a["tags"]))
            srcs = [("plex", {g: 1 for g in ar["tags"]}), ("mb-artist", mb_art.get(ar.get("mbid")) or {}),
                    ("plex-albums", {g: round(n / len(als), 2) for g, n in share.items()} if als else {})]
            self.artist_rows[ak] = {"artist_key": ak, "name": ar["title"], "albums": len(als),
                                    **self._audit(ar["tags"], srcs, {}, mb_art.get(ar.get("mbid")) or {})}

    def _fold(self, srcs) -> dict[str, dict]:
        """Every source's genres in canonical keys: key → name, junk, and each source's say (1 for a Plex tag,
        votes for MusicBrainz, the share of tracks or albums for track tags, sound and an artist's albums)."""
        out: dict[str, dict] = {}
        for src, d in srcs:
            for raw, v in d.items():
                for p in self.rules.parse(raw):
                    e = out.setdefault(p["key"], {"key": p["key"], "name": p["name"], "junk": p["junk"], "sources": {}})
                    e["sources"][src] = max(e["sources"].get(src, 0), v)
        return out

    def _audit(self, tags: list[str], srcs, rel: dict, art: dict) -> dict:
        R = self.rules
        issues, keys, shown = self._issues(tags)
        folded = self._fold(srcs)
        covered = {**keys, **{norm(i["tag"]): i["tag"] for i in issues if i["kind"] == "broad"}}
        recs = self._recs(folded, covered, rel, art)
        if any(R.broad(k) for k in covered):
            recs = [r for r in recs if r["key"] not in R.broad_tags]
        rec_keys = {r["key"] for r in recs}
        niche = {norm(i["tag"]) for i in issues if i["kind"] == "niche"}
        # The one list: every genre any source names, with its sources and what the rules make of it.
        merged = []
        for k, e in folded.items():
            if e["junk"]:
                status = "junk"
            elif k in keys:
                status = "niche" if k in niche else "keep"
            elif k in covered:
                status = "add"           # a missing broad tag
            elif k in rec_keys:
                status = "suggest"
            else:
                status = "other"
            merged.append({"tag": e["name"], "key": k, "status": status, "sources": e["sources"]})
        for k, name in covered.items():
            if k not in folded:
                merged.append({"tag": name, "key": k, "status": "add", "sources": {}})
        order = {"keep": 0, "add": 1, "suggest": 2, "niche": 3, "other": 4, "junk": 5}
        merged.sort(key=lambda m: (order[m["status"]], -len(m["sources"]), m["tag"]))
        proposed = [m["tag"] for m in merged if m["status"] in ("keep", "add", "suggest")]
        return {"tags": shown, "issues": issues, "recs": recs, "genres": merged, "proposed": proposed,
                "score": sum(WEIGHT[i["kind"]] for i in issues)}

    def _issues(self, tags: list[str]):
        R, issues, shown, keys = self.rules, [], [], {}
        for raw in tags:
            parts = R.parse(raw)
            good = [p for p in parts if not p["junk"]]
            for p in good:
                keys.setdefault(p["key"], p["name"])
            names = [p["name"] for p in good]
            rules = sorted({r for p in parts for r in p["rules"]})
            if not good:
                j = parts[0]["junk"] if parts else "personal"
                issues.append({"kind": "junk", "op": "remove", "tag": raw, "rule": j})
                shown.append({"name": raw, "status": "junk", "rule": j})
            elif names != [raw]:
                kind = "split" if len(parts) > 1 else "case" if rules == [R.d["case"]["id"]] else "spelling"
                issues.append({"kind": kind, "op": "rename", "tag": raw, "to": names, "rules": rules})
                shown.append({"name": raw, "status": kind, "to": names})
            else:
                shown.append({"name": raw, "status": "ok"})
        for k, name in keys.items():
            e = self.index.get(k)
            if e and e["niche"]:
                issues.append({"kind": "niche", "op": "remove", "tag": name})
                for s in shown:
                    if s["status"] == "ok" and norm(s["name"]) == k:
                        s["status"] = "niche"
        missing: dict[str, list[str]] = {}
        for k, name in keys.items():
            b = self.index[k]["broad"] if k in self.index else R.broad(k)
            if b and norm(b) not in keys:
                missing.setdefault(b, []).append(name)
        for b, because in missing.items():
            issues.append({"kind": "broad", "op": "add", "tag": b, "because": because})
        if not tags:
            issues.append({"kind": "untagged", "op": "add", "tag": None})
        return issues, keys, shown

    def _recs(self, folded: dict, covered: dict, rel: dict, art: dict, limit: int = 6) -> list[dict]:
        """Genres worth adding, from everything but the tags already there. Backed when MusicBrainz has enough
        votes for it on the release (and release group) or the artist (genres._support), when most of the
        tracks are tagged with it, or when two other sources agree. Release votes count most."""
        R = self.rules
        sup = {p["key"] for g in genres._support(rel) | genres._support(art) for p in R.parse(g)}
        top_rel, top_art = max(rel.values(), default=0) or 1, max(art.values(), default=0) or 1
        recs = []
        for k, e in folded.items():
            if e["junk"] or k in covered or (k in self.index and self.index[k]["niche"]):
                continue
            s = e["sources"]
            # Plex's track tags and the files' tags are the same files read twice: one voice between them.
            voices = {src: v for src, v in s.items() if not (src == "file" and "plex-track" in s)}
            agree = sum(1 for src, v in voices.items() if src != "plex" and (v >= SOUND_SHARE if src in ("sound", "plex-track", "file", "plex-albums") else v > 0))
            backed = (k in sup or s.get("plex-track", 0) >= TRACK_SHARE or s.get("file", 0) >= TRACK_SHARE
                      or s.get("plex-albums", 0) >= TRACK_SHARE or agree >= 2)
            if not backed:
                continue
            score = (s.get("mb-release", 0) / top_rel + 0.5 * s.get("mb-artist", 0) / top_art + 0.8 * max(s.get("plex-track", 0), s.get("file", 0))
                     + 0.8 * s.get("plex-albums", 0) + 0.3 * s.get("plex-artist", 0) + 0.5 * s.get("sound", 0))
            recs.append({"tag": e["name"], "key": k, "sources": s, "score": round(score, 3),
                         "release_votes": int(s.get("mb-release", 0)), "artist_votes": int(s.get("mb-artist", 0))})
        recs.sort(key=lambda r: (-r["score"], r["tag"]))
        return recs[:limit]

    # -- views ------------------------------------------------------------------------------------------

    def tag_rows(self) -> list[dict]:
        rows = []
        for e in self.index.values():
            uses = len(e["albums"]) + len(e["artists"])
            variants = sorted(({"name": n, **v} for n, v in e["variants"].items()),
                              key=lambda v: -(v["albums"] + v["artists"] + v["tracks"]))
            issues = []
            if e["junk"]:
                issues.append({"kind": "junk", "op": "remove", "rule": e["junk"]})
            off = [v["name"] for v in variants if v["name"] != e["name"]]
            if off and not e["junk"]:
                issues.append({"kind": "spelling", "op": "rename", "from": off, "to": e["name"]})
            if e["niche"]:
                issues.append({"kind": "niche", "op": "remove"})
            rows.append({"key": e["key"], "name": e["name"], "albums": len(e["albums"]), "artists": len(e["artists"]),
                         "tracks": e["tracks"], "uses": uses, "musicbrainz": e["mb"], "sound": e["sound"], "broad": e["broad"],
                         "is_broad": e["is_broad"], "variants": variants, "issues": issues})
        rows.sort(key=lambda r: (-r["uses"], -r["tracks"], r["name"]))
        return rows

    def families(self) -> list[dict]:
        """The hierarchy: each broad tag, the albums that carry it, the ones whose specific tags call for it
        but don't, and its children."""
        fam: dict[str, dict] = {}
        for k, e in self.index.items():
            b = e["broad"]
            if not b:
                continue
            f = fam.setdefault(b, {"tag": b, "key": norm(b), "children": [], "needing": set()})
            if not e["is_broad"]:
                f["needing"] |= e["albums"]
                if e["albums"]:
                    f["children"].append({"tag": e["name"], "key": k, "albums": len(e["albums"])})
        out = []
        for b, f in fam.items():
            have = self.index.get(f["key"], {}).get("albums", set())
            if not (have or f["needing"]):
                continue
            f["children"].sort(key=lambda c: (-c["albums"], c["tag"]))
            out.append({"tag": b, "key": f["key"], "albums": len(have | f["needing"]), "tagged": len(have),
                        "missing": len(f["needing"] - have), "children": f["children"]})
        out.sort(key=lambda f: -f["albums"])
        return out

    def rule_report(self) -> list[dict]:
        """Each rule and how many tags (distinct spellings) and uses (album and artist tags) it would change."""
        R = self.rules
        tags, uses, examples = Counter(), Counter(), defaultdict(list)
        for raw, n in self.raw_uses.items():
            parts = R.parse(raw)
            to = " + ".join(p["name"] for p in parts if not p["junk"]) or "(removed)"
            for rid in {r for p in parts for r in p["rules"]} | {p["junk"] for p in parts if p["junk"]}:
                tags[rid] += 1
                uses[rid] += n
                if len(examples[rid]) < 4:
                    examples[rid].append({"from": raw, "to": to})
        broad = Counter(i["tag"] for a in self.albums.values() for i in a["issues"] if i["kind"] == "broad")
        tags["broad"], uses["broad"] = len(broad), sum(broad.values())
        seen = set()
        for a in self.albums.values():
            for i in a["issues"]:
                if i["kind"] == "broad" and i["tag"] not in seen and len(examples["broad"]) < 4:
                    seen.add(i["tag"])
                    examples["broad"].append({"from": i["because"][0], "to": f"{i['because'][0]} + {i['tag']}"})
        niche = [e for e in self.index.values() if e["niche"]]
        tags["niche"], uses["niche"] = len(niche), sum(len(e["albums"]) + len(e["artists"]) for e in niche)
        examples["niche"] = [{"from": e["name"], "to": "(removed, or give it company)"} for e in niche[:4]]
        return [{**r, "tags": tags[r["id"]], "uses": uses[r["id"]], "examples": examples[r["id"]]} for r in R.rule_index()]

    def fixes(self, limit: int = 15) -> list[dict]:
        """The rule fixes that would tidy the most albums, biggest first."""
        agg: dict[tuple, dict] = {}
        for a in self.albums.values():
            for i in a["issues"]:
                if i["kind"] in ("untagged", "niche"):
                    continue
                to = tuple(i.get("to") or ())
                k = (i["op"], i["kind"], i["tag"], to)
                f = agg.setdefault(k, {"op": i["op"], "kind": i["kind"], "tag": i["tag"], "to": list(to), "albums": 0})
                f["albums"] += 1
        return sorted(agg.values(), key=lambda f: (-f["albums"], f["tag"] or ""))[:limit]

    def suggestions(self, limit: int = 12) -> list[dict]:
        """The genres suggested for the most albums, from the combined sources."""
        c = Counter(r["tag"] for a in self.albums.values() for r in a["recs"])
        return [{"tag": t, "albums": n, "key": norm(t), "in_use": norm(t) in self.index} for t, n in c.most_common(limit)]

    def summary(self) -> dict:
        albums = list(self.albums.values())
        clean = sum(1 for a in albums if not a["issues"])
        by_kind = Counter(k for a in albums for k in {i["kind"] for i in a["issues"]})
        tag_uses = sum(self.raw_uses.values())
        ok_uses = sum(n for raw, n in self.raw_uses.items()
                      if [p["name"] for p in self.rules.parse(raw) if not p["junk"]] == [raw])
        canon = [e for e in self.index.values() if not e["junk"]]
        return {
            "albums": len(albums), "artists": len(self.artist_rows), "clean": clean,
            "consistency": round(clean / len(albums), 3) if albums else 1.0,
            "spellings": len(self.raw_uses), "tags": len(canon), "junk": sum(1 for e in self.index.values() if e["junk"]),
            "niche": sum(1 for e in canon if e["niche"]),
            "tag_uses": tag_uses, "canonical_uses": round(ok_uses / tag_uses, 3) if tag_uses else 1.0,
            "issues": {k: by_kind.get(k, 0) for k in KINDS},
            "with_recs": sum(1 for a in albums if a["recs"]),
            "with_musicbrainz": sum(1 for a in albums if a["musicbrainz"]),
            "sources": SOURCES,
            "seconds": self.seconds,
        }

    def overview(self) -> dict:
        """Library → Tags' first page, in one go (cached in the stats table as library.tags)."""
        return {"summary": self.summary(), "fixes": self.fixes(), "suggestions": self.suggestions(),
                "rules": self.rule_report(), "families": self.families(), "tags": self.tag_rows(),
                "kinds": KINDS}

    def _page(self, rows: list[dict], page: int, size: int) -> dict:
        size = max(1, min(size, 100))
        start = (max(page, 1) - 1) * size
        return {"total": len(rows), "page": max(page, 1), "size": size, "items": rows[start:start + size]}

    def _filter(self, rows, issue, q, fields):
        if issue == "clean":
            rows = [a for a in rows if not a["issues"]]
        elif issue == "recs":
            rows = [a for a in rows if a["recs"]]
        elif issue:
            rows = [a for a in rows if any(i["kind"] == issue for i in a["issues"])]
        if q:
            ql = q.lower()
            rows = [a for a in rows if any(ql in (a[f] or "").lower() for f in fields)]
        return rows

    def album_page(self, issue: str | None = None, tag: str | None = None, q: str | None = None,
                   page: int = 1, size: int = 30) -> dict:
        rows = list(self.albums.values())
        have: set = set()
        if tag:
            k = norm(tag)
            have = self.index.get(k, {}).get("albums", set())
            need = {a for e in self.index.values() if not e["is_broad"] and e["broad"] and norm(e["broad"]) == k
                    for a in e["albums"]} - have
            rows = [a for a in rows if a["album_key"] in have or a["album_key"] in need]
        rows = self._filter(rows, issue, q, ("title", "artist"))
        if tag or issue == "clean":
            rows.sort(key=lambda a: ((a["artist"] or "").lower(), a["year"] or 0, (a["title"] or "").lower()))
        else:
            rows.sort(key=lambda a: (-a["score"], (a["artist"] or "").lower(), (a["title"] or "").lower()))
        out = self._page(rows, page, size)
        if tag:
            out["items"] = [{**a, "carries": a["album_key"] in have} for a in out["items"]]
        return out

    def artist_page(self, issue: str | None = None, tag: str | None = None, q: str | None = None,
                    page: int = 1, size: int = 30) -> dict:
        rows = list(self.artist_rows.values())
        if tag:
            have = self.index.get(norm(tag), {}).get("artists", set())
            rows = [a for a in rows if a["artist_key"] in have]
        rows = self._filter(rows, issue, q, ("name",))
        rows.sort(key=lambda a: ((a["name"] or "").lower()) if tag or issue == "clean" else (-a["score"], (a["name"] or "").lower()))
        return self._page(rows, page, size)

    def tag_detail(self, key: str) -> dict | None:
        k = norm(key)
        if k not in self.index:
            return None
        row = next(r for r in self.tag_rows() if r["key"] == k)
        e = self.index[k]
        children = next((f["children"] for f in self.families() if f["key"] == k), [])
        return {"tag": row, "children": children, "parent": None if e["is_broad"] else e["broad"]}


# Rebuilt when the library syncs, MusicBrainz fetches more, the analyzer's styles change or the rules file
# does. A second or two.
_STAMP = ("SELECT (SELECT MAX(fetched_at) FROM mb_releases), (SELECT MAX(fetched_at) FROM mb_artists), "
          "(SELECT value FROM meta WHERE key='last_sync')")


def stamp(con) -> list:
    try:
        mtime = RULES_PATH.stat().st_mtime
    except OSError:
        mtime = None
    from . import filetags, tagwrite
    return [*con.execute(_STAMP).fetchone(), genres.version(), mtime, filetags.stamp(con), tagwrite.stamp(con)]
