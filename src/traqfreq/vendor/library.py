"""jimbo-dj's library.py: ``sync`` copied unchanged at 1d8a7cb (``stats`` and ``_check_files`` aren't needed; traqfreq
has its own LIBRARY numbers). ``db`` and ``config`` are traqfreq's stand-ins (vendor/db.py, vendor/config.py): ``db.connect``
opens traqfreq's library.sqlite and only once the ``plex`` cut-over is owned. Called only through traqfreq.plexsync.run."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time

from . import db, metadata, plex
from .config import Settings

log = logging.getLogger(__name__)

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/library.py (sync)"


def sync(s: Settings, progress=None) -> dict:
    """Read every track from Plex into the tracks table, then albums, artists and audio streams.
    Returns a short summary. progress(detail) is told what's happening."""
    t0 = time.time()
    now = int(t0)
    server = plex.connect(s)
    section = plex.music_section(server, s)
    log.info("Plex %s (%s), library %r (section %s)", server.friendlyName, server.version, section.title, section.key)
    con = db.connect(s.db_path)
    seen = 0
    with con:
        for page, total in plex.iter_track_pages(server, section.key):
            rows = [plex.track_row(el, s, now) for el in page]
            db.upsert_tracks(con, rows)
            seen += len(rows)
            log.info("synced %d / %d tracks", seen, total)
        removed = con.execute(
            "UPDATE tracks SET removed_at=? WHERE seen_at<? AND removed_at IS NULL", (now, now)
        ).rowcount
        db.set_meta(con, "last_sync", str(now))
        db.set_meta(con, "server", json.dumps({
            "name": server.friendlyName, "version": server.version,
            "machine_id": server.machineIdentifier,
            "plex_pass": bool(getattr(server, "myPlexSubscription", False)),
            "section": section.title, "section_key": str(section.key),
        }))
    progress and progress("Reading albums and artists")
    with con:
        aa = metadata.sync_albums_artists(con, server, section.key, now)
    streams = metadata.sync_streams(con, server, progress and (lambda d, t: progress(f"Reading audio formats: {d:,} / {t:,}")))
    con.close()
    return {"tracks": seen, "removed": removed, **aa, "streams": streams, "seconds": round(time.time() - t0, 1)}

