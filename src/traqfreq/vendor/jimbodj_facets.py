"""jimbo-dj's chart filters (facets.py ``members``): the tracks behind one bar of a Files, Time or Place chart,
counted with the same rule the chart uses. Copied unchanged at 1d8a7cb.

LIBRARY uses the file, time, place and label facets (``library.tracks`` refuses the rest). The branch builder
(vendor/rules.py, T24) uses them all: ``genres`` is vendor/genres.py (``Styles``), ``history`` vendor/history.py
(``listened_keys``), ``insights`` vendor/jimbodj_insights.py (with ``track_family``), ``schedule`` its stand-in.
``scope`` is in vendor/facets.py.
"""
from __future__ import annotations

import json
import sqlite3

from . import genres  # vendor/genres.py (style and family facets)
from . import jimbodj_insights as insights
from .jimbodj_insights import schedule

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/facets.py"

# --- src/jimbodj/facets.py -------------------------------------------------------------------------------
FILE = ("quality", "format", "bits", "rate", "bitrate", "channels")
TIME = ("length", "decade", "added", "hour", "weekday")
PLACE = ("country", "city", "formed", "artist_type")
OTHER = ("label", "family", "style", "artist", "listened")
KEYS = FILE + TIME + PLACE + OTHER


def members(con: sqlite3.Connection, facet: str, value: str) -> set[int]:
    live = "removed_at IS NULL"
    if facet in FILE:
        return {r["rating_key"] for r in con.execute(f"SELECT rating_key, {insights.FILE_COLUMNS} FROM tracks WHERE {live}")
                if insights.file_buckets(r).get(facet) == value}
    if facet in TIME:
        years, tz = insights._release_years(con), schedule.tz()
        return {r["rating_key"] for r in con.execute(f"SELECT rating_key, {insights.TIME_COLUMNS} FROM tracks WHERE {live}")
                if insights.time_buckets(r, years, tz).get(facet) == value}
    if facet in PLACE:
        field = "type" if facet == "artist_type" else facet
        artists = [ak for ak, d in insights.artist_places(con).items() if d.get(field) == value]
        return _by(con, "artist_key", artists)
    if facet == "label":
        return _by(con, "album_key", [a for a, label in insights.album_labels(con).items() if label == value])
    if facet == "listened":
        from . import history
        return history.listened_keys(con, value)
    if facet == "artist":
        return {r[0] for r in con.execute(f"SELECT rating_key FROM tracks WHERE {live} AND artist=?", (value,))}
    if facet in ("family", "style"):
        st = genres.get(con)
        if facet == "style":
            return {k for k, sc in st.scores.items() if sc.get(value, 0) >= genres.MATCH}
        return {k for k, sc in st.scores.items() if insights.track_family(st, sc) == value}
    raise ValueError(f"no filter {facet!r}")


def _by(con, col: str, values: list) -> set[int]:
    if not values:
        return set()
    return {r[0] for r in con.execute(
        f"SELECT rating_key FROM tracks WHERE removed_at IS NULL AND {col} IN (SELECT value FROM json_each(?))", (json.dumps(values),))}
