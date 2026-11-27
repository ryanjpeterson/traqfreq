"""jimbo-dj's plex.py, copied unchanged at 1d8a7cb except ``connect``: jimbo-dj's builds plexapi's ``PlexServer``;
traqfreq has no plexapi, so ``connect`` is a stand-in that builds ``plexserver.PlexServer`` (GET only, the same
attributes and ``query``) and names traqfreq's setting. ``Settings`` is the stand-in in vendor/config.py.

jimbo-dj's docstring follows.

Reading the Plex music library.

Tracks are read as raw XML pages rather than plexapi objects: plexapi reloads an
object whenever an attribute is missing, which would mean one request per track
on a 50k-track library.
"""
from __future__ import annotations

import posixpath
from collections.abc import Iterator
from xml.etree.ElementTree import Element

from .config import Settings
from .plexserver import PlexServer

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/plex.py (all but connect)"

PAGE_SIZE = 2000
TRACK_TYPE = 10


class PlexError(RuntimeError):
    pass


def connect(s: Settings) -> PlexServer:  # traqfreq's stand-in (jimbo-dj's builds plexapi's PlexServer)
    if not s.plex_token:
        raise PlexError("TRAQFREQ_PLEX_TOKEN is not set")
    return PlexServer(s.plex_url, s.plex_token, timeout=60, transport=s.transport)


def music_sections(plex: PlexServer) -> list:
    return [sec for sec in plex.library.sections() if sec.type == "artist"]


def music_section(plex: PlexServer, s: Settings):
    sections = music_sections(plex)
    if s.music_section:
        for sec in sections:
            if sec.title == s.music_section:
                return sec
        names = ", ".join(sec.title for sec in sections) or "none"
        raise PlexError(f"No music library called {s.music_section!r} (found: {names})")
    if len(sections) == 1:
        return sections[0]
    names = ", ".join(sec.title for sec in sections) or "none"
    raise PlexError(f"Set PLEX_MUSIC_SECTION; music libraries found: {names}")


def map_path(plex_path: str | None, s: Settings) -> str | None:
    """Translate a file path as Plex sees it into the path this process reads (None: outside every music folder)."""
    if not plex_path:
        return None
    if not s.path_map:  # no folders set: read every file where Plex has it (Plex runs on this machine)
        return plex_path
    for plex_dir, local_dir in s.path_map:
        if plex_path == plex_dir or plex_path.startswith(plex_dir + "/"):
            rel = plex_path[len(plex_dir):].lstrip("/")
            return posixpath.join(local_dir, rel) if rel else local_dir
    return None


def _int(el: Element, name: str) -> int | None:
    v = el.get(name)
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def _float(el: Element, name: str) -> float | None:
    v = el.get(name)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def track_row(el: Element, s: Settings, now: int) -> dict:
    media = el.find("Media")
    parts = media.findall("Part") if media is not None else []
    part = parts[0] if parts else None
    plex_path = part.get("file") if part is not None else None
    artist = el.get("grandparentTitle")
    track_artist = el.get("originalTitle")
    return {
        "rating_key": int(el.get("ratingKey")),
        "guid": el.get("guid"),
        "title": el.get("title"),
        "artist": artist,
        "track_artist": track_artist if track_artist and track_artist != artist else None,
        "album": el.get("parentTitle"),
        "album_key": _int(el, "parentRatingKey"),
        "artist_key": _int(el, "grandparentRatingKey"),
        "disc": _int(el, "parentIndex"),
        "track_no": _int(el, "index"),
        "year": _int(el, "parentYear") or _int(el, "year"),
        "duration_ms": _int(el, "duration"),
        "plex_path": plex_path,
        "local_path": map_path(plex_path, s),
        "parts": len(parts),
        "file_size": _int(part, "size") if part is not None else None,
        "container": (part.get("container") if part is not None else None) or (media.get("container") if media is not None else None),
        "codec": media.get("audioCodec") if media is not None else None,
        "bitrate": _int(media, "bitrate") if media is not None else None,
        "channels": _int(media, "audioChannels") if media is not None else None,
        "view_count": _int(el, "viewCount") or 0,
        "last_viewed_at": _int(el, "lastViewedAt"),
        "user_rating": _float(el, "userRating"),
        "added_at": _int(el, "addedAt"),
        "updated_at": _int(el, "updatedAt"),
        "sonic_version": _int(el, "musicAnalysisVersion"),
        "seen_at": now,
    }


def iter_track_pages(plex: PlexServer, section_key: int | str) -> Iterator[tuple[list[Element], int]]:
    """Yield (track elements, library total) one page at a time."""
    start = 0
    while True:
        container = plex.query(
            f"/library/sections/{section_key}/all?type={TRACK_TYPE}"
            f"&X-Plex-Container-Start={start}&X-Plex-Container-Size={PAGE_SIZE}"
        )
        total = int(container.get("totalSize") or container.get("size") or 0)
        tracks = container.findall("Track")
        if not tracks:
            return
        yield tracks, total
        start += len(tracks)
        if start >= total:
            return
