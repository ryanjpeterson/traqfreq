"""jimbo-dj's watcher.py, copied unchanged at 1d8a7cb except ``enabled`` and ``interval``: traqfreq's watcher is
off unless TRAQFREQ_WATCH=on, every TRAQFREQ_WATCH_INTERVAL seconds (default 300, at least 60). ``config`` and ``db``
are traqfreq's stand-ins: ``db.connect`` refuses until the ``plex`` cut-over is owned, so the watcher never writes
before then. ``watch_fingerprint`` is a meta key the ``plex`` cut-over owns. jimbo-dj's docstring follows.

Watching Plex for new music, so anything that arrives is synced and enriched without waiting for the
nightly sync.

Every WATCH_INTERVAL seconds (default 300) the watcher asks Plex for a fingerprint of the music library:
how many tracks there are and the newest added and updated times (two one-item requests). While Plex is
still scanning (the section is "refreshing") it waits. When the fingerprint changes, it calls on_change
(the app syncs, which wakes the MusicBrainz enricher). Network only, no CPU to speak of, so it never
competes with the analyzer. JIMBODJ_WATCH=off turns it off.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable

from . import config, db, plex

log = logging.getLogger(__name__)

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/watcher.py (all but enabled, interval)"

_state: dict = {"started": False, "checked_at": None, "changed_at": None, "scanning": False, "error": None}
_lock = threading.Lock()


def interval() -> int:  # traqfreq's stand-in: TRAQFREQ_WATCH_INTERVAL (jimbo-dj's: WATCH_INTERVAL), same rule
    try:
        return max(60, int(os.environ.get("TRAQFREQ_WATCH_INTERVAL", "300")))
    except ValueError:
        return 300


def enabled() -> bool:  # traqfreq's stand-in: off unless TRAQFREQ_WATCH is on (jimbo-dj's: on unless JIMBODJ_WATCH=off)
    return os.environ.get("TRAQFREQ_WATCH", "off").strip().lower() in ("on", "1", "true", "yes")


def fingerprint(server, section) -> tuple[dict, bool]:
    """(fingerprint, Plex is scanning right now)."""
    def newest(sort: str) -> tuple[int, int | None]:
        c = server.query(f"/library/sections/{section.key}/all?type={plex.TRACK_TYPE}&sort={sort}:desc"
                         "&X-Plex-Container-Start=0&X-Plex-Container-Size=1")
        el = c.find("Track")
        return int(c.get("totalSize") or 0), int(el.get(sort.split(":")[0]) or 0) if el is not None else None

    total, added = newest("addedAt")
    _, updated = newest("updatedAt")
    scanning = False
    for el in server.query("/library/sections").findall("Directory"):
        if str(el.get("key")) == str(section.key):
            scanning = el.get("refreshing") == "1"
    return {"tracks": total, "added": added, "updated": updated}, scanning


def state() -> dict:
    with _lock:
        return {**_state, "enabled": enabled(), "interval": interval()}


def check(on_change: Callable[[str], bool]) -> str:
    """One look at Plex. on_change(reason) syncs and returns True when it worked."""
    s = config.load()
    server = plex.connect(s)
    section = plex.music_section(server, s)
    fp, scanning = fingerprint(server, section)
    with _lock:
        _state.update(checked_at=time.time(), scanning=scanning, error=None)
    if scanning:
        return "Plex is scanning; waiting for it to finish"
    con = db.connect(s.db_path)
    try:
        old = db.get_meta(con, "watch_fingerprint")
        if old and json.loads(old) == fp:
            return "nothing new"
        reason = "first look" if not old else (
            f"{fp['tracks'] - json.loads(old)['tracks']:+,} tracks" if json.loads(old)["tracks"] != fp["tracks"] else "tracks added or changed")
        log.info("watcher: library changed (%s)", reason)
        if on_change(reason):
            with con:
                db.set_meta(con, "watch_fingerprint", json.dumps(fp))
            with _lock:
                _state["changed_at"] = time.time()
            return f"synced: {reason}"
        return "sync didn't finish; trying again next time"
    finally:
        con.close()


def start(on_change: Callable[[str], bool], first_delay: float = 20) -> None:
    with _lock:
        if _state["started"] or not enabled():
            return
        _state["started"] = True

    def loop():
        time.sleep(first_delay)
        log.info("watcher on: checking Plex every %d s", interval())
        while True:
            try:
                check(on_change)
            except Exception as e:  # noqa: BLE001 - Plex down, network blip: try again next time
                log.info("watcher: %s", e)
                with _lock:
                    _state["error"] = str(e)
            time.sleep(interval())

    threading.Thread(target=loop, daemon=True, name="jimbodj-watcher").start()
