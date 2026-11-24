"""T19: the P3 gate (docs/specs/t13-servers.md): one to one, reasons that add up, and the spot check by ID.

Only the fixture: jimbo-dj's invented rows, the invented Jellyfin and Navidrome snapshots, and their answers
served by ``httpx.MockTransport`` (``test_reading.Servers``, which now also answers ``/Items?Ids=`` and
``getSong``). No network.
"""

import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from test_reading import ND, PASSWORD, Servers, _settings
from traqfreq import matching, servers_gate, snapshots, store
from traqfreq.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MF = _load("make_fixture", ROOT / "scripts/make_fixture.py")
GATE = _load("p3_gate", ROOT / "scripts/p3_gate.py")

# Navidrome with Report Real Path on: the fixture's hidden songs get their real files, and the one whose
# duration was made 6 s off (so the tags tier refuses it) gets Plex's.
REAL = {"b0000000000000000000000000000067": ("The Paper Lanterns/Low Tide Radio/01 Harbour Lights.flac", None),
        "b0000000000000000000000000000068": ("The Paper Lanterns/Low Tide Radio/02 Static Gulls.flac", None),
        "b0000000000000000000000000000069": ("Ada Vey/Quiet Engines/01 Coil.flac", 402),
        "b0000000000000000000000000000387": ("Ada Vey/Loose Ends/03 Night Bus.flac", None)}


def real_paths(nd: dict) -> dict:
    nd = copy.deepcopy(nd)
    for page in nd["song_pages"]:
        for s in page["subsonic-response"]["searchResult3"]["song"]:
            if s["id"] in REAL:
                f, dur = REAL[s["id"]]
                s["path"] = "/music/" + f
                if dur:
                    s["duration"] = dur
    return nd


class RealServers(Servers):
    def __init__(self, nd):
        super().__init__()
        self._songs = [s for p in nd["song_pages"] for s in p["subsonic-response"]["searchResult3"]["song"]]

    def songs(self):
        return self._songs


@pytest.fixture
def srv():
    return Servers()


def _client(legacy_db, tmp_path, srv, real=False):
    data = tmp_path / ("real" if real else "data")  # one data dir each: both snapshots carry one read_at
    MF.load_snapshots(data)
    if real:
        nd = real_paths(ND)
        store.save_snapshot(data, snapshots.from_navidrome(nd["scan_status"], nd["album_pages"], nd["song_pages"],
                                                           read_at=MF.SNAPSHOT_READ_AT))
    app = create_app(_settings(tmp_path, legacy_db, data_dir=data), server_transport=httpx.MockTransport(srv))
    return TestClient(app)


@pytest.fixture
def gate(legacy_db, tmp_path, srv):
    r = _client(legacy_db, tmp_path, srv).get("/api/servers/compare?seed=19")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def real(legacy_db, tmp_path):
    srv = RealServers(real_paths(ND))
    r = _client(legacy_db, tmp_path, srv, real=True).get("/api/servers/compare?seed=19")
    assert r.status_code == 200, r.text
    return r.json(), srv


def _check(g, name):
    return next(c for c in g["checks"] if c["check"] == name)


def _pair(c, name):
    return next(p for p in c["pairs"] if p["pair"] == name)


# --- the fixture as it is: Navidrome hides four paths --------------------------------------------------

def test_fixture_gate_fails_only_where_navidrome_hides_paths(gate, srv):
    assert gate["passed"] is False and gate["version"] == servers_gate.GATE_VERSION
    one = _check(gate, "one_to_one")
    jf, nd, jn = (_pair(one, p) for p in ("jellyfin", "navidrome", "jellyfin-navidrome"))
    assert jf["passed"] and (jf["visible"], jf["visible_matched"], jf["matched"], jf["hidden_paths"]) == (5, 5, 5, 0)
    assert jf["failures"] == {"visible_unmatched": 0, "item_twice": 0, "file_differs": 0}
    assert not nd["passed"] and nd["hidden_paths"] == 4 and not any(nd["failures"].values())
    assert jn["passed"] and jn["failures"] == {"item_twice": 0}
    assert _check(gate, "reasons")["passed"]
    assert any("Navidrome gives no real path for 4 of 9 items" in n for n in gate["notes"])
    spot = _check(gate, "spot")
    assert not spot["passed"] and spot["problems"].get("hidden_path")
    for r in spot["rows"]:  # every failing row fails on Navidrome's hidden paths alone
        if not r["passed"]:
            assert all(v["status"] in ("ok", "unmatched") or v.get("problems") == ["hidden_path"]
                       or "hidden_path" in (v.get("problems") or []) for v in r["servers"].values()), r
    assert {q.method for q in srv.requests} == {"GET"}
    assert {q.url.path for q in srv.requests} <= {"/Items", "/rest/getSong"}


def test_reasons_add_up(gate):
    why = _check(gate, "reasons")
    nd = _pair(why, "navidrome")["sides"]
    assert nd["left"] == {"total": 5, "matched": 4, "unmatched": 1, "reasons": {"hidden_path": 1}, "reasons_sum": 1,
                          "both": 0, "neither": 0, "unknown": {}, "adds_up": True, "passed": True}
    jfr = _pair(why, "jellyfin")["sides"]["right"]
    assert jfr["total"] == 14 and jfr["matched"] + jfr["unmatched"] == 14 and jfr["reasons_sum"] == jfr["unmatched"]
    assert len(why["pairs"]) == 3


# --- Navidrome with real paths: the gate passes --------------------------------------------------------

def test_gate_passes_with_real_paths(real):
    g, srv = real
    assert g["passed"], json.dumps([c for c in g["checks"] if not c["passed"]], indent=1)[:3000]
    assert g["notes"] == []
    one = _check(g, "one_to_one")
    nd = _pair(one, "navidrome")
    assert (nd["visible"], nd["visible_matched"], nd["hidden_paths"]) == (5, 5, 0)
    spot = _check(g, "spot")
    assert spot["failed"] == 0 and spot["seed"] == 19
    # every case is in the sample: each tier, note and reason of every pair
    whys = {w for r in spot["rows"] for w in r["why"]}
    for pair in g["checks"][1]["pairs"]:
        for side in ("left", "right"):
            for reason in pair["sides"][side]["reasons"]:
                assert any(w.startswith(f"{pair['pair']}: ") and w.endswith(reason) for w in whys), (pair["pair"], reason)
    assert {"jellyfin: file", "jellyfin: loose", "jellyfin: multi_part", "navidrome: file",
            "jellyfin-navidrome: plex", "jellyfin-navidrome: mbid"} <= whys
    # the fixture's 5 live copies: 101, 103 and 104 are cases, 102 and 105 drawn at random
    assert spot["random"] == 2 and spot["cases"] + 2 == spot["sample"]
    assert {r["rating_key"] for r in spot["rows"] if r["kind"] == "copy"} == {101, 102, 103, 104, 105}
    assert spot["asked"]["jellyfin"] > 0 and spot["asked"]["navidrome"] > 0
    assert sum(spot["asked"].values()) == len(srv.requests) and {q.method for q in srv.requests} == {"GET"}
    jn_mbid = next(r for r in spot["rows"] if "jellyfin-navidrome: mbid" in r["why"])
    assert jn_mbid["servers"]["navidrome"]["file_ok"] is None  # an m4a and a flac of one recording: no file asked
    assert all(PASSWORD not in str(q.url) for q in srv.requests)


def test_spot_check_catches_a_server_that_disagrees(legacy_db, tmp_path):
    nd = real_paths(ND)
    srv = RealServers(nd)
    for s in srv._songs:  # the server now says otherwise than the snapshot
        if s["id"] == "b0000000000000000000000000000065":
            s["duration"] = 300  # Plex: 312 s
        if s["id"] == "b0000000000000000000000000000066":
            s["path"] = "/music/Kollektiv Nord/Ringbahn/02 Ostkreuz (edit).flac"
    srv._songs = [s for s in srv._songs if s["id"] != "b0000000000000000000000000000068"]  # gone since
    g = _client(legacy_db, tmp_path, srv, real=True).get("/api/servers/compare?seed=19").json()
    spot = _check(g, "spot")
    assert not g["passed"] and not spot["passed"]
    rows = {r["rating_key"]: r["servers"]["navidrome"] for r in spot["rows"] if r["kind"] == "copy"}
    assert rows[101]["status"] == "differs" and rows[101]["problems"] == ["duration_differs"] and rows[101]["diff_ms"] == 12000
    assert rows[102]["status"] == "differs" and rows[102]["problems"] == ["file_differs"]
    assert rows[104]["status"] == "error" and "Song not found" in rows[104]["message"]
    assert _check(g, "one_to_one")["passed"] and _check(g, "reasons")["passed"]  # the snapshot itself is fine


def test_unreachable_server_is_asked_once(legacy_db, tmp_path):
    srv = RealServers(real_paths(ND))
    srv.fail["/rest/getSong"] = httpx.ConnectError("refused")
    g = _client(legacy_db, tmp_path, srv, real=True).get("/api/servers/compare?seed=19").json()
    spot = _check(g, "spot")
    assert not spot["passed"] and spot["asked"]["navidrome"] == 1
    msgs = {v["message"] for r in spot["rows"] for s, v in r["servers"].items() if s == "navidrome" and v.get("message")}
    assert any(m.startswith("Not asked: Couldn't reach Navidrome") for m in msgs)


# --- the parts ------------------------------------------------------------------------------------------

def test_one_to_one_catches_an_item_matched_twice_and_files_that_differ(legacy_db, tmp_path):
    from traqfreq import legacy
    MF.load_snapshots(tmp_path / "d")
    conn = legacy.connect(legacy_db)
    m = matching.matches(conn, tmp_path / "d")
    r = m.result["jellyfin"]
    pairs = {p["left"]: p for p in r["pairs"]}
    own = pairs[102]["right"]
    pairs[102]["right"] = pairs[101]["right"]  # two copies, two files, one item
    out = servers_gate._plex_pair(m, "jellyfin")
    assert not out["passed"] and out["failures"]["item_twice"] == 1 and out["failures"]["file_differs"] == 1
    assert out["rows"]["item_twice"][0]["rating_keys"] == [101, 102]
    del pairs[102]
    r["pairs"] = [p for p in r["pairs"] if p["left"] != 102]
    r["left"][102] = "ambiguous"
    assert not _pair(servers_gate.reasons(m), "jellyfin")["passed"]  # its item is now neither matched nor unmatched
    r["right"][own] = "ambiguous"
    out = servers_gate._plex_pair(m, "jellyfin")
    assert out["failures"]["visible_unmatched"] == 1 and out["visible_unmatched"] == {"ambiguous": 1}
    why = servers_gate.reasons(m)
    assert _pair(why, "jellyfin")["passed"]  # still adds up
    r["left"][102] = "made_up"
    assert not _pair(servers_gate.reasons(m), "jellyfin")["passed"]
    matching._built.clear()
    conn.close()


def test_sample_is_seeded_and_cases_come_first(legacy_db, tmp_path):
    from traqfreq import legacy
    MF.load_snapshots(tmp_path / "d")
    conn = legacy.connect(legacy_db)
    m = matching.matches(conn, tmp_path / "d")
    a, b = servers_gate.sample(m, 1), servers_gate.sample(m, 1)
    assert a == b and all(e["why"] for e in a)
    assert {e["rating_key"] for e in a if e["kind"] == "copy"} == {101, 102, 103, 104, 105}
    matching._built.clear()
    conn.close()


def test_no_snapshots_fails_and_asks_nothing(legacy_db, tmp_path, srv):
    app = create_app(_settings(tmp_path, legacy_db), server_transport=httpx.MockTransport(srv))
    g = TestClient(app).get("/api/servers/compare").json()
    assert not g["passed"] and srv.requests == []
    assert all(not c["passed"] for c in g["checks"])
    assert sum("has no snapshot" in n for n in g["notes"]) == 2


def test_gate_script_prints_and_exits(gate, real, monkeypatch):
    for answer, code, last in ((gate, 1, "NOT PASSED"), (real[0], 0, "PASSED")):
        monkeypatch.setattr(GATE, "from_url", lambda url, seed, a=answer: a)
        buf = io.StringIO()
        with redirect_stdout(buf):
            assert GATE.main(["--url", "http://traqfreq.test"]) == code
        out = buf.getvalue().splitlines()
        assert out[-1] == last and out[0] == "P3 gate: 5 live Plex copies"
    assert any("hidden paths 4" in line for line in GATE.report(gate).splitlines())


def test_gate_script_is_read_only():
    src = (ROOT / "scripts/p3_gate.py").read_text()
    assert "urlopen" in src and "method=" not in src and "data=" not in src
    src = (ROOT / "src/traqfreq/servers_gate.py").read_text()
    assert ".post(" not in src and "save_snapshot" not in src and "store." not in src
