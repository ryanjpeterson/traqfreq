import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traqfreq.app import create_app
from traqfreq.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def _load_make_fixture():
    spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def legacy_db(tmp_path) -> Path:
    """A fresh fixture DB per test (never real data)."""
    return _load_make_fixture().build(tmp_path / "jimbodj.sqlite")


@pytest.fixture
def client(legacy_db, tmp_path) -> TestClient:
    s = Settings(data_dir=tmp_path / "data", legacy_db=legacy_db, port=4491, host="127.0.0.1")
    return TestClient(create_app(s))
