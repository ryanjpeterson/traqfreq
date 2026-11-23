"""The three media servers traqfreq maps one song across (T13, spec docs/specs/t13-servers.md).

Plex is read through jimbo-dj's database (its last sync), never directly. Jellyfin and Navidrome are read by
traqfreq itself from T17 and T18, GET only; here they are "set up" or "not set up" from the environment.
Secrets (Jellyfin's API key, Navidrome's password) are never returned: the answer says only whether each
setting is there.
"""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlsplit

from .settings import Settings

SERVERS = ("plex", "jellyfin", "navidrome")
NAMES = {"plex": "Plex", "jellyfin": "Jellyfin", "navidrome": "Navidrome"}

# Each server's settings: (environment name, Settings field, secret?). Plex's are jimbo-dj's.
SETTINGS = {
    "plex": (("TRAQFREQ_PLEX_ROOTS", "plex_roots", False),),
    "jellyfin": (("TRAQFREQ_JELLYFIN_URL", "jellyfin_url", False), ("TRAQFREQ_JELLYFIN_KEY", "jellyfin_key", True),
                 ("TRAQFREQ_JELLYFIN_USER", "jellyfin_user", False)),
    "navidrome": (("TRAQFREQ_NAVIDROME_URL", "navidrome_url", False), ("TRAQFREQ_NAVIDROME_USER", "navidrome_user", False),
                  ("TRAQFREQ_NAVIDROME_PASSWORD", "navidrome_password", True)),
}
REQUIRED = {"jellyfin": ("jellyfin_url", "jellyfin_key"), "navidrome": ("navidrome_url", "navidrome_user", "navidrome_password")}
READER = {"jellyfin": "T17", "navidrome": "T18"}
READ_NOW = ("jellyfin",)  # servers whose reader has landed (T17); Navidrome's is T18


def _safe_url(url: str | None) -> str | None:
    """The URL without any user:password part or query (shown on SETUP)."""
    if not url:
        return None
    u = urlsplit(url)
    host = u.hostname or ""
    if u.port:
        host = f"{host}:{u.port}"
    return f"{u.scheme}://{host}{u.path}".rstrip("/") if u.scheme else None


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _plex(conn: sqlite3.Connection | None, settings: Settings) -> dict:
    out = {"server": "plex", "name": NAMES["plex"], "set_up": conn is not None, "read": conn is not None,
           "source": "jimbo-dj's database, read-only (its last Plex sync)",
           "settings": [{"env": "TRAQFREQ_PLEX_ROOTS", "set": bool(settings.plex_roots), "secret": False,
                         "value": ",".join(settings.plex_roots) or None}]}
    if conn is None:
        out["note"] = "jimbo-dj's database is not set (TRAQFREQ_LEGACY_DB)."
        return out
    try:
        server = json.loads(_meta(conn, "server") or "{}") or {}
    except ValueError:
        server = {}
    sync = _meta(conn, "last_sync")
    try:
        tracks = conn.execute("SELECT COUNT(*) FROM tracks WHERE removed_at IS NULL").fetchone()[0]
    except sqlite3.OperationalError:
        tracks = None
    out.update(server_name=server.get("name"), version=server.get("version"), section=server.get("section"),
               last_sync=int(float(sync)) if sync else None, tracks=tracks)
    return out


def _other(server: str, settings: Settings) -> dict:
    rows = []
    for env, field, secret in SETTINGS[server]:
        v = getattr(settings, field)
        rows.append({"env": env, "set": bool(v), "secret": secret,
                     "value": None if secret or not v else (_safe_url(v) if field.endswith("_url") else v)})
    set_up = all(getattr(settings, f) for f in REQUIRED[server])
    missing = [env for env, field, _ in SETTINGS[server] if field in REQUIRED[server] and not getattr(settings, field)]
    return {
        "server": server, "name": NAMES[server], "set_up": set_up, "read": False,
        "url": _safe_url(getattr(settings, f"{server}_url")),
        "settings": rows, "missing": missing,
        "note": (("Set up; traqfreq reads it when you refresh it (GET requests only)." if server in READ_NOW
                  else f"Set up; traqfreq reads it from {READER[server]} on (GET only).") if set_up
                 else f"Not set up: {', '.join(missing)} missing. Every page works without it."),
    }


def status(conn: sqlite3.Connection | None, settings: Settings) -> dict:
    """The three servers: Plex through jimbo-dj's database, Jellyfin and Navidrome from the environment."""
    return {"servers": [_plex(conn, settings), _other("jellyfin", settings), _other("navidrome", settings)],
            "read_only": "traqfreq never writes to any server: GET requests only, no playlists, plays or tags."}
