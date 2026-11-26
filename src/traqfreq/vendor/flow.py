"""Stand-in for jimbo-dj's flow.py, which rules.py imports at the top. ``rules.build`` (Picking, T25) calls
``order`` and ``describe``; T27 copies the real ones here (Camelot keys, tempo, loudness, energy). Until then the
picked tracks stay in pick order and have no transition, and every answer says so."""
from __future__ import annotations

STAND_IN = True


def order(tracks: list[dict]) -> list[dict]:
    """Stand-in: the tracks in the order ``pick`` took them (jimbo-dj orders them for flow)."""
    return list(tracks)


def describe(prev: dict | None, cur: dict) -> None:  # noqa: ARG001 - T27
    """Stand-in: no transition in words until T27."""
    return None
