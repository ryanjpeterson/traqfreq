"""Stand-in (not vendored) for jimbo-dj's ``tags.get``, which the vendored ``history._genre_tags`` imports inside its
body (``from . import tags``). jimbo-dj's is a background cache of its tag Library; traqfreq's is
``traqfreq.tags.library``: jimbo-dj's vendored Library (vendor/jimbodj_tags.py), built once per data stamp."""
from __future__ import annotations


def get(con):
    from .. import tags as traqfreq_tags
    return traqfreq_tags.library(con)
