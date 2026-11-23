"""jimbo-dj's Library charts (statcache's ``library.charts``), the parts LIBRARY counts with, copied unchanged.

From insights.py: keys by name (``keys``), files (``file_buckets``, ``files``: format, quality tier, bit depth,
sample rate, lossy bitrate, channels), time (``_release_years``, ``time_buckets``, ``when``: lengths, decades,
added, last played hour and weekday), place (``artist_places``, ``album_labels``, ``place``) and ``_all_views``,
with the constants they use. From live.py: ``distributions`` (the sound: BPM, Camelot, loudness, moods,
averages). statcache builds ``library.charts`` as ``{**insights._all_views(con), "sound": live.distributions(con)}``.

Not copied: ``genre_view`` and ``track_family`` (styles and genre families are TAGS, P4) and the Discogs genres
inside ``distributions`` (jimbo-dj's genres module). Stand-ins at the bottom (marked, not vendored) give the
copies the names they call in jimbo-dj: ``schedule.tz()`` returns the zone traqfreq hands in with ``in_tz``
(jimbo-dj's is its TZ, else America/Denver), ``genre_view`` says it isn't compared, and ``vendor/genres.py``
has no styles. Never edit the copies; re-copy them from jimbo-dj when it changes.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import sqlite3
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .jimbodj_library import ANALYZER_VERSION

VENDORED_FROM = "jimbo-dj 1d8a7cb src/jimbodj/insights.py, live.py"

# --- src/jimbodj/insights.py -----------------------------------------------------------------------------
LOSSLESS = {"flac", "alac", "pcm", "wav", "aiff", "ape", "wavpack", "wv", "dsd", "dsf", "tta"}
# The analyzer spells keys both ways (Ab, Bb, Eb but C#, F#); they're shown the conventional way.
NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_SPELLING = {"D#": "Eb", "G#": "Ab", "A#": "Bb", "Db": "C#", "Gb": "F#", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}
_SHARP = {"Eb": "D#", "Ab": "G#", "Bb": "A#"}
_CAMELOT_MAJOR = {"B": 1, "F#": 2, "C#": 3, "G#": 4, "D#": 5, "A#": 6, "F": 7, "C": 8, "G": 9, "D": 10, "A": 11, "E": 12}
_CAMELOT_MINOR = {"G#": 1, "D#": 2, "A#": 3, "F": 4, "C": 5, "G": 6, "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "C#": 12}
_OTHER = {"C#": "D♭", "Eb": "D♯", "F#": "G♭", "Ab": "G♯", "Bb": "A♯"}


def spell(key: str) -> str:
    return _SPELLING.get(key, key)
_COUNTRY_SHORT = {"United States of America": "United States", "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
                  "Russian Federation": "Russia", "Korea, Republic of": "South Korea"}
LENGTHS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 10), (10, 20), (20, None)]


def key_name(key: str | None, scale: str | None, short: bool = False) -> str | None:
    """'F#', 'minor' → 'F♯ minor' (short: 'F♯m')."""
    if not key or scale not in ("major", "minor"):
        return None
    k = spell(key).replace("#", "♯").replace("b", "♭")
    return (k + ("m" if scale == "minor" else "")) if short else f"{k} {scale}"


def _bar(label: str, value, **extra) -> dict:
    return {"label": label, "value": value, **extra}


def _loads(v, default):
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def keys(con) -> dict:
    rows: Counter = Counter()
    for r in con.execute(
        "SELECT f.key, f.scale, COUNT(*) FROM features f JOIN analysis a USING (rating_key) JOIN tracks t USING (rating_key) "
        "WHERE t.removed_at IS NULL AND a.status='ok' AND a.version>=? AND f.key IS NOT NULL GROUP BY 1, 2", (ANALYZER_VERSION,)):
        rows[(spell(r[0]), r[1])] += r[2]
    out = []
    for scale, table in (("major", _CAMELOT_MAJOR), ("minor", _CAMELOT_MINOR)):
        for n in NOTES:
            out.append({"key": n, "scale": scale, "label": key_name(n, scale, short=True), "name": key_name(n, scale),
                        "also": f"{_OTHER[n]} {scale}" if n in _OTHER else None,
                        "camelot": f"{table[_SHARP.get(n, n)]}{'B' if scale == 'major' else 'A'}", "value": rows.get((n, scale), 0)})
    total = sum(k["value"] for k in out) or 1
    major = sum(k["value"] for k in out if k["scale"] == "major")
    top = sorted(out, key=lambda k: -k["value"])[:5]
    return {"keys": out, "major_pct": round(100 * major / total, 1), "top": top}


BITRATES = (("<128k", 0, 128), ("128–191k", 128, 192), ("192–255k", 192, 256), ("256–319k", 256, 320), ("320k+", 320, 10**6))
FILE_COLUMNS = "LOWER(COALESCE(codec, container, '?')) codec, bit_depth, sample_rate, bitrate, channels"


def file_buckets(r) -> dict:
    """Which bar of each Files chart a track counts in (a row with FILE_COLUMNS). The charts and the
    Explore filters they link to both use this, so a bar's number and its tracks always match."""
    c = r["codec"]
    lossless = c in LOSSLESS
    out = {"format": c.upper(),
           "channels": {1: "Mono", 2: "Stereo"}.get(r["channels"], f"{r['channels']} channels" if r["channels"] else "?")}
    if r["sample_rate"]:
        out["rate"] = f"{r['sample_rate'] / 1000:g} kHz"
    if lossless:
        out["bits"] = f"{r['bit_depth']}-bit" if r["bit_depth"] else "?"
        hi = (r["bit_depth"] or 16) > 16 or (r["sample_rate"] or 44100) > 48000
        out["quality"] = "Hi-res lossless" if hi else "CD-quality lossless"
    else:
        br = r["bitrate"] or 0
        out["quality"] = "Lossy, 256k and up" if br >= 256 else "Lossy, under 256k"
        out["bitrate"] = next(label for label, lo, hi in BITRATES if lo <= br < hi)
    return out


def files(con) -> dict:
    live = "removed_at IS NULL"
    rows = con.execute(f"SELECT {FILE_COLUMNS}, file_size, duration_ms FROM tracks WHERE {live}").fetchall()
    fmt, depth, rate, chans, tier = Counter(), Counter(), Counter(), Counter(), Counter()
    size_by_fmt, lossy_rate = Counter(), Counter()
    for r in rows:
        b = file_buckets(r)
        fmt[b["format"]] += 1
        size_by_fmt[b["format"]] += r["file_size"] or 0
        tier[b["quality"]] += 1
        for key, c in (("bits", depth), ("rate", rate), ("channels", chans), ("bitrate", lossy_rate)):
            if b.get(key):
                c[b[key]] += 1
    n = len(rows) or 1
    lossless_n = tier["Hi-res lossless"] + tier["CD-quality lossless"]
    rate_order = sorted(rate.items(), key=lambda kv: float(kv[0].split()[0]))
    return {
        "tracks": len(rows),
        "lossless_pct": round(100 * lossless_n / n, 1),
        "hires": tier["Hi-res lossless"],
        "size_gb": round(sum(size_by_fmt.values()) / 1e9, 1),
        "read": con.execute(f"SELECT COUNT(*) FROM tracks WHERE {live} AND stream_size IS NOT NULL").fetchone()[0],
        "formats": [_bar(k, v, gb=round(size_by_fmt[k] / 1e9, 1)) for k, v in fmt.most_common(8)],
        "tiers": [_bar(k, tier[k]) for k in ("Hi-res lossless", "CD-quality lossless", "Lossy, 256k and up", "Lossy, under 256k")],
        "bit_depth": [_bar(k, v) for k, v in sorted(depth.items(), key=lambda kv: (kv[0] == "?", kv[0]))],
        "sample_rate": [_bar(k, v) for k, v in rate_order],
        "lossy_bitrate": [_bar(k, lossy_rate[k]) for k, _, _ in BITRATES],
        "channels": [_bar(k, v) for k, v in chans.most_common()],
    }


def _release_years(con) -> dict[int, int]:
    """Album → the year it first came out: MusicBrainz's first release, else Plex's release date or year."""
    out = {}
    for r in con.execute("SELECT a.album_key, a.year, a.released, m.first_release FROM albums a "
                         "LEFT JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok'"):
        for v in (r["first_release"], r["released"]):
            if v and len(v) >= 4 and v[:4].isdigit() and int(v[:4]) > 1000:
                out[r["album_key"]] = int(v[:4])
                break
        else:
            if r["year"]:
                out[r["album_key"]] = r["year"]
    return out


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIME_COLUMNS = "album_key, year, duration_ms, view_count, added_at, last_viewed_at"


def _length_label(lo, hi) -> str:
    return f"{lo}–{hi}" if hi else f"{lo}+"


def time_buckets(r, years: dict, tz) -> dict:
    """Which bar of each Time chart a track counts in (a row with TIME_COLUMNS); shared with Explore."""
    mins = (r["duration_ms"] or 0) / 60000
    out = {"length": next(_length_label(lo, hi) for lo, hi in LENGTHS if mins >= lo and (hi is None or mins < hi))}
    y = years.get(r["album_key"]) or r["year"]
    if y and 1900 <= y <= 2100:
        out["decade"] = f"{y // 10 * 10}s"
    if r["added_at"]:
        out["added"] = str(datetime.fromtimestamp(r["added_at"], tz).year)
    if r["last_viewed_at"]:
        dt = datetime.fromtimestamp(r["last_viewed_at"], tz)
        out["hour"], out["weekday"] = f"{dt.hour:02d}", WEEKDAYS[dt.weekday()]
    return out


def when(con) -> dict:
    years = _release_years(con)
    tz = schedule.tz()
    lengths = Counter()
    dec_tracks, dec_plays, dec_hours = Counter(), Counter(), Counter()
    added, hour, weekday = Counter(), Counter(), Counter()
    longest = []
    for r in con.execute(f"SELECT rating_key, title, artist, {TIME_COLUMNS} FROM tracks WHERE removed_at IS NULL"):
        b = time_buckets(r, years, tz)
        lengths[b["length"]] += 1
        mins = (r["duration_ms"] or 0) / 60000
        if "decade" in b:
            d = int(b["decade"][:4])
            dec_tracks[d] += 1
            dec_plays[d] += r["view_count"] or 0
            dec_hours[d] += mins / 60
        if "added" in b:
            added[int(b["added"])] += 1
        if "hour" in b:
            hour[int(b["hour"])] += 1
            weekday[WEEKDAYS.index(b["weekday"])] += 1
        longest.append((r["duration_ms"] or 0, r["rating_key"], r["title"], r["artist"], r["album_key"]))
    longest.sort(reverse=True)
    decades = sorted(dec_tracks)
    total_ms = sum(x[0] for x in longest)
    n = len(longest) or 1
    return {
        "lengths": [_bar(_length_label(lo, hi), lengths[_length_label(lo, hi)]) for lo, hi in LENGTHS],
        "average_minutes": round(total_ms / n / 60000, 1),
        "longest": [{"rating_key": k, "title": t, "artist": a, "album_key": ak, "minutes": round(ms / 60000, 1)}
                    for ms, k, t, a, ak in longest[:5]],
        "decades": [_bar(f"{d}s", dec_tracks[d], plays=dec_plays[d], hours=round(dec_hours[d])) for d in decades],
        "decade_plays": [_bar(f"{d}s", dec_plays[d]) for d in decades],
        "oldest": min(years.values(), default=None), "newest": max(years.values(), default=None),
        "added": [_bar(str(y), added[y]) for y in sorted(added)],
        "hours": [_bar(f"{h:02d}", hour[h]) for h in range(24)],
        "weekdays": [_bar(d, weekday[i]) for i, d in enumerate(WEEKDAYS)],
        "timezone": str(tz),
    }


def artist_places(con) -> dict[int, dict]:
    """Artist → its country, hometown (where it started, when that isn't the country), the decade it
    formed and its type, from Plex and MusicBrainz; shared by the Place charts and Explore."""
    out = {}
    for r in con.execute("SELECT a.artist_key, a.countries, m.area, m.country, m.begin_area, m.type, m.begin_year "
                         "FROM artists a LEFT JOIN mb_artists m ON m.mbid = a.mbid AND m.status='ok'"):
        plex_c = _loads(r["countries"], [])
        c = plex_c[0] if plex_c else (r["area"] if r["country"] else None)
        d = {}
        if c:
            d["country"] = c = _COUNTRY_SHORT.get(c, c)
        if r["begin_area"] and r["begin_area"] != c:
            d["city"] = r["begin_area"]
        if r["type"] and r["type"] != "Other":
            d["type"] = r["type"]
        if r["begin_year"]:
            d["formed"] = f"{r['begin_year'] // 10 * 10}s"
        out[r["artist_key"]] = d
    return out


def album_labels(con) -> dict[int, str]:
    """Album → its (first) label, from MusicBrainz, else Plex's studio."""
    out = {}
    for r in con.execute("SELECT a.album_key, a.studio, m.labels FROM albums a LEFT JOIN mb_releases m ON m.mbid = a.mbid AND m.status='ok'"):
        ls = _loads(r["labels"], []) or [x.strip() for x in (r["studio"] or "").split(";") if x.strip()]
        if ls:
            out[r["album_key"]] = ls[0]
    return out


def place(con) -> dict:
    country, cities, labels, types, formed = Counter(), Counter(), Counter(), Counter(), Counter()
    artist_tracks = Counter(r[0] for r in con.execute("SELECT artist_key FROM tracks WHERE removed_at IS NULL"))
    for ak, d in artist_places(con).items():
        n = artist_tracks.get(ak, 0)
        if not n:
            continue
        if "country" in d:
            country[d["country"]] += n
        if "city" in d:
            cities[d["city"]] += n
        if "type" in d:
            types[d["type"]] += 1
        if "formed" in d:
            formed[d["formed"]] += 1
    album_tracks = Counter(r[0] for r in con.execute("SELECT album_key FROM tracks WHERE removed_at IS NULL"))
    for alb, label in album_labels(con).items():
        labels[label] += album_tracks.get(alb, 0)
    total = sum(artist_tracks.values()) or 1
    return {
        "countries": [_bar(k, v) for k, v in country.most_common(15)],
        "countries_count": len(country),
        "known_pct": round(100 * sum(country.values()) / total, 1),
        "cities": [_bar(k, v) for k, v in cities.most_common(12)],
        "labels": [_bar(k, v) for k, v in labels.most_common(12)],
        "artist_types": [_bar(k, v) for k, v in types.most_common()],
        "formed": [_bar(k, v) for k, v in sorted(formed.items())],
    }


def _all_views(con) -> dict:
    t0 = time.time()
    data = {"keys": keys(con), "files": files(con), "time": when(con), "place": place(con), "genres": genre_view(con)}
    data["seconds"] = round(time.time() - t0, 2)
    return data


# --- src/jimbodj/live.py ---------------------------------------------------------------------------------
_BPM_BUCKETS = [(lo, lo + 10) for lo in range(60, 200, 10)]
_FEATURE_AVGS = ["danceability", "happy", "sad", "aggressive", "relaxed", "party", "voice"]


def distributions(con: sqlite3.Connection, version: int = ANALYZER_VERSION) -> dict:
    base = ("FROM features f JOIN analysis a USING (rating_key) JOIN tracks t USING (rating_key) "
            "WHERE t.removed_at IS NULL AND a.status='ok' AND a.version>=?")
    bpm = {f"{lo}–{hi}": 0 for lo, hi in _BPM_BUCKETS}
    for (b, n) in con.execute(f"SELECT CAST(f.bpm/10 AS INT)*10 b, COUNT(*) {base} AND f.bpm BETWEEN 60 AND 199.99 GROUP BY b", (version,)):
        bpm[f"{b}–{b + 10}"] = n
    camelot = {r[0]: r[1] for r in con.execute(f"SELECT f.camelot, COUNT(*) {base} AND f.camelot IS NOT NULL GROUP BY 1", (version,))}
    loud = {r[0]: r[1] for r in con.execute(
        f"SELECT CAST(-f.loudness_lufs/3 AS INT)*-3 b, COUNT(*) {base} AND f.loudness_lufs BETWEEN -30 AND 0 GROUP BY b ORDER BY b", (version,))}
    moods = con.execute(f"SELECT j.key, COUNT(*) n {base.replace('FROM features f', 'FROM features f, json_each(f.moods) j')} "
                        "GROUP BY j.key ORDER BY n DESC LIMIT 12", (version,)).fetchall()
    # Discogs genres a track keeps under genres.py's strict test, so each bar matches Explore's genre filter.
    from . import genres as genre_mod
    st = genre_mod.get(con)
    genres = Counter(g for (k,) in con.execute(f"SELECT f.rating_key {base}", (version,))
                     for g in st.sound_genres.get(k, ())).most_common(12)
    avgs = con.execute(f"SELECT {', '.join(f'AVG(f.{c})' for c in _FEATURE_AVGS)}, AVG(f.bpm), AVG(f.loudness_lufs) {base}", (version,)).fetchone()
    return {
        "bpm": [{"label": k, "value": v} for k, v in bpm.items()],
        "camelot": [{"label": f"{n}{m}", "value": camelot.get(f"{n}{m}", 0)} for m in "AB" for n in range(1, 13)],
        "loudness": [{"label": f"{k} LUFS", "value": v} for k, v in sorted(loud.items(), reverse=True)],
        "moods": [{"label": k, "value": v} for k, v in moods],
        "genres": [{"label": k, "value": v} for k, v in genres],
        "averages": {**{c: (round(avgs[i], 3) if avgs[i] is not None else None) for i, c in enumerate(_FEATURE_AVGS)},
                     "bpm": round(avgs[-2], 1) if avgs[-2] else None, "lufs": round(avgs[-1], 1) if avgs[-1] else None},
    }


# --- traqfreq's stand-ins, not vendored -------------------------------------------------------------------
DEFAULT_TZ = "America/Denver"  # jimbo-dj's schedule.tz() without TZ
_TZ: contextvars.ContextVar[ZoneInfo | None] = contextvars.ContextVar("jimbodj_schedule_tz", default=None)


class _Schedule:
    """jimbo-dj's ``schedule.tz()``: its TZ, else America/Denver. Here: the zone handed in with ``in_tz``."""

    @staticmethod
    def tz() -> ZoneInfo:
        return _TZ.get() or ZoneInfo(DEFAULT_TZ)


schedule = _Schedule()


def genre_view(con) -> dict:  # noqa: ARG001 - jimbo-dj's styles and families: TAGS (P4), not counted here
    return {"not_compared": "styles and genre families are TAGS (P4)"}


@contextlib.contextmanager
def in_tz(zone: ZoneInfo):
    """Run the copies with ``schedule.tz()`` = ``zone``."""
    token = _TZ.set(zone)
    try:
        yield
    finally:
        _TZ.reset(token)
