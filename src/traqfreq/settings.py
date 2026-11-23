"""Settings read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Repo checkout default: <repo>/web/dist (src layout: src/traqfreq/settings.py -> parents[2]).
DEFAULT_WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "dist"

# The modules in nav order (L1). LIBRARY and SETUP are core and always on.
MODULES = ("L", "H", "T", "D", "M", "F", "S")
CORE = frozenset({"L", "S"})
NAMES = {"L": "LIBRARY", "H": "HISTORY", "T": "TAGS", "D": "DISCOVER", "M": "MIXES", "F": "FETCH", "S": "SETUP"}


def parse_modules(raw: str | None) -> frozenset[str]:
    """TRAQFREQ_MODULES: comma-separated letters or names (``H,TAGS``). Core modules are always on."""
    on = set(CORE)
    by_name = {v: k for k, v in NAMES.items()}
    for part in (raw or "").split(","):
        p = part.strip().upper()
        if p in NAMES:
            on.add(p)
        elif p in by_name:
            on.add(by_name[p])
    return frozenset(on)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    legacy_db: Path | None
    port: int
    host: str
    web_dir: Path = DEFAULT_WEB_DIR
    modules: frozenset[str] = CORE
    tz: str | None = None  # TZ: jimbo-dj's listening time zone when its meta history_tz isn't set
    # P3 SERVERS (docs/specs/t13-servers.md). Empty = not set up. Secrets are never shown or logged.
    plex_roots: tuple[str, ...] = ()  # Plex's music folders, only if jimbo-dj stored none
    jellyfin_url: str | None = None
    jellyfin_key: str | None = None
    jellyfin_user: str | None = None
    navidrome_url: str | None = None
    navidrome_user: str | None = None
    navidrome_password: str | None = None
    navidrome_roots: tuple[str, ...] = ()  # Navidrome's music folders as its real paths show them (T18), if needed

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        legacy = env.get("TRAQFREQ_LEGACY_DB") or None
        return cls(
            data_dir=Path(env.get("TRAQFREQ_DATA_DIR", "./data")),
            legacy_db=Path(legacy) if legacy else None,
            port=int(env.get("TRAQFREQ_PORT", "4492")),
            host=env.get("TRAQFREQ_HOST", "0.0.0.0"),
            web_dir=Path(env.get("TRAQFREQ_WEB_DIR", str(DEFAULT_WEB_DIR))),
            modules=parse_modules(env.get("TRAQFREQ_MODULES")),
            tz=env.get("TZ") or None,
            plex_roots=tuple(r.strip() for r in (env.get("TRAQFREQ_PLEX_ROOTS") or "").split(",") if r.strip()),
            jellyfin_url=env.get("TRAQFREQ_JELLYFIN_URL") or None,
            jellyfin_key=env.get("TRAQFREQ_JELLYFIN_KEY") or None,
            jellyfin_user=env.get("TRAQFREQ_JELLYFIN_USER") or None,
            navidrome_url=env.get("TRAQFREQ_NAVIDROME_URL") or None,
            navidrome_user=env.get("TRAQFREQ_NAVIDROME_USER") or None,
            navidrome_password=env.get("TRAQFREQ_NAVIDROME_PASSWORD") or None,
            navidrome_roots=tuple(r.strip() for r in (env.get("TRAQFREQ_NAVIDROME_ROOTS") or "").split(",") if r.strip()),
        )
