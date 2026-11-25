"""jimbo-dj's browse.py (Explore), the part the branch builder's sound conditions use: ``SOUND`` and ``_where``,
copied unchanged at 1d8a7cb. ``rules.leaf_keys`` imports it as ``browse``. Nothing here writes."""
from __future__ import annotations

import json
import re

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/browse.py (SOUND, _where)"

# --- src/jimbodj/browse.py -------------------------------------------------------------------------------
SOUND = ("bpm", "key", "mood", "genre")


def _where(f: dict, version: int, keys: set[int] | None = None) -> tuple[str, list]:
    sql, args = ["t.removed_at IS NULL"], []
    if any(f.get(k) for k in SOUND):
        sql += ["a.status='ok'", "a.version>=?"]
        args.append(version)
    if keys is not None:
        sql.append("t.rating_key IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(keys)))
    if bpm := f.get("bpm"):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)?-(\d+(?:\.\d+)?)?", bpm)
        if not m:
            raise ValueError("bpm is lo-hi, like 120-130")
        if m[1]:
            sql.append("f.bpm >= ?")
            args.append(float(m[1]))
        if m[2]:
            sql.append("f.bpm < ?")
            args.append(float(m[2]))
    if key := f.get("key"):
        camelots = [k.strip().upper() for k in key.split(",") if k.strip()]
        sql.append(f"f.camelot IN ({','.join('?' * len(camelots))})")
        args += camelots
    if mood := f.get("mood"):
        sql.append("EXISTS (SELECT 1 FROM json_each(f.moods) j WHERE j.key=?)")
        args.append(mood)
    return " AND ".join(sql), args
