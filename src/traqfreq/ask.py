"""The Ask box (P5, T28): a few words to a line for the Junction. Read-only; nothing is saved.

Three ways in, each giving a line (jimbo-dj's branch: a group of conditions), each line with its count of live tracks
counted as jimbo-dj counts it (playlists.lines) and its URL form, so the Junction opens it:

- **Typed** (always on): ``facet:value`` parts, comma-separated as in jimbo-dj's URL form (``decade:1990s``,
  ``!mood:sad``). Each is checked with jimbo-dj's ``rules.clean``.
- **By sound** (when jimbodj-text answers, TRAQFREQ_TEXT_URL): the other words go to jimbo-dj's CLAP text server
  (vendor/prompt.py), and the vector is compared with every analysed track's CLAP audio embedding, as jimbo-dj's
  prompt Radio does (similar.more_like's prompt branch, below). The nearest tracks are the rows behind it. Their
  styles (``style`` as jimbo-dj's chart counts it, genres.MATCH) become the line: up to three, chosen one at a time,
  each time the one whose nearest tracks not covered yet weigh most by score, each on at least a tenth of them.
- **By Ollama** (only when TRAQFREQ_OLLAMA_URL is set; off by default): the words are read into styles, moods and
  decades with a local model (``/api/chat``, a JSON schema, low temperature), as jimbo-dj's Ollama spec plans
  (docs/specs/ollama.md at 1d8a7cb, not built there). The model only picks from values the library has: anything
  else is dropped and named. It never decides on its own: the line is shown, counted and opened like the others.

jimbodj-text's ``/embed`` and Ollama's ``/api/chat`` are POSTs that turn words into numbers or values; they read and
change nothing. Nothing here writes to jimbo-dj, Plex, Jellyfin, Navidrome or the files.
"""
from __future__ import annotations

import json
import re
import sqlite3

import httpx
import numpy as np

from . import playlists
from .vendor import genres, prompt, rules, vectors

NEAR = 100          # the nearest tracks whose styles make the line
MAX_STYLES = 3
MIN_SHARE = 0.10    # a style must cover at least this share of the nearest tracks
OLLAMA_TIMEOUT = httpx.Timeout(20.0, connect=3.0)
OLLAMA_STYLES = 400  # the most-used styles offered to the model
RULES = {
    "typed": "facet:value parts, comma-separated as in jimbo-dj's URL form (decade:1990s, !mood:sad), checked with "
             "rules.clean",
    "near": "the words' CLAP text vector (jimbodj-text) against every analysed track's CLAP audio embedding, centred "
            "on the library mean; the closest first (jimbo-dj's prompt Radio, similar.more_like)",
    "styles": f"from the {NEAR} nearest tracks: up to {MAX_STYLES} styles, one at a time, each time the one whose "
              "nearest tracks not covered yet weigh most by their scores, each on at least "
              f"{int(MIN_SHARE * 100)} % of them (style as jimbo-dj's chart counts it)",
    "ollama": "a local model (Ollama) reads the words into styles, moods and decades; only values the library has "
              "are kept, the rest are named as dropped",
    "count": "the live tracks the line matches, counted with jimbo-dj's rules (rules.leaf_keys, rules.evaluate)",
}
_TOKEN = re.compile(r"^(!?)\s*([a-z_]+)\s*:\s*(.+)$")


def split(text: str) -> tuple[list[dict], list[dict], str]:
    """The typed conditions (``all`` and ``not``) and the words left for the sound."""
    alls, nots, words = [], [], []
    for part in (text or "").split(","):
        m = _TOKEN.match(part.strip())
        if m and m[2] in rules.FIELDS:
            (nots if m[1] else alls).append({"f": m[2], "v": m[3].strip()})
        elif part.strip():
            words.append(part.strip())
    return alls, nots, prompt.clean(" ".join(words))


def _group(alls: list[dict], nots: list[dict] | None = None) -> dict:
    g = {"all": alls} if alls else {}
    if nots:
        g["not"] = nots
    return g


def _tree(match: dict, label: str) -> dict:
    return rules.clean({"n": rules.DEFAULT_N, "per_artist": 3, "shuffle": 0,
                        "branches": [{"id": "a", "share": rules.DEFAULT_N, "label": label[:60], "match": match}]})


def _line(conn: sqlite3.Connection, source: str, match: dict, label: str, default_tz: str | None, **extra) -> dict:
    """A suggested line as the Junction shows it: its conditions with their counts and its URL form."""
    tree = _tree(match, label)
    got = playlists.lines(conn, tree, default_tz)
    line = got["lines"][0]
    return {"source": source, "label": line["label"], "words": line["words"], "count": line["count"],
            "match": line["match"], "query": got["query"], "rule": RULES[source if source != "sound" else "styles"]} | extra


# --- by sound: jimbodj-text and the CLAP vectors ------------------------------------------------------------

def scores(index: vectors.Clap, vec: np.ndarray) -> np.ndarray:
    """jimbo-dj's prompt scores (similar.more_like, copied unchanged at 1d8a7cb): the CLAP text vector against
    every track's CLAP audio. The scores are smaller than audio-to-audio ones, so they're stretched to 0–1."""
    raw = index.clap @ vec
    lo, hi = float(np.percentile(raw, 5)), float(raw.max())
    return np.clip((raw - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)


def nearest(conn: sqlite3.Connection, text: str, url: str, transport=None, k: int = NEAR) -> list[tuple[int, float]]:
    """The k analysed tracks closest to the words, closest first, each with its score. Raises prompt.Unavailable
    when jimbodj-text doesn't answer, LookupError when nothing has been analysed."""
    index = vectors.clap(conn)
    if not len(index):
        raise LookupError("no track has CLAP vectors yet")
    s = scores(index, prompt.vector(url, text, transport))
    top = np.argsort(-s, kind="stable")[:k]
    return [(int(index.keys[i]), round(float(s[i]), 4)) for i in top]


def pick_styles(conn: sqlite3.Connection, near: list[tuple[int, float]]) -> list[dict]:
    """Up to MAX_STYLES styles covering the nearest tracks, one at a time: each time the style whose nearest tracks
    not covered yet weigh most (each by its score), then the more used style, then by name. Each must be on at
    least MIN_SHARE of the nearest tracks. Each comes with how many of them it is on."""
    st = genres.get(conn)
    weight = dict(near)
    by: dict[str, set[int]] = {}
    for k, _ in near:
        for name, v in st.scores.get(k, {}).items():
            if v >= genres.MATCH:
                by.setdefault(name, set()).add(k)
    need = max(2, int(np.ceil(MIN_SHARE * len(near))))
    left, out = set(weight), []
    while len(out) < MAX_STYLES:
        ranked = sorted((s for s in by if len(by[s]) >= need and by[s] & left),
                        key=lambda s: (-round(sum(weight[k] for k in by[s] & left), 6), -st.count[s], s))
        if not ranked:
            break
        best = ranked[0]
        out.append({"style": best, "near": len(by[best]), "new": len(by[best] & left)})
        left -= by.pop(best)
    return out


def by_sound(conn, words: str, typed: dict, url: str | None, transport, default_tz) -> dict:
    if not words:
        return {"state": "no_words"}
    if not url:
        return {"state": "off"}
    try:
        near = nearest(conn, words, url, transport)
    except prompt.Unavailable as e:
        return {"state": "unavailable", "error": str(e)}
    except LookupError as e:
        return {"state": "no_vectors", "error": str(e)}
    styles = pick_styles(conn, near)
    out = {"state": "ok", "near": len(near), "styles": styles, "rule": RULES["near"]}
    if styles:
        leaves = [{"f": "style", "v": s["style"]} for s in styles]
        sound = leaves[0] if len(leaves) == 1 else {"any": leaves}
        match = _group([sound] + typed.get("all", []), typed.get("not"))
        out["line"] = _line(conn, "sound", match, words, default_tz)
    return out


def near_rows(conn: sqlite3.Connection, text: str, url: str | None, transport=None, limit: int = 50,
              offset: int = 0) -> dict:
    """The rows behind the sound line: the nearest tracks, closest first, each with its score."""
    _, _, words = split(text)
    if not url or not words:
        raise ValueError("nothing to compare: no words, or jimbodj-text isn't set up")
    near = nearest(conn, words, url, transport)
    keys = [k for k, _ in near]
    score = dict(near)
    total, page = playlists._rows(conn, keys, max(1, min(limit, 200)), max(0, offset), order=keys)
    return {"text": words, "count": total, "rows": [r | {"score": score[r["rating_key"]]} for r in page],
            "limit": limit, "offset": offset, "rule": RULES["near"]}


# --- by Ollama (optional) -----------------------------------------------------------------------------------

def known(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """The values the model may pick from: the most-used styles, every mood the analyzer gave, every decade."""
    st = genres.get(conn)
    moods = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT j.key FROM features f, json_each(f.moods) j WHERE f.moods IS NOT NULL")})
    decades = sorted({f"{y // 10 * 10}s" for (y,) in conn.execute(
        "SELECT DISTINCT year FROM tracks WHERE removed_at IS NULL AND year > 0")})
    return {"style": [s for s, _ in st.count.most_common(OLLAMA_STYLES)], "mood": moods, "decade": decades}


SCHEMA = {"type": "object", "properties": {f: {"type": "array", "items": {"type": "string"}}
                                           for f in ("style", "mood", "decade")},
          "required": ["style", "mood", "decade"]}


def by_ollama(conn, text: str, typed: dict, url: str | None, model: str, transport, default_tz) -> dict:
    if not url:
        return {"state": "off"}
    words = prompt.clean(text)
    if not words:
        return {"state": "no_words"}
    have = known(conn)
    system = ("You turn a few words about music into filters. Pick only from these lists; leave a list empty when "
              "nothing fits. Answer with JSON.\n" + "\n".join(f"{f}: {', '.join(v)}" for f, v in have.items()))
    body = {"model": model, "stream": False, "format": SCHEMA, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": words}]}
    try:
        with httpx.Client(transport=transport, timeout=OLLAMA_TIMEOUT, follow_redirects=False) as c:
            r = c.post(f"{url.rstrip('/')}/api/chat", json=body)
        r.raise_for_status()
        got = json.loads(r.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        return {"state": "unavailable", "error": f"Ollama at {url} didn't answer: {e.__class__.__name__}"}
    kept, dropped, groups = {}, [], []
    for f, values in have.items():
        lower = {v.lower(): v for v in values}
        picks = []
        for v in got.get(f) or []:
            hit = lower.get(str(v).strip().lower())
            if hit is None:
                dropped.append({"f": f, "v": str(v)})
            elif hit not in picks:
                picks.append(hit)
        kept[f] = picks
        leaves = [{"f": f, "v": v} for v in picks[:4]]
        if leaves:
            groups.append(leaves[0] if len(leaves) == 1 else {"any": leaves})
    out = {"state": "ok", "model": model, "kept": kept, "dropped": dropped, "rule": RULES["ollama"]}
    if groups:
        out["line"] = _line(conn, "ollama", _group(groups + typed.get("all", []), typed.get("not")), words, default_tz)
    return out


# --- the Ask box ------------------------------------------------------------------------------------------

def ask(conn: sqlite3.Connection, text: str, text_url: str | None = None, ollama_url: str | None = None,
        ollama_model: str = "qwen2.5:7b", transport=None, default_tz: str | None = None) -> dict:
    """Words to lines: typed, by sound, by Ollama. Every line has its count and URL form; nothing is saved.
    Raises ValueError when a typed condition can't be read."""
    alls, nots, words = split(text)
    typed = {"all": alls, "not": nots}
    lines = []
    if alls or nots:
        lines.append(_line(conn, "typed", _group(alls, nots), "", default_tz))
    sound = by_sound(conn, words, typed, text_url, transport, default_tz)
    llm = by_ollama(conn, words, typed, ollama_url, ollama_model, transport, default_tz)
    lines += [x["line"] for x in (sound, llm) if x.get("line")]
    return {"text": text, "words": words, "typed": typed, "sound": sound, "ollama": llm, "lines": lines,
            "rules": RULES,
            "read_only": "A suggestion: nothing is saved. Open a line in the Junction to see what it picks."}
