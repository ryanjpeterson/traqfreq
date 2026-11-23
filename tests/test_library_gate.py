"""T12: the P2 gate (jimbo-dj's stored library.stats and library.charts next to traqfreq's), on the fixture."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import pytest

from traqfreq import legacy, library, library_gate as g
from traqfreq.vendor import jimbodj_facets as jf
from traqfreq.vendor import jimbodj_insights as ji

ROOT = Path(__file__).resolve().parents[1]
DENVER = ZoneInfo("America/Denver")


def _compare(db):
    conn = legacy.connect(db)
    return g.compare(conn, g.zone(conn))


def _copy(legacy_db, tmp_path, *sql, name="copy.sqlite"):
    copy = tmp_path / name
    copy.write_bytes(legacy_db.read_bytes())
    w = sqlite3.connect(copy)
    with w:
        for s in sql:
            w.execute(*s) if isinstance(s, tuple) else w.execute(s)
    w.close()
    return copy


def _row(c, name):
    return next(r for r in c["rows"] if r["name"] == name)


def test_gate_passes_with_one_explained_difference(legacy_db):
    c = _compare(legacy_db)
    assert c["passed"] is True and c["stored"] == 2 and c["matching"] == 1
    assert c["differ"] == 1 and c["explained"] == 1 and c["stale"] == 1
    assert (c["fields"], c["matching_fields"]) == (60, 59)
    assert c["timezone"] == "America/Denver"
    s, ch = _row(c, "library.stats"), _row(c, "library.charts")
    assert s["fresh"] is True and s["matches"] is True and s["compared"] == s["matching"] == 23
    assert ch["fresh"] is False and ch["matches"] is False and (ch["matching"], ch["compared"]) == (36, 37)
    bad = [f for f in ch["fields"] if f["matches"] is False]
    assert [f["field"] for f in bad] == ["files.formats"]
    assert bad[0]["first_diff"] == {"index": 0, "jimbodj": {"label": "FLAC", "value": 3, "gb": 0.1},
                                    "traqfreq": {"label": "FLAC", "value": 2, "gb": 0.1}}


def test_not_compared_fields_are_shown_as_stored(legacy_db):
    c = _compare(legacy_db)
    s = {f["field"]: f for f in _row(c, "library.stats")["fields"]}
    assert s["paths.folders"]["matches"] is None and s["paths.folders"]["jimbodj"]["/music"]["tracks"] == 5
    ch = {f["field"]: f for f in _row(c, "library.charts")["fields"]}
    assert ch["genres"]["matches"] is None and "TAGS" in ch["genres"]["skipped"]
    assert ch["sound.genres"]["matches"] is None and ch["sound.genres"]["jimbodj"][0]["label"] == "Electronic"
    assert "seconds" not in ch and "built_at" not in s
    # every compared part of the charts, one level down
    assert {f.split(".")[0] for f, x in ch.items() if x["matches"] is not None} == set(g.SECTIONS)


def test_charts_counted_jimbodj_way(legacy_db):
    """A few of the hand-worked numbers: decades by first release (MusicBrainz 2020 for Low Tide Radio), hours in
    Denver across the end of summer time, place with jimbo-dj's short country name."""
    conn = legacy.connect(legacy_db)
    ch = g.charts(conn, DENVER)
    assert ch["files"]["tiers"][0] == {"label": "Hi-res lossless", "value": 1}
    assert ch["time"]["decades"] == [{"label": "2010s", "value": 2, "plays": 3, "hours": 0},
                                     {"label": "2020s", "value": 3, "plays": 2, "hours": 0}]
    assert [h["label"] for h in ch["time"]["hours"] if h["value"]] == ["12", "14"]
    assert ch["place"]["countries"] == [{"label": "Germany", "value": 2}, {"label": "United Kingdom", "value": 2}]
    assert ch["sound"]["genres"] == [] and "not_compared" in ch["genres"]
    # another zone moves the hours: the gate uses the one jimbo-dj's stored charts name
    utc = g.charts(conn, ZoneInfo("UTC"))
    assert [h["label"] for h in utc["time"]["hours"] if h["value"]] == ["18", "21"]


def test_fresh_charts_that_differ_fail(legacy_db, tmp_path):
    conn = legacy.connect(legacy_db)
    now = json.dumps(g.charts_stamp(conn)[:2] + [9, g.charts_stamp(conn)[3]])
    copy = _copy(legacy_db, tmp_path, ("UPDATE stats SET stamp = ? WHERE name = 'library.charts'", (now,)))
    c = _compare(copy)
    assert _row(c, "library.charts")["fresh"] is True  # genres.version (9 here) isn't checked
    assert c["passed"] is False and c["explained"] == 0


def test_fresh_charts_that_match_pass(legacy_db, tmp_path):
    conn = legacy.connect(legacy_db)
    st = g.charts_stamp(conn)
    copy = _copy(legacy_db, tmp_path,
                 ("UPDATE stats SET stamp = ? WHERE name = 'library.charts'", (json.dumps([st[0], st[1], 5, st[3]]),)),
                 "UPDATE stats SET value = json_set(value, '$.files.formats[0].value', 2) WHERE name = 'library.charts'")
    c = _compare(copy)
    assert c["passed"] is True and c["differ"] == 0 and c["matching_fields"] == c["fields"] == 60


def test_stale_stats_row_and_a_wrong_count(legacy_db, tmp_path):
    copy = _copy(legacy_db, tmp_path,
                 "UPDATE stats SET value = json_set(value, '$.tracks', 6) WHERE name = 'library.stats'")
    c = _compare(copy)
    assert c["passed"] is False and c["differ"] == 2 and c["explained"] == 1
    f = next(f for f in _row(c, "library.stats")["fields"] if f["field"] == "tracks")
    assert (f["jimbodj"], f["traqfreq"], f["rows"]) == (6, 5, "")
    copy2 = _copy(copy, tmp_path, "UPDATE stats SET stamp = '[\"1\", \"2\"]' WHERE name = 'library.stats'",
                  name="stale.sqlite")
    c = _compare(copy2)
    assert c["passed"] is True and c["explained"] == 2


def test_no_stored_rows_does_not_pass(legacy_db, tmp_path):
    copy = _copy(legacy_db, tmp_path, "DELETE FROM stats WHERE name LIKE 'library.%'")
    c = _compare(copy)
    assert c["stored"] == 0 and c["passed"] is False


def test_every_field_opens_rows_with_its_number(legacy_db):
    """Each count's rows query lists as many tracks as its number; each chart bar's facet lists its bar's value."""
    conn = legacy.connect(legacy_db)
    c = _compare(legacy_db)
    ours = library.stats(conn)
    s = {f["field"]: f for f in _row(c, "library.stats")["fields"]}
    for field, want in (("tracks", 5), ("play_history.played_tracks", 2), ("sonic_analysis.tracks", 3),
                        ("paths.mapped", 4), ("paths.multi_part_tracks", 1)):
        assert library.tracks(conn, **_kw(s[field]["rows"]))["total"] == want, field
    assert s["play_history.top_artists"]["rows"]["Kollektiv Nord"] == ours["rows"]["top_artists"]["301"]
    ch = _row(c, "library.charts")
    checked = 0
    for f in ch["fields"]:
        if f["field"] in g.FACETS:
            bars = {b["label"]: b["value"] for b in ours_chart(conn)[f["field"]]}
            for label, q in f["rows"].items():
                total = library.tracks(conn, **_kw(q))["total"]
                if f["field"] in ("place.formed", "place.artist_types"):
                    assert total >= bars[label]  # these count artists; the rows are their tracks
                elif f["field"] == "time.decade_plays":
                    continue  # plays, not tracks: the rows are the decade's tracks
                else:
                    assert total == bars[label], (f["field"], label)
                checked += 1
    assert checked > 40


def ours_chart(conn):
    ch = g.charts(conn, DENVER)
    return {f"{s}.{k}": v for s in g.SECTIONS for k, v in ch[s].items()}


def _kw(q: str) -> dict:
    kw = {}
    for k, v in parse_qsl(q):
        kw[k] = True if v == "true" else False if v == "false" else int(v) if k in ("artist_key", "album_key") else v
    return kw


def test_facet_rows_say_their_rule(legacy_db):
    conn = legacy.connect(legacy_db)
    r = library.tracks(conn, facet="decade", value="2020s")
    assert r["total"] == 3 and sorted(x["rating_key"] for x in r["rows"]) == [103, 104, 105]
    assert "decade is 2020s" in r["rule"] and "json_each" not in r["rule"] and r["params"] == []
    assert r["filters"]["facet"] == "decade"
    for bad in ({"facet": "style", "value": "Techno"}, {"facet": "listened", "value": "x"}, {"facet": "format"}):
        with pytest.raises(ValueError):
            library.tracks(conn, **bad)


def test_vendored_copies_unchanged_names():
    assert ji.VENDORED_FROM.startswith("jimbo-dj 1d8a7cb") and jf.VENDORED_FROM.startswith("jimbo-dj 1d8a7cb")
    assert ji.BITRATES[-1][0] == "320k+" and jf.KEYS[:3] == ("quality", "format", "bits")
    with ji.in_tz(ZoneInfo("UTC")):
        assert str(ji.schedule.tz()) == "UTC"
    assert str(ji.schedule.tz()) == "America/Denver"


def test_gate_script_reads_only(legacy_db):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, str(ROOT / "scripts/p2_gate.py"), "--db", str(legacy_db)],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert "PASSED" in r.stdout and "library.charts" in r.stdout and "differs, stale" in r.stdout
    assert "files.formats" in r.stdout
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before


def test_api_compare_and_facet_rows(client, legacy_db):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    c = client.get("/api/library/compare").json()
    assert c["passed"] is True and c["stored"] == 2 and c["fields"] == 60
    assert client.get("/api/library/compare").json()["cache"]["hit"] is True
    r = client.get("/api/library/tracks", params={"facet": "format", "value": "FLAC"}).json()
    assert r["total"] == 2 and sorted(x["rating_key"] for x in r["rows"]) == [101, 105]
    assert client.get("/api/library/tracks", params={"facet": "style", "value": "x"}).status_code == 400
    assert client.get("/api/library/tracks", params={"facet": "format"}).status_code == 400
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before
