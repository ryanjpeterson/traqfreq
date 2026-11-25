"""jimbo-dj's make.py, the part that says which saved playlists have a tree: the spec types, ``kind_of``,
``silo``, ``clean`` and ``spec_of``, copied unchanged at 1d8a7cb. Building (candidates, build) is not copied: P5
builds trees through vendor/rules.py and shows the other kinds as jimbo-dj stored them."""
from __future__ import annotations

import re

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/make.py (HISTORY … MONTHS, Unmakeable, kind_of, silo, clean, spec_of)"

# --- src/jimbodj/make.py ---------------------------------------------------------------------------------
HISTORY = ("alltime", "period", "on", "week", "phase", "listening")
LIBRARY = ("rules", "filter", "releases")
RADIO = ("radio",)
TYPES = HISTORY + LIBRARY + RADIO
DEFAULT_N, MAX_N = 50, 200
_PERIOD = re.compile(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


class Unmakeable(ValueError):
    """The spec is fine but nothing in the library fits it (now)."""


def kind_of(spec: dict) -> str:
    t = spec["type"]
    return "history" if t in HISTORY else "explore" if t in LIBRARY else "like"


def silo(spec: dict) -> str:
    t = spec["type"]
    return "history" if t in HISTORY else "library" if t in LIBRARY else "radio"


def clean(spec: dict | None) -> dict:
    """The spec, checked and normalised. ValueError says what's wrong."""
    if not isinstance(spec, dict) or spec.get("type") not in TYPES:
        raise ValueError(f"a source is one of: {', '.join(TYPES)}")
    t = spec["type"]
    if t == "period":
        p = str(spec.get("period") or "").strip()
        m = _PERIOD.match(p)
        if not m or (m[2] and not 1 <= int(m[2]) <= 12):
            raise ValueError("a period is a year (2018), a month (2018-06) or a day (2018-06-21)")
        parts = [m[1]] + [f"{int(x):02d}" for x in m.groups()[1:] if x]
        return {"type": t, "period": "-".join(parts)}
    if t == "on":
        month, day = int(spec.get("month") or 0), int(spec.get("day") or 0)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            raise ValueError("this day is a month (1–12) and a day")
        return {"type": t, "month": month, "day": day}
    if t in ("week", "alltime"):
        return {"type": t}
    if t == "phase":
        if not spec.get("id"):
            raise ValueError("a phase needs its id")
        return {"type": t, "id": str(spec["id"])}
    if t == "listening":
        if spec.get("entity") not in ("artist", "album") or not spec.get("ref"):
            raise ValueError("listening is an artist or an album, by its slug")
        return {"type": t, "entity": spec["entity"], "ref": str(spec["ref"])}
    if t == "filter":  # older saves and pages: one branch
        from . import rules
        f = {str(k): str(v) for k, v in (spec.get("filters") or {}).items() if v not in (None, "")}
        if not f:  # the whole library, most played
            return {"type": t, "filters": {}}
        return {"type": "rules", "rules": rules.from_filters(f, int(spec.get("n") or rules.DEFAULT_N))}
    if t == "rules":
        from . import rules
        return {"type": t, "rules": rules.clean(spec.get("rules"))}
    if t == "releases":
        return {"type": t}
    seed = spec.get("seed") or {}
    if seed.get("type") not in ("track", "album", "artist", "filter", "prompt"):
        raise ValueError("a radio needs its seed")
    return {"type": t, "seed": seed}


def spec_of(row: dict) -> dict | None:
    """The spec that makes a saved playlist, from what it was saved with: `source.make`, or what older
    saves kept (a Radio seed, Explore's filters, Wrapped's period, This day's date). None: not a page's."""
    src = row.get("source") or {}
    try:
        if src.get("make"):
            return clean(src["make"])
        if row["kind"] == "like" and src.get("seed"):
            return clean({"type": "radio", "seed": src["seed"]})
        if row["kind"] == "explore" and src.get("filters"):
            return clean({"type": "filter", "filters": src["filters"]})
        if row["kind"] == "blend" and src.get("parts"):  # a genre blend: one branch per style
            from . import rules
            return {"type": "rules", "rules": rules.from_blend(src["parts"], int(src.get("n") or row.get("tracks") or 60),
                                                                int(src.get("per_artist") or 3), int(src.get("shuffle") or 0))}
        if row["kind"] == "explore" and src.get("wrapped"):
            return clean({"type": "period", "period": src["wrapped"]})
    except ValueError:
        return None
    return None
