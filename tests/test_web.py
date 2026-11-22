from fastapi.testclient import TestClient

from traqfreq.app import create_app
from traqfreq.settings import Settings


def _client(tmp_path, with_build=True):
    web = tmp_path / "dist"
    if with_build:
        (web / "assets").mkdir(parents=True)
        (web / "index.html").write_text("<!doctype html><title>traqfreq</title>")
        (web / "assets" / "app.js").write_text("console.log(1)")
    s = Settings(data_dir=tmp_path / "data", legacy_db=None, port=4492, host="127.0.0.1", web_dir=web)
    return TestClient(create_app(s))


def test_serves_index_and_assets(tmp_path):
    c = _client(tmp_path)
    assert "traqfreq" in c.get("/").text
    assert c.get("/assets/app.js").text == "console.log(1)"


def test_client_route_falls_back_to_index(tmp_path):
    c = _client(tmp_path)
    r = c.get("/history/plays")
    assert r.status_code == 200 and "traqfreq" in r.text


def test_api_still_wins_and_unknown_api_404s(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api/nope").status_code == 404


def test_no_build_no_mount(tmp_path):
    c = _client(tmp_path, with_build=False)
    assert c.get("/").status_code == 404
    assert c.get("/api/health").status_code == 200
