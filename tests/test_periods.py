"""T8: Years, Wrapped, On this day, Top, and the P1 gate (jimbo-dj's stored numbers next to traqfreq's).

Expected numbers are worked out by hand from the fixture's invented listens (scripts/make_fixture.py),
in America/Denver: 2026 has 5 plays of 5.2 + 3.683 + 4.083 + 6.7 + 3.75 = 23.42 min (0.4 h)."""

import datetime as dt
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from traqfreq import history, legacy, periods
from traqfreq.vendor import jimbodj_history as jd

ROOT = Path(__file__).resolve().parents[1]


def _ctx(db):
    conn = legacy.connect(db)
    return conn, history.listen_tz(conn), periods.Names(conn)


def test_vendored_period_code_unchanged():
    """_range, _minutes, top_range and TOP_PERIODS are jimbo-dj's text, unchanged (1d8a7cb)."""
    import inspect
    src = inspect.getsource(jd)
    for name in ("_range", "_minutes", "top_range"):
        assert f"def {name}(" in src
    assert jd.TOP_PERIODS == {"all": "All time", "30d": "Last 30 days", "12m": "Last 12 months"}
    assert jd.DAY == 86400


def test_minutes_rules():
    assert jd._minutes({"source": "lastfm", "ms_played": 999, "duration_ms": 312000}) == 5.2  # track length
    assert jd._minutes({"source": "lastfm", "ms_played": None, "duration_ms": None}) == 3.75  # 225 s
    daily = {"source": "applemusic", "ms_played": 900000, "duration_ms": 402000, "uri": "daily:2026-10-14:18"}
    assert jd._minutes(daily) == 6.7  # capped at the track
    assert jd._minutes({**daily, "uri": None}) == 15.0


def test_ranges_in_listening_zone(legacy_db):
    conn, tz, _ = _ctx(legacy_db)
    with jd.in_zone(tz):
        a, b = jd._range(conn, 2026, None)
        assert dt.datetime.fromtimestamp(a, dt.timezone.utc).isoformat() == "2026-01-01T07:00:00+00:00"
        a, b = jd._range(conn, 2026, 11, 2)
        assert b - a == 86400
        a, b = jd._range(conn, 2026, 11, 1)
        assert b - a == 90000  # clocks go back on 1 Nov 2026: a 25-hour day
        assert jd.top_range(conn, "all") == (None, None)
        a, b = jd.top_range(conn, "30d")
        today = dt.datetime.now(tz).date()
        assert dt.datetime.fromtimestamp(b, tz).date() == today + dt.timedelta(days=1)
        assert dt.datetime.fromtimestamp(a, tz).date() == today - dt.timedelta(days=29)
        with pytest.raises(ValueError):
            jd.top_range(conn, "2026-13")


def test_years_plays_and_hours(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    d = periods.daily(conn, tz, nm, dt.date(2026, 11, 22))
    assert [(y["year"], y["plays"], y["minutes"], y["hours"]) for y in d["years"]] == [(2025, 1, 5, 0), (2026, 5, 23, 0)]
    assert d["plays"] == 6 and d["matched_pct"] == 83.3
    assert d["highlights"]["busiest_day"] == {"date": "2026-11-01", "plays": 2}
    assert d["highlights"]["streak"]["best"] == 4  # 1-4 Nov
    assert d["highlights"]["first_play"]["date"] == "2025-12-31"


def test_on_this_day(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    d = periods.daily(conn, tz, nm, dt.date(2027, 11, 1))  # a year after the fixture's 1 Nov 2026
    assert d["on_this_day"] == [{"year": 2026, "plays": 2, "top": [
        {"artist": "Kollektiv Nord", "title": "Westkreuz", "plays": 1, "rating_key": 101, "album_key": 201},
        {"artist": "The Paper Lanterns", "title": "Harbour Lights", "plays": 1, "rating_key": 103, "album_key": 202}]}]
    assert periods.daily(conn, tz, nm, dt.date(2026, 11, 1))["on_this_day"] == []  # earlier years only


def test_wrapped_year_month_day(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    y = periods.wrapped(conn, tz, nm, 2026)
    assert (y["plays"], y["hours"], y["artists"], y["songs"], y["new_artists"], y["in_library_pct"]) == (5, 0.4, 4, 5, 3, 80.0)
    assert len(y["by_part"]) == 12 and y["by_part"][10]["value"] == 5  # all in November
    assert sum(p["value"] for p in y["hours_of_day"]) == 5 and sum(p["value"] for p in y["weekdays"]) == 5
    assert len(y["by_date"]) == 365 and y["every_play"] is None
    m = periods.wrapped(conn, tz, nm, 2026, 11)
    assert len(m["by_part"]) == 30 and m["plays"] == 5
    d = periods.wrapped(conn, tz, nm, 2026, 11, 1)
    assert [p["time"] for p in d["every_play"]] == ["13:15", "13:21"] and d["by_date"] is None
    assert periods.wrapped(conn, tz, nm, 2026, 10)["plays"] == 0
    # The 2026-01-01 05:30 UTC play is 2025 in Denver.
    assert periods.wrapped(conn, tz, nm, 2025)["plays"] == 1


def test_wrapped_top_entries_open_their_rows(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    w = periods.wrapped(conn, tz, nm, 2026)
    for a in w["top_artists"]:
        assert history.listens(conn, "play", period="2026", artist=a["key"])["total"] == a["plays"]
    for s in w["top_songs"]:
        assert history.listens(conn, "play", period="2026", song=s["key"])["total"] == s["plays"]
    for al in w["top_albums"]:
        assert history.listens(conn, "play", period="2026", album=al["key"])["total"] == al["plays"]
    # Spotify's Static Gulls names no album: it counts for its library track's (Low Tide Radio).
    assert w["top_albums"][0]["album"] == "Low Tide Radio" and w["top_albums"][0]["plays"] == 2
    for h in w["hours_of_day"]:
        assert history.listens(conn, "play", period="2026", hour=int(h["label"]))["total"] == h["value"]
    for i, d in enumerate(w["weekdays"]):
        assert history.listens(conn, "play", period="2026", weekday=i)["total"] == d["value"]


def test_top_by_plays_and_minutes(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    t = periods.top(conn, tz, nm, "all")
    assert [(x["name"], x["plays"], x["minutes"]) for x in t["albums"]["minutes"]] == [
        ("Ringbahn", 2, 10), ("Low Tide Radio", 2, 8), ("Quiet Engines", 1, 7)]
    assert [x["name"] for x in t["artists"]["plays"]][:2] == ["Kollektiv Nord", "The Paper Lanterns"]
    assert sum(x["plays"] for x in t["songs"]["plays"]) == t["plays"] == 6  # nothing counts twice
    p = periods.top_page(t, "songs", "minutes", per=12)
    assert p["items"][0]["rank"] == 1 and p["items"][0]["name"] == "Coil" and p["total"] == 6
    s = periods.top(conn, tz, nm, "2026", "spotify")
    assert s["plays"] == 1 and {x["source"] for x in s["sources"]} == {"lastfm", "plex", "spotify", "applemusic"}
    assert periods.top(conn, tz, nm, "2026-11")["plays"] == 5
    with pytest.raises(ValueError):
        periods.top_page(t, "genres")
    with pytest.raises(ValueError):
        periods.top(conn, tz, nm, "all", "napster")


def test_gate_on_fixture(legacy_db):
    conn, tz, nm = _ctx(legacy_db)
    c = periods.compare(conn, tz, nm, "2026-11-22", dt.date(2026, 11, 22))
    by = {(r["name"], r["params"]): r for r in c["rows"]}
    assert list(by) == [("history.overview", ""), ("history.wrapped", "2025"), ("history.wrapped", "2026"),
                        ("history.wrapped", "2026-10"), ("history.wrapped", "2026-11-01")]
    for k in [("history.overview", ""), ("history.wrapped", "2025"), ("history.wrapped", "2026"), ("history.wrapped", "2026-11-01")]:
        assert by[k]["matches"], by[k]
    # 2026-10: stored before the last import with 3 plays; there are none now. Stale, so explained.
    stale = by[("history.wrapped", "2026-10")]
    assert stale["matches"] is False and stale["fresh"] is False
    assert [f for f in stale["fields"] if not f["matches"]] == [{"field": "plays", "matches": False, "jimbodj": 3, "traqfreq": 0}]
    assert by[("history.wrapped", "2026")]["fresh"] is True
    # Library and tag numbers aren't compared in P1, and are said to be skipped.
    assert {f["field"]: f["matches"] for f in by[("history.wrapped", "2026")]["fields"]}["families"] is None
    assert c["passed"] is True and c["differ"] == 1 and c["explained"] == 1


def test_gate_fails_on_fresh_difference(legacy_db, tmp_path):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    import sqlite3
    w = sqlite3.connect(copy)
    with w:
        w.execute("UPDATE stats SET value = json_set(value, '$.plays', 6) WHERE name = 'history.wrapped' AND params = '2026'")
    w.close()
    conn, tz, nm = _ctx(copy)
    c = periods.compare(conn, tz, nm, "2026-11-22")
    assert c["passed"] is False and c["differ"] == 2 and c["explained"] == 1


def test_gate_script_reads_only(legacy_db):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, str(ROOT / "scripts/p1_gate.py"), "--db", str(legacy_db)],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert "PASSED" in r.stdout and "history.wrapped 2026-10" in r.stdout and "differs, stale" in r.stdout
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before


def test_api_years_wrapped_top_compare(client, legacy_db):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    y = client.get("/api/history/years").json()
    assert [x["year"] for x in y["years"]] == [2025, 2026] and "highlights" in y
    assert client.get("/api/history/years").json()["cache"]["hit"] is True
    assert "on_this_day" in client.get("/api/history/on-this-day").json()
    w = client.get("/api/history/wrapped", params={"period": "2026-11"}).json()
    assert w["plays"] == 5 and w["period"] == "2026-11"
    assert client.get("/api/history/wrapped", params={"period": "2026-13"}).status_code == 400
    t = client.get("/api/history/top", params={"period": "2026", "kind": "albums", "sort": "minutes"}).json()
    assert [i["name"] for i in t["items"]] == ["Low Tide Radio", "Quiet Engines", "Ringbahn"]
    assert client.get("/api/history/top", params={"period": "30d"}).status_code == 200
    assert client.get("/api/history/top", params={"kind": "genres"}).status_code == 400
    assert client.get("/api/history/top", params={"period": "soon"}).status_code == 400
    c = client.get("/api/history/compare").json()
    assert c["passed"] is True and c["stored"] == 5
    assert client.get("/api/history/compare").json()["cache"]["hit"] is True
    r = client.get("/api/history/listens", params={"album": "paperlanterns|lowtideradio", "period": "2026"}).json()
    assert r["total"] == 2
    assert client.get("/api/history/listens", params={"hour": 24}).status_code == 400
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before
