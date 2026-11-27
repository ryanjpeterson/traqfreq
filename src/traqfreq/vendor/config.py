"""A stand-in for jimbo-dj's config.py: the settings its Plex sync and watcher read (``Settings`` with ``plex_url``,
``plex_token``, ``music_section``, ``path_map``, ``db_path``; ``load``). ``parse_path_map`` is copied unchanged at
1d8a7cb. traqfreq's settings come from its own environment (TRAQFREQ_PLEX_URL, TRAQFREQ_PLEX_TOKEN,
TRAQFREQ_PLEX_MUSIC_SECTION, TRAQFREQ_PLEX_PATH_MAP), and ``db_path`` is traqfreq's library.sqlite, never jimbo-dj's file.
The token is never shown or logged: ``Settings.__repr__`` leaves it out."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/config.py (parse_path_map)"


# --- src/jimbodj/config.py -------------------------------------------------------------------------------
def parse_path_map(raw: str) -> tuple[tuple[str, str], ...]:
    """"plex1=local1,plex2=local2". A folder without "=local" is read where Plex has it."""
    pairs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        plex_dir, _, local_dir = item.partition("=")
        plex_dir = plex_dir.strip().rstrip("/")
        pairs.append((plex_dir, (local_dir.strip() or plex_dir).rstrip("/")))
    return tuple(sorted(pairs, key=lambda p: len(p[0]), reverse=True))


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    plex_url: str
    plex_token: str = field(repr=False)
    music_section: str
    path_map: tuple[tuple[str, str], ...]
    data_dir: Path
    transport: object = field(default=None, repr=False, compare=False)  # tests: httpx.MockTransport

    @property
    def db_path(self) -> Path:
        """traqfreq's library.sqlite (own.path), where every write of the sync and the watcher goes."""
        return self.data_dir / "library.sqlite"


CURRENT: Settings | None = None  # set by traqfreq.plexsync for the watcher (and tests); else read from the env


def from_traqfreq(s) -> Settings:
    """jimbo-dj's settings from traqfreq's (traqfreq.settings.Settings)."""
    return Settings(plex_url=(s.plex_url or "http://localhost:32400").rstrip("/"), plex_token=s.plex_token or "",
                    music_section=s.plex_section or "", path_map=parse_path_map(s.plex_path_map or ""),
                    data_dir=Path(s.data_dir))


def load() -> Settings:
    if CURRENT is not None:
        return CURRENT
    from ..settings import Settings as TraqfreqSettings

    return from_traqfreq(TraqfreqSettings.from_env())
