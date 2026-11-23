"""T5: HISTORY's read API counts listens the way jimbo-dj does, so nothing counts twice."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from traqfreq import history, legacy
from traqfreq.app import create_app
from traqfreq.settings import Settings


def _copy(legacy_db, tmp_path, *sql):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    w = sqlite3.connect(copy)  # a scratch copy of the fixture, never the legacy DB
    for q in sql:
        w.execute(q)
    w.commit()
    w.close()
    return legacy.connect(copy)


def test_overview_counts(legacy_db):
    before = legacy_db.read_bytes()
    o = history.overview(legacy.connect(legacy_db))
    assert o["plays"] == 6 and o["listens"] == 9
    assert o["not_plays"] == {"too_short": 1, "repeat": 1, "duplicate": 1}
    assert o["adds_up"] is True  # every listen in exactly one bucket
    assert o["matched"] == {"plays": 5, "pct": 83.3}
    assert o["songs"] == {"heard": 6, "matched": 5}
    assert o["jimbodj"]["matches"] is True and o["jimbodj"]["plays"] == 6
    assert legacy_db.read_bytes() == before


def test_overview_sources_in_priority_order(legacy_db):
    o = history.overview(legacy.connect(legacy_db))
    assert [s["source"] for s in o["sources"]] == ["lastfm", "plex", "spotify", "applemusic"]
    by = {s["source"]: s for s in o["sources"]}
    assert by["plex"]["duplicate"] == 1 and by["plex"]["duplicate_of"] == {"lastfm": 1} and by["plex"]["play"] == 1
    assert by["spotify"] == {**by["spotify"], "listens": 3, "play": 1, "too_short": 1, "repeat": 1, "duplicate": 0}
    assert by["lastfm"]["first"] == "2026-01-01T05:30:00Z" and by["lastfm"]["name"] == "Last.fm"
    assert sum(s["play"] for s in o["sources"]) == o["plays"]


def test_years_follow_listen_time_zone(legacy_db, tmp_path):
    o = history.overview(legacy.connect(legacy_db))  # no history_tz, no TZ: America/Denver
    assert o["timezone"] == "America/Denver"
    assert [(y["year"], y["plays"]) for y in o["years"]] == [(2025, 1), (2026, 5)]
    assert sum(y["plays"] for y in o["years"]) == o["plays"]
    assert [(y["year"], y["plays"]) for y in history.overview(legacy.connect(legacy_db), "UTC")["years"]] == [(2026, 6)]
    conn = _copy(legacy_db, tmp_path, "INSERT INTO meta VALUES ('history_tz', 'UTC')")
    assert history.overview(conn, "America/Denver")["timezone"] == "UTC"  # jimbo-dj's setting wins over TZ


def test_bad_time_zone_falls_back(legacy_db):
    assert str(history.listen_tz(legacy.connect(legacy_db), "Nowhere/Atlantis")) == "America/Denver"


@pytest.mark.parametrize("status,n", [("play", 6), ("too_short", 1), ("repeat", 1), ("duplicate", 1)])
def test_listens_show_the_rows(legacy_db, status, n):
    r = history.listens(legacy.connect(legacy_db), status)
    assert r["total"] == n == len(r["rows"])


def test_listens_filters(legacy_db):
    conn = legacy.connect(legacy_db)
    r = history.listens(conn, "play", source="lastfm")
    assert r["total"] == 3 and r["rule"] == "listens WHERE counted = 1 AND source = ?" and r["params"] == ["lastfm"]
    assert [x["started_at"] for x in r["rows"]] == ["2026-11-04T19:05:00Z", "2026-11-01T20:15:00Z", "2026-01-01T05:30:00Z"]
    assert r["rows"][0]["rating_key"] is None and r["rows"][1]["rating_key"] == 101  # via listen_matches
    assert history.listens(conn, "play", year=2025)["total"] == 1
    page = history.listens(conn, "play", limit=2, offset=4)
    assert page["total"] == 6 and len(page["rows"]) == 2
    with pytest.raises(ValueError):
        history.listens(conn, "skipped")


def test_api(client):
    o = client.get("/api/history/overview").json()
    assert o["plays"] == 6 and o["adds_up"]
    r = client.get("/api/history/listens", params={"status": "duplicate"}).json()
    assert r["rows"][0]["source"] == "plex" and r["rows"][0]["dup_of"] == "lastfm"
    assert client.get("/api/history/listens", params={"status": "nope"}).status_code == 400


def test_api_tz_from_env(legacy_db, tmp_path):
    s = Settings.from_env({"TRAQFREQ_LEGACY_DB": str(legacy_db), "TZ": "UTC", "TRAQFREQ_DATA_DIR": str(tmp_path / "data")})
    assert TestClient(create_app(s)).get("/api/history/overview").json()["timezone"] == "UTC"


def test_api_without_listens(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    c = TestClient(create_app(Settings(data_dir=tmp_path, legacy_db=db, port=4492, host="127.0.0.1")))
    assert c.get("/api/history/overview").status_code == 404
    c = TestClient(create_app(Settings(data_dir=tmp_path, legacy_db=None, port=4492, host="127.0.0.1")))
    assert c.get("/api/history/overview").status_code == 503
