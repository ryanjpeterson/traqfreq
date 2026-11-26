"""T28: the P5 gate, "Same tracks as jimbo-dj" (docs/specs/t24-playlists.md): the ten trees, check 3, the compare
endpoints and scripts/p5_gate.py. Fixture only. jimbo-dj's side is a stand-in here: its preview is traqfreq's own
answer (jimbo-dj's rules.build, vendored) and its GET /api/saved is store.listing, its own code at 1d8a7cb, on the
same rows; each test then changes one thing and the gate must say what."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from traqfreq import legacy, playlists_compare, playlists_gate
from traqfreq.vendor import rules, store

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("p5_gate", ROOT / "scripts/p5_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fixed_trees():
    """Every fixed tree reads with jimbo-dj's rules.clean; the first two alone use every kind of condition, so any
    ten trees do."""
    fixed = playlists_compare.fixed_trees()
    assert len(fixed) >= playlists_gate.TREES and len({t["id"] for t in fixed}) == len(fixed)
    for t in fixed:
        assert rules.clean(t["rules"])["branches"]
    two = set(playlists_gate.tree_features(fixed[0]["rules"])) | set(playlists_gate.tree_features(fixed[1]["rules"]))
    assert two == set(playlists_gate.FEATURES)


def test_features_by_hand():
    f = playlists_gate.features
    assert f({"all": [{"f": "decade", "v": "2010s"}]}) == {"and", "chart"}
    assert f({"any": [{"f": "bpm", "v": "1-2"}, {"f": "in", "v": "mix:daily"}]}) == {"or", "sound", "in"}
    assert f({"all": [{"any": [{"f": "genre", "v": "x"}]}], "not": [{"f": "listened", "v": "2020"}]}) == {
        "and", "or", "not", "nested", "genre", "listened"}
    assert f({"all": [{"f": "artist", "v": "Ada Vey"}, {"f": "family", "v": "Metal"}, {"f": "style", "v": "x"}]}) == {
        "and", "chart", "family", "style"}


def test_ten_trees(client, legacy_db):
    """The fixture's four saved trees by id (Night lines, the blend, From the 2020s as an old filter, Inside the
    lines), then the first six fixed trees; each with what traqfreq picks for it now."""
    c = client.get("/api/playlists/compare").json()
    assert c["gate"] == "P5" and len(c["trees"]) == 10
    assert [(t["source"]["kind"], t["source"].get("id")) for t in c["trees"][:4]] == [
        ("saved", 1), ("saved", 2), ("saved", 3), ("saved", 10)]
    assert [t["source"]["id"] for t in c["trees"][4:]] == [t["id"] for t in playlists_compare.fixed_trees()[:6]]
    assert c["coverage"]["ok"] and c["coverage"]["missing"] == []
    night = c["trees"][0]
    assert [(x["id"], x["count"], x["got"]) for x in night["lines"]] == [("a", 1, 1), ("b", 2, 1), ("c", 2, 2)]
    assert night["total"] == 4 and night["picked"] == 4
    assert all("error" not in t for t in c["trees"])
    # check 3's rows: every saved playlist, as GET /api/saved has them
    conn = legacy.connect(legacy_db)
    theirs = store.listing(conn)
    assert playlists_gate.check_saved(c["saved"]["rows"], theirs)["ok"]
    assert c["saved"]["count"] == 10 and all(x["asked_by"] == "scripts/p5_gate.py" for x in c["checks"])


def test_one_tree_and_stamp(client):
    t = client.get("/api/playlists/compare/trees/0").json()
    assert t["preview"]["tracks"] == [{"rating_key": 102, "branch": "a"}, {"rating_key": 105, "branch": "b"},
                                      {"rating_key": 101, "branch": "c"}, {"rating_key": 103, "branch": "c"}]
    assert t["stamp"] == client.get("/api/playlists/compare/stamp").json()["stamp"]
    assert client.get("/api/playlists/compare/trees/10").status_code == 404


def _fake(client, legacy_db, change=None, moves=0):
    """get/post for the script: traqfreq through the test client; jimbo-dj as described in the module doc."""
    calls = {"post": [], "stamp": 0}

    def get(base, path):
        if base == "http://jd":
            assert path == "/api/saved"
            rows = store.listing(legacy.connect(legacy_db))
            return {"playlists": change("saved", rows) if change else rows}
        if path.endswith("/stamp"):
            calls["stamp"] += 1
            s = client.get(path).json()
            return {"stamp": s["stamp"] + ("moved" if calls["stamp"] <= moves else "")}
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
        return r.json()

    def post(base, path, body):
        assert base == "http://jd" and path == "/api/rules/preview" and set(body) == {"rules"}
        calls["post"].append(body["rules"])
        i = len(calls["post"]) - 1
        # jimbo-dj's preview of this tree: the tree traqfreq used, built by the same vendored rules.build
        trees = client.get("/api/playlists/compare").json()["trees"]
        t = next(t for t in trees if t["rules"] == body["rules"])
        p = copy.deepcopy(client.get(f"/api/playlists/compare/trees/{t['i']}").json()["preview"])
        return change("preview", p, t["i"]) if change else p

    return get, post, calls


def test_script_passes(client, legacy_db):
    s = _script()
    get, post, calls = _fake(client, legacy_db)
    g = s.from_url("http://tq", "http://jd", get, post)
    assert g["passed"], json.dumps(g)[:2000]
    assert [c["passed"] for c in g["checks"]] == [True, True, True]
    assert len(calls["post"]) == 10 and all(r["asked"] == {"attempts": 1, "steady": True} for r in g["trees"])
    assert "PASSED" in s.report(g).splitlines()[-1]


def test_script_names_each_difference(client, legacy_db):
    """A line count, the order of two tracks and a saved title differ on jimbo-dj's side: each is named."""
    def change(kind, x, i=None):
        if kind == "saved":
            x[0]["title"] = x[0]["title"] + " (renamed)"
            return x
        if i == 0:
            x["branches"][1]["count"] += 1
            x["tracks"][2], x["tracks"][3] = x["tracks"][3], x["tracks"][2]
        return x
    s = _script()
    get, post, _ = _fake(client, legacy_db, change)
    g = s.from_url("http://tq", "http://jd", get, post)
    assert not g["passed"] and [c["passed"] for c in g["checks"]] == [False, False, False]
    night = g["trees"][0]
    assert night["lines"]["lines"][1]["fields"]["count"] == {"ours": 2, "theirs": 3, "ok": False}
    assert night["tracks"]["set"]["ok"] and night["tracks"]["order"]["first_difference"] == {
        "position": 3, "ours": 101, "theirs": 103}
    assert g["saved"]["differ_count"] == 1 and set(g["saved"]["differ"][0]["fields"]) == {"title"}
    text = s.report(g)
    assert "order differs first at 3" in text and "(renamed)" in text and text.endswith("NOT PASSED")


def test_script_asks_again_once(client, legacy_db):
    """The stamp moves once: the first tree is asked again, and the gate still compares."""
    s = _script()
    get, post, calls = _fake(client, legacy_db, moves=1)
    g = s.from_url("http://tq", "http://jd", get, post)
    assert g["trees"][0]["asked"] == {"attempts": 2, "steady": True} and len(calls["post"]) == 11
    assert g["passed"]


def test_script_only_posts_the_preview():
    s = _script()
    with pytest.raises(AssertionError):
        s.post("http://jd", "/api/saved", {})
    assert s.jimbodj_default("http://macmini:4492") == "http://macmini:4490"


def test_check_saved_rows():
    ours = [{"id": 1, "kind": "mix", "title": "A", "tracks": 3, "in_plex": True, "stale": False}]
    theirs = [{"id": 1, "kind": "mix", "title": "A", "tracks": 3, "in_plex": 1, "stale": 0, "slug": "a"},
              {"id": 2, "kind": "like", "title": "B", "tracks": 1, "in_plex": False, "stale": False}]
    r = playlists_gate.check_saved(ours, theirs)
    assert not r["ok"] and r["missing"] == [2] and r["same"] == 1 and r["differ"] == []
