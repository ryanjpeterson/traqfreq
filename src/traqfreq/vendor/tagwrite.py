"""jimbo-dj's Fix in Plex (tagwrite.py): its pure parts copied unchanged at 1d8a7cb.

Fix in Plex writes albums' genre tags to Plex and logs each batch in ``tag_edits``; it stays in jimbo-dj until
P6. Copied: ``FIXABLE`` and ``DEFAULT`` (the kinds of fix and the one the page starts with), ``stamp`` (the newest
applied or undone batch, part of the tags' data stamp in vendor/jimbodj_tags.py ``stamp``), and, since T22, the
preview: ``_dedupe``, ``proposal`` (an audited album row → its Plex tags after the fixes of some kinds, and the
changes) and ``plan`` (every album those kinds would change, and how many albums each kind touches). They only
read the audited rows. Not copied: ``ensure``, ``apply``, ``undo``, the file writes and anything else that writes:
traqfreq never writes to Plex, to jimbo-dj's database or to audio files.

One line differs from jimbo-dj: the import. jimbo-dj's ``from .tags import KINDS, norm`` is its tags.py, which is
vendor/jimbodj_tags.py here (vendor/tags.py is only the stand-in ``get``).
"""
from __future__ import annotations

from .jimbodj_tags import KINDS, norm

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/tagwrite.py (FIXABLE, DEFAULT, stamp, _dedupe, proposal, plan)"

# --- src/jimbodj/tagwrite.py -----------------------------------------------------------------------------
# What can be fixed, in the order the page offers them. "niche" and "untagged" need a person to decide.
FIXABLE = ["broad", "spelling", "case", "split", "junk"]
DEFAULT = ["broad"]


def stamp(con):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='tag_edits'").fetchone():
        return None
    a, u = con.execute("SELECT MAX(applied_at), MAX(undone_at) FROM tag_edits").fetchone()
    return max(a or 0, u or 0) or None


def _dedupe(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for t in tags:
        if t and norm(t) not in seen:
            seen.add(norm(t))
            out.append(t)
    return out


def proposal(row: dict, kinds: list[str]) -> tuple[list[str], list[dict]]:
    """An audited album row (tags.Library.albums) → (its Plex tags after the fixes of these kinds, the changes)."""
    before = [t["name"] for t in row["tags"]]
    after = list(before)
    changes = []
    for i in row["issues"]:
        if i["kind"] not in kinds:
            continue
        if i["op"] == "rename" and i["tag"] in after:
            at = after.index(i["tag"])
            after[at:at + 1] = i["to"]
            changes.append({"kind": i["kind"], "op": "rename", "tag": i["tag"], "to": i["to"]})
        elif i["op"] == "remove" and i["tag"] in after:
            after.remove(i["tag"])
            changes.append({"kind": i["kind"], "op": "remove", "tag": i["tag"]})
        elif i["op"] == "add" and i["tag"]:
            after.append(i["tag"])
            changes.append({"kind": i["kind"], "op": "add", "tag": i["tag"], "because": i.get("because") or []})
    after = _dedupe(after)
    return (after, changes) if after != before else (before, [])


def plan(lib, kinds: list[str] | None = None, album_keys: list[int] | None = None) -> dict:
    """The preview: every album whose Plex tags these kinds of fix would change, worst first, and how many
    albums each kind of fix touches across the library."""
    kinds = [k for k in (kinds or DEFAULT) if k in FIXABLE]
    want = set(album_keys) if album_keys else None
    items, counts = [], {k: 0 for k in FIXABLE}
    for row in lib.albums.values():
        for k in FIXABLE:
            if any(i["kind"] == k for i in row["issues"]) and proposal(row, [k])[1]:
                counts[k] += 1
        if want is not None and row["album_key"] not in want:
            continue
        after, changes = proposal(row, kinds)
        if changes:
            items.append({"album_key": row["album_key"], "title": row["title"], "artist": row["artist"], "year": row["year"],
                          "before": [t["name"] for t in row["tags"]], "after": after, "changes": changes})
    items.sort(key=lambda x: (x["artist"] or "", x["year"] or 0, x["title"] or ""))
    return {"kinds": kinds, "fixable": [{"kind": k, "label": KINDS[k], "albums": counts[k]} for k in FIXABLE],
            "albums": len(items), "items": items}
