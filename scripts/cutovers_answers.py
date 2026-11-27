"""Writes web/src/pages/cutovers.answers.json: GET /api/cutovers on the fixture (invented rows), before the copy and
after a copy, one sync from the Plex stand-in in tests/test_plexsync.py and a write on jimbo-dj's side (a stand-in for
a manual Sync and an import there). Times pinned so the file doesn't move. Run: uv run python scripts/cutovers_answers.py"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from fastapi.testclient import TestClient  # noqa: E402

from traqfreq import own, plexsync  # noqa: E402
from traqfreq.app import create_app  # noqa: E402
from traqfreq.settings import Settings  # noqa: E402
from test_plexsync import PATH_MAP, TOKEN, FakePlex  # noqa: E402

spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

NOW = 1794200400.0
with tempfile.TemporaryDirectory() as d, mock.patch("time.time", lambda: NOW):
    legacy_db = mf.build(Path(d) / "jimbodj.sqlite")
    s = Settings(data_dir=Path(d) / "data", legacy_db=legacy_db, port=4492, host="127.0.0.1",
                 plex_url="http://plex.test:32400", plex_token=TOKEN, plex_section="Music", plex_path_map=PATH_MAP)
    c = TestClient(create_app(s))
    out = {"before": c.get("/api/cutovers").json()}
    own.copy(legacy_db, s.data_dir, "plex", "Cut-over 1 at deploy")
    plexsync.run(s, "Nightly sync", FakePlex().transport())
    out["clean"] = c.get("/api/cutovers").json()
    j = sqlite3.connect(legacy_db)
    j.execute("INSERT INTO listens (id, source, started_at, artist, title, match_key) "
              "VALUES (10, 'lastfm', 1794200000, 'Ada Vey', 'Coil', 'ada vey|coil')")
    j.execute("UPDATE meta SET value = '1794200200' WHERE key = 'last_sync'")
    j.commit()
    j.close()
    out["moved"] = c.get("/api/cutovers").json()
for v in out.values():
    v["file"] = "data/library.sqlite"
text = json.dumps(out, indent=2, ensure_ascii=False)  # the API's order: rows keep their column order
assert TOKEN not in text
(ROOT / "web/src/pages/cutovers.answers.json").write_text(text + "\n")
print("wrote web/src/pages/cutovers.answers.json")
