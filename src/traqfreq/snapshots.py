"""Server snapshots: each server's item list in one shape (T14, spec docs/specs/t13-servers.md).

A snapshot is a server's whole item list as traqfreq read it, with when it was read, the server's own stamp
(Jellyfin: item count and newest ``DateCreated``; Navidrome: ``lastScan``) and its music folders. It is kept in
traqfreq's database (``store.save_snapshot``) and matched from there (``matching.py``).

This module only turns answers into items: Jellyfin's ``/Library/VirtualFolders`` and ``/Items``, Navidrome's
Subsonic ``getScanStatus``, ``getAlbumList2`` and ``search3``. It sends nothing: the readers that ask the
servers (GET only) are T16–T18. In T14 the answers are invented fixtures (``scripts/fixture_*.json``).

The **item shape**: ``server``, ``id`` (the server's own item ID), ``path`` (as the server reports it),
``hidden`` (the server gives no real path), ``root`` and ``file`` (the file key below the server's music
folder, as in identity.py), ``loose``, ``title``, ``artist``, ``album_artist``, ``album``, ``disc``,
``track``, ``duration_ms``, ``mb_recording``, ``mb_release``, ``size``, ``play_count``.
"""

from __future__ import annotations

import posixpath
import time

from .identity import _clean_root, common_folder, file_key, loose_key

ITEM_FIELDS = ("server", "id", "path", "hidden", "root", "file", "loose", "title", "artist", "album_artist",
               "album", "disc", "track", "duration_ms", "mb_recording", "mb_release", "size", "play_count")

FOLDER_SOURCES = {
    "server": "the server's own music folders",
    "common": "the folder every real path shares (the server names no folder paths)",
    "none": "no music folders: the server gives no real paths",
}


def _absolute(path: str | None) -> bool:
    if not path:
        return False
    p = path.replace("\\", "/")
    return p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] == "/")


def _int(v) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _item(server: str, roots: list[str], **f) -> dict:
    path = f.get("path") or None
    hidden = bool(path) and not _absolute(path)
    root, key = (None, None) if hidden else file_key(path, roots)
    out = dict(f, server=server, path=path, hidden=hidden, root=root, file=key, loose=loose_key(key))
    return {k: out.get(k) for k in ITEM_FIELDS}


def _roots(server_roots: list[str], paths: list[str]) -> tuple[list[str], str]:
    roots = [_clean_root(r) for r in server_roots if r and r.strip()]
    if roots:
        return sorted(set(roots), key=lambda r: (-len(r), r)), "server"
    real = [p for p in paths if _absolute(p)]
    c = common_folder(real)
    return ([c], "common") if c else ([], "none")


def jellyfin_item(it: dict, roots: list[str]) -> dict:
    """One Jellyfin ``/Items`` entry in the item shape, its file key below ``roots`` (a snapshot's folders)."""
    ms = (it.get("MediaSources") or [{}])[0] or {}
    ids = it.get("ProviderIds") or {}
    ticks = _int(it.get("RunTimeTicks"))
    artists = it.get("Artists") or []
    return _item(
        "jellyfin", roots, id=it.get("Id"), path=it.get("Path") or ms.get("Path"), title=it.get("Name"),
        artist=artists[0] if artists else it.get("AlbumArtist"), album_artist=it.get("AlbumArtist"),
        album=it.get("Album"), disc=_int(it.get("ParentIndexNumber")), track=_int(it.get("IndexNumber")),
        duration_ms=ticks // 10_000 if ticks else None, mb_recording=ids.get("MusicBrainzRecording") or None,
        mb_release=ids.get("MusicBrainzAlbum") or None, size=_int(ms.get("Size")),
        play_count=_int((it.get("UserData") or {}).get("PlayCount")))


def navidrome_song(s: dict, roots: list[str], album: dict | None = None) -> dict:
    """One Subsonic song in the item shape; ``album`` (its ``getAlbumList2`` entry) gives the release ID."""
    dur = _int(s.get("duration"))
    album = album or {}
    return _item(
        "navidrome", roots, id=s.get("id"), path=s.get("path"), title=s.get("title"), artist=s.get("artist"),
        album_artist=s.get("displayAlbumArtist") or album.get("artist"), album=s.get("album"),
        disc=_int(s.get("discNumber")), track=_int(s.get("track")),
        duration_ms=dur * 1000 if dur else None, mb_recording=s.get("musicBrainzId") or None,
        mb_release=album.get("musicBrainzId") or None, size=_int(s.get("size")),
        play_count=_int(s.get("playCount")))


def snapshot(server: str, items: list[dict], folders: list[str], folder_source: str, stamp: dict,
             read_at: float | None = None) -> dict:
    return {"server": server, "read_at": time.time() if read_at is None else read_at, "stamp": stamp,
            "folders": folders, "folder_source": folder_source, "items": items}


def from_jellyfin(virtual_folders: list[dict], pages: list[dict], read_at: float | None = None,
                  info: dict | None = None, user: str | None = None) -> dict:
    """A Jellyfin snapshot from ``/Library/VirtualFolders`` (its music libraries' ``Locations``) and the pages
    of ``/Items?IncludeItemTypes=Audio&Recursive=true&Fields=Path,ProviderIds,MediaSources,ParentId``.
    Duration is ``RunTimeTicks`` (100 ns); the file size is the first media source's; the play count is
    ``UserData.PlayCount`` (T17's reader fills it from one user's ``/Users/{id}/Items``, else leaves none).
    ``info`` is ``/System/Info/Public``: its ``ServerName`` and ``Version`` go in the stamp, with ``user``
    (whose play counts these are)."""
    raw = [it for page in pages for it in (page.get("Items") or []) if it.get("Type", "Audio") == "Audio"]
    locs = [loc for vf in virtual_folders or [] if vf.get("CollectionType") in (None, "music")
            for loc in vf.get("Locations") or []]
    roots, source = _roots(locs, [it.get("Path") for it in raw if it.get("Path")])
    items = [jellyfin_item(it, roots) for it in raw]
    created = [it.get("DateCreated") for it in raw if it.get("DateCreated")]
    total = pages[-1].get("TotalRecordCount") if pages else 0  # the newest total: it can move while pages are read
    stamp = {"items": total, "newest_created": max(created) if created else None}
    if info is not None:
        stamp.update(server_name=info.get("ServerName") or None, version=info.get("Version") or None, user=user)
    return snapshot("jellyfin", items, roots, source, stamp, read_at)


def _subsonic(answer: dict, key: str) -> dict:
    r = (answer or {}).get("subsonic-response") or {}
    if r.get("status") != "ok":
        raise ValueError(f"Navidrome answered {r.get('status')!r}: {(r.get('error') or {}).get('message')}")
    return r.get(key) or {}


def from_navidrome(scan_status: dict, album_pages: list[dict], song_pages: list[dict],
                   folders: list[str] = (), read_at: float | None = None, info: dict | None = None,
                   user: str | None = None, music_folders: dict | None = None) -> dict:
    """A Navidrome snapshot from Subsonic ``getScanStatus`` (``lastScan``), the pages of ``getAlbumList2``
    (each album's ``musicBrainzId`` is the release; Subsonic songs carry only the recording) and the pages of
    ``search3`` with an empty query (``songCount``/``songOffset``). With "Report Real Path" off a song's
    ``path`` is made up and relative: such a song is ``hidden`` and has no file key. Subsonic names no folder
    paths, so the music folder is ``folders`` if given (``TRAQFREQ_NAVIDROME_ROOTS``), else the folder every real
    path shares. ``info`` is ``ping`` (its ``type`` and ``serverVersion`` go in the stamp as ``server_name`` and
    ``version``, with ``user``, whose play counts these are); ``music_folders`` is ``getMusicFolders`` (their
    names go in the stamp: Subsonic gives no paths)."""
    albums = {a.get("id"): a for page in album_pages for a in _subsonic(page, "albumList2").get("album") or []}
    raw = [s for page in song_pages for s in _subsonic(page, "searchResult3").get("song") or []]
    roots, source = _roots(list(folders), [s.get("path") for s in raw if s.get("path")])
    items = [navidrome_song(s, roots, albums.get(s.get("albumId"))) for s in raw]
    scan = _subsonic(scan_status, "scanStatus")
    stamp = {"items": len(items), "last_scan": scan.get("lastScan"), "hidden_paths": sum(i["hidden"] for i in items)}
    if info is not None:
        ping = (info or {}).get("subsonic-response") or {}
        stamp.update(server_name=ping.get("type") or None, version=ping.get("serverVersion") or None, user=user,
                     open_subsonic=bool(ping.get("openSubsonic")), scan_count=_int(scan.get("count")))
    if music_folders is not None:
        stamp["music_folders"] = [f.get("name") for f in _subsonic(music_folders, "musicFolders").get("musicFolder") or []]
    return snapshot("navidrome", items, roots, source, stamp, read_at)


def folder_of(file: str | None) -> str | None:
    return posixpath.dirname(file) if file else None
