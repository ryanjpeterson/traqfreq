"""jimbo-dj's prompt.py: a few words turned into a CLAP text vector by jimbodj-text (jimbo-dj's CLAP text server,
:4491, native on the mini). ``clean`` and ``Unavailable`` are copied unchanged at 1d8a7cb, and the messages are
jimbo-dj's. ``_embed``, ``vector`` and ``available`` are stand-ins with the same shape: jimbo-dj's use ``requests``
and its ``config.load().text_url``; traqfreq has neither, so they take the URL (TRAQFREQ_TEXT_URL) and an httpx
client. jimbodj-text only turns text into numbers (``POST /embed``): it reads and changes nothing.
"""
from __future__ import annotations

import functools
import re

import httpx
import numpy as np

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/prompt.py (Unavailable, clean)"


# --- src/jimbodj/prompt.py -------------------------------------------------------------------------------
class Unavailable(RuntimeError):
    """jimbodj-text isn't answering."""


def clean(text: str) -> str:
    """The prompt as it's embedded: one line, no more than 200 characters. "walking-in-new-york-city" (a
    path) reads as "walking in new york city"."""
    t = re.sub(r"\s+", " ", (text or "").replace("-", " ") if " " not in (text or "") else (text or "")).strip()
    return t[:200]


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
TIMEOUT = httpx.Timeout(30.0, connect=3.0)  # jimbo-dj's: 30 s to embed


def _client(transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(transport=transport, timeout=TIMEOUT, follow_redirects=False)


@functools.lru_cache(maxsize=256)
def _embed_cached(url: str, text: str) -> tuple[float, ...]:
    return _embed(url, text, None)


def _embed(url: str, text: str, transport: httpx.BaseTransport | None) -> tuple[float, ...]:
    try:
        with _client(transport) as c:
            r = c.post(f"{url}/embed", json={"texts": [text]})
    except httpx.HTTPError as e:
        raise Unavailable(f"the prompt service (jimbodj-text at {url}) isn't answering: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise Unavailable(f"the prompt service said {r.status_code}: {r.text[:200]}")
    return tuple(r.json()["vectors"][0])


def vector(url: str, text: str, transport: httpx.BaseTransport | None = None) -> np.ndarray:
    """The prompt's CLAP text vector, L2-normalised (cached per prompt, as jimbo-dj's; not with a test transport)."""
    raw = _embed_cached(url, clean(text)) if transport is None else _embed(url, clean(text), transport)
    v = np.asarray(raw, dtype=np.float32)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def available(url: str, transport: httpx.BaseTransport | None = None) -> bool:
    try:
        with httpx.Client(transport=transport, timeout=3.0) as c:
            return c.get(f"{url}/health").is_success
    except httpx.HTTPError:
        return False
