from fastapi.testclient import TestClient

from traqfreq.app import create_app
from traqfreq.settings import Settings


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["legacy_db_present"] is True


def test_summary(client):
    r = client.get("/api/legacy/summary")
    assert r.status_code == 200
    assert r.json()["counts"]["listens"] == 6


def test_summary_unconfigured(tmp_path):
    c = TestClient(create_app(Settings(data_dir=tmp_path, legacy_db=None, port=4491, host="127.0.0.1")))
    assert c.get("/api/health").json()["legacy_db_configured"] is False
    assert c.get("/api/legacy/summary").status_code == 503


def test_settings_defaults():
    s = Settings.from_env({})
    assert s.port == 4491 and str(s.data_dir) == "data" and s.legacy_db is None
    s = Settings.from_env({"TRAQFREQ_PORT": "5000", "TRAQFREQ_LEGACY_DB": "/x/jimbodj.sqlite"})
    assert s.port == 5000 and str(s.legacy_db) == "/x/jimbodj.sqlite"
