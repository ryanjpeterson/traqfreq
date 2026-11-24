"""T23, TAGS: a page per tag, the genre map, movements and the P4 gate. On the fixture only
(scripts/make_fixture.py TAGS, STYLES, LISTENS); cases the fixture doesn't hold go in a scratch copy."""

import importlib.util
import io
import json
import shutil
import sqlite3
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from traqfreq import entities, legacy, proposals, tagpages, tags, tags_gate
from traqfreq.vendor import jimbodj_history as jh
from traqfreq.vendor import jimbodj_tags as jd

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GATE = _load("p4_gate", ROOT / "scripts/p4_gate.py")


def _conn(db):
    return legacy.connect(db)


def _edit(db, tmp_path, *steps, name="edited.sqlite"):
    out = tmp_path / name
    shutil.copyfile(db, out)
    c = sqlite3.connect(out)
    with c:
        for sql, args in steps:
            c.execute(sql, args)
    c.close()
    return out


def test_tag_page_ladders_and_children(legacy_db):
    d = tagpages.tag(_conn(legacy_db), "Death-Doom Metal")
    assert [[x["name"] for x in p] for p in d["ladders"]] == [["Metal", "Death Metal", "Death-Doom Metal"],
                                                              ["Metal", "Doom Metal", "Death-Doom Metal"]]
    assert [p["name"] for p in d["parents"]] == ["Death Metal", "Doom Metal"] and d["rung"] == 2
    assert d["broad_rule"] == {"how": "family", "family": "Metal", "match": "doom", "broad": "Metal"}
    m = tagpages.tag(_conn(legacy_db), "metal")
    assert m["root"] and m["ladders"] == [[{"key": "metal", "name": "Metal", "rung": 0}]]
    assert [c["name"] for c in m["children"]] == ["Black Metal", "Doom Metal", "Death Metal"]
    assert m["numbers"]["under"] == 2 and m["numbers"]["missing"] == 1 and m["below"] == 5


def test_spellings_and_rules(legacy_db):
    h = tagpages.tag(_conn(legacy_db), "hip hop")
    assert h["spellings"] == [{"raw": "Hip-Hop", "albums": 0, "artists": 1, "tracks": 0, "same": False, "split": False,
                               "rules": [{"id": "aliases", "label": "Known aliases and typos"}]}]
    d = tagpages.tag(_conn(legacy_db), "doom metal")
    assert {s["raw"]: s["rules"] for s in d["spellings"]}["doom metal"] == [{"id": "case", "label": jd.load_rules()["case"]["label"]}]
    j = tagpages.tag(_conn(legacy_db), "2010s")
    assert j["junk"]["id"] == "decades" and j["ladders"] == [] and j["broad_rule"] is None
    s = tagpages.tag(_conn(legacy_db), "Soundtrack")
    assert s["broad"] is None and s["ladders"] == []
    with pytest.raises(tags.NotFound):
        tagpages.tag(_conn(legacy_db), "polka")


def _top_genres(db) -> Counter:
    """jimbo-dj's Top genres, all time, worked out here the way _top does: every counted play, its library track,
    that track's tags by _genre_tags."""
    conn = _conn(db)
    by_track, _ = jh._genre_tags(conn)
    out = Counter()
    for (rk,) in conn.execute("SELECT COALESCE(l.rating_key, m.rating_key) FROM listens l LEFT JOIN listen_matches m "
                              "ON m.match_key = l.match_key WHERE l.counted = 1"):
        for k in by_track.get(rk) or ():
            out[k] += 1
    return out


def test_plays_are_jimbodj_top_genres(legacy_db):
    top = _top_genres(legacy_db)
    assert top["black metal"] == 2 and top["doom metal"] == 2 and top["soundtrack"] == 1
    conn = _conn(legacy_db)
    for k in {k for ks in jh._genre_tags(conn)[0].values() for k in ks}:
        assert tagpages.tag(conn, k)["numbers"]["plays"] == top[k], k
        t = tagpages.tag_tracks(conn, k, limit=200)
        assert t["plays"] == top[k] and t["total"] == tagpages.tag(conn, k)["numbers"]["tracks"]
        for row in t["items"]:  # each track's plays are its listens rows on LIBRARY
            assert entities.plays(conn, track=row["rating_key"])["total"] == row["plays"]


def test_tracks_sorted(legacy_db):
    t = tagpages.tag_tracks(_conn(legacy_db), "doom metal")
    # Low Tide Radio's disc order differs from its track order (T11): disc 1 track 2 comes before disc 2 track 1.
    assert [(x["title"], x["disc"], x["plays"]) for x in t["items"]] == [("Static Gulls", 1, 1), ("Harbour Lights", 2, 1)]
    a = tagpages.tag_tracks(_conn(legacy_db), "metal", sort="album")
    assert [x["title"] for x in a["items"]] == ["Westkreuz", "Ostkreuz"]
    with pytest.raises(ValueError):
        tagpages.tag_tracks(_conn(legacy_db), "doom metal", sort="x")


def test_sound_is_jimbodj_count(legacy_db):
    conn = _conn(legacy_db)
    lib = tags.library(conn)
    for r in lib.tag_rows():
        if lib.index[r["key"]]["junk"]:
            continue
        assert tagpages.tag(conn, r["key"])["numbers"]["sound"] == r["sound"], r["key"]
        assert tags.albums(conn, r["key"], "sound")["total"] == r["sound"]
    assert tags.albums(conn, "black metal", "sound")["items"][0]["title"] == "Ringbahn"
    # Under 20 analysed plays, jimbo-dj's sound_of says nothing.
    assert tagpages.tag(conn, "black metal")["profile"] is None


def test_sound_of_weights_plays(legacy_db):
    played = Counter({101: 15, 102: 10})
    s = jh.sound_of(_conn(legacy_db), played)
    assert s is not None and s["plays"] == 25


def test_map_lines(legacy_db):
    m = tagpages.overview(_conn(legacy_db))
    lad = tags.ladder(tags.library(_conn(legacy_db)))
    assert [x["key"] for x in m["lines"]] == lad["roots"]
    metal = m["lines"][0]
    assert metal["name"] == "Metal" and metal["under"] == 2
    tree = {s["name"]: [c["name"] for c in s["stations"]] for s in metal["stations"]}
    assert tree == {"Black Metal": ["Atmospheric Black Metal"], "Doom Metal": ["Death-Doom Metal"],
                    "Death Metal": ["Death-Doom Metal"]}
    # Death-Doom Metal is a station on both branches, and says so.
    dd = [c for s in metal["stations"] for c in s["stations"] if c["key"] == "death-doom metal"]
    assert [c["also"] for c in dd] == [["Death Metal"], ["Doom Metal"]]
    # Every tag on a ladder is a station on its line (once per parent).
    stops = sum(x["stops"] for x in m["lines"])
    assert stops == sum(len(n["parents"]) for n in lad["nodes"].values() if n["broad"] and not n["root"])
    assert [a["name"] for a in m["alone"]] == ["Soundtrack"]
    assert m["summary"] == {"lines": 5, "tags": 12, "alone": 1, "shared": 1, "deepest": 2, "movements": 5}


def test_movements_cross_broad_tags_and_change_nothing(legacy_db):
    conn = _conn(legacy_db)
    data = tagpages.load_movements()
    ids = [m["id"] for m in data["movements"]]
    assert len(ids) == len(set(ids))
    lib = tags.library(conn)
    before = json.dumps(tags.ladder(lib), sort_keys=True)
    mvs = tagpages.movements(lib, tags.ladder(lib), data)
    for m in mvs:
        assert len(m["broads"]) >= 2, m["id"]  # a movement crosses broad tags
        assert all(x["key"] == jd.norm(x["key"]) for x in m["tags"])
    assert json.dumps(tags.ladder(lib), sort_keys=True) == before  # no ladder changes
    doom = next(m for m in mvs if m["id"] == "doom-drone")
    assert [(x["name"], x["in_use"]) for x in doom["tags"]][:2] == [("Doom Metal", True), ("Sludge Metal", False)]
    page = tagpages.tag(conn, "doom metal", mvs=mvs)
    assert [m["id"] for m in page["movements"]] == ["doom-drone"]
    assert page["numbers"] == tagpages.tag(conn, "doom metal")["numbers"]  # no count changes


def test_movement_from_a_scratch_file(legacy_db, tmp_path):
    p = tmp_path / "movements.json"
    p.write_text(json.dumps({"version": 7, "movements": [
        {"id": "x", "name": "Gaze", "tags": ["Atmospheric Black Metal", "Post-Punk", "post punk", "2010s"]}]}))
    lib = tags.library(_conn(legacy_db))
    m = tagpages.movements(lib, tags.ladder(lib), tagpages.load_movements(p))[0]
    assert [x["key"] for x in m["tags"]] == ["atmospheric black metal", "post-punk"]  # one key once, junk out
    assert m["broads"] == ["Metal", "Rock"] and m["in_use"] == 2
    assert tagpages.movements_stamp(p).startswith("m7:")


def test_rule_questions_need_albums_or_artists(legacy_db, tmp_path):
    """T22's live run: track-only tags ("Funk Add To Lidarr Batch 10") asked rule questions; now only tags an
    album or an artist carries are asked."""
    assert proposals.PROPOSALS_VERSION == 2
    raw = json.dumps(["Funk Add To Lidarr Batch 10"])
    db = _edit(legacy_db, tmp_path, ("UPDATE tracks SET plex_genres = ? WHERE rating_key = 105", (raw,)))
    lib = tags.library(_conn(db))
    assert proposals.rule_questions(lib, tags.ladder(lib)) == []
    db2 = _edit(legacy_db, tmp_path, ("UPDATE albums SET genres = ? WHERE album_key = 203", (raw,)), name="b.sqlite")
    lib = tags.library(_conn(db2))
    assert [q["tag"] for q in proposals.rule_questions(lib, tags.ladder(lib))] == ["Funk Add To Lidarr Batch 10"]


def test_gate_on_the_fixture(client):
    g = client.get("/api/tags/compare").json()
    assert g["passed"] and [c["check"] for c in g["checks"]] == ["ladder", "tracks", "audit"]
    lad, trk, aud = g["checks"]
    assert lad["rules"] == {"broad": 3, "ok": 3, "matches": True, "differing": []} and lad["ends"]["ok"] == 8
    assert trk["tags"]["ok"] == 5 and trk["styles"]["kept"] == 3
    assert aud["fresh"] and aud["tags"]["ok"] == 13 and aud["fixes"]["ok"] == 4
    # The same as the three endpoints, read one by one (what the script does).
    same = tags_gate.compare(client.get("/api/tags/ladder").json()["check"], client.get("/api/tags/tracks/check").json(),
                             client.get("/api/tags/proposals").json()["check"])
    assert same == g


def test_gate_fails_on_a_fresh_stored_row_that_differs(legacy_db, tmp_path):
    c = sqlite3.connect(legacy_db)
    v = json.loads(c.execute("SELECT value FROM stats WHERE name = 'library.tags'").fetchone()[0])
    c.close()
    v["tags"][0]["musicbrainz"] = 9
    db = _edit(legacy_db, tmp_path, ("UPDATE stats SET value = ? WHERE name = 'library.tags'", (json.dumps(v),)))
    conn = _conn(db)
    lib, lad = tags._ready(conn)
    g = tags_gate.compare(tags.check(lib, lad, tags.stored(conn)), tags.track_check(conn),
                          proposals.check(lib, tags.stored(conn)))
    assert not g["passed"] and [c["passed"] for c in g["checks"]] == [True, True, False]
    d = g["checks"][2]["tags"]["differing"][0]
    assert list(d["fields"]) == ["musicbrainz"] and d["fields"]["musicbrainz"][1] == 9
    assert "musicbrainz" in GATE.report(g) and "NOT PASSED" in GATE.report(g)
    # No stored row at all: check 3 can't pass.
    db2 = _edit(legacy_db, tmp_path, ("DELETE FROM stats WHERE name = 'library.tags'", ()), name="none.sqlite")
    conn = _conn(db2)
    lib, lad = tags._ready(conn)
    g = tags_gate.compare(tags.check(lib, lad, None), tags.track_check(conn), proposals.check(lib, None))
    assert not g["passed"] and g["checks"][2] == {"check": "audit", "passed": False, "rule": tags_gate.RULES["audit"],
                                                  "page": "/tags/proposals", "stored": False, "fresh": None}
    assert "nothing to compare" in GATE.report(g)


def test_gate_script_prints_and_exits(client, monkeypatch):
    def get(url, path):
        assert url == "http://traqfreq.test"
        return client.get(path).json()
    monkeypatch.setattr(GATE, "get", get)
    out = io.StringIO()
    with redirect_stdout(out):
        assert GATE.main(["--url", "http://traqfreq.test"]) == 0
    assert out.getvalue().rstrip().endswith("PASSED") and "3 of 3 broad tags" in out.getvalue()
    with redirect_stdout(io.StringIO()) as j:
        assert GATE.main(["--url", "http://traqfreq.test", "--json"]) == 0
    assert json.loads(j.getvalue())["passed"]

    def down(url, path):
        raise OSError("connection refused")
    monkeypatch.setattr(GATE, "get", down)
    assert GATE.main(["--url", "http://traqfreq.test"]) == 2


def test_gate_script_is_read_only():
    src = (ROOT / "scripts/p4_gate.py").read_text()
    assert "urlopen(" in src and "method=" not in src and "data=" not in src
    mod = (ROOT / "src/traqfreq/tags_gate.py").read_text()
    assert "from ." not in mod and "import traqfreq" not in mod  # pure: reads answers only


def test_api(client):
    r = client.get("/api/tags/tag/death-doom metal")
    assert r.status_code == 200 and len(r.json()["ladders"]) == 2
    assert client.get("/api/tags/tag/nothing here").status_code == 404
    m = client.get("/api/tags/map")
    assert m.status_code == 200 and not m.json()["cache"]["hit"] and client.get("/api/tags/map").json()["cache"]["hit"]
    t = client.get("/api/tags/tracks", params={"tag": "black metal"}).json()
    assert t["total"] == 2 and t["plays"] == 2
    assert client.get("/api/tags/tracks", params={"tag": "black metal", "sort": "x"}).status_code == 400
    assert client.get("/api/tags/albums", params={"tag": "black metal", "set": "sound"}).json()["total"] == 1
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/tags/compare").status_code == 405


def test_never_writes(legacy_db, client):
    before = legacy_db.read_bytes()
    for path in ("/api/tags/map", "/api/tags/tag/metal", "/api/tags/tracks?tag=metal", "/api/tags/compare"):
        assert client.get(path).status_code == 200
    assert legacy_db.read_bytes() == before
