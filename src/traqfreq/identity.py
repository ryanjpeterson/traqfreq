"""Track identity, the Plex side (T13, spec docs/specs/t13-servers.md).

A copy is one live Plex track (jimbo-dj's ``tracks`` row, keyed by ``rating_key``). Its **file key** is the
path of its file below Plex's music folder: Unicode NFC, ``/`` separators, no leading slash, case kept. All
three servers read the same music folder, so the file key is what T14 matches Jellyfin items and Navidrome
songs by; the **loose key** (the file key case-folded) is the fallback for a server on a case-insensitive disk.
Each copy also carries its song (jimbo-dj's songs.py: artist and title without the version) and its match
key (jimbo-dj's history.py: how listens are matched), both vendored unchanged, for the tag tier.

Plex's music folders come from, in order: jimbo-dj's configured PATH_MAP folders (the keys of its stored
``library.stats`` ``paths.folders``), ``TRAQFREQ_PLEX_ROOTS``, or the folder every live path shares. The
answer says which.

Read-only: one SELECT over live tracks, kept in memory per library state (like the songs index).
"""

from __future__ import annotations

import json
import posixpath
import sqlite3
import threading
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import urlencode

from .vendor.jimbodj_history import match_key
from .vendor.jimbodj_songs import Index

IDENTITY_VERSION = 1

ISSUES = ("no_path", "outside_roots", "shared_file", "loose_clash", "multi_part", "no_duration")

RULES = {
    "copies": "Live tracks in jimbo-dj's database (removed_at IS NULL): one Plex copy each, keyed by rating_key.",
    "with_file": "Copies with a file key: Plex gives a path and it is inside one of Plex's music folders. "
                 "The file key is the path below that folder (Unicode NFC, / separators, case kept).",
    "files": "Distinct file keys among the copies.",
    "songs": "Songs as jimbo-dj counts them (songs.py): track artist (else album artist) and title without "
             "the version, so a live take and the album track are one song.",
    "songs_with_versions": "Songs with more than one copy in the library.",
    "match_keys": "Distinct listen match keys (history.py: normalised artist|title) among the copies.",
    "no_path": "Plex gives no file for the copy (plex_path is empty). No other server can be matched by file.",
    "outside_roots": "The file is outside every Plex music folder, so it has no file key.",
    "shared_file": "Two or more live copies point at one file. They will match the same item on another server.",
    "loose_clash": "Two different file keys that are equal once case-folded: on a case-insensitive disk they "
                   "would be one file, so the loose key can't decide between them.",
    "multi_part": "Plex joins two or more files into this copy and jimbo-dj keeps only the first part's path. "
                  "The other parts may be items of their own on Jellyfin and Navidrome.",
    "no_duration": "Plex gives no duration, so the tag tier (durations within 2 s) can't use the copy.",
}

ROOT_SOURCES = {
    "jimbodj": "jimbo-dj's music folders (its PATH_MAP, as stored in library.stats paths.folders)",
    "env": "TRAQFREQ_PLEX_ROOTS",
    "common": "the folder every live track's path shares (jimbo-dj stored no music folders)",
    "none": "no music folders: Plex gives no paths",
}

_Q = ("SELECT rating_key, guid, title, artist, track_artist, album, album_key, artist_key, disc, track_no, "
      "duration_ms, plex_path, parts, file_size FROM tracks WHERE removed_at IS NULL")


class NoLibrary(LookupError):
    pass


def _clean_root(r: str) -> str:
    r = unicodedata.normalize("NFC", r.strip().replace("\\", "/"))
    return r.rstrip("/") or "/"


def stored_folders(conn: sqlite3.Connection) -> list[str]:
    """The Plex folders jimbo-dj maps (keys of its stored library.stats paths.folders), if it stored any."""
    try:
        row = conn.execute("SELECT value FROM stats WHERE name = 'library.stats' ORDER BY built_at DESC").fetchone()
    except sqlite3.OperationalError:
        return []
    if not row:
        return []
    try:
        folders = ((json.loads(row[0]) or {}).get("paths") or {}).get("folders") or {}
    except (ValueError, AttributeError):
        return []
    return [_clean_root(k) for k in folders if isinstance(k, str) and k.strip()]


def common_folder(paths: list[str]) -> str | None:
    """The deepest folder every path is in ("/" when they share none but the root)."""
    dirs = [posixpath.dirname(_clean_root(p)) for p in paths if p]
    if not dirs:
        return None
    first = dirs[0].split("/")
    n = len(first)
    for d in dirs[1:]:
        parts = d.split("/")
        n = min(n, len(parts))
        for i in range(n):
            if parts[i] != first[i]:
                n = i
                break
    return "/".join(first[:n]) or "/"


def plex_roots(conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()) -> tuple[list[str], str]:
    """Plex's music folders and where they come from (a ROOT_SOURCES key). Longest first, so a nested folder
    wins over its parent."""
    roots, source = stored_folders(conn), "jimbodj"
    if not roots and env_roots:
        roots, source = [_clean_root(r) for r in env_roots if r.strip()], "env"
    if not roots:
        paths = [r[0] for r in conn.execute("SELECT plex_path FROM tracks WHERE removed_at IS NULL AND plex_path IS NOT NULL")]
        c = common_folder(paths)
        roots, source = ([c], "common") if c else ([], "none")
    return sorted(set(roots), key=lambda r: (-len(r), r)), source


def file_key(path: str | None, roots: list[str]) -> tuple[str | None, str | None]:
    """(root, file key) for a server path, or (None, None) when it is outside every root. NFC, / separators,
    no leading slash, case kept; the root itself is not a file."""
    if not path:
        return None, None
    p = unicodedata.normalize("NFC", path.replace("\\", "/"))
    while "//" in p:
        p = p.replace("//", "/")
    for root in roots:
        if root == "/":
            rel = p.lstrip("/")
        elif p.startswith(root + "/"):
            rel = p[len(root) + 1:]
        else:
            continue
        rel = rel.strip("/")
        if rel:
            return root, rel
    return None, None


def loose_key(key: str | None) -> str | None:
    """The file key case-folded (for a server on a case-insensitive disk)."""
    return unicodedata.normalize("NFC", key.casefold()) if key else None


class Identity:
    """Every live copy with its file key, loose key, song and match key, and its issues."""

    def __init__(self, conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()):
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tracks'").fetchone():
            raise NoLibrary("jimbo-dj's database has no tracks table")
        self.roots, self.root_source = plex_roots(conn, env_roots)
        self.copies: list[dict] = []
        for r in conn.execute(_Q):
            t = dict(r)
            root, key = file_key(t["plex_path"], self.roots)
            t.update(root=root, file=key, loose=loose_key(key), song=Index.song_key(t),
                     match_key=match_key(t["track_artist"] or t["artist"], t["title"]), issues=[])
            if not t["plex_path"]:
                t["issues"].append("no_path")
            elif key is None:
                t["issues"].append("outside_roots")
            if (t["parts"] or 0) > 1:
                t["issues"].append("multi_part")
            if not t["duration_ms"]:
                t["issues"].append("no_duration")
            self.copies.append(t)
        by_file = Counter(t["file"] for t in self.copies if t["file"])
        files_of_loose: dict[str, set[str]] = defaultdict(set)
        for t in self.copies:
            if t["file"]:
                files_of_loose[t["loose"]].add(t["file"])
        for t in self.copies:
            if t["file"] and by_file[t["file"]] > 1:
                t["issues"].insert(0, "shared_file")
            if t["file"] and len(files_of_loose[t["loose"]]) > 1:
                t["issues"].insert(0, "loose_clash")
            t["issues"].sort(key=ISSUES.index)
        self.song_copies = Counter(t["song"] for t in self.copies)
        self.by_key = {t["rating_key"]: t for t in self.copies}


def stamp(conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()) -> tuple:
    """What the identity is built from: which database, jimbo-dj's last sync, the live tracks (count, newest
    key), the stored library.stats row (its folders) and traqfreq's own roots setting."""
    file = conn.execute("PRAGMA database_list").fetchone()[2]
    sync = conn.execute("SELECT value FROM meta WHERE key = 'last_sync'").fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone() else None
    live = conn.execute("SELECT COUNT(*), MAX(rating_key) FROM tracks WHERE removed_at IS NULL").fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='tracks'").fetchone() else (0, None)
    try:
        st = conn.execute("SELECT MAX(built_at) FROM stats WHERE name = 'library.stats'").fetchone()[0]
    except sqlite3.OperationalError:
        st = None
    return (file, sync[0] if sync else None, *live, st, env_roots)


def cache_key(conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()) -> str:
    s = stamp(conn, env_roots)
    return "|".join([f"v{IDENTITY_VERSION}", *(str(x) if x is not None else "-" for x in s[1:5]), ",".join(env_roots)])


_built: dict[tuple, Identity] = {}
_lock = threading.Lock()


def identity(conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()) -> Identity:
    """The Identity for this database and library state (built once, then kept in memory)."""
    s = stamp(conn, env_roots)
    with _lock:
        idn = _built.get(s)
        if idn is None:
            _built.clear()
            idn = _built[s] = Identity(conn, env_roots)
        return idn


def _q(**params) -> str:
    return urlencode({k: v for k, v in params.items() if v is not None})


def summary(conn: sqlite3.Connection, env_roots: tuple[str, ...] = ()) -> dict:
    """Every identity count, with its rule (W3) and the /api/servers/copies query for its rows."""
    idn = identity(conn, env_roots)
    cs = idn.copies
    counts = {
        "copies": len(cs),
        "with_file": sum(1 for t in cs if t["file"]),
        "files": len({t["file"] for t in cs if t["file"]}),
        "songs": len(idn.song_copies),
        "songs_with_versions": sum(1 for n in idn.song_copies.values() if n > 1),
        "match_keys": len({t["match_key"] for t in cs}),
    }
    issues = {i: sum(1 for t in cs if i in t["issues"]) for i in ISSUES}
    rows = {"copies": _q(), "with_file": _q(has_file="true"), "files": _q(has_file="true"),
            "songs": _q(), "songs_with_versions": _q(versions="true"), "match_keys": _q(),
            **{i: _q(issue=i) for i in ISSUES}}
    folder_tracks = Counter(t["root"] for t in cs if t["root"])
    return {
        "counts": counts,
        "issues": issues,
        "clean": sum(1 for t in cs if not t["issues"]),
        "roots": [{"folder": r, "tracks": folder_tracks.get(r, 0)} for r in idn.roots],
        "root_source": idn.root_source,
        "root_rule": ROOT_SOURCES[idn.root_source],
        "rules": RULES,
        "rows": rows,
        "tiers": [
            {"tier": "file", "rule": "The same file key; then the same loose key when only one item has it."},
            {"tier": "mbid", "rule": "The same MusicBrainz recording and release, from the server's tags."},
            {"tier": "tags", "rule": "The same match key, album, disc and track number, durations within 2 s; "
                                     "only when exactly one candidate is left."},
        ],
        "version": IDENTITY_VERSION,
    }


COPY_FIELDS = ("rating_key", "guid", "title", "artist", "track_artist", "album", "album_key", "artist_key",
               "disc", "track_no", "duration_ms", "plex_path", "parts", "file_size", "root", "file", "loose",
               "song", "match_key", "issues")

SORTS = {
    "file": lambda t: (t["file"] is None, t["file"] or "", t["rating_key"]),
    "artist": lambda t: ((t["artist"] or "").casefold(), t["album"] or "", t["disc"] or 0, t["track_no"] or 0, t["rating_key"]),
    "key": lambda t: t["rating_key"],
}


def copies(conn: sqlite3.Connection, env_roots: tuple[str, ...] = (), issue: str | None = None,
           song: str | None = None, file: str | None = None, has_file: bool | None = None,
           versions: bool | None = None, rating_key: int | None = None, sort: str = "file",
           limit: int = 50, offset: int = 0) -> dict:
    """The copies behind an identity count, 50 a page: by issue, song key, file key (exact or loose), with a
    file key or not, songs with more than one copy, or one rating key."""
    if issue is not None and issue not in ISSUES:
        raise ValueError(f"issue must be one of {', '.join(ISSUES)}")
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)}")
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    idn = identity(conn, env_roots)
    sel = idn.copies
    rule = ["live copies"]
    if issue:
        sel = [t for t in sel if issue in t["issues"]]
        rule.append(f"with {issue}")
    if song:
        sel = [t for t in sel if t["song"] == song]
        rule.append(f"of song {song}")
    if file:
        fk = unicodedata.normalize("NFC", file.replace("\\", "/")).strip("/")
        lk = loose_key(fk)
        sel = [t for t in sel if t["file"] == fk or t["loose"] == lk]
        rule.append(f"whose file key is {fk} (or equal once case-folded)")
    if has_file is not None:
        sel = [t for t in sel if bool(t["file"]) == has_file]
        rule.append("with a file key" if has_file else "without a file key")
    if versions:
        sel = [t for t in sel if idn.song_copies[t["song"]] > 1]
        rule.append("of songs with more than one copy")
    if rating_key is not None:
        sel = [t for t in sel if t["rating_key"] == rating_key]
        rule.append(f"rating key {rating_key}")
    sel = sorted(sel, key=SORTS[sort])
    page = sel[offset:offset + limit]
    return {
        "total": len(sel),
        "offset": offset,
        "limit": limit,
        "sort": sort,
        "rule": ", ".join(rule),
        "copies": [{**{k: t[k] for k in COPY_FIELDS}, "song_copies": idn.song_copies[t["song"]]} for t in page],
    }
