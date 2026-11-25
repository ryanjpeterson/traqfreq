"""jimbo-dj's playlists.py, the names only: the emoji each kind of playlist starts with and ``base_name``, copied
unchanged at 1d8a7cb. Nothing that talks to Plex is copied (push, delete, rename, set_poster): traqfreq never writes."""
from __future__ import annotations

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/playlists.py (CLUSTER … PREFIXES, base_name)"

# --- src/jimbodj/playlists.py -----------------------------------------------------------------------------
# The name callers give → the emoji that starts the Plex title. Single code points, so no variation
# selectors to get lost on the way through Plex. "Cluster: " and "Explore: " are dropped from the title.
CLUSTER, MIX, LIKE, EXPLORE = "\U0001FAA9 ", "\U0001F3A7 ", "\U0001F501 ", "\U0001F9ED "  # 🪩 🎧 🔁 🧭
SETLIST = "\U0001F3A4 "  # 🎤
PREFIXES = (CLUSTER, MIX, LIKE, EXPLORE, SETLIST)


def base_name(title: str) -> str:
    """The name without its emoji: "🔁 More like AFI" → "More like AFI"."""
    for p in PREFIXES:
        if title.startswith(p):
            return title[len(p):]
    return title
