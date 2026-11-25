"""T25: the Junction (docs/specs/t24-playlists.md): rules.build's picking, vendored; copies on each server; gate
check 1 and the set of tracks of check 2. Fixture only (invented rows); scratch copies of it where a test needs a
ban or a second copy of a song, never the real database."""

import importlib.util
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traqfreq import junction, legacy, playlists, playlists_gate
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import flow, rules

ROOT = Path(__file__).resolve().parents[1]


def _mf():
    spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _client(db, data_dir):
    return TestClient(create_app(Settings(data_dir=data_dir, legacy_db=db, port=4492, host="127.0.0.1")))


@pytest.fixture
def snap_client(legacy_db, tmp_path):
    """The fixture with the invented Jellyfin and Navidrome snapshots loaded (P3's matches)."""
    d = tmp_path / "snapdata"
    _mf().load_snapshots(d)
    return _client(legacy_db, d)


def _scratch(legacy_db, tmp_path, *sql):
    """A scratch copy of the fixture with a few invented changes (a ban, a second copy of a song)."""
    db = tmp_path / "scratch.sqlite"
    shutil.copy(legacy_db, db)
    conn = sqlite3.connect(db)
    with conn:
        for s in sql:
            conn.execute(s)
    conn.close()
    return db


def test_picking_vendored_unchanged():
    """rules.py's Picking, make.details, bans' read side, similar._norm_title and _public, browse's plays sort and
    the index's meta query are jimbo-dj's at 1d8a7cb (checked against a copy beside the repo, as T24's test is)."""
    assert "Picking" in rules.VENDORED_FROM and hasattr(rules, "build") and hasattr(rules, "pick")
    assert flow.STAND_IN  # pick order until T27
    jimbodj = ROOT.parent / "jimbo-dj"
    if not (jimbodj / ".git").exists():
        return
    vendor = ROOT / "src/traqfreq/vendor"
    for path, mine, a, b in (("rules.py", "rules.py", "# --- Picking", "# --- Narrowing"),
                             ("make.py", "make.py", "def details(", "def tracks("),
                             ("similar.py", "similar.py", "def _norm_title(", "def seed_tracks("),
                             ("similar.py", "similar.py", "def _public(m", None),
                             ("bans.py", "bans.py", "KINDS = (", "\n\n\ndef ensure_schema"),
                             ("bans.py", "bans.py", "@dataclass", None),
                             ("browse.py", "browse.py", "# plays(): every", "\n\n\nSOUND"),
                             ("browse.py", "browse.py", "def _with_plays(", "\n\n\ndef matching("),
                             ("vectors.py", "vectors.py", "META_COLS = (", "\n\n\ndef _norm"),
                             ("vectors.py", "vectors.py", "_META_Q = (", "FULL_EVERY")):
        theirs = subprocess.run(["git", "-C", str(jimbodj), "show", f"1d8a7cb:src/jimbodj/{path}"],
                                capture_output=True, text=True, check=True).stdout
        i = theirs.index(a)
        part = theirs[i:theirs.index(b, i) if b else len(theirs)].rstrip()
        assert part in (vendor / mine).read_text(encoding="utf-8"), (path, a)


# Plays (jimbo-dj's plays_of, the larger of Plex's and the history's): 101 has 3, 104 has 2, 102, 103 and 105
# have 1 each. Ties: last played first (none), then album order (artist 301, 302, 303). So most played first is
# 101, 104, 102, 103, 105. jimbo-dj's index knows the tracks analysed at version 2 with status ok: 101 and 103.
NIGHT = {
    # a: 2010s, not sad. 101 and 102 are from 2019; 101's analysis says sad, 102's is too old to count: {102}.
    # b: Ada Vey, or played in 2025: {102, 105}. c: happy and (100-110 bpm or key 8A): {101, 103}.
    # Turns: a takes 102; b's 102 is gone, it takes 105; c takes 101. Next turn a and b have nothing left, c takes
    # 103. 4 of 20: every line ran short, so the rest goes unfilled.
    "branches": [{"id": "a", "count": 1, "share": 8, "got": 1, "available": 1},
                 {"id": "b", "count": 2, "share": 6, "got": 1, "available": 2},
                 {"id": "c", "count": 2, "share": 6, "got": 2, "available": 2}],
    "total": 4,
    "tracks": [{"rating_key": 102, "branch": "a"}, {"rating_key": 105, "branch": "b"},
               {"rating_key": 101, "branch": "c"}, {"rating_key": 103, "branch": "c"}],
}


def test_build_night_lines(legacy_db):
    """Shares, line priority by order, a song once, a short line leaving its rest: worked out by hand above."""
    r = junction.build(legacy.connect(legacy_db), _mf()._NIGHT)
    assert [{k: x[k] for k in ("id", "count", "share", "got", "available")} for x in r["lines"]] == NIGHT["branches"]
    assert r["total"] == 4 and r["preview"]["total"] == 4
    assert r["preview"]["tracks"] == NIGHT["tracks"]
    assert [t["line"] for t in r["picked"]["tracks"]] == ["a", "b", "c", "c"]
    assert r["picked"]["tracks"][0]["line_name"] == "Ringbahn, not sad"
    assert r["picked"]["order"] == "pick" and r["picked"]["count"] == 4
    assert r["picked"]["minutes"] == round((298000 + 402000 + 312000 + 221000) / 60000)
    assert r["summary"].startswith("4 tracks: 8 Ringbahn, not sad, 6 ")
    assert r["bans"] == {"songs": 0, "artists": 1, "styles": 0}  # Former Band: removed, so nothing is left out


def test_shuffle_is_seeded(legacy_db):
    """Inside the lines has Shuffle 2: a jitter seeded by the tree, so the same tree picks the same way."""
    conn = legacy.connect(legacy_db)
    a = junction.build(conn, _mf()._INSIDE)
    b = junction.build(conn, _mf()._INSIDE)
    assert a["preview"] == b["preview"]
    # a: in From the 2020s (103, 104, 105), not in Quiet Engines (103, 105): {104}. b: the daily mix's analysed
    # tracks: {101, 103}.
    assert [(x["id"], x["count"], x["got"]) for x in a["lines"]] == [("a", 1, 1), ("b", 2, 2)]
    assert {(t["rating_key"], t["branch"]) for t in a["preview"]["tracks"]} == {(104, "a"), (101, "b"), (103, "b")}


def test_per_artist_cap(client):
    """At most per_artist tracks by one artist: 101 and 102 are both Kollektiv Nord; with per=1 only 101 goes in."""
    r = client.get("/api/junction?b=decade:2010s&per=1").json()
    assert (r["per_artist"], r["lines"][0]["count"], r["lines"][0]["got"], r["lines"][0]["available"]) == (1, 2, 1, 2)
    assert [t["rating_key"] for t in r["picked"]["tracks"]] == [101]
    r = client.get("/api/junction?b=decade:2010s").json()  # the default cap, 3
    assert [t["rating_key"] for t in r["picked"]["tracks"]] == [101, 102]


def test_line_priority_by_order(client):
    """A track two lines share goes to the first that takes it."""
    r = client.get("/api/junction?b=artist:Kollektiv Nord~5&b=decade:2010s~5&n=10").json()
    assert [(t["rating_key"], t["line"]) for t in r["picked"]["tracks"]] == [(101, "a"), (102, "b")]
    r = client.get("/api/junction?b=decade:2010s~5&b=artist:Kollektiv Nord~5&n=10").json()
    assert [(t["rating_key"], t["line"]) for t in r["picked"]["tracks"]] == [(101, "a"), (102, "b")]
    assert [x["got"] for x in r["lines"]] == [1, 1]


def test_a_song_goes_in_once(legacy_db, tmp_path):
    """A live copy of Westkreuz (invented, 107) is the same song: the copy with more plays goes in, once."""
    db = _scratch(legacy_db, tmp_path,
                  "INSERT INTO tracks (rating_key, title, artist, album, album_key, artist_key, track_no, year, "
                  "duration_ms, seen_at) VALUES (107, 'Westkreuz (Live)', 'Kollektiv Nord', 'Live', 205, 301, 1, 2019, "
                  "330000, 1793844000)")
    r = junction.build(legacy.connect(db), rules.from_query("b=decade:2010s"))
    assert r["lines"][0]["count"] == 3 and r["lines"][0]["available"] == 3
    assert [t["rating_key"] for t in r["picked"]["tracks"]] == [101, 102]


def test_never_in_mixes(legacy_db, tmp_path):
    """A banned artist's tracks are left out, as make.details tests them: only tracks jimbo-dj's index knows. 101
    (analysed) goes; 102 (its analysis is too old for the index) stays, as it does in jimbo-dj."""
    db = _scratch(legacy_db, tmp_path,
                  "INSERT INTO bans VALUES (2, 'artist', 'kollektivnord', 'Kollektiv Nord', 1793844400)")  # history.norm_artist
    conn = legacy.connect(db)
    r = junction.build(conn, rules.from_query("b=decade:2010s"))
    line = r["lines"][0]
    assert (line["count"], line["banned"], line["available"], line["got"]) == (2, 1, 1, 1)
    assert [t["rating_key"] for t in r["picked"]["tracks"]] == [102]
    assert r["bans"]["artists"] == 2
    gone = junction.rows(conn, rules.from_query("b=decade:2010s"), "a", "banned")
    assert [x["rating_key"] for x in gone["rows"]] == [101]


def test_rows_behind_every_number(client):
    q = "b=decade:2010s,!mood:sad~8~Ringbahn%2C not sad&b=(artist:Ada Vey|listened:2025)~6&b=mood:happy,(bpm:100-110|key:8A)~6&n=20"
    r = client.get(f"/api/junction?{q}").json()
    assert [(x["id"], x["count"], x["got"], x["available"]) for x in r["lines"]] == [
        (b["id"], b["count"], b["got"], b["available"]) for b in NIGHT["branches"]]
    for x in r["lines"]:
        for which in ("count", "got", "available", "banned"):
            rows = client.get(f"/api/junction/rows?{q}&line={x['id']}&which={which}").json()
            assert rows["count"] == x[which], (x["id"], which)
    got = client.get(f"/api/junction/rows?{q}&line=c&which=got").json()
    assert [(x["rating_key"], x["line"]) for x in got["rows"]] == [(101, "c"), (103, "c")]
    pool = client.get(f"/api/junction/rows?{q}&line=b&which=available").json()
    assert [x["rating_key"] for x in pool["rows"]] == [102, 105]  # most played first, then album order
    picked = client.get(f"/api/junction/rows?{q}&which=picked").json()
    assert [(x["rating_key"], x["line"]) for x in picked["rows"]] == [(t["rating_key"], t["branch"]) for t in NIGHT["tracks"]]
    assert client.get(f"/api/junction/rows?{q}&line=a&which=nope").status_code == 400
    assert client.get(f"/api/junction/rows?{q}&line=zz&which=got").status_code == 404
    assert client.get("/api/junction?b=nope:x").status_code == 400


def test_saved_playlist_lines_pick(client):
    """A saved playlist's lines carry what they pick now, and its rows answer each number."""
    r = client.get("/api/playlists/night-lines").json()
    assert [(x["id"], x["got"], x["available"]) for x in r["lines"]["lines"]] == [
        (b["id"], b["got"], b["available"]) for b in NIGHT["branches"]]
    rows = client.get("/api/playlists/night-lines/rows?line=b&which=available").json()
    assert rows["count"] == 2
    picked = client.get("/api/playlists/night-lines/rows?which=picked").json()
    assert picked["count"] == 4
    assert client.get("/api/playlists/daily-mix/rows?which=picked").status_code == 404  # no lines


def test_gate_check_1_and_track_set(legacy_db):
    """Gate check 1 and check 2's set, against jimbo-dj's preview answer for Night lines, worked out by hand."""
    ours = junction.build(legacy.connect(legacy_db), _mf()._NIGHT)["preview"]
    c1 = playlists_gate.check_lines(ours, NIGHT)
    assert c1["ok"] and c1["total"] == {"ours": 4, "theirs": 4, "ok": True}
    c2 = playlists_gate.check_track_set(ours, NIGHT)
    assert c2["ok"] and c2["count"] == {"ours": 4, "theirs": 4}
    # A difference is named, never hidden.
    other = {**NIGHT, "branches": [{**NIGHT["branches"][0], "available": 3}, *NIGHT["branches"][1:]], "total": 5,
             "tracks": [{"rating_key": 102, "branch": "b"}, *NIGHT["tracks"][1:3], {"rating_key": 104, "branch": "c"}]}
    c1 = playlists_gate.check_lines(ours, other)
    assert not c1["ok"] and c1["lines"][0]["fields"]["available"] == {"ours": 1, "theirs": 3, "ok": False}
    assert c1["total"]["ok"] is False and all(x["ok"] for x in c1["lines"][1:])
    c2 = playlists_gate.check_track_set(ours, other)
    assert (c2["missing"], c2["extra"], c2["other_line"]) == ([104], [103], [{"rating_key": 102, "ours": "a", "theirs": "b"}])


def test_copies_on_each_server(snap_client):
    """Each switch says how many of the stored tracks have a copy on its server (P3's matches); a missing copy is
    named with its reason. 105's Navidrome item hides its path; 106 was removed from Plex."""
    rows = {x["id"]: x for k in snap_client.get("/api/playlists").json()["kinds"] for x in k["rows"]}
    night = {s["server"]: s["copies"] for s in rows[1]["switches"]}  # 101, 103, 102, 105
    assert {s: (c["count"], c["of"], c["missing"]) for s, c in night.items()} == {
        "plex": (4, 4, 0), "jellyfin": (4, 4, 0), "navidrome": (3, 4, 1)}
    assert night["navidrome"]["reasons"] == {"hidden_path": 1}
    gone = {s["server"]: s["copies"] for s in rows[6]["switches"]}  # 106, removed
    assert all((c["count"], c["reasons"]) == (0, {"removed": 1}) for c in gone.values())
    miss = snap_client.get("/api/playlists/night-lines/copies?server=navidrome&missing=true").json()
    assert [(x["rating_key"], x["reason"]) for x in miss["rows"]] == [(105, "hidden_path")]
    have = snap_client.get("/api/playlists/night-lines/copies?server=navidrome&missing=false").json()
    assert [x["rating_key"] for x in have["rows"]] == [101, 103, 102]  # play order
    every = snap_client.get("/api/playlists/1/copies?server=plex").json()
    assert every["count"] == 4 and all(x["copy"] for x in every["rows"])
    assert snap_client.get("/api/playlists/1/copies?server=spotify").status_code == 400
    one = snap_client.get("/api/playlists/night-lines").json()["playlist"]["switches"]
    assert one[2]["copies"]["missing"] == 1


def test_copies_without_snapshots(client):
    """No snapshot yet: Jellyfin's and Navidrome's copies are unknown, and say why; Plex's are counted."""
    rows = {x["id"]: x for k in client.get("/api/playlists").json()["kinds"] for x in k["rows"]}
    sw = {s["server"]: s["copies"] for s in rows[1]["switches"]}
    assert (sw["plex"]["count"], sw["plex"]["snapshot"]) == (4, True)
    assert (sw["jellyfin"]["count"], sw["jellyfin"]["snapshot"], sw["jellyfin"]["reasons"]) == (0, False, {"no_snapshot": 4})


def test_reads_only(client, legacy_db):
    """The Junction writes nothing: the legacy file is unchanged after every endpoint."""
    before = legacy_db.read_bytes()
    q = "b=decade:2010s~5&b=in:saved:from-the-2020s~5&shuffle=3"
    for url in (f"/api/junction?{q}", f"/api/junction/rows?{q}&line=a&which=available", "/api/playlists",
                "/api/playlists/night-lines", "/api/playlists/1/copies?server=plex"):
        assert client.get(url).status_code == 200, url
    assert legacy_db.read_bytes() == before
    assert playlists.SERVERS == ("plex", "jellyfin", "navidrome")
