"""Ordering a playlist so one track flows into the next: compatible keys on the Camelot wheel,
small tempo changes (half and double time count), no big jumps in loudness or energy."""
from __future__ import annotations

import re

_CAMELOT = re.compile(r"^(\d{1,2})([AB])$")


def camelot_steps(a: str | None, b: str | None) -> int | None:
    """Moves around the wheel from a to b: 0 same key; 1 a neighbour (±1, or relative major/minor)."""
    ma, mb = _CAMELOT.match(a or ""), _CAMELOT.match(b or "")
    if not ma or not mb:
        return None
    na, la, nb, lb = int(ma[1]), ma[2], int(mb[1]), mb[2]
    around = min((na - nb) % 12, (nb - na) % 12)
    return around + (0 if la == lb else 1)


def bpm_gap(a: float | None, b: float | None) -> float | None:
    """Relative tempo difference, treating half and double time as the same tempo."""
    if not a or not b:
        return None
    return min(abs(a * k - b) / b for k in (0.5, 1.0, 2.0))


def transition_cost(x: dict, y: dict) -> float:
    cost = 0.0
    steps = camelot_steps(x.get("camelot"), y.get("camelot"))
    if steps is not None:
        cost += {0: 0.0, 1: 0.15, 2: 0.45}.get(steps, 0.8)
    else:
        cost += 0.4
    gap = bpm_gap(x.get("bpm"), y.get("bpm"))
    if gap is not None:
        # Trust the tempo less when the beat tracker wasn't sure (rubato, ambient)
        conf = min(x.get("bpm_confidence") or 0, y.get("bpm_confidence") or 0)
        weight = 0.3 + 0.7 * min(conf / 3.0, 1.0)
        cost += weight * min(gap, 0.25) * 4  # up to +1 for a 25 % tempo jump
    if x.get("loudness_lufs") is not None and y.get("loudness_lufs") is not None:
        cost += min(abs(x["loudness_lufs"] - y["loudness_lufs"]) / 12, 0.5)
    if x.get("danceability") is not None and y.get("danceability") is not None:
        cost += 0.4 * abs(x["danceability"] - y["danceability"])
    return cost


def order(tracks: list[dict], start: dict | None = None, score_weight: float = 0.6) -> list[dict]:
    """Greedy walk: from the start (the seed, or the best track), repeatedly take the remaining track
    with the cheapest transition, nudged toward higher-scoring tracks so the best ones come early."""
    if len(tracks) <= 2:
        return list(tracks)
    left = list(tracks)
    cur = start
    if cur is None:
        cur = max(left, key=lambda t: t.get("score", 0))
        left.remove(cur)
        out = [cur]
    else:
        out = []
    while left:
        nxt = min(left, key=lambda t: transition_cost(cur, t) - score_weight * t.get("score", 0))
        left.remove(nxt)
        out.append(nxt)
        cur = nxt
    return out


def describe(prev: dict | None, cur: dict) -> dict:
    """How a track follows the one before it, for the UI."""
    if prev is None:
        return {}
    return {"key_steps": camelot_steps(prev.get("camelot"), cur.get("camelot")),
            "bpm_gap": round(g, 3) if (g := bpm_gap(prev.get("bpm"), cur.get("bpm"))) is not None else None}


# --- traqfreq ---------------------------------------------------------------------------------------------
# Every line above is jimbo-dj's flow.py at 1d8a7cb, unchanged (T27 replaces T25's stand-in). It reads only the
# track dicts it is handed: make.details gives them from the vectors index's meta (camelot, bpm, bpm_confidence,
# loudness_lufs, danceability; similar._public). rules.build calls order and describe. Pure: no database.
VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/flow.py (whole file)"
