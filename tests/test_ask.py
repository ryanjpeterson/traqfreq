"""T28: the Ask box, words to a line (docs/specs/t24-playlists.md). Fixture only, with a scratch copy where a test
needs CLAP vectors (the fixture has no embeddings). jimbodj-text and Ollama are httpx.MockTransport stand-ins:
nothing leaves the test."""

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from traqfreq import ask, legacy
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import prompt, vectors

ROOT = Path(__file__).resolve().parents[1]
TEXT, OLLAMA = "http://text.test", "http://ollama.test"
EXPECT_OLLAMA = 2  # black metal {101, 102} and the 2010s {101, 102}; "dark" isn't a mood the fixture has


def _vec(*hot: float) -> bytes:
    v = np.zeros(512, np.float32)
    v[: len(hot)] = hot
    return v.astype("<f4").tobytes()


@pytest.fixture
def clap_db(legacy_db, tmp_path):
    """The fixture with CLAP and EffNet vectors (invented): 102 brought to the current analyzer version and 104
    analysed, so four tracks are in the index. 101 and 102 (black metal) point one way, 103 and 104 (doom) another."""
    db = tmp_path / "clap.sqlite"
    shutil.copy(legacy_db, db)
    c = sqlite3.connect(db)
    with c:
        c.execute("UPDATE analysis SET version=2 WHERE rating_key=102")
        for table in ("analysis", "features"):  # 104 analysed as 103 was
            cols = ", ".join(r[1] for r in c.execute(f"PRAGMA table_info({table})") if r[1] != "rating_key")
            c.execute(f"INSERT INTO {table} (rating_key, {cols}) SELECT 104, {cols} FROM {table} WHERE rating_key=103")
        c.execute("CREATE TABLE embeddings (rating_key INTEGER, kind TEXT, dtype TEXT, vec BLOB)")
        for k, v in ((101, _vec(1.0, 0.1)), (102, _vec(0.9, 0.2)), (103, _vec(0.1, 1.0)), (104, _vec(0.2, 0.9))):
            c.execute("INSERT INTO embeddings VALUES (?, 'clap', 'float32', ?)", (k, v))
            c.execute("INSERT INTO embeddings VALUES (?, 'effnet', 'float32', ?)", (k, _vec(1.0)))
    c.close()
    return db


def _transport(text_vec=(1.0, 0.0), ollama=None, down=False):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url)))
        if down:
            raise httpx.ConnectError("refused")
        if req.url.host == "text.test" and req.url.path == "/embed":
            v = np.zeros(512)
            v[: len(text_vec)] = text_vec
            return httpx.Response(200, json={"model": "test", "vectors": [v.tolist()]})
        if req.url.host == "text.test" and req.url.path == "/health":
            return httpx.Response(200, json={"ok": True})
        if req.url.host == "ollama.test" and req.url.path == "/api/chat":
            body = json.loads(req.content)
            assert body["format"]["required"] == ["style", "mood", "decade"] and body["stream"] is False
            return httpx.Response(200, json={"message": {"content": json.dumps(ollama)}})
        return httpx.Response(404)

    t = httpx.MockTransport(handler)
    t.seen = seen
    return t


def _client(db, tmp_path, transport, text=TEXT, ollama=None):
    s = Settings(data_dir=tmp_path / "data", legacy_db=db, port=4492, host="127.0.0.1", text_url=text, ollama_url=ollama)
    return TestClient(create_app(s, ask_transport=transport))


def test_prompt_vendored_unchanged():
    """clean and Unavailable are jimbo-dj's prompt.py at 1d8a7cb; the CLAP half of vectors.py (_norm, _EMB_Q,
    _stamp, _vectors) and the prompt scores in similar.more_like are copied unchanged too."""
    assert prompt.clean("walking-in-new-york-city") == "walking in new york city"
    assert prompt.clean("  rainy   sunday  ") == "rainy sunday" and len(prompt.clean("x " * 300)) == 200
    jimbodj = ROOT.parent / "jimbo-dj"
    if not (jimbodj / ".git").exists():
        return
    show = lambda p: subprocess.run(["git", "-C", str(jimbodj), "show", f"1d8a7cb:src/jimbodj/{p}"],  # noqa: E731
                                    capture_output=True, text=True, check=True).stdout
    mine = (ROOT / "src/traqfreq/vendor/prompt.py").read_text()
    theirs = show("prompt.py")
    for a, b in (("class Unavailable", "\n\n\n@functools"), ("def clean(", "\n\n\n@functools")):
        i = theirs.index(a)
        assert theirs[i:theirs.index(b, i)].rstrip() in mine
    vec = (ROOT / "src/traqfreq/vendor/vectors.py").read_text()
    theirs = show("vectors.py")
    for a, b in (("def _norm(", "\n\n\n_EMB_Q"), ("_EMB_Q = (", "\n_META_Q"), ("def _stamp(", "\n\n\ndef _vectors"),
                 ("def _vectors(", "\n\n\nclass Index")):
        i = theirs.index(a)
        assert theirs[i:theirs.index(b, i)].rstrip() in vec, a
    sim = show("similar.py")
    for line in ("raw = index.clap @ seed[\"vector\"]", "lo, hi = float(np.percentile(raw, 5)), float(raw.max())",
                 "sims = np.clip((raw - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)"):
        assert line in sim
    src = (ROOT / "src/traqfreq/ask.py").read_text()
    assert "lo, hi = float(np.percentile(raw, 5)), float(raw.max())" in src
    assert "np.clip((raw - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)" in src


def test_clap_index_by_hand(clap_db):
    """Centred on the mean and normalised, as jimbo-dj's Index: four tracks with both vectors."""
    idx = vectors.clap(legacy.connect(clap_db))
    assert list(idx.keys) == [101, 102, 103, 104]
    assert np.allclose(np.linalg.norm(idx.clap, axis=1), 1)
    raw = np.array([[1.0, 0.1], [0.9, 0.2], [0.1, 1.0], [0.2, 0.9]])
    c = raw - raw.mean(0)
    assert np.allclose(idx.clap[:, :2], c / np.linalg.norm(c, axis=1, keepdims=True), atol=1e-6)


def test_no_embeddings_table(legacy_db, tmp_path):
    """The fixture has no embeddings: the sound side says so, the typed side still works."""
    r = _client(legacy_db, tmp_path, _transport()).get("/api/junction/ask", params={"q": "cold, decade:2010s"}).json()
    assert r["sound"]["state"] == "no_vectors"
    assert [x["source"] for x in r["lines"]] == ["typed"]


def test_nearest_and_the_line(clap_db, tmp_path):
    """Words pointing the black metal way: 101 and 102 nearest, then the doom tracks. The line is the styles that
    cover the nearest tracks, worked out by hand from the fixture's style scores (genres.MATCH 0.45):
    101 black metal, ambient, dark ambient, atmospheric black metal, metal; 102 black metal, atmospheric black
    metal, metal; 103 and 104 doom metal, death-doom metal, death metal, post-punk. A style must be on two of the
    four (a tenth, at least two): first the ones on 101 and 102 weigh most (black metal, atmospheric black metal and
    metal tie on weight and on use; by name, atmospheric black metal), then the doom ones (by name, death metal),
    then nothing is left uncovered."""
    t = _transport(text_vec=(1.0, 0.0))
    c = _client(clap_db, tmp_path, t)
    r = c.get("/api/junction/ask", params={"q": "frozen forest at night"}).json()
    s = r["sound"]
    assert s["state"] == "ok" and s["near"] == 4
    assert [x["style"] for x in s["styles"]] == ["atmospheric black metal", "death metal"]
    assert [(x["near"], x["new"]) for x in s["styles"]] == [(2, 2), (2, 2)]
    line = s["line"]
    assert line["source"] == "sound" and line["label"] == "frozen forest at night"
    assert line["count"] == 4  # 101, 102 (atmospheric black metal) and 103, 104 (death metal)
    assert line["query"] == "b=(style:atmospheric+black+metal|style:death+metal)~60~frozen+forest+at+night"
    rows = c.get("/api/junction/ask/rows", params={"q": "frozen forest at night"}).json()
    assert [x["rating_key"] for x in rows["rows"]][:2] == [101, 102] and rows["count"] == 4
    assert rows["rows"][0]["score"] == 1.0
    doom = c.get("/api/junction/ask/rows", params={"q": "frozen forest at night", "style": "death metal"}).json()
    assert [x["rating_key"] for x in doom["rows"]] == [103, 104] and doom["style"] == "death metal"
    assert all(m == "POST" and u == f"{TEXT}/embed" for m, u in t.seen)  # only the text server, only /embed


def test_typed_and_sound_together(clap_db, tmp_path):
    """Typed parts join the sound line (AND, and NOT), and stand as their own line too."""
    r = _client(clap_db, tmp_path, _transport(text_vec=(0.0, 1.0))).get(
        "/api/junction/ask", params={"q": "slow and heavy, decade:2010s, !mood:sad"}).json()
    assert r["words"] == "slow and heavy"
    assert r["typed"] == {"all": [{"f": "decade", "v": "2010s"}], "not": [{"f": "mood", "v": "sad"}]}
    typed, sound = r["lines"]
    # 2010s: 101 and 102; both are sad here (102's analysis is at the current version in this copy): none left.
    assert typed["source"] == "typed" and typed["count"] == 0
    assert sound["match"]["all"][1] == {"type": "condition", "f": "decade", "v": "2010s", "text": "2010s",
                                        "count": 2, "path": "all.1"}
    assert sound["match"]["not"][0]["v"] == "sad"
    # Doom first this time (103 and 104 nearest), then the black metal side; the typed parts leave none of the four.
    assert [x["style"] for x in r["sound"]["styles"]] == ["death metal", "atmospheric black metal"]
    assert sound["count"] == 0


def test_text_server_down_and_off(clap_db, tmp_path):
    r = _client(clap_db, tmp_path, _transport(down=True)).get("/api/junction/ask", params={"q": "storm, decade:2010s"}).json()
    assert r["sound"]["state"] == "unavailable" and "jimbodj-text" in r["sound"]["error"]
    assert [x["source"] for x in r["lines"]] == ["typed"]
    c = _client(clap_db, tmp_path, _transport(down=True))
    assert c.get("/api/junction/ask/rows", params={"q": "storm"}).status_code == 503
    off = _client(clap_db, tmp_path, _transport(), text=None).get("/api/junction/ask", params={"q": "storm"}).json()
    assert off["sound"]["state"] == "off" and off["ollama"]["state"] == "off" and off["lines"] == []


def test_ollama_grounded(clap_db, tmp_path):
    """Ollama only picks from the library's values: an unknown style and mood are dropped and named."""
    t = _transport(ollama={"style": ["Black Metal", "Shoegaze Polka"], "mood": ["dark", "glorious"], "decade": ["2010s"]})
    r = _client(clap_db, tmp_path, t, ollama=OLLAMA).get("/api/junction/ask", params={"q": "grim winter"}).json()
    o = r["ollama"]
    assert o["state"] == "ok" and o["kept"]["style"] == ["black metal"] and o["kept"]["decade"] == ["2010s"]
    assert {(d["f"], d["v"]) for d in o["dropped"]} == {("style", "Shoegaze Polka"), ("mood", "dark"), ("mood", "glorious")}
    line = o["line"]
    assert line["source"] == "ollama" and [x["source"] for x in r["lines"]] == ["sound", "ollama"]
    assert line["match"]["all"][0]["v"] == "black metal" and line["count"] == EXPECT_OLLAMA
    # A value the words also type isn't added twice: the typed part stays as typed.
    r = _client(clap_db, tmp_path, t, ollama=OLLAMA).get("/api/junction/ask", params={"q": "grim winter, decade:2010s"}).json()
    assert r["ollama"]["line"]["query"].startswith("b=style:black+metal,decade:2010s~60")


def test_ask_writes_nothing(clap_db, tmp_path):
    before = clap_db.read_bytes()
    c = _client(clap_db, tmp_path, _transport(ollama={"style": [], "mood": [], "decade": []}), ollama=OLLAMA)
    assert c.get("/api/junction/ask", params={"q": "anything, style:black metal"}).status_code == 200
    assert clap_db.read_bytes() == before
