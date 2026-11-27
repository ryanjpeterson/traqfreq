"""jimbo-dj's metadata.py, copied unchanged at 1d8a7cb. Its docstring follows.

Library metadata beyond the track list, read from Plex during a sync (read-only):

- albums: genre tags, original release date, label, MusicBrainz release ID;
- artists: country, genre tags, MusicBrainz artist ID;
- per track: bit depth and sample rate (from the audio stream) and the track's own genre and mood tags.

The track listing Plex pages through doesn't include streams, so those come from bulk metadata
requests (200 tracks each, about 0.1 s), only for tracks not read yet or whose file changed.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from xml.etree.ElementTree import Element

from .plex import _int

log = logging.getLogger(__name__)

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/metadata.py (whole file)"

ALBUM_TYPE, ARTIST_TYPE = 9, 8
PAGE = 2000
STREAM_BATCH = 200


def _tags(el: Element, name: str) -> list[str]:
    return [t.get("tag") for t in el.findall(name) if t.get("tag")]


def _mbid(el: Element) -> str | None:
    for g in el.findall("Guid"):
        gid = g.get("id") or ""
        if gid.startswith("mbid://"):
            return gid[7:]
    gid = el.get("guid") or ""
    return gid[7:] if gid.startswith("mbid://") else None


def _pages(server, section_key, kind: int):
    start = 0
    while True:
        c = server.query(f"/library/sections/{section_key}/all?type={kind}&includeGuids=1"
                         f"&X-Plex-Container-Start={start}&X-Plex-Container-Size={PAGE}")
        items = c.findall("Directory")
        if not items:
            return
        yield items
        start += len(items)
        if start >= int(c.get("totalSize") or c.get("size") or 0):
            return


def sync_albums_artists(con, server, section_key, now: int) -> dict:
    albums = artists = 0
    for page in _pages(server, section_key, ALBUM_TYPE):
        con.executemany(
            "INSERT INTO albums VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(album_key) DO UPDATE SET title=excluded.title, "
            "artist_key=excluded.artist_key, year=excluded.year, released=excluded.released, studio=excluded.studio, "
            "genres=excluded.genres, mbid=excluded.mbid, seen_at=excluded.seen_at",
            [(int(el.get("ratingKey")), el.get("title"), _int(el, "parentRatingKey"), _int(el, "year"),
              el.get("originallyAvailableAt"), el.get("studio"), json.dumps(_tags(el, "Genre")), _mbid(el), now)
             for el in page])
        albums += len(page)
    for page in _pages(server, section_key, ARTIST_TYPE):
        con.executemany(
            "INSERT INTO artists VALUES (?,?,?,?,?,?) ON CONFLICT(artist_key) DO UPDATE SET title=excluded.title, "
            "countries=excluded.countries, genres=excluded.genres, mbid=excluded.mbid, seen_at=excluded.seen_at",
            [(int(el.get("ratingKey")), el.get("title"), json.dumps(_tags(el, "Country")),
              json.dumps(_tags(el, "Genre")), _mbid(el), now) for el in page])
        artists += len(page)
    return {"albums": albums, "artists": artists}


def sync_streams(con, server, progress: Callable[[int, int], None] | None = None) -> int:
    """Bit depth, sample rate and track tags for tracks not read yet, or whose file changed."""
    keys = [r[0] for r in con.execute(
        "SELECT rating_key FROM tracks WHERE removed_at IS NULL AND stream_size IS NOT file_size")]
    done = 0
    for i in range(0, len(keys), STREAM_BATCH):
        batch = keys[i:i + STREAM_BATCH]
        c = server.query("/library/metadata/" + ",".join(map(str, batch)))
        rows = []
        for el in c.findall("Track"):
            media = el.find("Media")
            part = media.find("Part") if media is not None else None
            stream = next((s for s in (part.findall("Stream") if part is not None else []) if s.get("streamType") == "2"), None)
            rows.append((
                _int(stream, "bitDepth") if stream is not None else None,
                _int(stream, "samplingRate") if stream is not None else None,
                _int(part, "size") if part is not None else None,
                json.dumps(_tags(el, "Genre")), json.dumps(_tags(el, "Mood")),
                int(el.get("ratingKey")),
            ))
        con.executemany("UPDATE tracks SET bit_depth=?, sample_rate=?, stream_size=?, plex_genres=?, plex_moods=? "
                        "WHERE rating_key=?", rows)
        con.commit()
        done += len(rows)
        if progress:
            progress(done, len(keys))
    return done
