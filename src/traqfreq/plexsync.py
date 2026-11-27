"""T30, P6 cut-over 1: traqfreq's Plex sync and watcher (docs/specs/t29-cutovers.md).

jimbo-dj's sync is vendored unchanged (vendor/library.py ``sync``, vendor/plex.py, vendor/metadata.py) and so is its
watcher (vendor/watcher.py). This module is the only way in, and it adds traqfreq's rules around them:

- **One writer.** It writes only traqfreq's ``library.sqlite`` and only once the ``plex`` cut-over is owned
  (``own.record(...)["state"] == "owned"``); before that it refuses with the reason. The vendored ``db.connect``
  refuses on its own too, so the watcher can't write early either. One sync at a time (a lock).
- **Plex is read, never changed.** GET only (vendor/plexserver.py). The URL and token come from the environment
  (TRAQFREQ_PLEX_URL, TRAQFREQ_PLEX_TOKEN); the token is never shown, returned or logged.
- **Paths stay jimbo-dj's.** Before writing, every stored track's ``local_path`` is worked out again with
  TRAQFREQ_PLEX_PATH_MAP; if any comes out different, the sync refuses rather than rewrite them.
- **Logged.** Every sync, refused, failed or done, is a row in ``runs`` with its reason, counts and note (when
  library.sqlite exists: a refusal never creates the file). A sync has nothing to undo: the next one reads Plex again.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import own
from .settings import Settings
from .vendor import config, library, plex, watcher

JOB = "plex_sync"
CUTOVER = "plex"
UNDO = "Nothing to undo: a sync only mirrors Plex, and the next one reads it again."
NOTHING = "Nothing was written."
EXAMPLES = 5

_lock = threading.Lock()


class SyncRefused(RuntimeError):
    """The sync didn't start: the reason says why. Nothing was written."""


class SyncFailed(RuntimeError):
    """The sync started and stopped on an error (Plex down, say). What it wrote before is kept, as in jimbo-dj."""


def config_for(settings: Settings, transport=None) -> config.Settings:
    cfg = config.from_traqfreq(settings)
    return config.Settings(plex_url=cfg.plex_url, plex_token=cfg.plex_token, music_section=cfg.music_section,
                           path_map=cfg.path_map, data_dir=cfg.data_dir, transport=transport)


def safe_url(url: str | None) -> str | None:
    if not url:
        return None
    u = urlsplit(url)
    host = (u.hostname or "") + (f":{u.port}" if u.port else "")
    return f"{u.scheme}://{host}{u.path}".rstrip("/") if u.scheme else None


def settings_view(settings: Settings) -> dict:
    """What SETUP may show: never the token, only whether it's set."""
    return {"url": safe_url(settings.plex_url), "token_set": bool(settings.plex_token),
            "section": settings.plex_section, "path_map": settings.plex_path_map,
            "env": ["TRAQFREQ_PLEX_URL", "TRAQFREQ_PLEX_TOKEN", "TRAQFREQ_PLEX_MUSIC_SECTION", "TRAQFREQ_PLEX_PATH_MAP"]}


def path_map_check(data_dir: Path, cfg: config.Settings) -> dict:
    """Every stored track's local_path worked out again from its plex_path with this path map (plex.map_path, as the
    sync will): how many come out different, with a few examples. Read-only."""
    p = own.path(data_dir)
    conn = sqlite3.connect(f"file:{quote(str(p.resolve()))}?mode=ro", uri=True)
    try:
        checked = differ = 0
        examples = []
        for plex_path, local_path in conn.execute("SELECT plex_path, local_path FROM tracks WHERE plex_path IS NOT NULL"):
            checked += 1
            mapped = plex.map_path(plex_path, cfg)
            if mapped != local_path:
                differ += 1
                if len(examples) < EXAMPLES:
                    examples.append({"plex_path": plex_path, "stored": local_path, "mapped": mapped})
    finally:
        conn.close()
    return {"checked": checked, "differ": differ, "examples": examples}


def _clean(text: str, settings: Settings) -> str:
    return text.replace(settings.plex_token, "…") if settings.plex_token else text


def run(settings: Settings, reason: str, transport=None, progress=None) -> dict:
    """One Plex sync into library.sqlite, logged in ``runs``. Raises SyncRefused (nothing written) or SyncFailed."""
    t0 = time.time()
    data_dir = settings.data_dir

    def refuse(why: str, counts: dict | None = None):
        if own.path(data_dir).is_file():
            own.log_run(data_dir, JOB, t0, False, counts or {}, f"Refused: {why}", reason or "-", NOTHING)
        raise SyncRefused(why)

    if not (reason or "").strip():
        raise SyncRefused("a reason is required")
    state = own.record(data_dir, CUTOVER)["state"]
    if state != own.OWNED:
        refuse(f"the {CUTOVER} cut-over isn't owned by traqfreq ({state.replace('_', ' ')}), so jimbo-dj still "
               f"writes its tables. Run traqfreq-cutover copy {CUTOVER} at deploy, after jimbo-dj's sync is off.")
    if not settings.plex_url:
        refuse("TRAQFREQ_PLEX_URL is not set")
    if not settings.plex_token:
        refuse("TRAQFREQ_PLEX_TOKEN is not set")
    if not _lock.acquire(blocking=False):
        refuse("a sync is already running")
    try:
        cfg = config_for(settings, transport)
        pm = path_map_check(data_dir, cfg)
        if pm["differ"]:
            ex = pm["examples"][0]
            refuse(f"TRAQFREQ_PLEX_PATH_MAP doesn't give jimbo-dj's paths: {pm['differ']:,} of {pm['checked']:,} stored "
                   f"tracks would get another local_path (e.g. {ex['plex_path']!r} is stored as {ex['stored']!r}, "
                   f"the map gives {ex['mapped']!r}). Set it to jimbo-dj's PLEX_PATH_MAP.", {"path_map": pm})
        try:
            summary = library.sync(cfg, progress)
        except Exception as e:  # noqa: BLE001 - Plex down, a timeout: logged, and the next run tries again
            why = _clean(f"{type(e).__name__}: {e}", settings)
            if "PLEX_MUSIC_SECTION" in why:  # jimbo-dj's message names its own setting
                why += " (in traqfreq: TRAQFREQ_PLEX_MUSIC_SECTION)"
            own.log_run(data_dir, JOB, t0, False, {}, f"Failed: {why}", reason,
                        "Nothing to undo: what was read before the error mirrors Plex; the next sync reads it again.")
            raise SyncFailed(why) from None
        note = (f"{summary['tracks']:,} tracks read from Plex, {summary['removed']:,} no longer there, "
                f"{summary['albums']:,} albums, {summary['artists']:,} artists, {summary['streams']:,} audio formats read")
        run_id = own.log_run(data_dir, JOB, t0, True, summary, note, reason, UNDO)
        return {"ok": True, "run": run_id, "note": note, **summary}
    finally:
        _lock.release()


# --- the watcher ----------------------------------------------------------------------------------------------
def _on_change(settings: Settings, transport, why: str) -> bool:
    try:
        run(settings, f"Watcher: Plex changed ({why})", transport)
        return True
    except (SyncRefused, SyncFailed):
        return False


def start_watcher(settings: Settings, transport=None, first_delay: float = 20) -> bool:
    """Start jimbo-dj's watcher (vendored) when TRAQFREQ_WATCH=on. Returns whether it's on."""
    if not watcher.enabled():
        return False
    config.CURRENT = config_for(settings, transport)
    watcher.start(lambda why: _on_change(settings, transport, why), first_delay=first_delay)
    return True


def watch_state() -> dict:
    """The watcher's state (jimbo-dj's: started, checked_at, changed_at, scanning, error, enabled, interval)."""
    return watcher.state()
