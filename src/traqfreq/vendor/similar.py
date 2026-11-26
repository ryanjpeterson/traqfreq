"""jimbo-dj's similar.py, the two helpers rules.build uses: ``_norm_title`` (a song goes in once, ``pick``) and
``_public`` (a track as make.details hands it on), copied unchanged at 1d8a7cb. Radio (more_like) and the vectors
search are not copied: P5 doesn't make Radio. Nothing here reads or writes the database."""
from __future__ import annotations

import json
import re

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/similar.py (_norm_title, _public)"


# --- src/jimbodj/similar.py -------------------------------------------------------------------------------
def _norm_title(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)  # (Remastered 2011), [Live]
    s = re.sub(r"\s+-\s+(remaster|live|mono|stereo|demo|edit|version).*$", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _public(m: dict) -> dict:
    d = {"key": m.get("key"), "scale": m.get("scale")}
    d |= {k: m[k] for k in ("rating_key", "artist", "artist_key", "track_artist", "title", "album", "album_key",
                           "year", "duration_ms", "bpm", "bpm_confidence", "camelot", "loudness_lufs",
                           "danceability", "aggressive", "relaxed", "happy", "sad", "voice")}
    d["moods"] = list(json.loads(m["moods"] or "{}"))[:3] if isinstance(m["moods"], str) else list(m["moods"] or [])[:3]
    d["genres"] = [g.split("---")[-1] for g in (json.loads(m["genres"] or "{}") if isinstance(m["genres"], str) else m["genres"] or {})][:2]
    return d
