"""jimbo-dj's Fix in Plex (tagwrite.py): only ``stamp`` copied unchanged at 1d8a7cb.

Fix in Plex writes albums' genre tags to Plex and logs each batch in ``tag_edits``; it stays in jimbo-dj until
P6. ``stamp`` (the newest applied or undone batch) is part of the tags' data stamp (vendor/jimbodj_tags.py
``stamp``), so traqfreq sees when a fix changed the tags. Nothing else is copied: traqfreq never writes to Plex.
"""
from __future__ import annotations

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/tagwrite.py (stamp)"

# --- src/jimbodj/tagwrite.py -----------------------------------------------------------------------------
def stamp(con):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='tag_edits'").fetchone():
        return None
    a, u = con.execute("SELECT MAX(applied_at), MAX(undone_at) FROM tag_edits").fetchone()
    return max(a or 0, u or 0) or None
